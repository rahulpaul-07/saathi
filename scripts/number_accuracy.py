"""Does a number survive translation? The production masked path on bare numbers (local model).

For each source language, each number word, each carrier sentence and each target language it runs
`translate_masked` (exactly what a turn runs) and parses the numbers out of the restored text with
the target language's own number parser. A value counts as kept when the expected number is among
them. Run it before and after a masking change and compare the two JSON files with --compare.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from saathi.facts.lexicons import _kn_native_numbers, lexicon_for
from saathi.facts.numbers import parse_number
from saathi.facts.text import tokenize
from saathi.masking import translate_masked
from saathi.translate import RoutingTranslator

SINGLE = (2, 3, 4, 5, 6, 7, 8, 9)
COMPOUND = (12, 19, 21, 29, 35, 44, 56, 57, 59, 63, 77, 85, 89, 99)
HUNDRED = 100
DIGIT_VALUES = (2, 5, 9, 12, 56, 57, 77, 99)

WORDS: dict[str, dict[int, str]] = {
    "hi": dict(
        zip(
            (*SINGLE, *COMPOUND, HUNDRED),
            "दो तीन चार पांच छह सात आठ नौ बारह उन्नीस इक्कीस उनतीस पैंतीस चौवालीस छप्पन सत्तावन उनसठ "
            "तिरसठ सतहत्तर पचासी नवासी निन्यानवे सौ".split(),
            strict=True,
        )
    ),
    "bn": dict(
        zip(
            (*SINGLE, *COMPOUND, HUNDRED),
            "দুই তিন চার পাঁচ ছয় সাত আট নয় বারো ঊনিশ একুশ ঊনত্রিশ পঁয়ত্রিশ চুয়াল্লিশ ছাপ্পান্ন সাতান্ন "
            "ঊনষাট তেষট্টি সাতাত্তর পঁচাশি ঊননব্বই নিরানব্বই একশো".split(),
            strict=True,
        )
    ),
}
_KN = {value: word for word, value in _kn_native_numbers().items()}
WORDS["kn"] = {value: _KN[value] for value in (*SINGLE, *COMPOUND)}
WORDS["kn"][HUNDRED] = "ನೂರು"
# The same numbers written as digits, to see whether the model already keeps those.
DIGITS: dict[str, dict[int, str]] = {
    lang: {value: str(value) for value in DIGIT_VALUES} for lang in ("kn", "hi", "bn")
}

CARRIERS: dict[str, dict[str, str]] = {
    "kn": {
        "minutes": "ಅಣ್ಣ, {n} ನಿಮಿಷದಲ್ಲಿ ಬರುತ್ತೇನೆ",
        "meters": "{n} ಮೀಟರ್ ನೇರ ಹೋಗಿ",
        "door": "ಅಣ್ಣ, {n} ನಂಬರ್ ಡೋರ್ ಗೆ ಬನ್ನಿ",
    },
    "hi": {
        "minutes": "भैया, मैं {n} मिनट में आता हूँ",
        "meters": "{n} मीटर सीधे जाइए",
        "door": "भैया, {n} नंबर दरवाजे पर आइए",
    },
    "bn": {
        "minutes": "দাদা, আমি {n} মিনিটে আসছি",
        "meters": "{n} মিটার সোজা যান",
        "door": "দাদা, {n} নম্বর ঘরে আসুন",
    },
}
TARGETS = ("en", "hi", "bn", "kn")


def numbers_in(text: str, lang: str) -> list[int]:
    lex = lexicon_for(lang)
    tokens = tokenize(text)
    found: list[int] = []
    index = 0
    while index < len(tokens):
        number = parse_number(tokens, index, lex)
        if number is not None and not number.ambiguous and number.value.isdecimal():
            found.append(int(number.value))
            index = max(number.end, index + 1)
        else:
            index += 1
    return found


def run(out: Path, source: dict[str, dict[int, str]], only: list[int] | None) -> None:
    translator = RoutingTranslator()
    rows: list[dict[str, object]] = []
    for src, by_value in source.items():
        lex = lexicon_for(src)
        for value, word in by_value.items():
            if only is not None and value not in only:
                continue
            parsed = parse_number(tokenize(word), 0, lex)
            if parsed is None or parsed.value != str(value):
                print(f"skip {src} {value} {word!r}: parser reads {parsed}", file=sys.stderr)
                continue
            for carrier, template in CARRIERS[src].items():
                text = template.format(n=word)
                for tgt in TARGETS:
                    if tgt == src:
                        continue
                    result = translate_masked(translator, text, src, tgt)
                    rows.append(
                        {
                            "src": src,
                            "tgt": tgt,
                            "value": value,
                            "word": word,
                            "carrier": carrier,
                            "text": text,
                            "out": result.text,
                            "raw": result.raw,
                            "verified": result.verified,
                            "kept": value in numbers_in(result.text, tgt),
                        }
                    )
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    summarize(rows)


def summarize(rows: list[dict[str, object]]) -> None:
    groups: dict[str, list[bool]] = defaultdict(list)
    for row in rows:
        value = int(str(row["value"]))
        klass = "single-digit word" if value < 10 else "compound word"
        groups[f"{klass} / {row['carrier']}"].append(bool(row["kept"]))
        groups[f"{klass} / all carriers"].append(bool(row["kept"]))
        groups[f"{row['src']}->{row['tgt']} / {klass}"].append(bool(row["kept"]))
    for name in sorted(groups):
        kept = groups[name]
        print(f"{name:<46} kept {sum(kept):>3}/{len(kept):<3} ({100 * sum(kept) / len(kept):.0f}%)")
    unverified = sum(1 for row in rows if not row["verified"])
    print(f"unverified: {unverified}/{len(rows)}")


def compare(before: Path, after: Path) -> None:
    old = {
        (r["src"], r["tgt"], r["value"], r["carrier"]): r
        for r in json.loads(before.read_text("utf-8"))
    }
    new = {
        (r["src"], r["tgt"], r["value"], r["carrier"]): r
        for r in json.loads(after.read_text("utf-8"))
    }
    worse = [k for k in old if k in new and old[k]["kept"] and not new[k]["kept"]]
    better = [k for k in old if k in new and not old[k]["kept"] and new[k]["kept"]]
    print(
        f"cases {len(old)} -> {len(new)}; kept before {sum(bool(r['kept']) for r in old.values())},"
        f" after {sum(bool(r['kept']) for r in new.values())}"
    )
    print(f"worse ({len(worse)}):")
    for k in worse:
        print("  ", k, "|", old[k]["out"], "=>", new[k]["out"])
    print(f"better: {len(better)}")
    print(
        f"unverified before {sum(not r['verified'] for r in old.values())},"
        f" after {sum(not r['verified'] for r in new.values())}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--digits", action="store_true", help="numbers written as digits")
    parser.add_argument("--only", type=int, nargs="+", help="restrict to these values")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BEFORE", "AFTER"))
    args = parser.parse_args()
    if args.compare:
        compare(*args.compare)
    elif args.out:
        run(args.out, DIGITS if args.digits else WORDS, args.only)
    else:
        parser.error("give --out or --compare")
    return 0


if __name__ == "__main__":
    sys.exit(main())
