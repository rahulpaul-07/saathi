"""Latency study: 20 turns x 2 Gnani calls = 40 calls. Spends credits; run --dry-run first.

  uv run --no-sync python scripts/latency_study.py --dry-run  print the plan; sends nothing
  uv run --no-sync python scripts/latency_study.py --yes      really run it (author awake, on AC)

Needs WAV files in eval/audio/latency/ (gitignored). Logic and tests live in
saathi.evaluation.latency.
"""

import sys
from pathlib import Path

from saathi.evaluation.latency import main

if __name__ == "__main__":
    sys.exit(main(root=Path(__file__).resolve().parent.parent))
