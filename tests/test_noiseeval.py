import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from saathi.evaluation import noisemix
from saathi.evaluation.calls import BudgetExceededError, CallLedger, SlidingWindowLimiter
from saathi.evaluation.factscore import GoldFact, GoldUtterance, load_gold
from saathi.evaluation.noiseeval import (
    CONDITIONS,
    REPORT_SETS,
    PlannedCall,
    check_budget,
    load_results,
    plan_calls,
    prepare_clips,
    run_calls,
    save_results,
    summarize,
)
from saathi.evaluation.wavtools import RecordingError
from wavs import make_wav

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "eval" / "gold" / "directions.json"


def _utterance(n: int) -> GoldUtterance:
    return GoldUtterance(f"t{n}", "test", "en", f"Gate number {n}.", (GoldFact("gate", str(n)),))


def _speech_wav(seconds: float = 3.0) -> bytes:
    t = np.arange(round(seconds * noisemix.RATE)) / noisemix.RATE
    on = (np.sin(2 * np.pi * 1.5 * t) > 0).astype(float)
    return noisemix.write_wav(0.3 * np.sin(2 * np.pi * 220 * t) * on)


def _street_wav(seconds: float = 40.0) -> bytes:
    return noisemix.write_wav(noisemix.pink_noise(seconds, 5))


def _recordings(tmp_path: Path, gold: list[GoldUtterance]) -> Path:
    folder = tmp_path / "audio"
    folder.mkdir()
    for u in gold:
        (folder / f"{u.id}.wav").write_bytes(_speech_wav())
    return folder


class FakeGnani:
    """Stands in for MeteredGnani: counts like it, never touches the network."""

    def __init__(self, ledger: CallLedger, answer: Any) -> None:
        self.ledger = ledger
        self.answer = answer
        self.sent: list[tuple[int, str]] = []

    async def transcribe(self, audio: bytes, filename: str, language_code: str) -> str:
        self.ledger.spend("noise-stt")
        self.sent.append((len(audio), language_code))
        return str(self.answer(len(self.sent)))


def test_plan_over_the_real_gold_set_is_150_calls_clean_first() -> None:
    gold = load_gold(GOLD)
    calls = plan_calls(gold, Path("eval/audio/gold"))
    assert len(gold) == 30 and len(calls) == 150
    assert [c.condition.name for c in calls[:30]] == ["clean"] * 30
    assert len({c.key for c in calls}) == 150
    by_condition = {c.condition.name for c in calls}
    assert by_condition == {"clean", "street_20", "street_10", "street_5", "pink_10"}
    assert sum(c.condition.noise == "pink" for c in calls) == 30


def test_dry_run_with_absent_audio_lists_calls_and_sends_nothing(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    out = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "eval_noise.py"), "run", "--dry-run",
            "--audio-dir", str(tmp_path / "none"), "--ledger", str(ledger_path),
            "--results", str(tmp_path / "r.json"),
            "--street-file", str(tmp_path / "street.wav"),
        ],
        capture_output=True, text=True, cwd=tmp_path, env={"PATH": "", "SYSTEMROOT": "C:\\Windows"},
    )  # fmt: skip
    assert out.returncode == 0, out.stderr
    assert "150 pending" in out.stdout and "[MISSING]" in out.stdout
    assert "Recordings missing: 30 of 30" in out.stdout
    assert "Street noise: " in out.stdout and "[MISSING]" in out.stdout.split("Street noise:")[1]
    assert "30 clean, 30 street_20, 30 street_10, 30 street_5, 30 pink_10" in out.stdout
    assert "0 spent + 150 planned = 150 of cap 780" in out.stdout
    assert not ledger_path.exists()  # the ledger is only written by a spend


def test_check_budget_refuses_a_plan_over_the_cap(tmp_path: Path) -> None:
    ledger = CallLedger(tmp_path / "l.json", cap=100)
    ledger.spend("probe", 22)
    check_budget(ledger, 78)
    with pytest.raises(BudgetExceededError):
        check_budget(ledger, 79)


async def test_run_refuses_before_any_call_when_plan_exceeds_cap(tmp_path: Path) -> None:
    gold = [_utterance(1), _utterance(2)]
    calls = plan_calls(gold, _recordings(tmp_path, gold))
    clips, problems = prepare_clips(calls, 1, _street_wav())
    ledger = CallLedger(tmp_path / "l.json", cap=7)  # 8 calls planned
    fake = FakeGnani(ledger, lambda n: "x")
    with pytest.raises(BudgetExceededError):
        await run_calls(calls, clips, fake, SlidingWindowLimiter(), ledger, {}, lambda r: None)
    assert problems == [] and fake.sent == [] and ledger.total == 0


async def test_cap_reached_mid_run_stops_and_keeps_saved_results(tmp_path: Path) -> None:
    gold = [_utterance(1)]
    calls = plan_calls(gold, _recordings(tmp_path, gold))
    clips, _ = prepare_clips(calls, 1, _street_wav())
    ledger = CallLedger(tmp_path / "l.json", cap=5)

    def answer(n: int) -> str:
        if n == 2:
            ledger.spend("retries", 3)  # hidden retries use the headroom after the pre-check passed
        return "x"

    fake = FakeGnani(ledger, answer)
    results: dict[str, dict[str, Any]] = {}
    with pytest.raises(BudgetExceededError):
        await run_calls(calls, clips, fake, SlidingWindowLimiter(), ledger, results, lambda r: None)
    assert len(results) == 2 and ledger.total == 5 and len(fake.sent) == 2


async def test_run_saves_after_each_call_and_resume_skips_finished(tmp_path: Path) -> None:
    gold = [_utterance(1), _utterance(2)]
    calls = plan_calls(gold, _recordings(tmp_path, gold))
    clips, _ = prepare_clips(calls, 1, _street_wav())
    ledger = CallLedger(tmp_path / "l.json")
    saved = tmp_path / "results.json"
    results: dict[str, dict[str, Any]] = {}
    fake = FakeGnani(ledger, lambda n: f" Gate number {n} ")

    def save(rows: dict[str, dict[str, Any]]) -> None:
        save_results(saved, {"seed": 1}, rows)

    await run_calls(calls[:3], clips, fake, SlidingWindowLimiter(), ledger, results, save)
    assert len(load_results(saved)) == 3
    await run_calls(calls, clips, fake, SlidingWindowLimiter(), ledger, load_results(saved), save)
    assert len(fake.sent) == 10 and ledger.total == 10  # 3 + 7, no clip sent twice
    assert all(lang == "en-IN" for _, lang in fake.sent)
    assert load_results(saved)["t1|clean"]["transcript"] == "Gate number 1"


async def test_unready_clips_block_the_whole_run(tmp_path: Path) -> None:
    gold = [_utterance(1)]
    calls = plan_calls(gold, tmp_path / "absent")
    clips, _ = prepare_clips(calls, 1, _street_wav())
    ledger = CallLedger(tmp_path / "l.json")
    fake = FakeGnani(ledger, lambda n: "x")
    with pytest.raises(RecordingError):
        await run_calls(calls, clips, fake, SlidingWindowLimiter(), ledger, {}, lambda r: None)
    assert fake.sent == []


def test_prepare_clips_reports_missing_and_bad_audio_and_is_deterministic(tmp_path: Path) -> None:
    gold = [_utterance(1), _utterance(2), _utterance(3)]
    folder = tmp_path / "audio"
    folder.mkdir()
    (folder / "t1.wav").write_bytes(_speech_wav())
    (folder / "t2.wav").write_bytes(make_wav(2.0, rate=8000))  # wrong sample rate
    calls = plan_calls(gold, folder)
    clips, problems = prepare_clips(calls, 9, _street_wav())
    assert set(clips) == {f"t1|{c.name}" for c in CONDITIONS}
    assert any("t2.wav" in p and "16 kHz" in p for p in problems)
    assert clips["t1|clean"].wav == (folder / "t1.wav").read_bytes()  # clean is untouched
    assert clips["t1|street_5"].wav != clips["t1|street_20"].wav
    assert clips["t1|street_10"].measured_snr_db == pytest.approx(10.0, abs=0.01)
    again, _ = prepare_clips(calls, 9, _street_wav())
    assert again["t1|street_10"].wav == clips["t1|street_10"].wav


def test_prepare_clips_reports_a_silent_recording(tmp_path: Path) -> None:
    gold = [_utterance(1)]
    folder = tmp_path / "audio"
    folder.mkdir()
    (folder / "t1.wav").write_bytes(make_wav(2.0))  # digital silence
    clips, problems = prepare_clips(plan_calls(gold, folder), 1, _street_wav())
    assert "t1|clean" in clips and "t1|street_20" not in clips
    assert any("silent" in p for p in problems)


def test_prepare_clips_street_file_under_30_s_is_reported_once(tmp_path: Path) -> None:
    gold = [_utterance(1)]
    calls = plan_calls(gold, _recordings(tmp_path, gold))
    clips, problems = prepare_clips(calls, 1, _street_wav(10.0))
    assert len(problems) == 1 and "street noise file" in problems[0] and "30 s" in problems[0]
    assert set(clips) == {"t1|clean", "t1|pink_10"}  # pink still works without the street file


def test_prepare_clips_missing_street_file_is_reported_once(tmp_path: Path) -> None:
    gold = [_utterance(1), _utterance(2)]
    calls = plan_calls(gold, _recordings(tmp_path, gold))
    clips, problems = prepare_clips(calls, 1, None)
    assert len(problems) == 1 and "street noise file is missing" in problems[0]
    assert not any(k.split("|")[1].startswith("street") for k in clips)


def test_prepare_clips_street_file_wrong_format_is_reported(tmp_path: Path) -> None:
    gold = [_utterance(1)]
    calls = plan_calls(gold, _recordings(tmp_path, gold))
    _, problems = prepare_clips(calls, 1, make_wav(40.0, rate=8000))
    assert len(problems) == 1 and "16 kHz" in problems[0]


def test_prepare_clips_street_shorter_than_longest_utterance_is_reported(tmp_path: Path) -> None:
    gold = [_utterance(1)]
    folder = _recordings(tmp_path, gold)
    (folder / "t1.wav").write_bytes(_speech_wav(45.0))
    _, problems = prepare_clips(plan_calls(gold, folder), 1, _street_wav(31.0))
    assert len(problems) == 1 and "shorter than the longest utterance" in problems[0]


def test_street_and_pink_at_the_same_snr_are_different_clips(tmp_path: Path) -> None:
    gold = [_utterance(1)]
    calls = plan_calls(gold, _recordings(tmp_path, gold))
    clips, _ = prepare_clips(calls, 4, _street_wav())
    assert clips["t1|street_10"].wav != clips["t1|pink_10"].wav
    assert clips["t1|pink_10"].measured_snr_db == pytest.approx(10.0, abs=0.01)


def test_report_sets_never_pool_street_and_pink() -> None:
    for _, conditions in REPORT_SETS:
        assert conditions[0].name == "clean"
        assert len({c.noise for c in conditions[1:]}) == 1
    assert [len(c) for _, c in REPORT_SETS] == [4, 2]


def _results(gold: list[GoldUtterance], degraded: set[str]) -> dict[str, dict[str, Any]]:
    return {
        f"{u.id}|{c.name}": {"transcript": "" if c.name in degraded else u.text}
        for u in gold
        for c in CONDITIONS
    }


def test_summary_perfect_and_degraded_conditions() -> None:
    gold = [_utterance(n) for n in range(1, 11)]
    summaries = summarize(gold, _results(gold, {"street_5"}), CONDITIONS, seed=1, resamples=300)
    by_name = {s.condition: s for s in summaries}
    assert by_name["clean"].n == 10
    assert by_name["clean"].recall.point == 1.0 and by_name["clean"].precision.point == 1.0
    assert by_name["street_5"].recall.point == 0.0 and by_name["street_5"].precision.point is None
    drop = by_name["street_5"].recall_drop_vs_clean
    assert drop is not None and drop.point == 1.0 and drop.low == 1.0
    assert by_name["clean"].recall_drop_vs_clean is None


def test_summary_ci_is_seeded_and_wide_with_mixed_results() -> None:
    gold = [_utterance(n) for n in range(1, 21)]
    results = _results(gold, set())
    for u in gold[:8]:
        results[f"{u.id}|street_10"]["transcript"] = ""
    first = summarize(gold, results, CONDITIONS, seed=3, resamples=500)
    assert first == summarize(gold, results, CONDITIONS, seed=3, resamples=500)
    recall = {s.condition: s.recall for s in first}["street_10"]
    assert recall.point == pytest.approx(0.6)
    assert recall.low is not None and recall.high is not None
    assert recall.low < 0.6 < recall.high and recall.high - recall.low > 0.3


def test_summary_uses_only_utterances_present_in_every_condition() -> None:
    gold = [_utterance(n) for n in range(1, 5)]
    results = _results(gold, set())
    del results["t4|street_5"]
    assert {s.n for s in summarize(gold, results, CONDITIONS, 1, 50)} == {3}
    assert summarize(gold, {}, CONDITIONS, 1, 50) == []


def test_plannedcall_key_is_stable() -> None:
    call = PlannedCall(_utterance(7), CONDITIONS[2], Path("x.wav"))
    assert call.key == "t7|street_10"
