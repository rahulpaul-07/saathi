"""Slice 5: FLORES translation quality (chrF++), per-sentence time and guard signals.

Compares greedy decoding with beam search on every directed pair of the four languages, using
ground-truth FLORES text (no STT), so it measures the translator alone. Makes no Gnani calls.

Usage (laptop on AC power):
  uv run --no-sync python scripts/eval_translation.py              # 12 pairs x 50 sentences
  uv run --no-sync python scripts/eval_translation.py --full       # greedy, whole devtest, the
                                                                   # 4 pairs the app supports
Results: eval/results/translation/<config>_<src>-<tgt>.json (finished shards are skipped, so an
interrupted run resumes). Summarize with scripts/eval_report.py.
"""

import argparse
import itertools
import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from functools import partial
from pathlib import Path

from saathi.evaluation.flores import load_devtest, sample_indices
from saathi.evaluation.power import PowerError, PowerGuard, wait_for_ac
from saathi.evaluation.runinfo import run_metadata
from saathi.evaluation.translation import SentenceRow, evaluate_sentence, summarize
from saathi.languages import EVALUATED_LANGUAGES, EVALUATED_PAIRS
from saathi.translate import IndicTrans2Translator

DATA_DIR = Path("eval/data")
OUT_DIR = Path("eval/results/translation")
WARMUP_RUNS = 3
SAMPLE_SIZE = 50
POWER_WAIT_S = 8 * 3600


def run_shard(
    out_dir: Path,
    translator: IndicTrans2Translator,
    config: str,
    src: str,
    tgt: str,
    indices: list[int],
    beams: int,
    allow_battery: bool,
    corpora: dict[str, list[str]],
) -> None:
    path = out_dir / f"{config}_{src}-{tgt}.json"
    if path.exists():
        print(f"skip {path.name} (done)")
        return
    guard = PowerGuard(allow_battery=allow_battery)
    sources = [corpora[src][i] for i in indices]
    references = [corpora[tgt][i] for i in indices]
    rows: list[SentenceRow] = []
    for i, source, reference in zip(indices, sources, references, strict=True):
        guard.check()
        rows.append(evaluate_sentence(translator, i, source, reference, src, tgt))
    summary = summarize(rows, references)
    payload = {
        "meta": run_metadata(guard.state, num_beams=beams),
        "config": config,
        "src": src,
        "tgt": tgt,
        "summary": asdict(summary),
        "rows": [asdict(row) for row in rows],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"{path.name}: chrF++ {summary.chrf_pp:.1f}, mean {summary.ms_mean:.0f} ms, "
        f"p95 {summary.ms_p95:.0f} ms, flagged {summary.flagged}/{summary.n}"
    )


def run_with_power_retry(shard: Callable[[], None], allow_battery: bool) -> None:
    """Run one shard; if the power state changes mid-shard, wait for AC and redo that shard."""
    while True:
        try:
            shard()
            return
        except PowerError as exc:
            print(f"power problem: {exc}")
            if allow_battery or not wait_for_ac(timeout_s=POWER_WAIT_S):
                raise
            print("AC power is back; redoing this shard from the start")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--beams", type=int, default=5)
    parser.add_argument("--full", action="store_true", help="greedy on all 1012 sentences")
    parser.add_argument("--allow-battery", action="store_true", help="tag results as battery")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="result folder (smoke tests)")
    args = parser.parse_args()
    out_dir: Path = args.out

    if not args.allow_battery:
        print("waiting for AC power if needed (up to 8 h)")
        if not wait_for_ac(timeout_s=POWER_WAIT_S):
            print("still on battery; nothing was run", file=sys.stderr)
            return 2

    corpora = {lang: load_devtest(DATA_DIR, lang) for lang in EVALUATED_LANGUAGES}
    total = len(corpora["bn"])
    jobs: list[tuple[str, int, str, str]]  # (config, beams, src, tgt)
    if args.full:
        indices = list(range(total))
        jobs = []
        for pair in sorted(sorted(p) for p in EVALUATED_PAIRS):
            jobs += [("greedy-full", 1, pair[0], pair[1]), ("greedy-full", 1, pair[1], pair[0])]
    else:
        indices = sample_indices(total, args.count)
        jobs = [
            (config, beams, src, tgt)
            for src, tgt in itertools.permutations(EVALUATED_LANGUAGES, 2)
            for config, beams in (("greedy", 1), (f"beam{args.beams}", args.beams))
        ]

    translators: dict[int, IndicTrans2Translator] = {}
    for _, beams, _, _ in jobs:
        if beams not in translators:
            translator = IndicTrans2Translator(num_beams=beams)
            translator.load()
            for _ in range(WARMUP_RUNS):  # CUDA setup and kernel selection, excluded from timing
                translator.translate(corpora["bn"][0], "bn", "kn")
            translators[beams] = translator

    try:
        for config, beams, src, tgt in jobs:
            run_with_power_retry(
                partial(
                    run_shard,
                    out_dir,
                    translators[beams],
                    config,
                    src,
                    tgt,
                    indices,
                    beams,
                    args.allow_battery,
                    corpora,
                ),
                args.allow_battery,
            )
    except PowerError as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
