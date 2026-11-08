"""Stored rider voices: what is missing, the resumable build, and the lookup replay that follows.
Gnani and the translator are fakes here; no network, no key, no model."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from saathi.demobundle import (
    BUNDLE_NAME,
    BUNDLE_VERSION,
    DemoBundle,
    StoredFact,
    clip_digest,
    load_bundle,
)
from saathi.evaluation.calls import BudgetExceededError
from saathi.evaluation.demoset import read_turns
from saathi.evaluation.rider_voices import (
    MIN_GAP_S,
    PROGRESS_NAME,
    Pair,
    attach_missing_facts,
    build_voices,
    load_progress,
    missing_pairs,
    new_turns_per_language,
    picker_pairs,
    turns_without_facts,
)
from saathi.facts import extract_facts
from saathi.gnani import GnaniError
from saathi.languages import LANGUAGES
from test_room_api import FakeTranslator
from wavs import make_wav

TRANSCRIPT = "gate number 2 near the blue temple"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_rider_voices.py"
OTHER_LANGUAGES = len(LANGUAGES) - 1


class CountingTranslator(FakeTranslator):
    def __init__(self) -> None:
        self.calls = 0

    def translate(self, text: str, src: str, tgt: str) -> str:
        self.calls += 1
        return super().translate(text, src, tgt)


class ForbiddenTranslator:
    """Any use at all is a test failure: a stored turn is served without translating anything."""

    def translate(self, text: str, src: str, tgt: str) -> str:
        raise AssertionError("the translator was used")


class FakeSpeech:
    """Records every request. `fail` names 1-based call numbers that raise a Gnani error and
    `stop_at` the one that raises the ledger's budget error."""

    def __init__(self, fail: tuple[int, ...] = (), stop_at: int | None = None) -> None:
        self.requests: list[tuple[str, str, str]] = []
        self._fail = fail
        self._stop_at = stop_at

    async def synthesize(self, text: str, language_code: str, voice: str) -> bytes:
        self.requests.append((text, language_code, voice))
        number = len(self.requests)
        if number == self._stop_at:
            raise BudgetExceededError("cap")
        if number in self._fail:
            raise GnaniError("speech service error 429", 429)
        return make_wav(0.1 + number / 1000)


def _quiet(_: str) -> None:
    """The build's progress lines are not under test."""


def _write_bundle(bundle_dir: Path, turns: list[dict[str, object]]) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    body = {"version": BUNDLE_VERSION, "turns": turns}
    (bundle_dir / BUNDLE_NAME).write_text(json.dumps(body), encoding="utf-8")


def _old_turn(sha: str, src: str, tgt: str, bundle_dir: Path) -> dict[str, object]:
    name = f"old-{src}-{tgt}.wav"
    (bundle_dir / name).parent.mkdir(parents=True, exist_ok=True)
    (bundle_dir / name).write_bytes(make_wav(0.2))
    return {
        "clip_sha256": sha,
        "src": src,
        "tgt": tgt,
        "transcript": TRANSCRIPT,
        "translation": "old translation",
        "verified": True,
        "audio": name,
    }


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    """Two picker clips (en and hi) and one earlier stored turn for each, stored without facts."""
    clips, bundle = tmp_path / "clips", tmp_path / "bundle"
    clips.mkdir()
    listed = []
    turns = []
    for clip_id, lang, seconds, tgt in (("a", "en", 0.5, "kn"), ("b", "hi", 0.6, "en")):
        wav = make_wav(seconds)
        (clips / f"{clip_id}.wav").write_bytes(wav)
        listed.append({"id": clip_id, "lang": lang, "label": clip_id, "label_local": ""})
        bundle.mkdir(exist_ok=True)
        turns.append(_old_turn(clip_digest(wav), lang, tgt, bundle))
    (clips / "manifest.json").write_text(json.dumps({"clips": listed}), encoding="utf-8")
    _write_bundle(bundle, turns)
    return clips, bundle


def _missing(clips: Path, bundle: Path) -> list[Pair]:
    return missing_pairs(picker_pairs(clips, bundle), bundle)


def test_every_picker_clip_wants_every_other_rider_language(tmp_path: Path) -> None:
    clips, bundle = _setup(tmp_path)
    pairs = picker_pairs(clips, bundle)
    assert len(pairs) == 2 * OTHER_LANGUAGES
    assert all(pair.src != pair.tgt for pair in pairs)


def test_a_pair_with_stored_audio_is_not_planned_and_one_without_its_file_is(
    tmp_path: Path,
) -> None:
    clips, bundle = _setup(tmp_path)
    assert len(_missing(clips, bundle)) == 2 * OTHER_LANGUAGES - 2
    (bundle / "old-en-kn.wav").unlink()  # the turn is listed but its audio is gone
    missing = _missing(clips, bundle)
    assert ("a", "kn") in {(p.clip_id, p.tgt) for p in missing}


def test_turns_to_add_are_counted_per_rider_language(tmp_path: Path) -> None:
    clips, bundle = _setup(tmp_path)
    counts = new_turns_per_language(_missing(clips, bundle))
    assert set(counts) == set(LANGUAGES)
    assert sum(counts.values()) == 2 * OTHER_LANGUAGES - 2
    assert counts["kn"] == 1  # clip b only: clip a already has kn
    assert counts["en"] == 0  # clip a is English and clip b already has en


async def test_the_build_stores_text_facts_verified_flag_and_audio_of_that_exact_text(
    tmp_path: Path,
) -> None:
    clips, bundle = _setup(tmp_path)
    gnani = FakeSpeech()
    report = await build_voices(
        _missing(clips, bundle), bundle, gnani, FakeTranslator(), say=_quiet
    )
    turns = read_turns(bundle)

    assert len(report.stored) == len(gnani.requests) == 2 * OTHER_LANGUAGES - 2
    assert not report.failed
    assert len(turns) == 2 * OTHER_LANGUAGES
    assert _missing(clips, bundle) == []
    new = [t for t in turns if not t.audio.startswith("old-")]
    spoken = {request[0] for request in gnani.requests}
    for turn in new:
        assert turn.facts is not None and (bundle / turn.audio).read_bytes().startswith(b"RIFF")
        assert turn.translation in spoken
    codes = {LANGUAGES[t.tgt].gnani_code for t in new}
    assert {request[1] for request in gnani.requests} == codes


async def test_older_turns_get_their_facts_with_no_call_and_keep_their_text_and_audio(
    tmp_path: Path,
) -> None:
    clips, bundle = _setup(tmp_path)
    assert turns_without_facts(bundle) == 2
    assert attach_missing_facts(bundle, FakeTranslator()) == 2
    older = read_turns(bundle)
    assert turns_without_facts(bundle) == 0
    assert [t.translation for t in older] == ["old translation"] * 2
    assert all((bundle / t.audio).is_file() for t in older)
    assert attach_missing_facts(bundle, ForbiddenTranslator()) == 0  # nothing left to do


async def test_a_failed_call_is_recorded_not_retried_and_the_run_goes_on(tmp_path: Path) -> None:
    clips, bundle = _setup(tmp_path)
    gnani = FakeSpeech(fail=(3,))
    report = await build_voices(
        _missing(clips, bundle), bundle, gnani, FakeTranslator(), say=_quiet
    )

    assert len(gnani.requests) == 2 * OTHER_LANGUAGES - 2  # one request per pair, none repeated
    assert list(report.failed.values()) == ["gnani status 429"]
    assert len(report.stored) == len(gnani.requests) - 1
    assert load_progress(bundle).failures == report.failed


async def test_a_failed_pair_waits_for_retry_failed_and_keeps_its_first_translation(
    tmp_path: Path,
) -> None:
    clips, bundle = _setup(tmp_path)
    translator = CountingTranslator()
    first = FakeSpeech(fail=(1,))
    await build_voices(_missing(clips, bundle), bundle, first, translator, say=_quiet)
    translated = translator.calls
    failed_text = first.requests[0][0]

    skipped = FakeSpeech()
    held = await build_voices(_missing(clips, bundle), bundle, skipped, translator, say=_quiet)
    assert skipped.requests == [] and len(held.skipped) == 1

    retry = FakeSpeech()
    await build_voices(
        _missing(clips, bundle), bundle, retry, translator, retry_failed=True, say=_quiet
    )
    assert [request[0] for request in retry.requests] == [failed_text]
    assert translator.calls == translated  # translated once, not again
    assert _missing(clips, bundle) == []
    assert load_progress(bundle).failures == {}


async def test_a_stopped_run_resumes_without_paying_for_a_stored_pair_twice(
    tmp_path: Path,
) -> None:
    clips, bundle = _setup(tmp_path)
    total = 2 * OTHER_LANGUAGES - 2
    with pytest.raises(BudgetExceededError):
        await build_voices(
            _missing(clips, bundle), bundle, FakeSpeech(stop_at=5), FakeTranslator(), say=_quiet
        )
    assert len(_missing(clips, bundle)) == total - 4  # four pairs were stored before the stop

    resumed = FakeSpeech()
    await build_voices(_missing(clips, bundle), bundle, resumed, FakeTranslator(), say=_quiet)
    assert len(resumed.requests) == total - 4
    assert _missing(clips, bundle) == []


async def test_a_translation_that_comes_back_empty_is_a_failure_without_a_call(
    tmp_path: Path,
) -> None:
    class EmptyTranslator:
        def translate(self, text: str, src: str, tgt: str) -> str:
            return ""

    clips, bundle = _setup(tmp_path)
    gnani = FakeSpeech()
    # No facts in the text, so nothing can stand in for the empty translation.
    pair = Pair("a", clip_digest(b"x"), "en", "bn", "hello there")
    report = await build_voices([pair], bundle, gnani, EmptyTranslator(), say=_quiet)
    assert gnani.requests == [] and list(report.failed.values()) == ["EmptyTranslationError"]


def test_a_stored_fact_round_trips_exactly() -> None:
    for fact in extract_facts(TRANSCRIPT, "en"):
        assert StoredFact.of(fact).to_fact() == fact


async def test_a_complete_stored_turn_is_served_without_translating_or_localising(
    tmp_path: Path,
) -> None:
    clips, bundle = _setup(tmp_path)
    await build_voices(_missing(clips, bundle), bundle, FakeSpeech(), FakeTranslator(), say=_quiet)
    loaded = load_bundle(bundle)
    assert isinstance(loaded, DemoBundle)
    clip = (clips / "a.wav").read_bytes()

    result = await loaded.replay(clip, "en", "ta", ForbiddenTranslator())  # would raise if used

    stored = next(t for t in read_turns(bundle) if (t.src, t.tgt) == ("en", "ta"))
    assert result.translation == stored.translation
    assert result.facts == tuple(f.to_fact() for f in (stored.facts or []))
    assert result.audio == (bundle / stored.audio).read_bytes()


async def test_a_pair_that_is_still_missing_falls_back_to_the_local_path(tmp_path: Path) -> None:
    clips, bundle = _setup(tmp_path)
    loaded = load_bundle(bundle)
    assert loaded is not None
    translator = CountingTranslator()

    result = await loaded.replay((clips / "a.wav").read_bytes(), "en", "ta", translator)

    assert translator.calls > 0 and result.audio == b""


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_rider_voices", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clips: Path, bundle: Path, *args: str
) -> int:
    argv = [
        "build_rider_voices.py",
        "--clips-dir",
        str(clips),
        "--out-dir",
        str(bundle),
        "--ledger",
        str(tmp_path / "ledger.json"),
        *args,
    ]
    monkeypatch.setattr(sys, "argv", argv)
    return int(_load_script().main())


def test_dry_run_prints_the_plan_and_sends_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clips, bundle = _setup(tmp_path)
    before = (bundle / BUNDLE_NAME).read_bytes()

    status = _run_script(monkeypatch, tmp_path, clips, bundle, "--dry-run")

    out = capsys.readouterr().out
    planned = 2 * OTHER_LANGUAGES - 2
    assert status == 0
    assert f"calls planned: {planned} " in out
    assert f"ledger 0/1500 -> {planned}" in out
    assert "  kn: 1" in out and f"{MIN_GAP_S} s" in out
    assert (bundle / BUNDLE_NAME).read_bytes() == before
    assert not (tmp_path / "ledger.json").exists() and not (bundle / PROGRESS_NAME).exists()


def test_a_plan_over_the_budget_is_refused_before_anything_is_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clips, bundle = _setup(tmp_path)

    status = _run_script(monkeypatch, tmp_path, clips, bundle, "--run", "--budget", "5")

    assert status == 2 and "REFUSED" in capsys.readouterr().out
    assert not (tmp_path / "ledger.json").exists()


def test_the_budget_cannot_be_raised_past_the_hard_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clips, bundle = _setup(tmp_path)
    assert _run_script(monkeypatch, tmp_path, clips, bundle, "--dry-run", "--budget", "291") == 1
