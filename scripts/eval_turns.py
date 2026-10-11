"""Slice 5: the Gnani-backed evaluation (spends credits). Run each step by hand, on AC power.

  plan       print the call budget and what has been spent (no calls)
  sentences  write the list of sentences to read aloud for the real-speech set (no calls)
  synth      Gnani TTS of 40 FLORES bn sentences -> eval/audio/synth/   (--limit N to try a few)
  latency    41 full bn->kn turns on those clips; p50/p95 per stage       (80+2 calls)
  stt-real   Gnani STT on your 10 recordings in eval/audio/real/          (10 calls)
  report     combine the result files into eval/results/stt_summary.md   (no calls)

All Gnani calls are counted in eval/state/gnani_ledger.json (global cap in calls.py) and paced
to at most 3 calls per 10 s. The audio in `synth` is Gnani TTS fed to Gnani STT: clean synthetic
audio, an optimistic best case. `stt-real` is the honest set: your voice on the laptop microphone.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import Any

from saathi.config import get_settings
from saathi.evaluation.calls import (
    GNANI_CALL_CAP,
    LATENCY_TURNS,
    PLANNED_CALLS,
    REAL_CLIPS,
    SYNTH_CLIPS,
    CallLedger,
    MeteredGnani,
    SlidingWindowLimiter,
    planned_total,
)
from saathi.evaluation.flores import load_devtest, sample_indices
from saathi.evaluation.metrics import chrf_pp, percentile
from saathi.evaluation.power import PowerError, PowerGuard
from saathi.evaluation.runinfo import run_metadata
from saathi.evaluation.stt import SttRow, score_transcript, summarize_stt
from saathi.evaluation.turns import call_with_retry, measure_turn, summarize_latency
from saathi.evaluation.wavtools import RecordingError, check_recording, resample_to_16k
from saathi.gnani import GnaniError
from saathi.languages import LANGUAGES
from saathi.translate import IndicTrans2Translator

SRC, TGT = "bn", "kn"
DATA_DIR = Path("eval/data")
SYNTH_DIR = Path("eval/audio/synth")
REAL_DIR = Path("eval/audio/real")
RESULTS_DIR = Path("eval/results")
LEDGER_PATH = Path("eval/state/gnani_ledger.json")
SENTENCES_FILE = REAL_DIR / "sentences.txt"
LATENCY_FILE = RESULTS_DIR / "turns_latency.json"
REAL_FILE = RESULTS_DIR / "turns_real_stt.json"
SUMMARY_FILE = RESULTS_DIR / "stt_summary.md"
WARMUP_TRANSLATIONS = 3
CLEAN_LABEL = "clean synthetic audio (Gnani TTS fed to Gnani STT)"


def synth_indices() -> list[int]:
    return sample_indices(1012, 50)[:SYNTH_CLIPS]


def real_indices() -> list[int]:
    """Every 4th synth sentence, so each recording has a clean-synthetic twin to compare with."""
    return synth_indices()[::4][:REAL_CLIPS]


def clip_path(folder: Path, index: int) -> Path:
    return folder / f"{SRC}_{index:04d}.wav"


def new_translator(beams: int) -> IndicTrans2Translator:
    translator = IndicTrans2Translator(num_beams=beams)
    translator.load()
    for _ in range(WARMUP_TRANSLATIONS):
        translator.translate(load_devtest(DATA_DIR, SRC)[0], SRC, TGT)
    return translator


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {path}")


def cmd_plan() -> int:
    ledger = CallLedger(LEDGER_PATH)
    print("Gnani calls planned (expected):")
    for name, calls in PLANNED_CALLS.items():
        print(f"  {name:9} {calls:4}  (spent so far: {ledger.spent(name)})")
    print(f"  total     {planned_total():4}  cap {GNANI_CALL_CAP}, spent {ledger.total}")
    print(f"  retry reserve {GNANI_CALL_CAP - planned_total()} calls (429s are retried, counted)")
    print("  pacing: at most 3 calls in any 10 s; a turn reserves both of its calls up front")
    print(f"  latency = {LATENCY_TURNS} turns (the first is a discarded warm-up) x 2 calls")
    return 0


def cmd_sentences() -> int:
    corpus = load_devtest(DATA_DIR, SRC)
    REAL_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"{clip_path(REAL_DIR, i).name}\t{corpus[i]}" for i in real_indices()]
    SENTENCES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {SENTENCES_FILE}: read each sentence aloud once, naturally, in a quiet room,")
    print("and save it as 16 kHz mono WAV under the file name on its line (see docs/EVAL.md)")
    return 0


async def cmd_synth(limit: int) -> int:
    corpus = load_devtest(DATA_DIR, SRC)
    ledger = CallLedger(LEDGER_PATH)
    gnani = MeteredGnani(get_settings(), ledger, "synth")
    limiter = SlidingWindowLimiter()
    language = LANGUAGES[SRC]
    SYNTH_DIR.mkdir(parents=True, exist_ok=True)
    made = 0
    try:
        for index in synth_indices()[:limit]:
            path = clip_path(SYNTH_DIR, index)
            if path.exists():
                continue
            audio, retries = await call_with_retry(
                partial(gnani.synthesize, corpus[index], language.gnani_code, language.tts_voice),
                limiter,
            )
            path.write_bytes(resample_to_16k(audio))
            made += 1
            print(f"{path.name}: {len(audio)} bytes, retries {retries}")
    finally:
        await gnani.aclose()
    print(f"made {made} clips; ledger total {ledger.total}/{GNANI_CALL_CAP}")
    return 0


def translate_gold(translator: IndicTrans2Translator, indices: list[int]) -> list[str]:
    """Translate the ground-truth source text: the translator's quality with no STT in front."""
    corpus = load_devtest(DATA_DIR, SRC)
    return [translator.translate(corpus[i], SRC, TGT) for i in indices]


def translation_scores(
    translator: IndicTrans2Translator, rows: list[SttRow], translations: dict[int, str]
) -> dict[str, Any]:
    """chrF++ against the kn reference: translating the transcript vs the ground-truth text."""
    kn = load_devtest(DATA_DIR, TGT)
    indices = [row.index for row in rows if row.index in translations]
    if not indices:
        return {"n": 0}
    gold = translate_gold(translator, indices)
    references = [kn[i] for i in indices]
    return {
        "n": len(indices),
        "from_transcript_chrf_pp": chrf_pp([translations[i] for i in indices], references),
        "from_ground_truth_chrf_pp": chrf_pp(gold, references),
    }


def translate_transcripts(translator: IndicTrans2Translator, rows: list[SttRow]) -> dict[int, str]:
    out: dict[int, str] = {}
    for row in rows:
        result = translator.translate_with_stats(row.transcript, SRC, TGT)
        if not result.capped:
            out[row.index] = result.text
    return out


async def cmd_latency(beams: int, allow_battery: bool) -> int:
    indices = synth_indices()
    missing = [
        clip_path(SYNTH_DIR, i).name for i in indices if not clip_path(SYNTH_DIR, i).exists()
    ]
    if missing:
        print(f"missing {len(missing)} synth clips (run `synth` first): {missing[:3]} ...")
        return 1
    guard = PowerGuard(allow_battery=allow_battery)
    translator = new_translator(beams)
    ledger = CallLedger(LEDGER_PATH)
    gnani = MeteredGnani(get_settings(), ledger, "latency")
    limiter = SlidingWindowLimiter()
    corpus = load_devtest(DATA_DIR, SRC)
    turns: list[dict[str, Any]] = []
    try:
        for position, index in enumerate([indices[0], *indices]):  # first turn is the warm-up
            guard.check()
            audio = clip_path(SYNTH_DIR, index).read_bytes()
            outcome = await measure_turn(audio, SRC, TGT, gnani, translator, limiter)
            warmup = position == 0
            turns.append({"index": index, "warmup": warmup, **asdict(outcome)})
            state = outcome.failure or ("retried" if outcome.retries else "ok")
            print(f"turn {position}/{LATENCY_TURNS - 1} #{index}: {state}")
    finally:
        await gnani.aclose()

    measured = [t for t in turns if not t["warmup"]]
    clean = [t["timings"] for t in measured if t["timings"]]
    from saathi.pipeline import Timings

    latency = summarize_latency([Timings(**t) for t in clean]) if clean else {}
    rows = [
        score_transcript(t["index"], t["transcript"], corpus[t["index"]])
        for t in measured
        if t["transcript"] is not None
    ]
    translations = {t["index"]: t["translation"] for t in measured if t["translation"] is not None}
    write_json(
        LATENCY_FILE,
        {
            "meta": run_metadata(guard.state, num_beams=beams),
            "audio": CLEAN_LABEL,
            "turns_measured": len(measured),
            "latency_samples": len(clean),
            "rate_limited_retries": sum(t["retries"] for t in measured),
            "failures": [
                {"index": t["index"], "reason": t["failure"]} for t in measured if t["failure"]
            ],
            "latency": {stage: asdict(stats) for stage, stats in latency.items()},
            "stt": asdict(summarize_stt(rows, [corpus[r.index] for r in rows])) if rows else {},
            "stt_rows": [asdict(r) for r in rows],
            "translation": translation_scores(translator, rows, translations),
            "calls_spent": ledger.spent("latency"),
        },
    )
    return 0


async def cmd_stt_real(allow_battery: bool, beams: int) -> int:
    indices = real_indices()
    problems: list[str] = []
    for index in indices:  # validate every file before the first paid call
        path = clip_path(REAL_DIR, index)
        try:
            check_recording(path.read_bytes())
        except (OSError, RecordingError) as exc:
            problems.append(f"{path.name}: {exc}")
    if problems:
        print("fix these recordings first (nothing was sent):\n  " + "\n  ".join(problems))
        return 1
    guard = PowerGuard(allow_battery=allow_battery)
    corpus = load_devtest(DATA_DIR, SRC)
    ledger = CallLedger(LEDGER_PATH)
    gnani = MeteredGnani(get_settings(), ledger, "stt-real")
    limiter = SlidingWindowLimiter()
    rows: list[SttRow] = []
    call_ms: list[float] = []
    retries_total = 0
    try:
        for index in indices:
            guard.check()
            audio = clip_path(REAL_DIR, index).read_bytes()
            start = time.perf_counter()
            transcript, retries = await call_with_retry(
                partial(gnani.transcribe, audio, "turn.wav", LANGUAGES[SRC].gnani_code), limiter
            )
            if retries == 0:
                call_ms.append((time.perf_counter() - start) * 1000)
            retries_total += retries
            rows.append(score_transcript(index, transcript.strip(), corpus[index]))
            print(f"#{index}: CER {rows[-1].cer:.2f}, head missed {rows[-1].head_missed}")
    except GnaniError as exc:
        print(f"stopped by Gnani error {exc.status}; {len(rows)} clips done, nothing saved")
        return 1
    finally:
        await gnani.aclose()
    translator = new_translator(beams)
    write_json(
        REAL_FILE,
        {
            "meta": run_metadata(guard.state, num_beams=beams),
            "audio": "real speech: the author's own voice on the laptop microphone",
            "rate_limited_retries": retries_total,
            "stt_ms_p50": percentile(call_ms, 50) if call_ms else None,
            "stt_ms_p95": percentile(call_ms, 95) if call_ms else None,
            "stt": asdict(summarize_stt(rows, [corpus[r.index] for r in rows])),
            "stt_rows": [asdict(r) for r in rows],
            "translation": translation_scores(
                translator, rows, translate_transcripts(translator, rows)
            ),
            "calls_spent": ledger.spent("stt-real"),
        },
    )
    return 0


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def cmd_report() -> int:
    if not LATENCY_FILE.exists() and not REAL_FILE.exists():
        print("no result files yet")
        return 1
    parts = ["# STT and latency results (generated by scripts/eval_turns.py report)\n"]
    clean: dict[str, Any] = (
        json.loads(LATENCY_FILE.read_text("utf-8")) if LATENCY_FILE.exists() else {}
    )
    real: dict[str, Any] = json.loads(REAL_FILE.read_text("utf-8")) if REAL_FILE.exists() else {}
    if clean:
        meta = clean["meta"]
        parts.append(
            f"## Turn latency, bn->kn, {CLEAN_LABEL}\n\n"
            f"Power: {meta['power_state']}, beams: {meta['num_beams']}, device: {meta['device']}, "
            f"commit {meta['git_commit']}. {clean['latency_samples']} clean turns "
            f"({clean['rate_limited_retries']} rate-limited retries excluded, "
            f"{len(clean['failures'])} failed turns).\n"
        )
        parts.append("| stage | p50 ms | p95 ms | mean ms | max ms |\n|---|---|---|---|---|")
        for stage, s in clean["latency"].items():
            parts.append(
                f"| {stage} | {s['p50']:.0f} | {s['p95']:.0f} | {s['mean']:.0f} | {s['max']:.0f} |"
            )
        parts.append("")
    if real and real.get("stt_ms_p50") is not None:
        parts.append(
            f"STT call alone on real speech: p50 {real['stt_ms_p50']:.0f} ms, "
            f"p95 {real['stt_ms_p95']:.0f} ms (n={real['stt']['n']}).\n"
        )
    sets = {CLEAN_LABEL: clean, "real speech (own voice)": real}
    parts.append("## STT accuracy against the known text\n")
    parts.append(
        "Text normalized (NFC, punctuation stripped, case folded) before CER and chrF++.\n"
    )
    parts.append(
        "| audio | n | CER mean | CER median | chrF++ | first-2-word miss | later-word miss |\n"
        "|---|---|---|---|---|---|---|"
    )
    for label, data in sets.items():
        if data.get("stt"):
            s = data["stt"]
            parts.append(
                f"| {label} | {s['n']} | {s['cer_mean']:.3f} | {s['cer_median']:.3f} "
                f"| {s['chrf_pp']:.1f} "
                f"| {_pct(s['head_rate'])} ({s['head_missed']}/{s['head_words']}) "
                f"| {_pct(s['tail_rate'])} ({s['tail_missed']}/{s['tail_words']}) |"
            )
    if clean.get("stt_rows") and real.get("stt_rows"):
        shared = {r["index"] for r in real["stt_rows"]}
        twins = [r for r in clean["stt_rows"] if r["index"] in shared]
        head_w = sum(r["head_words"] for r in twins)
        tail_w = sum(r["tail_words"] for r in twins)
        parts.append(
            f"\nClean synthetic twins of the {len(twins)} recorded sentences: "
            f"CER mean {statistics.fmean(r['cer'] for r in twins):.3f}, "
            f"first-2-word miss {_pct(sum(r['head_missed'] for r in twins) / head_w)}, "
            f"later-word miss {_pct(sum(r['tail_missed'] for r in twins) / tail_w)}.\n"
        )
    parts.append("## Translation quality: from the transcript vs from the ground-truth text\n")
    parts.append("chrF++ against the kn reference, same translator, same sentences.\n")
    parts.append("| audio | n | from transcript | from ground truth |\n|---|---|---|---|")
    for label, data in sets.items():
        t = data.get("translation")
        if t and t["n"]:
            parts.append(
                f"| {label} | {t['n']} | {t['from_transcript_chrf_pp']:.1f} "
                f"| {t['from_ground_truth_chrf_pp']:.1f} |"
            )
    SUMMARY_FILE.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"wrote {SUMMARY_FILE}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "command", choices=["plan", "sentences", "synth", "latency", "stt-real", "report"]
    )
    parser.add_argument("--limit", type=int, default=SYNTH_CLIPS, help="synth: clips to make")
    parser.add_argument("--beams", type=int, default=None, help="default: TRANSLATOR_NUM_BEAMS")
    parser.add_argument("--allow-battery", action="store_true", help="run, tagged as battery")
    args = parser.parse_args()
    try:
        match args.command:
            case "plan":
                return cmd_plan()
            case "sentences":
                return cmd_sentences()
            case "report":
                return cmd_report()
        beams = args.beams or get_settings().translator_num_beams
        match args.command:
            case "synth":
                return asyncio.run(cmd_synth(args.limit))
            case "latency":
                return asyncio.run(cmd_latency(beams, args.allow_battery))
            case _:
                return asyncio.run(cmd_stt_real(args.allow_battery, beams))
    except PowerError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except GnaniError as exc:
        print(f"Gnani error {exc.status}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
