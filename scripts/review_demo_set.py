"""Review table for the 50-clip guided demo. Reads files only: no Gnani calls, no key.

For every clip: id, language, type, the expected facts, the facts read from the stored STT
transcript, MATCH or MISMATCH, and the stored translation. Mismatches (and clips that failed to
build) come first; no clip is dropped. --source checks the written text instead of the transcript,
which can be run before any paid call. Writes Markdown to --out and prints the mismatch list.
"""

import argparse
import hashlib
import sys
from collections.abc import Sequence
from pathlib import Path

from saathi.evaluation.demoset import (
    ExpectedFact,
    Layout,
    SetClip,
    compare_facts,
    load_clip_set,
    load_progress,
    read_turns,
)
from saathi.facts import Fact, extract_facts

ROOT = Path(__file__).resolve().parent.parent


def describe_expected(expected: Sequence[ExpectedFact]) -> str:
    return ", ".join(f"{e.kind} {e.value}" for e in expected)


def describe_heard(facts: Sequence[Fact]) -> str:
    return ", ".join(f"{f.kind} {f.value}" for f in facts) or "none"


def cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="store_true", help="check the written text, not STT")
    parser.add_argument("--clip-set", type=Path, default=ROOT / "demo" / "clip_set.json")
    parser.add_argument("--clips-dir", type=Path, default=ROOT / "demo" / "clips")
    parser.add_argument("--bundle-dir", type=Path, default=ROOT / "demo" / "bundle")
    parser.add_argument("--out", type=Path, default=ROOT / "scratch" / "demo_set_review.md")
    args = parser.parse_args()

    clips = load_clip_set(args.clip_set)
    layout = Layout(args.clips_dir, args.bundle_dir)
    turns = read_turns(layout.bundle_dir)
    failures = load_progress(layout.bundle_dir).failures
    by_key = {(t.clip_sha256, t.src, t.tgt): t for t in turns}

    rows: list[tuple[int, SetClip, str, str, str, str]] = []
    for clip in clips:
        translation = ""
        if args.source:
            heard_text = clip.text
        else:
            wav = layout.wav(clip)
            turn = None
            if wav.is_file():
                sha = hashlib.sha256(wav.read_bytes()).hexdigest()
                turn = by_key.get((sha, clip.lang, clip.tgt))
            if turn is None:
                reason = failures.get(clip.id, "not built")
                rows.append((0, clip, "-", f"FAILED ({reason})", "", ""))
                continue
            heard_text, translation = turn.transcript, turn.translation
        heard = extract_facts(heard_text, clip.lang)
        diffs = compare_facts(clip.expected, heard)
        verdict = "MATCH" if not diffs else "MISMATCH: " + "; ".join(diffs)
        rows.append(
            (1 if not diffs else 0, clip, describe_heard(heard), verdict, heard_text, translation)
        )

    rows.sort(key=lambda row: row[0])  # stable: failures and mismatches first, set order kept
    lines = [
        "| id | lang | type | review | expected | heard | result | transcript | translation |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for _, clip, heard_facts, verdict, text, translation in rows:
        lines.append(
            "| "
            + " | ".join(
                cell(v)
                for v in (
                    clip.id,
                    clip.lang,
                    clip.type,
                    clip.review_status,
                    describe_expected(clip.expected),
                    heard_facts,
                    verdict,
                    text,
                    translation,
                )
            )
            + " |"
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", "utf-8")
    bad = [row for row in rows if row[0] == 0]
    print(f"{len(rows) - len(bad)} MATCH, {len(bad)} not matching; table written to {args.out}")
    for _, clip, _, verdict, _, _ in bad:
        print(f"  {clip.id:22} {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
