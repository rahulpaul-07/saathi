import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from huggingface_hub.errors import GatedRepoError

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_models.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fetch_models", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_route_is_fetched_at_its_pinned_revision(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load()
    fetched: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module, "snapshot_download", lambda repo_id, revision: fetched.append((repo_id, revision))
    )
    assert module.main() == 0
    assert fetched == [
        (repo, module.MODEL_REVISIONS[repo]) for repo in module.ROUTE_MODELS.values()
    ]
    assert "models ready" in capsys.readouterr().out


def test_a_gated_repo_stops_with_an_instruction_and_no_error_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load()

    def refuse(repo_id: str, revision: str) -> None:
        raise GatedRepoError("401 secret-looking detail")

    monkeypatch.setattr(module, "snapshot_download", refuse)
    assert module.main() == 1
    err = capsys.readouterr().err
    assert "HF_TOKEN" in err and "gated" in err
    assert "secret-looking" not in err
