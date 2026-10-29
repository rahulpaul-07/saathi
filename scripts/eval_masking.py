"""Text A/B of the three translation arms on the synthetic gold set. Offline, GPU, no Gnani calls.

  uv run --no-sync python scripts/eval_masking.py [--split dev|test|all] [--targets bn hi kn en]
      [--out eval/results/masking_ab.json] [--limit N]

Arms: A toolkit default (plain translation), B masked (numbers and loanwords restored from tables,
the model text is kept even when a slot was lost), C masked with the fact-summary fallback (what
the app speaks). For each arm the extractor is run on the translated text in the target language
and scored against the gold structured facts (landmarks excluded: they are open vocabulary).
The gold text is used only as translation input, so the extractor is never tuned on this output.
Landmark renderings are listed for human review, not scored.
"""

import argparse
import dataclasses
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from saathi.evaluation.factscore import GoldUtterance, load_gold, score_transcript, select
from saathi.facts import extract_facts
from saathi.facts.text import key, tokenize
from saathi.landmarks import localize_landmarks
from saathi.languages import LANGUAGES
from saathi.loanwords import concept_of, written
from saathi.masking import translate_masked
from saathi.summary import fact_summary
from saathi.translate import DegenerateTranslationError, RoutingTranslator, TranslationInputError

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "eval" / "gold" / "directions.json"
ARMS = ("A_default", "B_masked", "C_masked_summary")


def _concepts(text: str, lang: str) -> set[str]:
    found = (concept_of(token.key, lang) for token in tokenize(text))
    return {concept for concept in found if concept is not None}


def _structured(gold: GoldUtterance, tgt: str) -> GoldUtterance:
    facts = tuple(fact for fact in gold.facts if fact.kind != "landmark")
    return dataclasses.replace(gold, lang=tgt, facts=facts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--split", choices=["dev", "test", "all"], default="all")
    parser.add_argument("--targets", nargs="+", default=["bn", "hi", "kn", "en"])
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "results" / "masking_ab.json")
    parser.add_argument("--limit", type=int, default=None, help="first N utterances (smoke run)")
    args = parser.parse_args()
    for tgt in args.targets:
        if tgt not in LANGUAGES:
            print(f"unknown language {tgt!r}", file=sys.stderr)
            return 2

    translator = RoutingTranslator()
    utterances = select(load_gold(GOLD), args.split)[: args.limit]
    totals: dict[str, defaultdict[str, float]] = {arm: defaultdict(float) for arm in ARMS}
    unverified = pairs = 0
    seconds = {"plain": 0.0, "masked": 0.0}
    landmarks: list[dict[str, Any]] = []
    for utterance in utterances:
        facts = tuple(extract_facts(utterance.text, utterance.lang))
        wanted = _concepts(utterance.text, utterance.lang)
        for tgt in args.targets:
            if tgt == utterance.lang:
                continue
            pairs += 1
            try:
                started = time.perf_counter()
                plain = translator.translate(utterance.text, utterance.lang, tgt)
                seconds["plain"] += time.perf_counter() - started
                started = time.perf_counter()
                masked = translate_masked(translator, utterance.text, utterance.lang, tgt, facts)
                seconds["masked"] += time.perf_counter() - started
            except (DegenerateTranslationError, TranslationInputError) as error:
                print(f"{utterance.id} {utterance.lang}->{tgt}: {type(error).__name__}")
                continue
            summary = fact_summary(facts, tgt)
            outputs = {
                "A_default": plain,
                "B_masked": masked.text,
                "C_masked_summary": masked.text if masked.verified else (summary or plain),
            }
            unverified += not masked.verified
            for arm, text in outputs.items():
                report = score_transcript(_structured(utterance, tgt), text)
                tally = totals[arm]
                for kind_score in report.by_kind.values():
                    tally["tp"] += kind_score.tp
                    tally["fp"] += kind_score.fp
                    tally["fn"] += kind_score.fn
                tally["all_correct"] += report.all_correct
                tally["utterances"] += 1
                present = {key(word) for word in text.split()}
                tally["loanwords_wanted"] += len(wanted)
                tally["loanwords_kept"] += sum(key(written(c, tgt)) in present for c in wanted)
            for fact in localize_landmarks(facts, utterance.lang, tgt, translator):
                if fact.kind == "landmark":
                    landmarks.append(
                        {"id": utterance.id, "src": utterance.lang, "tgt": tgt,
                         "value": fact.value, "local": fact.local}
                    )

    summary_rows = {}
    for arm in ARMS:
        t = totals[arm]
        found = t["tp"] + t["fn"]
        summary_rows[arm] = {
            "recall": round(t["tp"] / found, 3) if found else None,
            "wrong_extras": int(t["fp"]),
            "all_correct": f"{int(t['all_correct'])}/{int(t['utterances'])}",
            "loanword_kept": f"{int(t['loanwords_kept'])}/{int(t['loanwords_wanted'])}",
        }
    result = {
        "split": args.split,
        "targets": args.targets,
        "pairs": pairs,
        "unverified_masked": f"{unverified}/{pairs}",
        "seconds_per_pair": {k: round(v / pairs, 2) if pairs else None for k, v in seconds.items()},
        "arms": summary_rows,
        "landmarks_localized": f"{sum(1 for x in landmarks if x['local'])}/{len(landmarks)}",
        "landmarks": landmarks,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for arm, row in summary_rows.items():
        print(f"{arm:<18} {row}")
    print(f"unverified masked: {unverified}/{pairs}  landmarks: {result['landmarks_localized']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
