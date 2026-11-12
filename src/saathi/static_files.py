"""The UI files, served so that a browser checks for a newer copy before it reuses one."""

import os

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class RevalidatedStaticFiles(StaticFiles):
    """Static files sent with `Cache-Control: no-cache`.

    The pages, scripts and styles keep fixed names, so a browser that held them for a heuristic
    period could pair a new page with an old script after a deploy. `no-cache` still lets it keep a
    copy: it asks with the ETag first and gets an empty 304 when nothing changed.
    """

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        # Also set on a 304: the answer to a revalidation carries the policy of the copy it keeps.
        response.headers["Cache-Control"] = "no-cache"
        return response
