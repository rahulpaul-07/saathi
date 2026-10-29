import json
from pathlib import Path
from typing import cast

import pytest

from saathi.evaluation import latency
from saathi.evaluation.calls import CallLedger, SlidingWindowLimiter
from saathi.evaluation.liveturn import main as live_main
from saathi.evaluation.power import PowerGuard, PowerState
from saathi.gnani import GnaniClient
from wavs import make_wav

SECRET = "synthetic text that must never be printed"


class FakeGnani:
    def __init__(self, ledger: CallLedger) -> None:
        self.ledger = ledger

    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        self.ledger.spend(latency.LEDGER_LABEL)
        return "gate number 2"

    async def synthesize(self, text: str, language: str, voice: str) -> bytes:
        self.ledger.spend(latency.LEDGER_LABEL)
        return b"RIFFfake"

    async def aclose(self) -> None:
        return None


class FakeTranslator:
    def translate(self, text: str, src: str, tgt: str) -> str:
        return SECRET


@pytest.fixture
def paths(tmp_path: Path) -> dict[str, Path]:
    audio = tmp_path / "audio"
    audio.mkdir()
    (audio / "a.wav").write_bytes(make_wav())
    return {"audio": audio, "ledger": tmp_path / "ledger.json", "out": tmp_path / "latency.json"}


def run(paths: dict[str, Path], tmp_path: Path, *flags: str) -> int:
    return latency.main(
        [
            "--audio-dir", str(paths["audio"]),
            "--ledger", str(paths["ledger"]),
            "--out", str(paths["out"]),
            *flags,
        ],
        root=tmp_path,
        make_gnani=lambda ledger: cast(GnaniClient, FakeGnani(ledger)),
        make_translator=FakeTranslator,
        limiter=SlidingWindowLimiter(max_calls=1000, window_s=0.0),
        guard_factory=lambda battery: PowerGuard(lambda: PowerState.AC),
    )  # fmt: skip


def test_dry_run_plans_forty_calls_and_sends_nothing(
    paths: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(paths, tmp_path, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "20 turns x 2 calls = 40 Gnani calls" in out
    assert "Dry run: nothing was sent." in out
    assert not paths["ledger"].exists()


def test_real_mode_refuses_without_yes(paths: dict[str, Path], tmp_path: Path) -> None:
    assert run(paths, tmp_path) == 2
    assert not paths["ledger"].exists()


def test_refuses_without_audio_or_over_budget_or_bad_pair(
    paths: dict[str, Path], tmp_path: Path
) -> None:
    (paths["audio"] / "a.wav").unlink()
    assert run(paths, tmp_path, "--dry-run") == 2
    (paths["audio"] / "a.wav").write_bytes(make_wav())
    CallLedger(paths["ledger"]).spend("other", 251)
    assert run(paths, tmp_path, "--dry-run") == 2
    assert run(paths, tmp_path, "--dry-run", "--src", "kn", "--tgt", "kn") == 2


def test_yes_runs_twenty_turns_and_prints_no_text(
    paths: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(paths, tmp_path, "--yes") == 0
    shown = capsys.readouterr()
    assert SECRET not in shown.out + shown.err
    assert CallLedger(paths["ledger"]).spent(latency.LEDGER_LABEL) == 40
    result = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert result["clean_samples"] == 20 and result["power"] == "ac"
    assert SECRET not in paths["out"].read_text(encoding="utf-8")


@pytest.mark.parametrize("target", ["te", "gu", "ml", "mr", "pa", "ta"])
def test_each_beta_smoke_test_is_a_three_call_dry_run(
    target: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gold = Path(__file__).resolve().parent.parent / "eval" / "gold" / "directions.json"
    code = live_main(
        ["--dry-run", "--target", target, "--gold", str(gold),
         "--ledger", str(tmp_path / "ledger.json")],
        root=tmp_path,
    )  # fmt: skip
    assert code == 0
    out = capsys.readouterr().out
    assert f"kn -> {target}: exactly 3 Gnani calls" in out
    assert not (tmp_path / "ledger.json").exists()


def test_unknown_or_source_target_is_refused(tmp_path: Path) -> None:
    for target in ("xx", "kn"):
        assert live_main(["--dry-run", "--target", target], root=tmp_path) == 2
