"""The conditional-masking arm of the translation matrix, next to the stored plain and current arms.

  collect   for every matrix pair and the same 20 scorable sentences as masking_reversal, translate
            with conditional masking and back-translate to English; checkpoints after each pair,
            rerun to resume. Local model only, no Gnani calls, needs AC power (like the matrix).
  report    score all three arms (plain and current masking come from the masking_reversal
            checkpoint, so they are the very outputs published in EVAL.md) with the English
            extractor of today and with the one before 2026-11-01; write
            eval/results/masking_conditional_matrix.json

Two scores per arm, as in scripts/analyze_masking_reversal.py: "back" translates the output to
English and runs the English extractor (the matrix score); "direct" runs the target-language
extractor on the output (the A/B score). Landmarks are excluded. Synthetic sentences only.
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_masking_reversal as reversal  # noqa: E402, I001
import eval_translation_matrix as matrix  # noqa: E402
from legacy_extractor import legacy_english  # noqa: E402
from saathi.evaluation.factscore import GoldUtterance, load_gold  # noqa: E402
from saathi.evaluation.power import PowerError, PowerGuard  # noqa: E402
from saathi.evaluation.runinfo import git_commit  # noqa: E402
from saathi.masking import translate_masked  # noqa: E402
from saathi.translate import RoutingTranslator  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "eval" / "state" / "conditional_matrix.json"
RESULT = ROOT / "eval" / "results" / "masking_conditional_matrix.json"
ARMS = ("plain", "masked", "conditional")  # "masked" is the current mode, as in the reversal state


def load() -> dict[str, Any]:
    if STATE.exists():
        loaded: dict[str, Any] = json.loads(STATE.read_text("utf-8"))
        return loaded
    return {"pairs": {}}


def save(state: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def collect(max_hours: float, allow_battery: bool) -> int:
    try:
        guard = PowerGuard(allow_battery=allow_battery)
    except PowerError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    translator = RoutingTranslator()
    published = reversal.load()
    if not published["pairs"]:
        print("masking_reversal checkpoint is missing", file=sys.stderr)
        return 2
    state = load()
    state.setdefault("power_states", [])
    if guard.state.value not in state["power_states"]:
        state["power_states"].append(guard.state.value)
    todo = [key for key in sorted(published["pairs"]) if key not in state["pairs"]]
    print(f"{len(todo)} of {len(published['pairs'])} pairs to do", flush=True)
    deadline = time.monotonic() + max_hours * 3600
    for key in todo:
        try:
            guard.check()
        except PowerError as exc:
            print(f"stopped: {exc}; rerun to resume", file=sys.stderr)
            return 1
        if time.monotonic() > deadline:
            print("stopped: time limit; rerun to resume", file=sys.stderr)
            return 1
        src, tgt = key.split(">")
        started = time.perf_counter()
        out = []
        for rec in published["pairs"][key]:
            output: str | None = None
            verified = False
            try:
                result = translate_masked(translator, rec["source"], src, tgt, None, "conditional")
                output, verified = result.text, result.verified
            except matrix.TRANSLATION_ERRORS:
                pass
            back = None
            if output is not None:
                back = output if tgt == "en" else reversal.translate_or_none(
                    translator, output, tgt, "en"
                )
            out.append({"id": rec["id"], "output": output, "back": back, "verified": verified})
        state["pairs"][key] = out
        save(state)
        print(f"{key} {len(out)} sentences {time.perf_counter() - started:.0f}s", flush=True)
    return 0


def score_all(scorer: str) -> dict[str, Any]:
    """Recall per arm and score route over all pairs, with the `scorer` English extractor."""
    published = reversal.load()
    state = load()
    gold = {u.id: u for u in load_gold(matrix.GOLD)}
    wanted = 0
    found: dict[str, int] = defaultdict(int)
    by_kind: dict[str, int] = defaultdict(int)
    verified: dict[str, int] = defaultdict(int)
    sentences = 0
    for key, recs in sorted(published["pairs"].items()):
        _, tgt = key.split(">")
        conditional = {r["id"]: r for r in state["pairs"].get(key, [])}
        for rec in recs:
            item = gold[rec["id"]]
            english = GoldUtterance(
                item.id, item.split, "en", rec["source"],
                tuple(f for f in item.facts if f.kind != "landmark"),
            )  # fmt: skip
            cond = conditional.get(rec["id"])
            if cond is None:
                continue
            sentences += 1
            wanted += len(english.facts)
            texts = {
                "plain": (rec["plain"]["output"], rec["plain"]["back"]),
                "masked": (rec["masked"]["output"], rec["masked"]["back"]),
                "conditional": (cond["output"], cond["back"]),
            }
            verified["masked"] += rec["verified"]
            verified["conditional"] += cond["verified"]
            for arm, (output, back) in texts.items():
                if scorer == "legacy":
                    with legacy_english():
                        lost_back = reversal.missed(english, back, "en")
                        lost_direct = reversal.missed(english, output, tgt)
                else:
                    lost_back = reversal.missed(english, back, "en")
                    lost_direct = reversal.missed(english, output, tgt)
                found[f"back_{arm}"] += len(english.facts) - len(lost_back)
                found[f"direct_{arm}"] += len(english.facts) - len(lost_direct)
                for fact in lost_back:
                    by_kind[f"{arm}:{fact.split(':')[0]}"] += 1
    return {
        "sentences": sentences,
        "facts": wanted,
        "recall": {k: round(v / wanted, 3) for k, v in sorted(found.items())} if wanted else {},
        "found": dict(sorted(found.items())),
        "back_missed_by_kind": dict(sorted(by_kind.items())),
        "verified": dict(verified),
    }


def report() -> int:
    state = load()
    if not state["pairs"]:
        print("nothing collected yet", file=sys.stderr)
        return 2
    result: dict[str, Any] = {
        "commit": git_commit(),
        "pairs": len(state["pairs"]),
        "power_states": state.get("power_states", []),
        "new": score_all("new"),
        "legacy": score_all("legacy"),
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for scorer in ("legacy", "new"):
        print(scorer, json.dumps(result[scorer]["recall"]), result[scorer]["verified"])
    print(f"RESULT {RESULT.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["collect", "report"])
    parser.add_argument("--max-hours", type=float, default=2.0)
    parser.add_argument(
        "--allow-battery", action="store_true",
        help="accuracy does not depend on power; the state is recorded in the result",
    )
    args = parser.parse_args()
    return collect(args.max_hours, args.allow_battery) if args.mode == "collect" else report()


if __name__ == "__main__":
    sys.exit(main())
