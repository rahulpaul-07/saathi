from pathlib import Path

from saathi.evaluation.fleurs import Clip
from saathi.evaluation.noiseeval import CLEAN, STREET_CONDITIONS
from saathi.evaluation.speecheval import (
    SPEECH_CONDITIONS,
    format_cer,
    plan_speech_calls,
    summarize_cer,
    verify_audio,
)

AUDIO = b"pcm"
SHA = "d8b4f0e5c04ee5ecf3a7b3ab0c1da3dd3eb5a50d3d0e2ff0d4b1c7e0b6e2c2e8"


def clip(lang: str, name: str, text: str, sha: str = SHA) -> Clip:
    return Clip(lang, f"{lang}-{name}", f"{name}.wav", "1", text, text, 5.0, sha)


def test_plan_has_one_call_per_clip_and_condition_clean_first(tmp_path: Path) -> None:
    clips = [clip("kn", "a", "abc"), clip("hi", "b", "def")]
    calls = plan_speech_calls(clips, tmp_path)
    assert len(calls) == len(clips) * len(SPEECH_CONDITIONS) == 8
    assert [c.condition for c in calls[:2]] == [CLEAN, CLEAN]
    assert calls[0].path == tmp_path / "kn" / "a.wav"
    assert {c.condition.name for c in calls} == {"clean", *(s.name for s in STREET_CONDITIONS)}


def test_verify_audio_reports_missing_and_tampered_files(tmp_path: Path) -> None:
    (tmp_path / "kn").mkdir()
    (tmp_path / "kn" / "a.wav").write_bytes(b"not what was pinned")
    problems = verify_audio([clip("kn", "a", "x"), clip("hi", "b", "x")], tmp_path)
    assert len(problems) == 2
    assert any("missing" in p for p in problems) and any("SHA-256" in p for p in problems)


def results_for(clips: list[Clip], hypothesis: dict[str, str]) -> dict[str, dict[str, str]]:
    return {
        f"{c.id}|{k.name}": {"transcript": hypothesis.get(k.name, c.raw)}
        for c in clips
        for k in SPEECH_CONDITIONS
    }


def test_cer_rises_with_noise_and_is_paired_against_clean() -> None:
    clips = [clip("kn", f"c{i}", "abcdefghij") for i in range(4)] + [clip("hi", "h", "abcdefghij")]
    results = results_for(clips, {"street_5": "abcdefghxx"})
    rows = {r.lang: r for r in summarize_cer(clips, results, SPEECH_CONDITIONS, seed=1)}
    assert rows["kn"].cells["clean"].mean == 0.0
    assert rows["kn"].cells["street_5"].mean == 0.2
    assert rows["all"].cells["street_5"].n == 5
    assert rows["all"].delta_vs_clean["street_5"].mean == 0.2
    assert "street_5" in format_cer("street noise", list(rows.values()), SPEECH_CONDITIONS)


def test_clips_missing_a_condition_are_left_out_of_every_column() -> None:
    clips = [clip("kn", "a", "abc"), clip("kn", "b", "abc")]
    results = results_for(clips, {})
    del results["kn-b|street_10"]
    rows = summarize_cer(clips, results, SPEECH_CONDITIONS, seed=1)
    assert {name: cell.n for name, cell in rows[-1].cells.items()} == {
        "clean": 1,
        "street_20": 1,
        "street_10": 1,
        "street_5": 1,
    }


def test_nothing_usable_gives_no_rows_to_misreport() -> None:
    clips = [clip("kn", "a", "abc")]
    rows = summarize_cer(clips, {}, SPEECH_CONDITIONS, seed=1)
    assert [r.lang for r in rows] == ["all"] and rows[0].cells["clean"].mean is None
