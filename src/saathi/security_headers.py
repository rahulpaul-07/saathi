"""Content-Security-Policy on every response.

Pure ASGI rather than BaseHTTPMiddleware so the SSE streams are passed through untouched.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def content_security_policy(allow_same_origin_frames: bool) -> str:
    """The policy for the UI.

    `media-src` adds `blob:` because turn audio is fetched with the bearer token and played from an
    object URL; script and style stay `'self'` only (no inline code, no `unsafe-inline`).
    `frame-ancestors` is `'none'` except in demo mode, where /demo.html frames the two room pages.
    """
    ancestors = "'self'" if allow_same_origin_frames else "'none'"
    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self'",
            "object-src 'none'",
            "base-uri 'none'",
            f"frame-ancestors {ancestors}",
            "media-src 'self' blob:",
        ]
    )


class CspMiddleware:
    def __init__(self, app: ASGIApp, policy: str) -> None:
        self._app = app
        self._policy = policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_csp(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Content-Security-Policy"] = self._policy
            await send(message)

        await self._app(scope, receive, send_with_csp)
