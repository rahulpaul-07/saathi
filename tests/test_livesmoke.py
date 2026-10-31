"""The live smoke logic against a real local server, with Gnani replaced at the network."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import SecretStr

from placeholders import carry
from saathi.config import Settings
from saathi.evaluation import livesmoke
from saathi.evaluation.calls import CallLedger, SlidingWindowLimiter
from saathi.gnani import STT_PATH, TTS_PATH
from wavs import make_streaming_wav, make_wav

BASE = "https://api.test"
FIRST = "second cross third main gate number 4 near the bakery"
CORRECTION = "sorry gate number 2"
SECRET_WORDS = ("near the", "hindi text", "sorry gate")


class FakeTranslator:
    def translate(self, text: str, src: str, tgt: str) -> str:
        return carry("hindi text", text)


def settings() -> Settings:
    return Settings(gnani_api_key=SecretStr("k"), gnani_base_url=BASE)


def make_gnani(
    ledger: CallLedger, ceiling: int = livesmoke.CALLS_CEILING
) -> livesmoke.GuardedGnani:
    # A wide-open limiter: pacing is tested in test_calls; here it would only add waiting.
    return livesmoke.GuardedGnani(settings(), ledger, SlidingWindowLimiter(1000), ceiling)


async def run(
    ledger: CallLedger, ceiling: int = livesmoke.CALLS_CEILING
) -> livesmoke.SmokeReport:
    clips = {livesmoke.FIRST_CLIP: make_wav(), livesmoke.CORRECTION_CLIP: make_wav()}
    return await livesmoke.run_live(
        settings(),
        ledger,
        clips,
        lambda _s, led, _lim: make_gnani(led, ceiling),
        lambda _s: FakeTranslator(),
    )


def mock_gnani(stt: list[httpx.Response] | None = None) -> respx.Route:
    """Answer the two Gnani endpoints; let the local test server through."""
    respx.route(host="127.0.0.1").pass_through()
    respx.post(f"{BASE}{TTS_PATH}").mock(
        return_value=httpx.Response(200, content=make_streaming_wav())
    )
    answers = stt or [
        httpx.Response(200, json={"success": True, "transcript": FIRST}),
        httpx.Response(200, json={"success": True, "transcript": CORRECTION}),
    ]
    return respx.post(f"{BASE}{STT_PATH}").mock(side_effect=answers)


@respx.mock
async def test_full_journey_passes_with_six_calls(tmp_path: Path) -> None:
    mock_gnani()
    ledger = CallLedger(tmp_path / "ledger.json")

    report = await run(ledger)

    assert [step.name for step in report.steps if not step.ok] == []
    assert report.passed and len(report.steps) == 9
    assert report.calls_spent == livesmoke.CALLS_PLANNED == ledger.total
    assert report.turn_facts[0].keys() >= {"cross", "main", "gate"}


@respx.mock
async def test_summary_holds_no_transcript_or_translation(tmp_path: Path) -> None:
    mock_gnani()
    report = await run(CallLedger(tmp_path / "ledger.json"))

    text = json.dumps(report.to_json(date(2026, 10, 31)))

    assert report.passed
    assert not any(word in text for word in SECRET_WORDS)
    assert json.loads(text)["content_free"] is True


@respx.mock
async def test_a_fatal_gnani_status_stops_the_run_after_one_call(tmp_path: Path) -> None:
    stt = mock_gnani([httpx.Response(401, text="bad key")])
    ledger = CallLedger(tmp_path / "ledger.json")

    report = await run(ledger)

    assert not report.passed
    assert report.stopped_early is not None and "401" in report.stopped_early
    assert stt.call_count == 1 and report.calls_spent == 1
    assert all(step.ok for step in report.steps)  # nothing was recorded as passing falsely


@respx.mock
async def test_the_run_ceiling_stops_before_the_next_call(tmp_path: Path) -> None:
    mock_gnani()
    ledger = CallLedger(tmp_path / "ledger.json")

    report = await run(ledger, ceiling=2)

    assert not report.passed
    assert report.calls_spent == 2


@respx.mock
async def test_a_misheard_correction_fails_the_marker_step_and_the_run_goes_on(
    tmp_path: Path,
) -> None:
    mock_gnani(
        [
            httpx.Response(200, json={"success": True, "transcript": FIRST}),
            httpx.Response(200, json={"success": True, "transcript": "sorry"}),
        ]
    )

    report = await run(CallLedger(tmp_path / "ledger.json"))

    failed = [step.name for step in report.steps if not step.ok]
    assert failed and failed[0].startswith("turn 2")
    assert len(report.steps) == 9  # later steps still ran and are reported


def test_dry_run_sends_nothing_and_needs_the_clips(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clips = tmp_path / "clips"
    clips.mkdir()
    for name in (livesmoke.FIRST_CLIP, livesmoke.CORRECTION_CLIP):
        (clips / f"{name}.wav").write_bytes(make_wav())

    code = livesmoke.main(
        ["--dry-run", "--clips", str(clips), "--ledger", str(tmp_path / "l.json")], root=tmp_path
    )

    assert code == 0
    assert "6 Gnani calls planned" in capsys.readouterr().out
    assert not (tmp_path / "l.json").exists()


def test_without_yes_nothing_is_spent(tmp_path: Path) -> None:
    clips = tmp_path / "clips"
    clips.mkdir()
    for name in (livesmoke.FIRST_CLIP, livesmoke.CORRECTION_CLIP):
        (clips / f"{name}.wav").write_bytes(make_wav())

    code = livesmoke.main(
        ["--clips", str(clips), "--ledger", str(tmp_path / "l.json")], root=tmp_path
    )

    assert code == 2


def test_missing_clips_are_refused(tmp_path: Path) -> None:
    code = livesmoke.main(
        ["--dry-run", "--clips", str(tmp_path / "none"), "--ledger", str(tmp_path / "l.json")],
        root=tmp_path,
    )

    assert code == 2


def test_the_plan_would_refuse_to_pass_the_cap(tmp_path: Path) -> None:
    ledger_path = tmp_path / "l.json"
    ledger_path.write_text(json.dumps({"other": 1498}))

    code = livesmoke.main(["--dry-run", "--ledger", str(ledger_path)], root=tmp_path)

    assert code == 2
