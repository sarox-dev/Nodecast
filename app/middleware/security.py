"""Small ASGI security boundaries shared by every API route."""
import os

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.core.security import MAX_REQUEST_BYTES


class RequestSecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_BYTES:
                    await JSONResponse({"detail": "Request body is too large"}, status_code=413)(scope, receive, send)
                    return
            except ValueError:
                await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(scope, receive, send)
                return

        method = scope.get("method", "GET").upper()
        if method in {"POST", "PUT", "PATCH", "DELETE"} and "nodecast_token=" in headers.get("cookie", ""):
            origin = headers.get("origin")
            if origin:
                configured = os.getenv("NODECAST_PUBLIC_ORIGIN", "").rstrip("/")
                host = headers.get("host", "")
                scheme = scope.get("scheme", "http")
                expected = configured or f"{scheme}://{host}"
                if origin.rstrip("/") != expected:
                    await JSONResponse({"detail": "Cross-origin request rejected"}, status_code=403)(scope, receive, send)
                    return

        # Reading receive() eagerly for bodyless requests can block Uvicorn:
        # GET/HEAD/OPTIONS do not have to emit an http.request body event.
        if method not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        chunks = []
        received = 0
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] != "http.request":
                await self.app(scope, receive, send)
                return
            chunk = message.get("body", b"")
            received += len(chunk)
            if received > MAX_REQUEST_BYTES:
                await JSONResponse({"detail": "Request body is too large"}, status_code=413)(scope, receive, send)
                return
            chunks.append(chunk)
            more_body = message.get("more_body", False)

        replayed = False

        async def replay_receive():
            nonlocal replayed
            if replayed:
                return {"type": "http.request", "body": b"", "more_body": False}
            replayed = True
            return {"type": "http.request", "body": b"".join(chunks), "more_body": False}

        await self.app(scope, replay_receive, send)
