"""Why did masking lose in the translation matrix? Local model only, no Gnani calls.

  collect   re-run every matrix pair on the same 20 scorable sentences and keep the evidence per
            sentence (source text, both outputs, both back-translations, what each arm missed);
            checkpoints after each pair, rerun to resume
  report    print the analysis from the checkpoint and write eval/results/masking_reversal.json
  examples  write 10 "plain right, masked wrong" and 5 scoring-check examples to a Markdown file

Two scores per arm: "back-translated" is the matrix score (translate to Y, back to English, English
extractor); "direct" is the earlier A/B score (the Y-language extractor on the Y text). Same gold.
The source sentences are the matrix's machine-generated ones (eval/state/translation_matrix_partial
.json must exist). Synthetic addresses only; the checkpoint stays in the gitignored eval/state.
"""

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_translation_matrix as matrix  # noqa: E402, I001
from saathi.evaluation.factscore import GoldUtterance, score  # noqa: E402
from saathi.evaluation.power import PowerError, PowerGuard  # noqa: E402
from saathi.evaluation.runinfo import git_commit  # noqa: E402
from saathi.evaluation.transmatrix import digit_survival  # noqa: E402
from saathi.facts import extract_facts  # noqa: E402
from saathi.masking import mask, translate_masked  # noqa: E402
from saathi.translate import RoutingTranslator  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "eval" / "state" / "masking_reversal.json"
RESULT = ROOT / "eval" / "results" / "masking_reversal.json"
ARMS = ("plain", "masked")
SLOT = re.compile(r"#\s*L\s*(\d+)", re.IGNORECASE)
# Brackets or the toolkit's own entity tag around a restored slot: the model mangled the marker.
RESIDUE = re.compile(r"[<>\[\]]|\bID\s*\d|\bI\.\s*D\.")


def load() -> dict[str, Any]:
    if STATE.exists():
        loaded: dict[str, Any] = json.loads(STATE.read_text("utf-8"))
        return loaded
    return {"pairs": {}}


def save(state: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def missed(gold: GoldUtterance, text: str | None, lang: str) -> list[str]:
    """Gold facts the `lang` extractor does not find in `text` (all when there is no text)."""
    if text is None:
        return [f"{f.kind}:{f.value}" for f in gold.facts]
    target = GoldUtterance(gold.id, gold.split, lang, text, gold.facts)
    _, misses = score([target])
    return [f"{f.kind}:{f.value}" for miss in misses for f in miss.missed]


def value_forms(text: str, src: str) -> list[str]:
    """How each clear number in the source is written: ascii, native or word."""
    forms = []
    for fact in extract_facts(text, src):
        if fact.value_start is None or fact.value_end is None or fact.ambiguous:
            continue
        span = text[fact.value_start : fact.value_end]
        digits = [c for c in span if c.isdecimal()]
        forms.append("word" if not digits else "ascii" if all(c.isascii() for c in digits)
                     else "native")
    return forms


def slot_audit(raw: str | None, expected: list[int]) -> dict[str, bool]:
    seen = [int(m) for m in SLOT.findall(raw or "")]
    return {
        "dropped": any(n not in seen for n in expected),
        "duplicated": any(seen.count(n) > 1 for n in set(seen)),
        "invented": any(n not in expected for n in seen),
    }


def translate_or_none(translator: RoutingTranslator, text: str, src: str, tgt: str) -> str | None:
    try:
        return translator.translate(text, src, tgt)
    except matrix.TRANSLATION_ERRORS:
        return None


def collect_record(
    translator: RoutingTranslator, item: GoldUtterance, text: str, src: str, tgt: str
) -> dict[str, Any]:
    facts = tuple(extract_facts(text, src))
    slots = mask(text, src, facts).slots
    out: dict[str, str | None] = {"plain": translate_or_none(translator, text, src, tgt)}
    verified, raw = False, None
    try:
        masked = translate_masked(translator, text, src, tgt, facts)
        out["masked"], verified, raw = masked.text, masked.verified, masked.raw
    except matrix.TRANSLATION_ERRORS:
        out["masked"] = None
    record: dict[str, Any] = {
        "id": item.id,
        "source": text,
        "forms": value_forms(text, src),
        "loanwords": sum(slot.kind == "loanword" for slot in slots),
        "nfacts": len(item.facts),
        "verified": verified,
        "raw": raw,
        "audit": slot_audit(raw, [slot.number for slot in slots]),
    }
    for arm in ARMS:
        output = out[arm]
        back = None
        if output is not None:
            try:
                back = output if tgt == "en" else translator.translate(output, tgt, "en")
            except matrix.TRANSLATION_ERRORS:
                back = None
        kept, wanted = (0, 0) if output is None else digit_survival(text, output)
        record[arm] = {
            "output": output,
            "back": back,
            "direct_missed": missed(item, output, tgt),
            "back_missed": missed(item, back, "en"),
            "digits_kept": kept,
            "digits_wanted": wanted,
        }
    return record


def collect(max_hours: float) -> int:
    try:
        guard = PowerGuard()
    except PowerError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    translator = RoutingTranslator()
    matrix_state = matrix.load_state()
    items = list(matrix.english_texts(translator, matrix_state).values())
    state = load()
    todo = [p for p in matrix.pairs() if f"{p[0]}>{p[1]}" not in state["pairs"]]
    print(f"{len(todo)} of {len(matrix.pairs())} pairs to do, {len(items)} sentences each")
    deadline = time.monotonic() + max_hours * 3600
    for src, tgt in todo:
        try:
            guard.check()
        except PowerError as exc:
            print(f"stopped: {exc}; rerun to resume", file=sys.stderr)
            return 1
        if time.monotonic() > deadline:
            print("stopped: time limit; rerun to resume", file=sys.stderr)
            return 1
        started = time.perf_counter()
        records = []
        for item in items:
            text = matrix.source_text(translator, matrix_state, item, src)
            if text is not None:
                records.append(collect_record(translator, item, text, src, tgt))
        state["pairs"][f"{src}>{tgt}"] = records
        save(state)
        print(f"{src}>{tgt} {len(records)} sentences {time.perf_counter() - started:.0f}s",
              flush=True)
    return 0


# ---- analysis ---------------------------------------------------------------------------------


def records(state: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (key.split(">")[0], key.split(">")[1], rec)
        for key, recs in sorted(state["pairs"].items())
        for rec in recs
    ]


def sentence_class(rec: dict[str, Any]) -> str:
    forms = set(rec["forms"])
    if not forms:
        return "none"
    digit = forms & {"ascii", "native"}
    return "digits" if digit and "word" not in forms else "words" if not digit else "mixed"


def recall(rows: list[tuple[str, str, dict[str, Any]]], arm: str, how: str) -> tuple[int, int]:
    """(facts found, facts wanted) for an arm, scored 'back' or 'direct'."""
    wanted = sum(rec["nfacts"] for _, _, rec in rows)
    lost = sum(len(rec[arm][f"{how}_missed"]) for _, _, rec in rows)
    return wanted - lost, wanted


def pct(pair: tuple[int, int]) -> str:
    return "n/a" if not pair[1] else f"{pair[0] / pair[1]:.2f} ({pair[0]}/{pair[1]})"


def cause(rec: dict[str, Any]) -> str:
    """Why masked lost more facts than plain on this sentence (back-translated score)."""
    masked = rec["masked"]
    if masked["output"] is None:
        return "masked translation failed"
    if not rec["verified"]:
        audit = rec["audit"]
        if audit["dropped"]:
            return "fallback: slot dropped"
        if audit["duplicated"]:
            return "fallback: slot duplicated"
        return "fallback: slot invented"
    if RESIDUE.search(masked["output"]) and not RESIDUE.search(rec["plain"]["output"] or ""):
        return "verified, but placeholder residue is left in the text"
    if masked["digits_kept"] < masked["digits_wanted"]:
        return "verified, but a source digit is absent"
    if len(masked["direct_missed"]) >= len(masked["back_missed"]):
        return "masked text itself lacks the fact (target-language extractor)"
    return "back-translation lost it (masked text is fine)"


def report(state: dict[str, Any]) -> dict[str, Any]:
    rows = records(state)
    result: dict[str, Any] = {"commit": git_commit(), "sentences": len(rows)}

    print("1. How the source numbers are written (clear number facts), per source language")
    print("| src | numbers | ascii digits | native digits | words | loanwords per sentence |")
    print("|---|---|---|---|---|---|")
    forms_by_src: dict[str, Counter[str]] = defaultdict(Counter)
    loan_by_src: Counter[str] = Counter()
    sent_by_src: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()
    for src, _, rec in rows:
        if (src, rec["id"]) in seen:  # the source text is the same for every target
            continue
        seen.add((src, rec["id"]))
        forms_by_src[src].update(rec["forms"])
        loan_by_src[src] += rec["loanwords"]
        sent_by_src[src] += 1
    result["forms_by_source"] = {}
    for src in sorted(forms_by_src):
        c = forms_by_src[src]
        total = sum(c.values())
        share = {k: (c[k] / total if total else 0.0) for k in ("ascii", "native", "word")}
        result["forms_by_source"][src] = {"numbers": total, **share}
        print(f"| {src} | {total} | {share['ascii']:.2f} | {share['native']:.2f} | "
              f"{share['word']:.2f} | {loan_by_src[src] / sent_by_src[src]:.1f} |")

    print("\n2. Fact recall by how the source writes its numbers (all targets; en target has no "
          "back-translation step)")
    print("| class | sentence-pairs | back plain | back masked | direct plain | direct masked |")
    print("|---|---|---|---|---|---|")
    result["by_class"] = {}
    for label in ("digits", "words", "mixed", "none"):
        for scope, subset in (
            (label, [r for r in rows if sentence_class(r[2]) == label]),
            (f"{label}, target en", [r for r in rows
                                      if sentence_class(r[2]) == label and r[1] == "en"]),
        ):
            if not subset:
                continue
            cells = {f"{how}_{arm}": recall(subset, arm, how)
                     for how in ("back", "direct") for arm in ARMS}
            result["by_class"][scope] = {k: list(v) for k, v in cells.items()}
            print(f"| {scope} | {len(subset)} | {pct(cells['back_plain'])} | "
                  f"{pct(cells['back_masked'])} | {pct(cells['direct_plain'])} | "
                  f"{pct(cells['direct_masked'])} |")

    print("\n   All pairs, then by target kind:")
    for label, subset in (
        ("all pairs", rows),
        ("target en", [r for r in rows if r[1] == "en"]),
        ("target not en", [r for r in rows if r[1] != "en"]),
    ):
        cells = {f"{how}_{arm}": recall(subset, arm, how)
                 for how in ("back", "direct") for arm in ARMS}
        result.setdefault("overall", {})[label] = {k: list(v) for k, v in cells.items()}
        print(f"   {label}: back plain {pct(cells['back_plain'])}, "
              f"masked {pct(cells['back_masked'])}; direct plain {pct(cells['direct_plain'])}, "
              f"masked {pct(cells['direct_masked'])}")

    print("\n3. Fallback rate per source, and where the masked loss comes from")
    by_src: dict[str, list[bool]] = defaultdict(list)
    for src, _, rec in rows:
        by_src[src].append(not rec["verified"])
    result["fallback_by_source"] = {s: sum(v) / len(v) for s, v in sorted(by_src.items())}
    for src, flags in sorted(by_src.items()):
        print(f"   {src}: {sum(flags)}/{len(flags)} = {sum(flags) / len(flags):.2f}")
    lost: Counter[str] = Counter()
    lost_kind: Counter[str] = Counter()
    gained_kind: Counter[str] = Counter()
    gained = 0
    for _, _, rec in rows:
        plain_miss, masked_miss = rec["plain"]["back_missed"], rec["masked"]["back_missed"]
        extra = len(masked_miss) - len(plain_miss)
        if extra > 0:
            lost[cause(rec)] += extra
        else:
            gained += -extra
        lost_kind.update(m.split(":")[0] for m in masked_miss if m not in plain_miss)
        gained_kind.update(m.split(":")[0] for m in plain_miss if m not in masked_miss)
    result["lost_by_kind"] = dict(lost_kind)
    result["gained_by_kind"] = dict(gained_kind)
    print("   by fact kind (masked missed but plain found / plain missed but masked found):")
    for kind in sorted(set(lost_kind) | set(gained_kind)):
        print(f"   {kind:<6} {lost_kind[kind]:>4} / {gained_kind[kind]:>4}")
    total_lost = sum(lost.values())
    result["loss_by_cause"] = dict(lost)
    result["facts_masked_found_that_plain_missed"] = gained
    print(f"   facts masked lost beyond plain: {total_lost}; facts masked found that plain "
          f"missed: {gained}; net {gained - total_lost}")
    for name, count in lost.most_common():
        print(f"   {count:>4}  {name}")
    print(f"RESULT {RESULT.name}")
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def pick(
    rows: list[tuple[str, str, dict[str, Any]]], count: int, wrong_only: bool
) -> list[tuple[str, str, dict[str, Any]]]:
    """Plain right and masked wrong on the back-translated score, one per source language first.

    With `wrong_only` keep only sentences where the masked text itself is fine (the target-language
    extractor finds more of the facts than the back-translation does).
    """
    def artefact(rec: dict[str, Any]) -> bool:
        return len(rec["masked"]["direct_missed"]) < len(rec["masked"]["back_missed"])

    pool = [
        r for r in rows
        if not r[2]["plain"]["back_missed"] and r[2]["masked"]["back_missed"]
        and (not wrong_only or artefact(r[2]))
    ]
    chosen: list[tuple[str, str, dict[str, Any]]] = []
    # First one per source language, then fill up in order.
    for item in pool:
        if len(chosen) < count and all(item[0] != c[0] for c in chosen):
            chosen.append(item)
    for item in pool:
        if len(chosen) < count and item not in chosen:
            chosen.append(item)
    return chosen


def examples(state: dict[str, Any], out: Path) -> None:
    rows = records(state)
    lines = ["# Masking reversal: examples (synthetic addresses)", "",
             "## 10 sentences where plain was right and masked was wrong (back-translated score)"]
    for number, (src, tgt, rec) in enumerate(pick(rows, 10, wrong_only=False), 1):
        lines += [
            "", f"### {number}. {src} to {tgt}, {rec['id']}, {cause(rec)}",
            f"- source: {rec['source']}",
            f"- plain: {rec['plain']['output']}",
            f"- masked: {rec['masked']['output']}",
            f"- masked raw (model output): {rec['raw']}",
            f"- plain back: {rec['plain']['back']}",
            f"- masked back: {rec['masked']['back']}",
            f"- lost by masked: {rec['masked']['back_missed']}; verified: {rec['verified']}",
        ]
    lines += ["", "## 5 scoring checks: masked text is fine, the back-translation lost the fact"]
    for number, (src, tgt, rec) in enumerate(pick(rows, 5, wrong_only=True), 1):
        lines += [
            "", f"### {number}. {src} to {tgt}, {rec['id']}",
            f"- masked text: {rec['masked']['output']}",
            f"- extractor in {tgt} finds all gold facts here: {not rec['masked']['direct_missed']}",
            f"- masked back: {rec['masked']['back']}",
            f"- English extractor misses: {rec['masked']['back_missed']}",
            f"- plain back (for contrast): {rec['plain']['back']}",
        ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["collect", "report", "examples"])
    parser.add_argument("--max-hours", type=float, default=2.0)
    parser.add_argument("--out", type=Path, default=ROOT / "scratch" / "masking_examples.md")
    args = parser.parse_args()
    if args.mode == "collect":
        return collect(args.max_hours)
    state = load()
    if not state["pairs"]:
        print("nothing collected yet", file=sys.stderr)
        return 2
    if args.mode == "report":
        report(state)
    else:
        examples(state, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
