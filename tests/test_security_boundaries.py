import asyncio
import socket

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes import capture
from app.api.routes import auth as auth_routes
from app.middleware.security import RequestSecurityMiddleware
from app.models.capture_package import CapturePackage
from app.services import auth, database, outbound_security, raw_storage


def test_capture_id_rejects_path_traversal_but_keeps_legacy_ids():
    assert CapturePackage(capture_id="test_capture_001").capture_id == "test_capture_001"
    with pytest.raises(ValidationError):
        CapturePackage(capture_id="../../users/admin")


def test_raw_storage_path_stays_beneath_user_root(tmp_path, monkeypatch):
    monkeypatch.setattr(raw_storage, "CONTENTS_DIR", tmp_path)
    expected = tmp_path / "users" / "user-a" / "raw" / "capture_001"
    assert raw_storage._raw_dir("user-a", "capture_001") == expected.resolve()
    with pytest.raises(ValueError):
        raw_storage._raw_dir("user-a", "../user-b")


def test_snapshot_requires_owned_capture_and_is_sandboxed(monkeypatch):
    monkeypatch.setattr(capture, "get_capture_ref", lambda user_id, capture_id: {"id": capture_id})
    monkeypatch.setattr(capture, "get_raw_html", lambda *_: "<script>parent.document.body.textContent='owned'</script>")
    response = capture.get_capture_html("capture_001", {"user_id": "user-a"})
    assert "sandbox" in response.headers["content-security-policy"]
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"

    monkeypatch.setattr(capture, "get_capture_ref", lambda *_: None)
    with pytest.raises(HTTPException) as error:
        capture.get_capture_html("capture_001", {"user_id": "user-b"})
    assert error.value.status_code == 404


def test_provider_url_blocks_private_network_and_credentials(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80)),
    ])
    with pytest.raises(outbound_security.UnsafeProviderURL):
        outbound_security.validate_provider_url("http://provider.example/v1")
    assert outbound_security.validate_provider_url("http://provider.example/v1", allow_private=True) == "http://provider.example/v1"
    with pytest.raises(outbound_security.UnsafeProviderURL):
        outbound_security.validate_provider_url("https://user:pass@provider.example/v1", allow_private=True)


def test_non_admin_provider_is_bound_to_known_public_host(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.18.3.2", 443)),
    ])
    assert outbound_security.validate_provider_destination(
        "https://openrouter.ai/api/v1", "openrouter", is_admin=False,
    ) == "https://openrouter.ai/api/v1"
    with pytest.raises(outbound_security.UnsafeProviderURL):
        outbound_security.validate_provider_destination(
            "https://attacker.example/api/v1", "openrouter", is_admin=False,
        )


def test_token_scope_and_version_are_enforced(monkeypatch):
    account = {"id": "user-a", "username": "coder", "token_version": 2}
    monkeypatch.setattr(auth, "get_user_by_id", lambda *_: account)
    extension_token = auth.create_token("user-a", "coder", scope="extension")
    payload = auth.decode_token(extension_token)
    assert auth._principal(payload, {"user"}) is None
    assert auth._principal(payload, {"extension"})["user_id"] == "user-a"
    account["token_version"] = 3
    assert auth._principal(payload, {"extension"}) is None


def test_password_boundary_handles_bcrypt_limit_without_server_error():
    password_hash = auth.hash_password("correct horse battery staple")
    assert auth.verify_password("x" * 73, password_hash) is False
    assert auth.password_is_supported("x" * 72)
    assert not auth.password_is_supported("x" * 73)


def test_web_session_switches_only_between_authenticated_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "USERS_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(database, "USERS_DATA_DIR", tmp_path / "users")
    first = database.create_user_in_db("owner", "hash", is_admin=True)
    second = database.create_user_in_db("member", "hash")
    database.create_web_session("secret", first, 3600)
    assert database.get_web_session_user("secret")["id"] == first
    assert not database.switch_web_session_account("secret", second)
    assert database.add_web_session_account("secret", second, 3600)
    assert database.get_web_session_user("secret")["id"] == second
    assert database.switch_web_session_account("secret", first)
    assert database.web_session_binding_matches(database.web_session_binding("secret"), first)
    assert not database.web_session_binding_matches(database.web_session_binding("secret"), second)


def test_request_middleware_rejects_cross_origin_cookie_and_large_body(monkeypatch):
    monkeypatch.setattr("app.middleware.security.MAX_REQUEST_BYTES", 4)
    called = []

    async def app(_scope, receive, send):
        called.append(await receive())
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def run(headers, body=b""):
        sent = []
        messages = iter([{"type": "http.request", "body": body, "more_body": False}])

        async def receive():
            return next(messages)

        async def send(message):
            sent.append(message)

        await RequestSecurityMiddleware(app)(
            {"type": "http", "method": "POST", "scheme": "http", "headers": headers},
            receive,
            send,
        )
        return sent[0]["status"]

    cross_origin = asyncio.run(run([
        (b"host", b"localhost:5000"),
        (b"origin", b"https://evil.example"),
        (b"cookie", b"nodecast_token=secret"),
    ]))
    too_large = asyncio.run(run([(b"host", b"localhost:5000")], b"12345"))
    allowed = asyncio.run(run([(b"host", b"localhost:5000")], b"1234"))
    assert (cross_origin, too_large, allowed) == (403, 413, 204)
    assert called[-1]["body"] == b"1234"


def test_request_middleware_allows_the_current_local_origin_with_a_lan_public_origin(monkeypatch):
    monkeypatch.setenv("NODECAST_PUBLIC_ORIGIN", "http://192.168.8.116:5000")

    async def app(_scope, _receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def run(origin):
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await RequestSecurityMiddleware(app)(
            {
                "type": "http",
                "method": "POST",
                "scheme": "http",
                "headers": [
                    (b"host", b"localhost:5000"),
                    (b"origin", origin.encode()),
                    (b"cookie", b"nodecast_token=secret"),
                ],
            },
            receive,
            send,
        )
        return sent[0]["status"]

    assert asyncio.run(run("http://localhost:5000")) == 204
    assert asyncio.run(run("https://evil.example")) == 403


def test_request_middleware_allows_extension_pairing_exchange_only(monkeypatch):
    monkeypatch.delenv("NODECAST_PUBLIC_ORIGIN", raising=False)

    async def app(_scope, _receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def run(path, *, bearer=False):
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        headers = [
            (b"host", b"localhost:5000"),
            (b"origin", b"moz-extension://nodecast-test"),
            (b"cookie", b"nodecast_token=secret"),
        ]
        if bearer:
            headers.append((b"authorization", b"Bearer extension-token"))

        await RequestSecurityMiddleware(app)(
            {
                "type": "http",
                "method": "POST",
                "scheme": "http",
                "path": path,
                "headers": headers,
            },
            receive,
            send,
        )
        return sent[0]["status"]

    assert asyncio.run(run("/api/extension/exchange")) == 204
    assert asyncio.run(run("/api/capture")) == 403
    assert asyncio.run(run("/api/capture", bearer=True)) == 204


def test_request_middleware_does_not_read_get_body(monkeypatch):
    called = []

    async def app(_scope, _receive, send):
        called.append(True)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        raise AssertionError("GET middleware must not wait for a request body")

    async def run():
        sent = []

        async def send(message):
            sent.append(message)

        await RequestSecurityMiddleware(app)(
            {"type": "http", "method": "GET", "scheme": "http", "headers": [(b"host", b"localhost:5000")]},
            receive,
            send,
        )
        return sent[0]["status"]

    assert asyncio.run(run()) == 204
    assert called == [True]


def test_auth_rate_limit_prunes_expired_keys(monkeypatch):
    auth_routes._attempts.clear()
    auth_routes._attempts["old"] = [0.0]
    monkeypatch.setattr(auth_routes.time, "monotonic", lambda: 1000.0)
    auth_routes._check_rate_limit("current")
    assert "old" not in auth_routes._attempts
