from __future__ import annotations

from typing import Any

from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

MAX_BODY_BYTES = 8 * 1024


class BodySizeLimit:
    """Rejette les requêtes HTTP dont le corps dépasse ``max_bytes`` octets réels."""

    def __init__(self, app: Any, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] != "http.request":
                break
            body.extend(message.get("body", b""))
            more_body = message.get("more_body", False)
            if len(body) > self.max_bytes:
                response = JSONResponse({"detail": "Requête trop volumineuse."}, status_code=413)
                await response(scope, receive, send)
                return

        replayed = False

        async def buffered_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, buffered_receive, send)
