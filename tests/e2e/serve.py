"""Serve the real FastAPI app (and so the real static UI) for the Playwright check.

The browser test intercepts /turn, so Gnani and the model are never reached: the translator is a
stub and the Gnani key is a dummy. Run: uv run --no-sync python tests/e2e/serve.py
"""

import uvicorn
from pydantic import SecretStr

from saathi.app import create_app
from saathi.config import Settings

PORT = 8765


class StubTranslator:
    def translate(self, text: str, src: str, tgt: str) -> str:
        raise AssertionError("the e2e test must intercept /turn")


if __name__ == "__main__":
    app = create_app(Settings(gnani_api_key=SecretStr("dummy")), translator=StubTranslator())
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
