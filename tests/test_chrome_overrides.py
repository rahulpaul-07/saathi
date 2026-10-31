"""Hand-written interface text wins over the generated table and survives regeneration."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from saathi.chrome import CHROME, ENGLISH
from saathi.chrome_overrides import OVERRIDES, Table, apply_overrides

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "gen_chrome.py"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_chrome", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_an_override_replaces_the_generated_text_and_leaves_the_input_alone() -> None:
    generated: Table = {"hi": {"a": ("generated", "pending"), "b": ("kept", "reviewed")}}
    by_hand: Table = {"hi": {"a": ("by hand", "pending")}, "kn": {"c": ("x", "pending")}}
    merged = apply_overrides(generated, by_hand)
    assert merged["hi"] == {"a": ("by hand", "pending"), "b": ("kept", "reviewed")}
    assert merged["kn"] == {"c": ("x", "pending")}
    assert generated["hi"]["a"] == ("generated", "pending")


def test_the_live_table_shows_every_override_even_when_the_data_file_disagrees() -> None:
    for code, strings in OVERRIDES.items():
        for key, (text, status) in strings.items():
            assert key in ENGLISH, (code, key)
            assert (CHROME[code][key].text, CHROME[code][key].review_status) == (text, status)


class _Generated:
    """Stands in for the model: every string comes back as the word GENERATED."""

    def load(self, models: tuple[str, ...]) -> None:
        return None

    def translate(self, text: str, src: str, tgt: str) -> str:
        return "GENERATED"


def test_regenerating_never_overwrites_a_hand_written_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generator: Any = _load_generator()
    monkeypatch.setattr(generator, "RoutingTranslator", _Generated)
    monkeypatch.setattr(generator, "DATA", tmp_path / "chrome_data.py")
    monkeypatch.setattr(generator, "REPORT", tmp_path / "report.json")
    monkeypatch.setattr(generator, "TRANSLATED", {})
    monkeypatch.setattr(generator, "OVERRIDES", {"hi": {"choose_a_clip": ("by hand", "pending")}})

    assert generator.main() == 0

    written = (tmp_path / "chrome_data.py").read_text(encoding="utf-8")
    assert '"choose_a_clip": ("by hand", "pending")' in written
    hindi_block = written.split('"hi": {')[1].split("    },")[0]
    assert hindi_block.count("GENERATED") == len(ENGLISH) - 1  # every other string was generated
    rows = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["rows"]
    assert not [r for r in rows if r["lang"] == "hi" and r["key"] == "choose_a_clip"]


@pytest.mark.parametrize("code", ["bn", "hi"])
def test_the_author_reviewed_the_choose_a_clip_text_in_bengali_and_hindi(code: str) -> None:
    assert OVERRIDES[code]["choose_a_clip"][1] == "reviewed"
    assert CHROME[code]["choose_a_clip"].review_status == "reviewed"
