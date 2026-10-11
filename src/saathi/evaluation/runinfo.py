"""Metadata recorded with every result file, so a number can be traced to what produced it."""

import platform
import subprocess
from datetime import UTC, datetime
from typing import Any

from saathi.evaluation.power import PowerState


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def run_metadata(power: PowerState, *, num_beams: int) -> dict[str, Any]:
    import torch

    return {
        "power_state": power.value,
        "num_beams": num_beams,
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "torch": torch.__version__,
        "python": platform.python_version(),
        "git_commit": git_commit(),
        "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
