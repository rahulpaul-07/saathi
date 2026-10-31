"""Live smoke test through the HTTP API: 6 Gnani calls planned, 12 at most. Spends credits.

  uv run --no-sync python scripts/smoke_live.py --dry-run  print the plan; sends nothing
  uv run --no-sync python scripts/smoke_live.py --yes      really run it (author awake only)

Writes a content-free summary to eval/results/live_smoke.json. Logic and tests live in
saathi.evaluation.livesmoke.
"""

import sys
from pathlib import Path

from saathi.evaluation.livesmoke import main

if __name__ == "__main__":
    sys.exit(main(root=Path(__file__).resolve().parent.parent))
