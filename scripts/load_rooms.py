"""Load test with a fake Gnani client: many rooms taking turns at once, in one process.

  uv run --no-sync python scripts/load_rooms.py [--rooms 50] [--turns 6] [--gnani-ms 40]

Spends no credits and needs no key, GPU or network. The app runs in-process behind httpx's ASGI
transport, so this measures the app's own work (routing, validation, room and card bookkeeping,
fact extraction, event fan-out) and nothing else. It does NOT measure the translation model, real
Gnani latency, TLS or the network; those dominate a real turn (see docs/EVAL.md).

"Server time" is each turn request's wall time minus the time it spent waiting in the fake Gnani
calls, so it stays comparable whatever --gnani-ms is.
"""

import argparse
import asyncio
import contextvars
import ctypes
import gc
import io
import itertools
import logging
import statistics
import sys
import time
import wave
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import cast

import httpx
from pydantic import SecretStr

from saathi.app import create_app
from saathi.config import Settings
from saathi.gnani import GnaniClient
from saathi.rooms import Event, Role, Room, RoomManager

# Synthetic addresses only. They give facts, so the card path runs too.
TRANSCRIPTS = (
    "gate number 2 near the blue temple",
    "second cross third main gate number 4",
    "gate number 7 opposite the green bakery",
    "okay thank you",
)

_gnani_wait: contextvars.ContextVar[list[float]] = contextvars.ContextVar("gnani_wait")


class FakeGnani:
    """Answers instantly after a fixed delay, and records the delay against the current request."""

    def __init__(self, delay_s: float) -> None:
        self._delay_s = delay_s
        self._transcripts = itertools.cycle(TRANSCRIPTS)

    async def _wait(self) -> None:
        start = time.perf_counter()
        await asyncio.sleep(self._delay_s)
        _gnani_wait.get().append(time.perf_counter() - start)

    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        await self._wait()
        return next(self._transcripts)

    async def synthesize(self, text: str, language: str, voice: str) -> bytes:
        await self._wait()
        return b"RIFFfake-speech" * 100

    async def aclose(self) -> None:
        return None


class FakeTranslator:
    def translate(self, text: str, src: str, tgt: str) -> str:
        return text  # the real model is out of scope here; see the module docstring


def one_second_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)
    return buf.getvalue()


def process_memory_mb() -> float:
    """Resident memory of this process in MB, with the standard library only."""
    if sys.platform == "win32":

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        # Explicit types: the default int conversion truncates the 64-bit process handle.
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if not psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            raise OSError("GetProcessMemoryInfo failed")
        return float(counters.WorkingSetSize) / 2**20
    with open("/proc/self/statm", encoding="ascii") as statm:
        return int(statm.read().split()[1]) * 4096 / 2**20


@dataclass
class Result:
    server_ms: list[float] = field(default_factory=list)
    errors: int = 0
    requests: int = 0


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def drain(queues: dict[Role, asyncio.Queue[Event | None]]) -> None:
    """Empty the event queues, as a connected browser would, so fan-out is exercised."""
    for queue in queues.values():
        while not queue.empty():
            queue.get_nowait()


async def run_room(
    client: httpx.AsyncClient, manager: RoomManager, turns: int, wav: bytes, result: Result
) -> Room:
    created = (await client.post("/rooms", json={"language": "en"})).json()
    code = created["code"]
    joined = (await client.post(f"/rooms/{code}/join", json={"language": "kn"})).json()
    tokens: dict[Role, str] = {"customer": created["token"], "rider": joined["token"]}
    room = manager.authorize(code, tokens["customer"]).room
    queues = {role: manager.subscribe(room, role) for role in tokens}
    for i in range(turns):
        who: Role = "customer" if i % 3 != 2 else "rider"
        waits: list[float] = []
        _gnani_wait.set(waits)
        start = time.perf_counter()
        response = await client.post(
            f"/rooms/{code}/turn",
            files={"audio": ("a.wav", wav, "audio/wav")},
            headers={"Authorization": f"Bearer {tokens[who]}"},
        )
        elapsed = time.perf_counter() - start
        result.requests += 1
        if response.status_code != 200:
            result.errors += 1
        else:
            result.server_ms.append((elapsed - sum(waits)) * 1000)
        drain(queues)
    return room


async def main_async(rooms: int, turns: int, gnani_ms: float) -> int:
    settings = Settings(
        gnani_api_key=SecretStr("load-test"),
        # One client IP drives every room here, so the per-IP limits would only measure themselves.
        room_rate_limit_per_minute=100_000,
        turn_rate_limit_per_minute=100_000,
        reply_rate_limit_per_minute=100_000,
        max_rooms=rooms + 1,
    )
    manager = RoomManager(max_rooms=rooms + 1)
    fake_gnani = cast(GnaniClient, FakeGnani(gnani_ms / 1000))
    app = create_app(settings, fake_gnani, FakeTranslator(), manager)
    # create_app turns INFO logging on; thousands of request lines would skew the timings.
    logging.getLogger().setLevel(logging.WARNING)
    result = Result()
    wav = one_second_wav()
    gc.collect()
    before = process_memory_mb()
    started = time.perf_counter()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://saathi"
    ) as client:
        live = await asyncio.gather(
            *(run_room(client, manager, turns, wav, result) for _ in range(rooms))
        )
        gc.collect()
        loaded = process_memory_mb()
        elapsed = time.perf_counter() - started
        for room in live:
            manager.close(room)
    gc.collect()
    after_close = process_memory_mb()

    print(f"rooms={rooms} turns/room={turns} fake gnani={gnani_ms:g} ms per call (2 calls/turn)")
    print(f"requests={result.requests} errors={result.errors} wall={elapsed:.2f}s "
          f"({result.requests / elapsed:.0f} turns/s)")
    if result.server_ms:
        print(f"server time per turn (excluding fake Gnani): "
              f"p50={statistics.median(result.server_ms):.1f} ms "
              f"p95={percentile(result.server_ms, 0.95):.1f} ms "
              f"max={max(result.server_ms):.1f} ms")
    print(f"process memory: before={before:.0f} MB, rooms alive={loaded:.0f} MB, "
          f"after close={after_close:.0f} MB")
    return 1 if result.errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rooms", type=int, default=50)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--gnani-ms", type=float, default=40.0)
    args = parser.parse_args()
    return asyncio.run(main_async(args.rooms, args.turns, args.gnani_ms))


if __name__ == "__main__":
    sys.exit(main())
