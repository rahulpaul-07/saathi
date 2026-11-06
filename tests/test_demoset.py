"""The 50-clip demo set: the committed manifest, the resumable build and the fact comparison.
Gnani is always a fake here; no network and no key."""

import json
from pathlib import Path

import pytest

from saathi.demobundle import BUNDLE_NAME
from saathi.evaluation import noisemix
from saathi.evaluation.calls import BudgetExceededError
from saathi.evaluation.democlips import CLIP_SPECS
from saathi.evaluation.demoset import (
    ExpectedFact,
    Layout,
    SetClip,
    build_set,
    compare_facts,
    load_clip_set,
    load_progress,
    planned_calls,
    read_turns,
    set_problems,
    write_manifest,
)
from saathi.facts import extract_facts
from saathi.gnani import GnaniError
from saathi.languages import LANGUAGES
from test_democlips import _tone
from test_room_api import FakeTranslator

CLIP_SET = Path(__file__).resolve().parent.parent / "demo" / "clip_set.json"
HEARD = "second cross fourth main gate number three"


def _clip(clip_id: str, tgt: str = "kn", existing: bool = False) -> SetClip:
    return SetClip(
        id=clip_id,
        lang="en",
        type="street",
        text="Second cross, fourth main, gate number three.",
        expected=[
            ExpectedFact(kind="cross", value="2"),
            ExpectedFact(kind="main", value="4"),
            ExpectedFact(kind="gate", value="3"),
        ],
        tgt=tgt,
        review_status="machine-written, not reviewed",
        label="Test clip",
        existing=existing,
    )


class FakeSpeech:
    """Counts calls; `fail` names the 1-based call numbers that raise a Gnani error."""

    def __init__(self, fail: tuple[int, ...] = (), stop_at: int | None = None) -> None:
        self.calls: list[str] = []
        self._fail = fail
        self._stop_at = stop_at
        self.heard = HEARD

    def _tick(self, kind: str) -> None:
        self.calls.append(kind)
        if self._stop_at is not None and len(self.calls) == self._stop_at:
            raise BudgetExceededError("cap")
        if len(self.calls) in self._fail:
            raise GnaniError("speech service error 504", 504)

    async def synthesize(self, text: str, language_code: str, voice: str) -> bytes:
        self._tick("tts")
        return _tone(24000)

    async def transcribe(self, audio: bytes, filename: str, language_code: str) -> str:
        self._tick("stt")
        return self.heard


def _layout(tmp_path: Path) -> Layout:
    return Layout(tmp_path / "clips", tmp_path / "bundle")


async def _build(tmp_path: Path, clips: list[SetClip], gnani: FakeSpeech, **kwargs: bool):  # type: ignore[no-untyped-def]
    return await build_set(
        clips,
        gnani,
        FakeTranslator(),
        noisemix.pink_noise(5.0, 1),
        _layout(tmp_path),
        1,
        say=lambda _: None,
        **kwargs,
    )


# --- the committed manifest --------------------------------------------------------------------


def test_the_committed_set_is_complete_and_marks_who_must_review_it() -> None:
    clips = load_clip_set(CLIP_SET)
    assert len(clips) == 50
    assert set_problems(clips) == []
    for clip in clips:
        expected = (
            "for author review" if clip.lang in ("bn", "hi") else "machine-written, not reviewed"
        )
        assert clip.review_status == expected
        assert clip.expected, clip.id
    assert sum(clip.existing for clip in clips) == 5
    assert {c.id for c in clips if c.existing} == {spec.id for spec in CLIP_SPECS}


def test_an_incomplete_set_is_reported() -> None:
    problems = set_problems([_clip("en-street")])
    assert any(p.startswith("bn:") for p in problems)
    assert any("never a rider language" in p for p in problems)


def test_a_clip_cannot_be_recorded_for_its_own_language() -> None:
    with pytest.raises(ValueError):
        _clip("en-street", tgt="en")


def test_every_rider_language_is_known_to_the_service() -> None:
    assert {c.tgt for c in load_clip_set(CLIP_SET)} == set(LANGUAGES)


# --- comparing facts ---------------------------------------------------------------------------


def test_matching_facts_have_no_differences() -> None:
    clip = _clip("en-street")
    assert compare_facts(clip.expected, extract_facts(clip.text, "en")) == []


def test_a_spoken_correction_replaces_the_mistake_like_the_card_does() -> None:
    heard = extract_facts("gate number four. Sorry, gate number two", "en")
    assert compare_facts([ExpectedFact(kind="gate", value="2")], heard) == []


def test_a_wrong_missing_or_extra_fact_is_a_difference() -> None:
    heard = extract_facts("second cross, gate number five", "en")
    expected = [ExpectedFact(kind="cross", value="2"), ExpectedFact(kind="gate", value="3")]
    assert compare_facts(expected, heard) == ["gate: expected 3, heard 5"]
    assert compare_facts([ExpectedFact(kind="main", value="4")], heard) == [
        "cross: expected None, heard 2",
        "gate: expected None, heard 5",
        "main: expected 4, heard None",
    ]


def test_landmarks_match_by_name_and_extras_count() -> None:
    heard = extract_facts("gate number five, opposite the bus stop", "en")
    expected = [
        ExpectedFact(kind="gate", value="5"),
        ExpectedFact(kind="landmark", value="bus stop"),
    ]
    assert compare_facts(expected, heard) == []
    missing = [*expected, ExpectedFact(kind="landmark", value="pharmacy")]
    assert compare_facts(missing, heard) == ["landmark missing: pharmacy"]
    assert compare_facts(expected[:1], heard) == ["landmark extra: bus stop"]


# --- the build ---------------------------------------------------------------------------------


async def test_a_new_clip_costs_three_calls_and_becomes_a_replayable_turn(tmp_path: Path) -> None:
    gnani = FakeSpeech()
    report = await _build(tmp_path, [_clip("en-street")], gnani)
    assert gnani.calls == ["tts", "stt", "tts"]
    assert report.built == ["en-street"] and report.failed == {}
    (turn,) = read_turns(tmp_path / "bundle")
    assert (turn.src, turn.tgt, turn.transcript) == ("en", "kn", HEARD)
    assert (tmp_path / "bundle" / turn.audio).is_file()
    assert write_manifest([_clip("en-street")], _layout(tmp_path)) == ["en-street"]
    manifest = json.loads((tmp_path / "clips" / "manifest.json").read_text("utf-8"))
    assert [c["id"] for c in manifest["clips"]] == ["en-street"]


async def test_a_clip_whose_transcript_misreads_a_fact_stays_out_of_the_picker(
    tmp_path: Path,
) -> None:
    gnani = FakeSpeech()
    gnani.heard = "second cross fifth main gate number three"  # the expected card says fourth main
    report = await _build(tmp_path, [_clip("en-street")], gnani)
    assert report.built == ["en-street"]  # still built and kept for the eval
    assert write_manifest([_clip("en-street")], _layout(tmp_path)) == []
    manifest = json.loads((tmp_path / "clips" / "manifest.json").read_text("utf-8"))
    assert manifest == {"clips": []}


async def test_an_existing_clip_is_never_rebuilt(tmp_path: Path) -> None:
    gnani = FakeSpeech()
    await _build(tmp_path, [_clip("en-old", existing=True)], gnani)
    assert gnani.calls == []
    assert (
        planned_calls([_clip("en-old", existing=True)], _layout(tmp_path), load_progress(tmp_path))
        == 0
    )


async def test_a_finished_run_is_free_to_run_again(tmp_path: Path) -> None:
    clips = [_clip("en-a"), _clip("en-b", tgt="hi")]
    await _build(tmp_path, clips, FakeSpeech())
    again = FakeSpeech()
    await _build(tmp_path, clips, again)
    assert again.calls == []
    assert planned_calls(clips, _layout(tmp_path), load_progress(tmp_path / "bundle")) == 0


async def test_a_failure_is_recorded_not_retried_and_the_run_continues(tmp_path: Path) -> None:
    clips = [_clip("en-a"), _clip("en-b", tgt="hi")]
    gnani = FakeSpeech(fail=(2,))  # the first clip's transcription fails
    report = await _build(tmp_path, clips, gnani)
    assert gnani.calls == [
        "tts",
        "stt",
        "tts",
        "stt",
        "tts",
    ]  # clip b ran in full, a was not retried
    assert report.failed == {"en-a": "gnani status 504"} and report.built == ["en-b"]
    assert load_progress(tmp_path / "bundle").failures == {"en-a": "gnani status 504"}


async def test_the_next_run_resumes_after_the_failed_step_only_when_asked(tmp_path: Path) -> None:
    clips = [_clip("en-a")]
    await _build(tmp_path, clips, FakeSpeech(fail=(2,)))
    skipped = FakeSpeech()
    report = await _build(tmp_path, clips, skipped)
    assert skipped.calls == [] and report.skipped == ["en-a"]
    retry = FakeSpeech()
    await _build(tmp_path, clips, retry, retry_failed=True)
    assert retry.calls == ["stt", "tts"]  # the customer speech already paid for is reused
    assert load_progress(tmp_path / "bundle").failures == {}


async def test_a_stop_at_the_budget_keeps_what_was_paid_for(tmp_path: Path) -> None:
    clips = [_clip("en-a")]
    with pytest.raises(BudgetExceededError):
        await _build(tmp_path, clips, FakeSpeech(stop_at=3))  # stt succeeded, rider speech refused
    assert load_progress(tmp_path / "bundle").transcripts == {"en-a": HEARD}
    resumed = FakeSpeech()
    await _build(tmp_path, clips, resumed)
    assert resumed.calls == ["tts"]  # neither the customer speech nor the transcription again
    assert len(read_turns(tmp_path / "bundle")) == 1


async def test_an_empty_transcript_is_a_recorded_failure(tmp_path: Path) -> None:
    gnani = FakeSpeech()
    gnani.heard = "   "
    report = await _build(tmp_path, [_clip("en-a")], gnani)
    assert report.failed == {"en-a": "NoSpeechError"}
    assert not (tmp_path / "bundle" / BUNDLE_NAME).exists()


def test_the_dry_run_count_is_three_calls_per_unbuilt_clip(tmp_path: Path) -> None:
    clips = [_clip("en-a"), _clip("en-b", tgt="hi"), _clip("en-old", existing=True)]
    assert planned_calls(clips, _layout(tmp_path), load_progress(tmp_path)) == 6
