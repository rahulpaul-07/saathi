"""Gold A/B of plain, current masking and conditional masking, scored by two extractors. Local only.

  uv run --no-sync python scripts/eval_masking_modes.py [--targets bn hi kn en] [--limit N]
      [--out eval/results/masking_modes.json]

Same method as scripts/eval_masking.py (translate the gold text, run the target-language extractor
on the output, score against the gold structured facts, landmarks excluded). Each pair is
translated once per arm and every output is scored twice, with the current English extractor and
with the one from before 2026-11-01 (scripts/legacy_extractor.py), so the rescoring effect and the
masking effect are separate. Arms: A plain; B current masking; B_cond conditional masking; C and
C_cond add the fact-summary fallback when the masked text failed its slot check. No Gnani calls.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_masking import GOLD, _structured  # noqa: E402, I001
from legacy_extractor import legacy_english  # noqa: E402
from saathi.evaluation.factscore import load_gold, score_transcript, select  # noqa: E402
from saathi.evaluation.runinfo import git_commit  # noqa: E402
from saathi.facts import extract_facts  # noqa: E402
from saathi.languages import LANGUAGES  # noqa: E402
from saathi.masking import translate_masked  # noqa: E402
from saathi.summary import fact_summary  # noqa: E402
from saathi.translate import DegenerateTranslationError, RoutingTranslator, TranslationInputError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "eval" / "state" / "masking_modes.json"
ARMS = ("A_plain", "B_current", "B_conditional", "C_current", "C_conditional")
SCORERS = ("new", "legacy")


def save_state(
    tally: dict[str, dict[str, defaultdict[str, float]]],
    unverified: dict[str, int],
    pairs: int,
    done: set[str],
) -> None:
    """Checkpoint after every pair: a full run takes hours and the machine may be needed."""
    STATE.parent.mkdir(parents=True, exist_ok=True)
    body = {"tally": tally, "unverified": unverified, "pairs": pairs, "done": sorted(done)}
    STATE.write_text(json.dumps(body), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--targets", nargs="+", default=["bn", "hi", "kn", "en"])
    parser.add_argument(
        "--out", type=Path, default=ROOT / "eval" / "results" / "masking_modes.json"
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--fresh", action="store_true", help="ignore the saved state")
    args = parser.parse_args()
    if any(tgt not in LANGUAGES for tgt in args.targets):
        print("unknown language", file=sys.stderr)
        return 2

    translator = RoutingTranslator()
    utterances = select(load_gold(GOLD), "all")[: args.limit]
    tally: dict[str, dict[str, defaultdict[str, float]]] = {
        scorer: {arm: defaultdict(float) for arm in ARMS} for scorer in SCORERS
    }
    unverified = {"current": 0, "conditional": 0}
    pairs = 0
    done: set[str] = set()
    if STATE.exists() and not args.fresh:
        saved = json.loads(STATE.read_text(encoding="utf-8"))
        for scorer in SCORERS:
            for arm in ARMS:
                tally[scorer][arm].update(saved["tally"][scorer][arm])
        unverified = saved["unverified"]
        pairs = saved["pairs"]
        done = set(saved["done"])
        print(f"resuming after {pairs} pairs")
    for utterance in utterances:
        facts = tuple(extract_facts(utterance.text, utterance.lang))
        for tgt in args.targets:
            if tgt == utterance.lang or f"{utterance.id}>{tgt}" in done:
                continue
            try:
                plain = translator.translate(utterance.text, utterance.lang, tgt)
                current = translate_masked(translator, utterance.text, utterance.lang, tgt, facts)
                cond = translate_masked(
                    translator, utterance.text, utterance.lang, tgt, facts, "conditional"
                )
            except (DegenerateTranslationError, TranslationInputError) as error:
                print(f"{utterance.id} {utterance.lang}->{tgt}: {type(error).__name__}")
                continue
            pairs += 1
            summary = fact_summary(facts, tgt) or plain
            unverified["current"] += not current.verified
            unverified["conditional"] += not cond.verified
            outputs = {
                "A_plain": plain,
                "B_current": current.text,
                "B_conditional": cond.text,
                "C_current": current.text if current.verified else summary,
                "C_conditional": cond.text if cond.verified else summary,
            }
            gold = _structured(utterance, tgt)
            for scorer in SCORERS:
                for arm, text in outputs.items():
                    if scorer == "legacy":
                        with legacy_english():
                            report = score_transcript(gold, text)
                    else:
                        report = score_transcript(gold, text)
                    t = tally[scorer][arm]
                    for kind in report.by_kind.values():
                        t["tp"] += kind.tp
                        t["fp"] += kind.fp
                        t["fn"] += kind.fn
                    t["all_correct"] += report.all_correct
                    t["n"] += 1
            done.add(f"{utterance.id}>{tgt}")
            save_state(tally, unverified, pairs, done)
            print(f"{pairs} {utterance.id} {utterance.lang}->{tgt}", flush=True)

    rows: dict[str, Any] = {}
    for scorer in SCORERS:
        rows[scorer] = {}
        for arm in ARMS:
            t = tally[scorer][arm]
            found = t["tp"] + t["fn"]
            rows[scorer][arm] = {
                "recall": round(t["tp"] / found, 3) if found else None,
                "wrong_extras": int(t["fp"]),
                "all_correct": f"{int(t['all_correct'])}/{int(t['n'])}",
            }
    result = {
        "commit": git_commit(),
        "split": "all",
        "targets": args.targets,
        "pairs": pairs,
        "unverified": {k: f"{v}/{pairs}" for k, v in unverified.items()},
        "scorers": {"new": "extractor as of 2026-11-01", "legacy": "extractor before it"},
        "arms": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for scorer in SCORERS:
        for arm in ARMS:
            print(f"{scorer:<7}{arm:<16}{rows[scorer][arm]}")
    print(f"unverified: {result['unverified']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
