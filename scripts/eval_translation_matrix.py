"""Translation-safety matrix: X to Y for all ten languages, plain vs masked. Local model only.

  --estimate   time a few pairs and print the full-run estimate; changes nothing
  (default)    run every pair, checkpointing after each; rerun to resume
  --report     write eval/results/translation_matrix.json and print the tables from the checkpoint

Method (see saathi.evaluation.transmatrix): the 30 gold utterances are taken in English (the 12
English ones as written; the other 18 machine-translated to English, so they are
"machine-generated source text"), then machine-translated to each source language X. Only
utterances whose English text still scores every gold fact with the English extractor are used
(the "scorable" set), so a low cell is not just a gold-file mismatch. Landmarks are excluded (open
vocabulary). No Gnani calls, no key. Needs AC power (the run is hours long); stops if it changes.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from saathi.evaluation.factscore import GoldUtterance, load_gold, score_transcript
from saathi.evaluation.power import PowerError, PowerGuard
from saathi.evaluation.runinfo import git_commit
from saathi.evaluation.transmatrix import (
    ARMS,
    ArmTally,
    CellTally,
    cell_from_json,
    digit_survival,
    format_grid,
    merge,
)
from saathi.facts import extract_facts
from saathi.languages import LANGUAGES
from saathi.masking import translate_masked
from saathi.translate import DegenerateTranslationError, RoutingTranslator, TranslationInputError

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "eval" / "gold" / "directions.json"
STATE = ROOT / "eval" / "state" / "translation_matrix_partial.json"
RESULT = ROOT / "eval" / "results" / "translation_matrix.json"
LANGS = tuple(sorted(LANGUAGES))
TRANSLATION_ERRORS = (DegenerateTranslationError, TranslationInputError)


def load_state() -> dict[str, Any]:
    if STATE.exists():
        loaded: dict[str, Any] = json.loads(STATE.read_text("utf-8"))
        return loaded
    return {"english": {}, "sources": {}, "cells": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def english_texts(translator: RoutingTranslator, state: dict[str, Any]) -> dict[str, GoldUtterance]:
    """The scorable gold utterances with their English text (machine-made unless already en)."""
    gold = load_gold(GOLD)
    scorable: dict[str, GoldUtterance] = {}
    for item in gold:
        text = state["english"].get(item.id)
        if text is None:
            text = (
                item.text if item.lang == "en" else translator.translate(item.text, item.lang, "en")
            )
            state["english"][item.id] = text
        facts = tuple(f for f in item.facts if f.kind != "landmark")
        english = GoldUtterance(item.id, item.split, "en", text, facts)
        # Recall only: the extractor also reports landmarks, which are not in the gold here.
        report = score_transcript(english, text)
        if facts and all(kind.fn == 0 for kind in report.by_kind.values()):
            scorable[item.id] = english
    save_state(state)
    return scorable


def source_text(
    translator: RoutingTranslator, state: dict[str, Any], item: GoldUtterance, lang: str
) -> str | None:
    cache = state["sources"].setdefault(lang, {})
    if item.id not in cache:
        try:
            cache[item.id] = (
                item.text if lang == "en" else translator.translate(item.text, "en", lang)
            )
        except TRANSLATION_ERRORS:
            cache[item.id] = None
    cached: str | None = cache[item.id]
    return cached


def back_to_english(translator: RoutingTranslator, text: str, tgt: str) -> str:
    return text if tgt == "en" else translator.translate(text, tgt, "en")


def score_arm(arm: ArmTally, item: GoldUtterance, english: str | None) -> None:
    if english is None:
        arm.failed += 1
        arm.fn += len(item.facts)
        return
    report = score_transcript(item, english)
    for kind in report.by_kind.values():
        arm.tp += kind.tp
        arm.fn += kind.fn


def run_cell(
    translator: RoutingTranslator,
    state: dict[str, Any],
    items: list[GoldUtterance],
    src: str,
    tgt: str,
) -> CellTally:
    cell = CellTally()
    assert cell.plain is not None and cell.masked is not None
    for item in items:
        text = source_text(translator, state, item, src)
        if text is None:
            continue
        cell.utterances += 1
        facts = tuple(extract_facts(text, src))
        outputs: dict[str, str | None] = {}
        try:
            outputs["plain"] = translator.translate(text, src, tgt)
        except TRANSLATION_ERRORS:
            outputs["plain"] = None
        try:
            masked = translate_masked(translator, text, src, tgt, facts)
            outputs["masked"] = masked.text
            cell.fallbacks += not masked.verified
        except TRANSLATION_ERRORS:
            outputs["masked"] = None
        for name in ARMS:
            arm: ArmTally = getattr(cell, name)
            out = outputs[name]
            if out is not None:
                kept, wanted = digit_survival(text, out)
                arm.digits_kept += kept
                arm.digits_wanted += wanted
            try:
                english = None if out is None else back_to_english(translator, out, tgt)
            except TRANSLATION_ERRORS:
                english = None
            score_arm(arm, item, english)
    return cell


def pairs() -> list[tuple[str, str]]:
    return [(s, t) for s in LANGS for t in LANGS if s != t]


def estimate(translator: RoutingTranslator, items: list[GoldUtterance], per_pair: int) -> None:
    state = load_state()
    sample = [("en", "kn"), ("hi", "ta"), ("bn", "en")]
    started = time.perf_counter()
    for src, tgt in sample:
        run_cell(translator, state, items[:per_pair], src, tgt)
    seconds = (time.perf_counter() - started) / (len(sample) * per_pair)
    total = seconds * len(items) * len(pairs())
    print(f"scorable utterances: {len(items)}; timed on {per_pair} per pair")
    print(f"{seconds:.1f} s per sentence per pair (source text included) -> "
          f"{len(pairs())} pairs = {total / 3600:.1f} h")


def report(items: list[GoldUtterance], state: dict[str, Any], per_pair: int) -> None:
    cells = {k: cell_from_json(v) for k, v in state["cells"].items()}
    by_source = {s: merge([c for k, c in cells.items() if k.startswith(f"{s}>")]) for s in LANGS}
    by_target = {t: merge([c for k, c in cells.items() if k.endswith(f">{t}")]) for t in LANGS}
    result = {
        "commit": git_commit(),
        "scorable_utterances": len(items),
        "sentences_per_pair": per_pair,
        "pairs_done": len(cells),
        "source_text": "machine-generated (English gold, machine-translated to each source)",
        "cells": {k: c.to_json() for k, c in cells.items()},
        "by_source": {k: c.to_json() for k, c in by_source.items()},
        "by_target": {k: c.to_json() for k, c in by_target.items()},
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for arm in ARMS:
        print(f"\nFact recall, {arm}\n{format_grid(LANGS, cells, arm)}")
    print("\nPer source / per target (plain recall, masked recall, fallback rate):")
    for label, group in (("source", by_source), ("target", by_target)):
        for lang, cell in group.items():
            assert cell.plain is not None and cell.masked is not None
            rate = cell.fallbacks / cell.utterances if cell.utterances else float("nan")
            print(f"  {label} {lang}: plain {cell.plain.recall} masked {cell.masked.recall} "
                  f"fallback {rate:.2f}")
    print(f"\nwrote {RESULT}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--estimate", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--per-pair", type=int, default=0, help="utterances per pair (0 = all)")
    parser.add_argument("--max-hours", type=float, default=4.0)
    args = parser.parse_args()

    translator = RoutingTranslator()
    state = load_state()
    scorable = english_texts(translator, state)
    items = list(scorable.values())
    per_pair = args.per_pair or len(items)
    items = items[:per_pair]
    if args.estimate:
        estimate(translator, items, min(3, len(items)))
        return 0
    if args.report:
        report(items, state, per_pair)
        return 0

    try:
        guard = PowerGuard()
    except PowerError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    todo = [p for p in pairs() if f"{p[0]}>{p[1]}" not in state["cells"]]
    print(f"{len(todo)} of {len(pairs())} pairs to do, {len(items)} sentences each")
    for src, tgt in todo:
        try:
            guard.check()
        except PowerError as exc:
            print(f"stopped: {exc}; rerun to resume", file=sys.stderr)
            return 1
        started = time.perf_counter()
        cell = run_cell(translator, state, items, src, tgt)
        state["cells"][f"{src}>{tgt}"] = cell.to_json()
        save_state(state)
        assert cell.plain is not None and cell.masked is not None
        print(f"{src}>{tgt}  plain {cell.plain.recall}  masked {cell.masked.recall}  "
              f"fallbacks {cell.fallbacks}/{cell.utterances}  {time.perf_counter() - started:.0f}s",
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
