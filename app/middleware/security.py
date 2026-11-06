"""Small ASGI security boundaries shared by every API route."""
import os
import re
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.core.security import MAX_REQUEST_BYTES


def _is_extension_origin(origin: str) -> bool:
    parsed = urlsplit(origin)
    return parsed.scheme in {"chrome-extension", "moz-extension"} and bool(parsed.netloc)


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
                # A local installation may intentionally be reached through
                # localhost and its LAN address.  The configured public origin
                # remains trusted, but the request's own Host is also a valid
                # same-origin browser surface.  Do not turn a LAN preference
                # into a CSRF block for the local address.
                allowed_origins = {f"{scheme}://{host}".rstrip("/")}
                if configured:
                    allowed_origins.add(configured)
                is_pairing_exchange = scope.get("path") == "/api/extension/exchange"
                path = scope.get("path", "")
                is_extension_capture = (
                    ((method == "POST" and path == "/api/capture") or
                     (method == "PUT" and re.fullmatch(r"/api/capture/[A-Za-z0-9_-]{12,64}/reason", path)))
                    and headers.get("authorization", "").lower().startswith("bearer ")
                )
                # Browser extensions exchange a short-lived, one-time pairing
                # code from their own origin.  Chrome may attach the local
                # Nodecast cookie to that request, but the response identity is
                # still bound solely to the pairing code.  Permit only this
                # narrow, explicitly recognised extension-origin flow.
                if (
                    origin.rstrip("/") not in allowed_origins
                    and not (
                        _is_extension_origin(origin)
                        and (is_pairing_exchange or is_extension_capture)
                    )
                ):
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
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            # StreamingResponse listens on receive() for http.disconnect after
            # the request body has been consumed. Returning an immediate empty
            # http.request here creates a tight loop that starves the event
            # loop, stalls the stream, and blocks unrelated API requests.
            return await receive()

        await self.app(scope, replay_receive, send)
