import importlib.util
from pathlib import Path
from types import ModuleType

from saathi.evaluation.democlips import CLIP_SPECS

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backtranslate_demo.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("backtranslate_demo", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_faithful_back_translation_passes() -> None:
    module = _load()
    bakery = next(s for s in CLIP_SPECS if s.id == "kn-bakery")
    english = "Third cross, fifth main, gate number four, next to the bakery"
    _, lost = module.report_row(bakery, english)
    assert lost == []


def test_a_changed_number_and_a_dropped_landmark_are_flagged() -> None:
    module = _load()
    bakery = next(s for s in CLIP_SPECS if s.id == "kn-bakery")
    english = "Third cross, fifth main, gate number two, near the shop"
    _, lost = module.report_row(bakery, english)
    assert lost == ["gate 4", "landmark bakery"]


def test_every_clip_declares_its_intended_facts() -> None:
    assert all(spec.facts for spec in CLIP_SPECS)
