import json
import subprocess
import sys
from pathlib import Path

from saathi.evaluation.calls import GNANI_CALL_CAP

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "log_demo_calls.py"


def _run(ledger: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--ledger", str(ledger), *args],
        capture_output=True, text=True, cwd=ledger.parent,
        env={"PATH": "", "SYSTEMROOT": "C:\\Windows"},  # cwd off the repo: Windows caches go there
    )  # fmt: skip


def test_calls_are_added_under_the_label_and_accumulate(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    first = _run(ledger, "10")
    second = _run(ledger, "8", "--label", "demo-rehearsal")
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(ledger.read_text()) == {"demo-live": 10, "demo-rehearsal": 8}
    assert f"ledger now 18/{GNANI_CALL_CAP}" in second.stdout


def test_a_count_that_passes_the_cap_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"other": GNANI_CALL_CAP - 5}))
    out = _run(ledger, "6")
    assert out.returncode == 2
    assert "refused" in out.stderr
    assert json.loads(ledger.read_text()) == {"other": GNANI_CALL_CAP - 5}


def test_a_zero_or_absurd_count_is_rejected(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    assert _run(ledger, "0").returncode == 2
    assert _run(ledger, "5000").returncode == 2
    assert not ledger.exists()
