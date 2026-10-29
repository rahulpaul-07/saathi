"""Back-translate the demo clip sentences to English, as a read-through for non-speakers.

Local IndicTrans2 indic-en, greedy; no Gnani calls and no audio. For each clip it prints the source
sentence, the English back-translation, the facts the clip is meant to carry, what the fact
extractor finds in the source (the chips), and whether each intended fact is visible in the English.
The English check is a keyword match near the fact word, so it flags, it does not prove: read the
table. It cannot judge whether the Kannada, Tamil or Telugu is natural, only whether the meaning
survives.
"""

import re
import sys

from saathi.evaluation.democlips import CLIP_SPECS, ClipSpec
from saathi.facts import extract_facts
from saathi.translate import RoutingTranslator

WINDOW = 3  # a number counts for "gate" if it is within this many words of it
KIND_WORDS = {"cross": "cross", "main": "main", "gate": "gate"}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def fact_visible(english: str, kind: str, keywords: tuple[str, ...]) -> bool:
    words = _words(english)
    anchor = KIND_WORDS.get(kind)
    if anchor is None:  # landmark: the name anywhere
        return any(any(k in word for k in keywords) for word in words)
    for i, word in enumerate(words):
        if word == anchor:
            near = words[max(0, i - WINDOW) : i + WINDOW + 1]
            if any(k in near for k in keywords):
                return True
    return False


def report_row(spec: ClipSpec, english: str) -> tuple[list[str], list[str]]:
    """(lines to print, names of facts that did not survive)"""
    lost = [
        f"{kind} {value}"
        for kind, value, keywords in spec.facts
        if not fact_visible(english, kind, keywords)
    ]
    intended = ", ".join(f"{kind} {value}" for kind, value, _ in spec.facts)
    chips = ", ".join(f"{f.kind} {f.value}" for f in extract_facts(spec.text, spec.lang))
    lines = [
        f"{spec.id} ({spec.lang})",
        f"  source:    {spec.text}",
        f"  English:   {english}",
        f"  intended:  {intended}",
        f"  chips:     {chips or 'none'}",
        f"  verdict:   {'FLAG, not visible in English: ' + ', '.join(lost) if lost else 'ok'}",
    ]
    return lines, lost


def main() -> int:
    translator = RoutingTranslator()
    flagged = 0
    for spec in CLIP_SPECS:
        english = translator.translate(spec.text, spec.lang, "en")
        lines, lost = report_row(spec, english)
        print("\n".join(lines) + "\n")
        flagged += bool(lost)
    print(f"{flagged} of {len(CLIP_SPECS)} clips flagged")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
