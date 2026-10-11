"""Slice 5: the two phone-check cases, run as text only (no Gnani calls, no audio).

Usage: uv run --no-sync python scripts/eval_phone_cases.py
Writes eval/results/phone_cases.json. The texts are the author's own phrases (docs/DESIGN.md).
"""

import json
from pathlib import Path

from saathi.evaluation.power import PowerGuard
from saathi.evaluation.runinfo import run_metadata
from saathi.guard import has_repeated_phrase
from saathi.translate import IndicTrans2Translator

OUT = Path("eval/results/phone_cases.json")
CASES = {
    "case1_ground_truth": (
        "হে ঈশ্বর আমায় ভালো রাখো আমায় এই যন্ত্রণার জ্বালা দিও না ঠিক করো আমায় একটা "
        "বড় চাকরি দাও প্রিপারেশনটা ভালো করে করাও"
    ),
    "case1_as_heard_by_stt": (
        "সেই শর্ট আমায় ভালো রাখো আমায় এই যন্ত্রণার জ্বালা দিও না ঠিক করো আমায় একটা "
        "বড় চাকরি দাও প্রিপারেশনটা ভালো করে করাও"
    ),
    "case2_word_sense": "আমার লাইফ তো পুরো বেকারই চলছে",
}
WARMUPS = 3


def main() -> None:
    power = PowerGuard()
    results: dict[str, dict[str, object]] = {}
    for beams in (1, 5):
        translator = IndicTrans2Translator(num_beams=beams)
        translator.load()
        for _ in range(WARMUPS):
            translator.translate_with_stats("আমি ভালো আছি", "bn", "kn")
        for name, text in CASES.items():
            result = translator.translate_with_stats(text, "bn", "kn")
            results.setdefault(name, {"input": text})[f"beams{beams}"] = {
                "output": result.text,
                "capped": result.capped,
                "repeated_phrase": has_repeated_phrase(result.text),
                "output_tokens": result.longest_output_tokens,
                "input_tokens": result.longest_input_tokens,
            }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    meta = run_metadata(power.state, num_beams=1)
    del meta["num_beams"]  # each case records its own greedy (beams1) and beam (beams5) result
    payload = {"meta": meta, "cases": results}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
