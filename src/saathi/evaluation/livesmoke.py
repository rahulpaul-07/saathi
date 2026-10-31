"""Live smoke test through the app's own HTTP API (spends at most 12 Gnani calls, plans 6).

A real server runs in this process and two clients talk to it over HTTP and server-sent events,
exactly as the two phones do. Gnani is real and metered; the translator is the real local one.
The speech comes from the prepared demo clips (synthetic Gnani TTS plus licensed noise), so no
person's voice or address is involved. The pair (kn customer, hi rider) is only an example.

The result file is content-free by design: step names, pass or fail, fact kinds and counts. It
never holds a transcript, a translation or an address. Stage timings are not recorded because the
3-calls-per-10-seconds pacing is inside them; scripts/latency_study.py measures that.
"""

import argparse
import asyncio
import json
import sys
from collections import Counter
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI
from pydantic import ValidationError

from saathi.app import create_app
from saathi.config import Settings, get_settings
from saathi.evaluation.calls import (
    BudgetExceededError,
    CallLedger,
    MeteredGnani,
    SlidingWindowLimiter,
)
from saathi.gnani import GnaniError
from saathi.languages import LANGUAGES
from saathi.rooms import RoomManager
from saathi.translate import RoutingTranslator, Translator

LEDGER_LABEL = "smoke_live"
CUSTOMER_LANG = "kn"
RIDER_LANG = "hi"
FIRST_CLIP = "kn-bakery"
CORRECTION_CLIP = "kn-gate-correction"
CALLS_PLANNED = 6  # 2 turns x (STT + TTS), plus one quick-reply TTS each way
CALLS_CEILING = 12  # the run refuses to send a 13th, retries included
EVENT_TIMEOUT_S = 30.0
FATAL_STATUSES = frozenset({401, 402, 403})  # bad key, no credit, forbidden: never go on


class SmokeError(Exception):
    """The run cannot continue; the message is safe to print (no content)."""


@dataclass
class Step:
    name: str
    ok: bool


@dataclass
class SmokeReport:
    steps: list[Step] = field(default_factory=list)
    calls_spent: int = 0
    ledger_total: int = 0
    turn_facts: list[dict[str, int]] = field(default_factory=list)
    stopped_early: str | None = None

    @property
    def passed(self) -> bool:
        return self.stopped_early is None and all(step.ok for step in self.steps)

    def to_json(self, today: date) -> dict[str, Any]:
        return {
            "date": today.isoformat(),
            "pair": f"{CUSTOMER_LANG} customer, {RIDER_LANG} rider (example pair)",
            "clips": [FIRST_CLIP, CORRECTION_CLIP],
            "content_free": True,
            "passed": self.passed,
            "stopped_early": self.stopped_early,
            "gnani_calls": self.calls_spent,
            "ledger_total": self.ledger_total,
            "fact_kinds_per_turn": self.turn_facts,
            "steps": [{"name": step.name, "ok": step.ok} for step in self.steps],
        }


class GuardedGnani(MeteredGnani):
    """Metered client that also paces calls, holds this run's ceiling and stops on fatal codes."""

    def __init__(
        self,
        settings: Settings,
        ledger: CallLedger,
        limiter: SlidingWindowLimiter,
        ceiling: int = CALLS_CEILING,
    ) -> None:
        super().__init__(settings, ledger, LEDGER_LABEL)
        self._ledger_view = ledger
        self._limiter = limiter
        self._ceiling = ceiling
        self.fatal_status: int | None = None

    async def _post(self, path: str, **kwargs: object) -> httpx.Response:
        if self.fatal_status is not None:
            raise GnaniError("stopped after a fatal Gnani status", self.fatal_status)
        if self._ledger_view.spent(LEDGER_LABEL) >= self._ceiling:
            raise BudgetExceededError(f"this run's ceiling of {self._ceiling} calls is reached")
        await self._limiter.acquire(1)
        try:
            return await super()._post(path, **kwargs)
        except GnaniError as exc:
            if exc.status in FATAL_STATUSES:
                self.fatal_status = exc.status
            raise


class EventTap:
    """Reads one participant's event stream in the background and lets a step wait for an event."""

    def __init__(self, client: httpx.AsyncClient, code: str, token: str) -> None:
        self._client = client
        self._path = f"/rooms/{code}/events"
        self._headers = {"Authorization": f"Bearer {token}"}
        self._items: list[tuple[str, dict[str, Any]]] = []
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._pump())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _pump(self) -> None:
        async with self._client.stream("GET", self._path, headers=self._headers) as response:
            name: str | None = None
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    name = line[len("event: ") :]
                elif line.startswith("data: ") and name is not None:
                    self._items.append((name, json.loads(line[len("data: ") :])))
                    name = None

    def mark(self) -> int:
        return len(self._items)

    async def wait_for(
        self,
        name: str,
        *,
        after: int = 0,
        where: Callable[[dict[str, Any]], bool] = lambda _data: True,
    ) -> dict[str, Any]:
        """The first event called `name` after position `after` that satisfies `where`."""
        async with asyncio.timeout(EVENT_TIMEOUT_S):
            seen = after
            while True:
                while seen < len(self._items):
                    item_name, data = self._items[seen]
                    seen += 1
                    if item_name == name and where(data):
                        return data
                await asyncio.sleep(0.05)


@asynccontextmanager
async def serve(app: FastAPI) -> AsyncIterator[str]:
    """Run the app on an ephemeral local port and give its base URL."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        if task.done():
            raise SmokeError("the local server did not start")
        await asyncio.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _send(
    client: httpx.AsyncClient, method: str, path: str, expected: int, **kwargs: Any
) -> httpx.Response:
    response = await client.request(method, path, **kwargs)
    if response.status_code != expected:
        raise SmokeError(f"{method} {path.rsplit('/', 1)[-1]} answered {response.status_code}")
    return response


def _entries(card: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["fact"]["kind"]: entry for entry in card["entries"]}


def _changed(entries: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(kind for kind, entry in entries.items() if entry["previous"] is not None)


def _asked(entries: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(kind for kind, entry in entries.items() if entry["question"] is not None)


async def run_smoke(
    client: httpx.AsyncClient, clips: dict[str, bytes], report: SmokeReport
) -> None:
    """The whole journey. Assertion failures are recorded and the run goes on; an HTTP failure
    raises SmokeError because every later step would depend on it."""

    def record(name: str, ok: bool) -> None:
        report.steps.append(Step(name, ok))

    created = (await _send(client, "POST", "/rooms", 201, json={"language": CUSTOMER_LANG})).json()
    code = created["code"]
    joined = (
        await _send(client, "POST", f"/rooms/{code}/join", 200, json={"language": RIDER_LANG})
    ).json()
    customer, rider = created["token"], joined["token"]
    record("rooms: create and join", joined["peer_language"] == CUSTOMER_LANG)

    customer_tap = EventTap(client, code, customer)
    rider_tap = EventTap(client, code, rider)
    customer_tap.start()
    rider_tap.start()
    try:
        await customer_tap.wait_for("state")
        await rider_tap.wait_for("state")

        async def post_reply(kind: str, body: dict[str, str], token: str) -> None:
            await _send(
                client, "POST", f"/rooms/{code}/{kind}", 204, json=body, headers=_auth(token)
            )

        async def speak(clip: str) -> dict[str, Any]:
            files = {"audio": (f"{clip}.wav", clips[clip], "audio/wav")}
            response = await _send(
                client, "POST", f"/rooms/{code}/turn", 200, files=files, headers=_auth(customer)
            )
            body: dict[str, Any] = response.json()
            report.turn_facts.append(dict(Counter(fact["kind"] for fact in body["facts"])))
            return body

        # Turn 1: a full set of facts, nothing changed yet.
        rider_mark = rider_tap.mark()
        if not (await speak(FIRST_CLIP))["facts"]:
            # No card event is ever sent for a turn without facts, and every later step needs one.
            raise SmokeError("turn 1 found no facts")
        turn = await rider_tap.wait_for("turn", after=rider_mark)
        card = await rider_tap.wait_for("card", after=rider_mark)
        entries = _entries(card)
        record(
            "turn 1: card has cross, main, gate and no changed marker",
            {"cross", "main", "gate"} <= entries.keys() and not _changed(entries),
        )
        audio = await _send(client, "GET", turn["audio_path"], 200, headers=_auth(rider))
        record("turn 1: translated audio is served", len(audio.content) > 1000)
        first_gate = entries["gate"]["fact"]["value"] if "gate" in entries else None

        # Turn 2: the spoken correction changes the gate only.
        rider_mark, customer_mark = rider_tap.mark(), customer_tap.mark()
        corrected = False
        if (await speak(CORRECTION_CLIP))["facts"]:  # none: nothing to wait for, the step fails
            views = [
                _entries(await rider_tap.wait_for("card", after=rider_mark)),
                _entries(await customer_tap.wait_for("card", after=customer_mark)),
            ]
            corrected = all(
                _changed(view) == ["gate"]
                and view["gate"]["previous"] == first_gate
                and view["gate"]["fact"]["value"] != first_gate
                for view in views
            )
        record("turn 2: correction marks only the gate, was the first value", corrected)

        # Quick replies, one each way. The first is synthesized in the rider's language, the
        # second in the customer's, so each costs one TTS call.
        rider_mark = rider_tap.mark()
        await post_reply("quick-reply", {"phrase_id": "come_to_gate"}, customer)
        got = await rider_tap.wait_for("quick_reply", after=rider_mark)
        record(
            "quick reply: customer to rider arrives with audio",
            got["phrase_id"] == "come_to_gate" and got["audio_path"] is not None,
        )
        customer_mark = customer_tap.mark()
        await post_reply("quick-reply", {"phrase_id": "reached_gate"}, rider)
        got = await customer_tap.wait_for("quick_reply", after=customer_mark)
        record(
            "quick reply: rider to customer arrives with audio",
            got["phrase_id"] == "reached_gate" and got["audio_path"] is not None,
        )

        # Chips: the rider asks about the main road, then confirms the gate. No Gnani calls.
        customer_mark = customer_tap.mark()
        await post_reply("chip-reply", {"kind": "main", "action": "ask"}, rider)
        view = _entries(await customer_tap.wait_for("card", after=customer_mark))
        record(
            "chip ask: customer sees one question, on the asked chip",
            _asked(view) == ["main"] and _changed(view) == ["gate"],
        )
        customer_mark = customer_tap.mark()
        await post_reply("chip-reply", {"kind": "gate", "action": "confirm"}, rider)
        view = _entries(await customer_tap.wait_for("card", after=customer_mark))
        record(
            "chip confirm: gate confirmed, marker cleared, question unchanged",
            view["gate"]["confirmed"] and not _changed(view) and _asked(view) == ["main"],
        )

        rider_mark, customer_mark = rider_tap.mark(), customer_tap.mark()
        await _send(client, "DELETE", f"/rooms/{code}", 204, headers=_auth(customer))
        await rider_tap.wait_for("closed", after=rider_mark)
        await customer_tap.wait_for("closed", after=customer_mark)
        record("room end: both sides told", True)
    finally:
        await customer_tap.stop()
        await rider_tap.stop()


def load_clips(directory: Path) -> dict[str, bytes]:
    try:
        names = (FIRST_CLIP, CORRECTION_CLIP)
        return {name: (directory / f"{name}.wav").read_bytes() for name in names}
    except OSError as exc:
        raise SmokeError(
            f"demo clips are missing in {directory.as_posix()} (see scripts/make_demo_clips.py)"
        ) from exc


def format_plan(ledger: CallLedger) -> str:
    kn, hi = LANGUAGES[CUSTOMER_LANG], LANGUAGES[RIDER_LANG]
    return "\n".join(
        [
            f"Live smoke through the HTTP API, {CUSTOMER_LANG} customer and {RIDER_LANG} rider: "
            f"{CALLS_PLANNED} Gnani calls planned, ceiling {CALLS_CEILING}",
            f"  turn {FIRST_CLIP}: STT {kn.gnani_code}, TTS {hi.gnani_code}",
            f"  turn {CORRECTION_CLIP}: STT {kn.gnani_code}, TTS {hi.gnani_code}",
            f"  quick reply customer to rider: TTS {hi.gnani_code} (come_to_gate)",
            f"  quick reply rider to customer: TTS {kn.gnani_code} (reached_gate)",
            "  chip ask and chip confirm: no Gnani calls",
            f"Ledger '{LEDGER_LABEL}': {ledger.spent(LEDGER_LABEL)} spent so far; total "
            f"{ledger.total} spent + {CALLS_PLANNED} planned = {ledger.total + CALLS_PLANNED} "
            f"of cap {ledger.cap}",
            "Pacing: at most 3 calls per 10 s; the run stops at the first failed step or a "
            "401, 402 or 403 from Gnani.",
        ]
    )


GnaniFactory = Callable[[Settings, CallLedger, SlidingWindowLimiter], GuardedGnani]
TranslatorFactory = Callable[[Settings], Translator]


def _real_translator(settings: Settings) -> Translator:
    translator = RoutingTranslator(num_beams=settings.translator_num_beams)
    translator.load()
    return translator


async def run_live(
    settings: Settings,
    ledger: CallLedger,
    clips: dict[str, bytes],
    make_gnani: GnaniFactory,
    make_translator: TranslatorFactory,
) -> SmokeReport:
    report = SmokeReport()
    before = ledger.spent(LEDGER_LABEL)
    gnani = make_gnani(settings, ledger, SlidingWindowLimiter())
    # No start-up TTS warm-up: it would be a seventh call.
    quiet = settings.model_copy(update={"warm_tts": False, "demo_input": False})
    translator = await asyncio.to_thread(make_translator, quiet)
    app = create_app(quiet, gnani, translator, RoomManager(max_rooms=quiet.max_rooms))
    try:
        async with serve(app) as base_url:
            async with httpx.AsyncClient(base_url=base_url, timeout=120.0) as client:
                try:
                    await run_smoke(client, clips, report)
                except (SmokeError, TimeoutError, httpx.HTTPError, KeyError) as exc:
                    report.stopped_early = type(exc).__name__ + (
                        f": {exc}" if isinstance(exc, SmokeError) else ""
                    )
    finally:
        report.calls_spent = ledger.spent(LEDGER_LABEL) - before
        report.ledger_total = ledger.total
    if gnani.fatal_status is not None:
        report.stopped_early = f"Gnani answered {gnani.fatal_status}; stopped"
    return report


def main(
    argv: list[str] | None = None,
    *,
    root: Path,
    make_gnani: GnaniFactory | None = None,
    make_translator: TranslatorFactory = _real_translator,
    today: date | None = None,
) -> int:
    """Exit codes: 0 every step passed, 1 a step failed or the run stopped, 2 refused."""
    parser = argparse.ArgumentParser(description="Live smoke test through the HTTP API.")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; send nothing")
    parser.add_argument("--yes", action="store_true", help="required to really spend the calls")
    parser.add_argument("--clips", type=Path, default=root / "demo" / "clips")
    parser.add_argument(
        "--ledger", type=Path, default=root / "eval" / "state" / "gnani_ledger.json"
    )
    parser.add_argument(
        "--out", type=Path, default=root / "eval" / "results" / "live_smoke.json"
    )
    args = parser.parse_args(argv)

    try:
        ledger = CallLedger(args.ledger)
        print(format_plan(ledger))
        if ledger.total + CALLS_PLANNED > ledger.cap:
            raise SmokeError("would pass the call cap")
        clips = load_clips(args.clips)
    except (SmokeError, OSError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return 0
    if not args.yes:
        print("refused: pass --yes to spend these calls (or --dry-run)", file=sys.stderr)
        return 2

    try:
        settings = get_settings()
    except ValidationError:
        print("refused: Gnani settings are missing (see .env.example)", file=sys.stderr)
        return 2
    factory = make_gnani or (lambda s, led, lim: GuardedGnani(s, led, lim))
    report = asyncio.run(run_live(settings, ledger, clips, factory, make_translator))
    for step in report.steps:
        print(f"{'ok  ' if step.ok else 'FAIL'} {step.name}")
    if report.stopped_early:
        print(f"stopped early: {report.stopped_early}", file=sys.stderr)
    print(f"gnani calls this run: {report.calls_spent}; ledger {report.ledger_total}/{ledger.cap}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report.to_json(today or date.today()), indent=2) + "\n", encoding="utf-8"
    )
    return 0 if report.passed else 1
