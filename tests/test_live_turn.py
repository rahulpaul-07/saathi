import io
import json
import wave
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from saathi.evaluation import liveturn
from saathi.evaluation.calls import CallLedger, SlidingWindowLimiter
from saathi.gnani import GnaniClient, GnaniError

KN_TEXT = "ನಮ್ಮ ಮನೆ ಎರಡನೇ ಕ್ರಾಸ್, ಮೂರನೇ ಮೇನ್, ಗೇಟ್ ನಂಬರ್ ಎರಡು ಹತ್ತಿರ, ಆಪೋಸಿಟ್ ಗಣೇಶ ದೇವಸ್ಥಾನ"
SECRET_TRANSLATION = "synthetic translation that must never be printed"


def _wav(amplitude: int = 3000) -> bytes:
    samples = (np.sin(np.linspace(0, 200, 8000)) * amplitude).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes(samples.tobytes())
    return buffer.getvalue()


class FakeGnani:
    def __init__(self, ledger: CallLedger, fail: bool = False) -> None:
        self.ledger = ledger
        self.fail = fail
        self.calls: list[str] = []

    def _count(self, name: str) -> None:
        self.ledger.spend(liveturn.LEDGER_LABEL)
        self.calls.append(name)
        if self.fail:
            raise GnaniError("speech service error 500", 500)

    async def synthesize(self, text: str, language_code: str, voice: str) -> bytes:
        self._count(f"tts:{language_code}")
        return _wav()

    async def transcribe(self, audio: bytes, filename: str, language_code: str) -> str:
        self._count(f"stt:{language_code}")
        return KN_TEXT

    async def aclose(self) -> None:
        pass


class FakeTranslator:
    def translate(self, text: str, src: str, tgt: str) -> str:
        return SECRET_TRANSLATION


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.gold = tmp_path / "gold.json"
        self.gold.write_text(
            json.dumps(
                {
                    "utterances": [
                        {"id": "g02", "split": "test", "lang": "kn", "text": KN_TEXT, "facts": []},
                        {"id": "g03", "split": "dev", "lang": "en", "text": "Gate 3.", "facts": []},
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.ledger_path = tmp_path / "ledger.json"
        self.out = tmp_path / "live"
        self.created: list[FakeGnani] = []

    def make_gnani(self, ledger: CallLedger) -> GnaniClient:
        fake = FakeGnani(ledger)
        self.created.append(fake)
        return cast(GnaniClient, fake)

    def run(self, *flags: str, gnani: bool = True) -> int:
        def no_client(ledger: CallLedger) -> GnaniClient:
            raise AssertionError("a client must not be created")

        return liveturn.main(
            [
                "--gold",
                str(self.gold),
                "--ledger",
                str(self.ledger_path),
                "--out-dir",
                str(self.out),
                *flags,
            ],
            root=self.tmp,
            make_gnani=self.make_gnani if gnani else no_client,
            make_translator=FakeTranslator,
            limiter=SlidingWindowLimiter(max_calls=3, window_s=0.0),
        )


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def test_dry_run_sends_nothing_and_needs_no_key(
    harness: Harness, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    assert harness.run("--dry-run", gnani=False) == 0
    out = capsys.readouterr().out
    assert "exactly 3 Gnani calls" in out
    assert "0 spent + 3 planned = 3 of cap 290" in out
    assert "Dry run: nothing was sent." in out
    assert KN_TEXT not in out
    assert not harness.ledger_path.exists()


def test_real_mode_refuses_without_yes(harness: Harness) -> None:
    assert harness.run(gnani=False) == 2
    assert not harness.ledger_path.exists()


def test_budget_cap_refuses_before_any_call(harness: Harness) -> None:
    CallLedger(harness.ledger_path).spend("other", 289)
    assert harness.run("--yes", gnani=False) == 2
    assert harness.run("--dry-run", gnani=False) == 2


def test_unknown_or_non_kannada_sentence_is_refused(harness: Harness) -> None:
    assert harness.run("--dry-run", "--gold-id", "g99", gnani=False) == 2
    assert harness.run("--dry-run", "--gold-id", "g03", gnani=False) == 2


def test_yes_runs_three_calls_and_prints_no_text(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    assert harness.run("--yes") == 0
    captured = capsys.readouterr()
    assert harness.created[0].calls == ["tts:kn-IN", "stt:kn-IN", "tts:bn-IN"]
    assert CallLedger(harness.ledger_path).spent(liveturn.LEDGER_LABEL) == 3
    shown = captured.out + captured.err
    assert KN_TEXT not in shown
    assert SECRET_TRANSLATION not in shown
    assert "gate x1" in shown
    assert "output level: rms" in shown
    assert (harness.out / "g02_kn_bn.wav").read_bytes()


def test_show_text_prints_transcript_translation_and_facts(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    assert harness.run("--yes", "--show-text") == 0
    out = capsys.readouterr().out
    assert f"kn transcript: {KN_TEXT}" in out
    assert f"bn translation: {SECRET_TRANSLATION}" in out
    assert "facts: " in out and "gate: 2" in out


def test_gnani_failure_is_reported_without_details(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing(ledger: CallLedger) -> GnaniClient:
        return cast(GnaniClient, FakeGnani(ledger, fail=True))

    code = liveturn.main(
        ["--gold", str(harness.gold), "--ledger", str(harness.ledger_path), "--yes"],
        root=harness.tmp,
        make_gnani=failing,
        make_translator=FakeTranslator,
        limiter=SlidingWindowLimiter(max_calls=3, window_s=0.0),
    )
    assert code == 1
    assert "Gnani error 500" in capsys.readouterr().err


def test_measure_level_of_known_signal() -> None:
    level = liveturn.measure_level(_wav(16384))
    assert level.peak_dbfs == pytest.approx(-6.0, abs=0.1)
    assert level.seconds == 0.5
