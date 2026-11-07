"""The language matrix: its checks, its clip loader, its report and its driver. The driver runs
against the real app with a fake translator and a Gnani stand-in; no model, network or credit."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import httpx
import pytest

from saathi.app import create_app
from saathi.demobundle import BUNDLE_NAME, BUNDLE_VERSION, clip_digest
from saathi.evaluation.demoset import PROGRESS_NAME, ExpectedFact
from saathi.evaluation.langmatrix import (
    ClipRun,
    GnaniForbidden,
    MappingEvidence,
    MappingRow,
    MatrixClip,
    Seen,
    check_turn,
    is_wav,
    landmark_counts,
    load_matrix_clips,
    mapping_evidence,
    render_report,
    report_json,
    run_matrix,
    shown_differences,
)
from saathi.facts import extract_facts
from saathi.gnani import GnaniClient
from saathi.languages import LANGUAGES
from saathi.rooms import RoomManager
from test_public_app import public_settings
from test_room_api import FakeTranslator
from wavs import make_wav

EN_TEXT = "gate number 2 near the blue temple"
HI_TEXT = "दूसरे क्रॉस, चौथे मेन, गेट नंबर तीन, मंदिर के पास।"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "language_matrix.py"


def chip(kind: str = "gate", value: str = "2", label: str = "Gate") -> dict[str, Any]:
    return {"kind": kind, "value": value, "heard": value, "label": label, "local": None}


def gate_two() -> tuple[ExpectedFact, ...]:
    return (ExpectedFact(kind="gate", value="2"),)


def make_clip(recorded: frozenset[str] = frozenset({"hi"})) -> MatrixClip:
    return MatrixClip("en-street", "en", b"wav", gate_two(), recorded)


def good_seen(**overrides: Any) -> Seen:
    fields: dict[str, Any] = {
        "status": 200,
        "ms": 10.0,
        "rider_event": True,
        "customer_facts": (chip(),),
        "rider_facts": (chip(),),
        "translation": "text",
        "verified": True,
        "audio_path": "/rooms/ABC234/turns/x/audio",
        "audio_status": 200,
        "audio_playable": True,
    }
    fields.update(overrides)
    return Seen(**fields)


# --- the checks ---------------------------------------------------------------------------------


def test_shown_chips_equal_to_the_expected_facts_have_no_differences() -> None:
    assert shown_differences(gate_two(), [chip()]) == []


def test_a_wrong_missing_or_extra_chip_is_reported() -> None:
    assert shown_differences(gate_two(), [chip(value="9")]) == ["gate: expected 2, heard 9"]
    assert shown_differences(gate_two(), []) == ["gate: expected 2, heard None"]
    extra = shown_differences(gate_two(), [chip(), chip("floor", "3")])
    assert extra == ["floor: expected None, heard 3"]


def test_a_malformed_chip_is_a_difference_not_a_crash() -> None:
    assert "malformed" in shown_differences(gate_two(), [{"kind": "door", "value": "2"}])[0]
    assert "malformed" in shown_differences(gate_two(), [{"kind": "gate", "value": 2}])[0]


def test_landmark_chips_are_counted_with_and_without_a_local_rendering() -> None:
    chips = [chip(), chip("landmark", "temple"), {**chip("landmark", "mosque"), "local": "masjid"}]
    assert landmark_counts(chips) == (2, 1)


def test_is_wav_needs_a_riff_wave_header_and_some_samples() -> None:
    assert is_wav(make_wav(0.1))
    assert not is_wav(b"RIFFfake-speech")
    assert not is_wav(b"")


def test_a_good_recorded_turn_passes() -> None:
    assert check_turn(make_clip(), "hi", good_seen()) == []


def test_an_unrecorded_pair_passes_with_the_text_only_fallback() -> None:
    text_only = good_seen(audio_path=None, audio_status=None, audio_playable=False)
    assert check_turn(make_clip(), "kn", text_only) == []


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"status": 422, "error_code": "demo_no_match"}, "refused with HTTP 422 demo_no_match"),
        ({"rider_event": False}, "received no turn"),
        ({"translation": "  "}, "translation is empty"),
        ({"rider_facts": (chip(value="9"),)}, "rider chips: gate: expected 2, heard 9"),
        ({"customer_facts": ()}, "customer chips: gate: expected 2, heard None"),
        ({"rider_facts": (chip(label=" "),)}, "a rider chip has no label"),
        (
            {"audio_path": None, "audio_status": None, "audio_playable": False},
            "recorded for this pair but the rider got text only",
        ),
        ({"audio_playable": False, "audio_status": 404}, "did not load as a WAV (HTTP 404)"),
    ],
)
def test_each_way_a_replay_can_fail_is_reported(overrides: dict[str, Any], expected: str) -> None:
    problems = check_turn(make_clip(), "hi", good_seen(**overrides))
    assert any(expected in problem for problem in problems), problems


def test_audio_offered_for_a_pair_that_was_never_recorded_fails() -> None:
    problems = check_turn(make_clip(), "kn", good_seen())
    assert any("no audio was recorded for this pair" in problem for problem in problems)


def test_the_gnani_stand_in_refuses_and_counts_any_use() -> None:
    gnani = GnaniForbidden()
    with pytest.raises(AssertionError, match="transcribe"):
        _ = gnani.transcribe
    assert gnani.attempts == ["transcribe"]


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("language_matrix", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_run_settings_ignore_a_dotenv_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stand-in .env with a recognisable value: were it read, masking_mode would not be "current".
    (tmp_path / ".env").write_text("SAATHI_MASKING_MODE=conditional\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SAATHI_MASKING_MODE", raising=False)
    settings = load_script().build_settings(tmp_path / "budget.json")
    assert settings.masking_mode == "current"
    assert settings.public_mode is True
    assert settings.gnani_api_key.get_secret_value() == "not-a-credential"
    assert settings.budget_file == tmp_path / "budget.json"


# --- the clip loader ----------------------------------------------------------------------------


def clip_set_entry(clip_id: str, tgt: str = "hi") -> dict[str, Any]:
    return {
        "id": clip_id,
        "lang": "en",
        "type": "street",
        "text": EN_TEXT,
        "expected": [{"kind": "gate", "value": "2"}],
        "tgt": tgt,
        "review_status": "for author review",
        "label": clip_id,
    }


def write_clip_set(root: Path, listed: list[str]) -> tuple[Path, Path, Path]:
    clips_dir, bundle_dir = root / "clips", root / "bundle"
    clips_dir.mkdir()
    bundle_dir.mkdir()
    wavs = {"en-a": make_wav(0.5), "en-b": make_wav(0.6)}
    for clip_id, wav in wavs.items():
        (clips_dir / f"{clip_id}.wav").write_bytes(wav)
    (clips_dir / "manifest.json").write_text(
        json.dumps({"clips": [{"id": clip_id} for clip_id in listed]}), encoding="utf-8"
    )
    clip_set = root / "clip_set.json"
    entries = [clip_set_entry("en-a"), clip_set_entry("en-b")]
    clip_set.write_text(json.dumps({"version": 1, "clips": entries}), encoding="utf-8")
    turns = [
        {
            "clip_sha256": clip_digest(wavs["en-a"]),
            "src": "en",
            "tgt": tgt,
            "transcript": EN_TEXT,
            "translation": "stored",
            "verified": True,
            "audio": "turn.wav",
        }
        for tgt in ("hi", "kn")
    ]
    (bundle_dir / BUNDLE_NAME).write_text(
        json.dumps({"version": BUNDLE_VERSION, "turns": turns}), encoding="utf-8"
    )
    return clip_set, clips_dir, bundle_dir


def test_only_clips_in_the_manifest_are_verified_and_the_rest_are_left_out(tmp_path: Path) -> None:
    clip_set, clips_dir, bundle_dir = write_clip_set(tmp_path, ["en-a"])
    clips, left_out = load_matrix_clips(clip_set, clips_dir, bundle_dir)
    assert [clip.id for clip in clips] == ["en-a"]
    assert left_out == ["en-b"]
    assert clips[0].recorded_for == {"hi", "kn"}
    assert clips[0].wav == make_wav(0.5)
    assert clips[0].expected == gate_two()


def test_a_manifest_entry_that_is_not_in_the_set_is_refused(tmp_path: Path) -> None:
    clip_set, clips_dir, bundle_dir = write_clip_set(tmp_path, ["en-a", "en-ghost"])
    with pytest.raises(ValueError, match="en-ghost"):
        load_matrix_clips(clip_set, clips_dir, bundle_dir)


# --- the Gnani mapping evidence -----------------------------------------------------------------


def write_mapping_fixture(root: Path) -> tuple[Path, Path, Path]:
    """Four clips, all recorded for a Hindi rider: one fully built, one whose transcription failed,
    one never started and one that an earlier build recorded."""
    clips_dir, bundle_dir = root / "clips", root / "bundle"
    clips_dir.mkdir()
    bundle_dir.mkdir()
    built = make_wav(0.5)
    (clips_dir / "en-built.wav").write_bytes(built)
    (clips_dir / "kn-stuck.wav").write_bytes(make_wav(0.6))
    (bundle_dir / "en-built-hi.wav").write_bytes(make_wav(0.4))
    entries = [
        {**clip_set_entry("en-built"), "lang": "en"},
        {**clip_set_entry("kn-stuck"), "lang": "kn"},
        {**clip_set_entry("te-never"), "lang": "te"},
        {**clip_set_entry("ta-earlier"), "lang": "ta", "existing": True},
    ]
    clip_set = root / "clip_set.json"
    clip_set.write_text(json.dumps({"version": 1, "clips": entries}), encoding="utf-8")
    turn = {
        "clip_sha256": clip_digest(built),
        "src": "en",
        "tgt": "hi",
        "transcript": EN_TEXT,
        "translation": "stored",
        "verified": True,
        "audio": "en-built-hi.wav",
    }
    (bundle_dir / BUNDLE_NAME).write_text(
        json.dumps({"version": BUNDLE_VERSION, "turns": [turn]}), encoding="utf-8"
    )
    progress = {"transcripts": {}, "failures": {"kn-stuck": "gnani status 504"}}
    (bundle_dir / PROGRESS_NAME).write_text(json.dumps(progress), encoding="utf-8")
    return clip_set, clips_dir, bundle_dir


def test_the_mapping_rows_count_what_the_build_stored_for_each_language(tmp_path: Path) -> None:
    evidence = mapping_evidence(*write_mapping_fixture(tmp_path))
    rows = {row.lang: row for row in evidence.rows}
    assert sorted(rows) == sorted(LANGUAGES)
    for code, language in LANGUAGES.items():
        assert (rows[code].stt_code, rows[code].voice) == (language.gnani_code, language.tts_voice)
    assert (rows["en"].clips, rows["en"].speech_made, rows["en"].transcribed) == (1, 1, 1)
    assert (rows["kn"].clips, rows["kn"].speech_made, rows["kn"].transcribed) == (1, 1, 0)
    assert (rows["te"].clips, rows["te"].speech_made, rows["te"].transcribed) == (1, 0, 0)
    # Three clips of the build are recorded for the Hindi rider; only one has its recording.
    assert (rows["hi"].rider_clips, rows["hi"].rider_made) == (3, 1)


def test_a_clip_that_stopped_early_is_listed_with_its_cause_and_first_missing_call(
    tmp_path: Path,
) -> None:
    evidence = mapping_evidence(*write_mapping_fixture(tmp_path))
    assert evidence.failures == (
        "`kn-stuck` (kn): gnani status 504; first call not stored: transcription",
        "`te-never` (te): no failure recorded; first call not stored: customer speech",
    )


def test_a_turn_whose_rider_recording_is_missing_counts_as_not_stored(tmp_path: Path) -> None:
    clip_set, clips_dir, bundle_dir = write_mapping_fixture(tmp_path)
    (bundle_dir / "en-built-hi.wav").unlink()
    evidence = mapping_evidence(clip_set, clips_dir, bundle_dir)
    rows = {row.lang: row for row in evidence.rows}
    assert rows["hi"].rider_made == 0
    assert evidence.failures[0] == (
        "`en-built` (en): no failure recorded; first call not stored: rider speech"
    )


def test_clips_an_earlier_build_recorded_are_listed_and_not_counted(tmp_path: Path) -> None:
    evidence = mapping_evidence(*write_mapping_fixture(tmp_path))
    assert evidence.earlier == ("ta-earlier",)
    assert {row.lang: row.clips for row in evidence.rows}["ta"] == 0


# --- the report ---------------------------------------------------------------------------------


def run_of(
    src: str,
    tgt: str,
    ms: float,
    problems: tuple[str, ...] = (),
    clip_id: str = "clip",
    stored: bool = False,
) -> ClipRun:
    return ClipRun(clip_id, src, tgt, ms, stored, True, 1, 0, problems)


def test_the_report_marks_each_pair_and_lists_every_failure_with_its_cause() -> None:
    cause = "rider chips: gate: expected 2, heard 9"
    runs = [
        run_of("en", "hi", 100.0, stored=True),
        run_of("hi", "en", 200.0, problems=(cause,), clip_id="hi-street"),
    ]
    text = render_report(
        runs, languages=["hi", "en"], meta={"device": "test"}, left_out=["x-1"], gnani_attempts=0
    )
    assert "1 of 2 ordered pairs passed" in text
    assert "| en | n/a | ok 100 |" in text
    assert "| hi | FAIL 200 | n/a |" in text
    assert f"- `hi` to `en`, clip `hi-street`: {cause}" in text
    assert "Gnani calls made by this run: 0" in text
    assert "`x-1`" in text


def test_a_clean_run_says_so_and_a_cell_shows_the_median() -> None:
    runs = [run_of("en", "hi", ms) for ms in (100.0, 300.0, 200.0)] + [run_of("hi", "en", 50.0)]
    text = render_report(runs, languages=["en", "hi"], meta={}, left_out=[], gnani_attempts=0)
    assert "2 of 2 ordered pairs passed" in text
    assert "None: every replay passed." in text
    assert "| en | n/a | ok 200 |" in text
    assert "Gnani language mapping" not in text  # only a run given the evidence reports it


def test_the_report_says_the_times_are_no_benchmark_and_what_unverified_means() -> None:
    text = render_report(
        [run_of("en", "hi", 10.0)], languages=["en", "hi"], meta={}, left_out=[], gnani_attempts=0
    )
    assert "a correctness run, not a benchmark" in text
    assert "`eval/results/latency.json`" in text
    assert "came back from the model exactly once" in text
    assert "the facts spelled out from tables instead of the model's sentence" in text


MAPPING = MappingEvidence(
    rows=(MappingRow("kn", "kn-IN", "Saanvi", 5, 5, 4, 3, 3),),
    failures=("`kn-stuck` (kn): gnani status 504; first call not stored: transcription",),
    earlier=("kn-gate",),
)


def test_the_report_shows_the_mapping_table_and_the_clips_that_stopped_early() -> None:
    text = render_report(
        [run_of("en", "hi", 10.0)],
        languages=["en", "hi"],
        meta={},
        left_out=[],
        gnani_attempts=0,
        mapping=MAPPING,
    )
    assert "## Gnani language mapping" in text
    assert "| kn | kn-IN | Saanvi | 5 of 5 | 4 of 5 | 3 of 3 |" in text
    assert "Clips recorded by an earlier build are not counted: `kn-gate`." in text
    assert "- `kn-stuck` (kn): gnani status 504; first call not stored: transcription" in text


def test_the_mapping_section_says_none_when_every_clip_got_all_three_calls() -> None:
    clean = MappingEvidence(rows=MAPPING.rows)
    text = render_report(
        [run_of("en", "hi", 10.0)],
        languages=["en", "hi"],
        meta={},
        left_out=[],
        gnani_attempts=0,
        mapping=clean,
    )
    assert "Clips that did not get all three calls stored:\n\n- None." in text
    assert "earlier build" not in text


def test_the_json_report_carries_the_mapping_only_when_it_was_given() -> None:
    runs = [run_of("en", "hi", 10.0)]
    # Through JSON, as the file is written: a tuple comes back as a list.
    written = json.dumps(report_json(runs, meta={}, left_out=[], gnani_attempts=0, mapping=MAPPING))
    given = json.loads(written)
    assert given["mapping"]["rows"][0]["stt_code"] == "kn-IN"
    assert given["mapping"]["failures"] == [MAPPING.failures[0]]
    assert report_json(runs, meta={}, left_out=[], gnani_attempts=0)["mapping"] is None


# --- the driver, through the real route ---------------------------------------------------------


def write_bundle(directory: Path, turns: list[tuple[bytes, str, str, str]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "turn.wav").write_bytes(make_wav(0.5))
    body = [
        {
            "clip_sha256": clip_digest(wav),
            "src": src,
            "tgt": tgt,
            "transcript": text,
            "translation": "stored translation",
            "verified": True,
            "audio": "turn.wav",
        }
        for wav, src, tgt, text in turns
    ]
    (directory / BUNDLE_NAME).write_text(
        json.dumps({"version": BUNDLE_VERSION, "turns": body}), encoding="utf-8"
    )


def expected_of(text: str, lang: str) -> tuple[ExpectedFact, ...]:
    return tuple(
        ExpectedFact(kind=fact.kind, value=fact.value) for fact in extract_facts(text, lang)
    )


def matrix_app(bundle_dir: Path, gnani: GnaniForbidden, manager: RoomManager) -> httpx.AsyncClient:
    settings = public_settings(demo_bundle_dir=bundle_dir, demo_clips_dir=bundle_dir / "clips")
    app = create_app(settings, cast(GnaniClient, gnani), FakeTranslator(), manager)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://saathi")


async def test_run_matrix_reports_recorded_and_text_only_pairs(tmp_path: Path) -> None:
    en_wav, hi_wav = make_wav(0.7), make_wav(0.9)
    write_bundle(tmp_path, [(en_wav, "en", "hi", EN_TEXT), (hi_wav, "hi", "kn", HI_TEXT)])
    clips = [
        MatrixClip("en-street", "en", en_wav, expected_of(EN_TEXT, "en"), frozenset({"hi"})),
        MatrixClip("hi-street", "hi", hi_wav, expected_of(HI_TEXT, "hi"), frozenset({"kn"})),
    ]
    gnani, manager = GnaniForbidden(), RoomManager(max_rooms=1)
    async with matrix_app(tmp_path, gnani, manager) as client:
        runs = await run_matrix(client, manager, clips, ["en", "hi"])
    by_pair = {(run.src, run.tgt): run for run in runs}
    assert [run.problems for run in runs] == [(), ()]
    assert by_pair[("en", "hi")].stored_audio is True
    assert by_pair[("hi", "en")].stored_audio is False
    assert all(run.ms > 0 for run in runs)
    assert gnani.attempts == []


async def test_a_wrong_expectation_fails_its_cell_with_the_chip_difference(tmp_path: Path) -> None:
    en_wav, hi_wav = make_wav(0.7), make_wav(0.9)
    write_bundle(tmp_path, [(en_wav, "en", "hi", EN_TEXT), (hi_wav, "hi", "kn", HI_TEXT)])
    wrong = (ExpectedFact(kind="gate", value="9"),)
    clips = [
        MatrixClip("en-street", "en", en_wav, wrong, frozenset({"hi"})),
        MatrixClip("hi-street", "hi", hi_wav, expected_of(HI_TEXT, "hi"), frozenset({"kn"})),
    ]
    gnani, manager = GnaniForbidden(), RoomManager(max_rooms=1)
    async with matrix_app(tmp_path, gnani, manager) as client:
        runs = await run_matrix(client, manager, clips, ["en", "hi"])
    failed = [run for run in runs if run.problems]
    assert [(run.src, run.tgt) for run in failed] == [("en", "hi")]
    assert "rider chips: gate: expected 9, heard 2" in failed[0].problems


async def test_a_clip_the_bundle_does_not_hold_is_refused_and_never_goes_live(
    tmp_path: Path,
) -> None:
    write_bundle(tmp_path, [(make_wav(0.7), "en", "hi", EN_TEXT)])
    strangers = [
        MatrixClip("en-x", "en", make_wav(1.1), gate_two(), frozenset()),
        MatrixClip("hi-x", "hi", make_wav(1.2), gate_two(), frozenset()),
    ]
    gnani, manager = GnaniForbidden(), RoomManager(max_rooms=1)
    async with matrix_app(tmp_path, gnani, manager) as client:
        runs = await run_matrix(client, manager, strangers, ["en", "hi"])
    assert all("HTTP 422 demo_no_match" in run.problems[0] for run in runs)
    assert gnani.attempts == []


async def test_a_language_with_no_verified_clip_stops_the_run_before_any_replay(
    tmp_path: Path,
) -> None:
    write_bundle(tmp_path, [(make_wav(0.7), "en", "hi", EN_TEXT)])
    clips = [MatrixClip("en-x", "en", make_wav(0.7), gate_two(), frozenset())]
    manager = RoomManager(max_rooms=1)
    async with matrix_app(tmp_path, GnaniForbidden(), manager) as client:
        with pytest.raises(ValueError, match="hi"):
            await run_matrix(client, manager, clips, ["en", "hi"])
