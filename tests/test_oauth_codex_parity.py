"""Integration tests for the Codex-CLI-parity OAuth changes.

Covers the three specific bug-fix surfaces:
  1. Callback handler emits Connection: close + the success body.
  2. GET /cancel marks state and frees the port.
  3. _bind_with_cancel_retry recovers from a held port (when the holder
     is one of our own callback servers honoring /cancel).
"""
from __future__ import annotations
import socket
import threading
import time
from http.client import HTTPConnection

import pytest

from quantclaw.dashboard import oauth


def _free_port() -> int:
    """Return a probably-free TCP port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_handler_server(provider_id: str, port: int) -> tuple[oauth.HTTPServer, threading.Thread]:
    """Bind a callback server bound to (provider_id, port) and start the
    same serve loop ``start_oauth_flow`` uses, so we exercise the real code path."""
    handler = type(
        f"Handler_{provider_id}_{port}",
        (oauth._OAuthCallbackHandler,),
        {"provider_id": provider_id, "code_verifier": "test-verifier"},
    )
    server = oauth._ReusableHTTPServer(("127.0.0.1", port), handler)
    oauth._active_servers[provider_id] = server
    oauth._auth_state[provider_id] = {"status": "waiting", "state": "test-state"}

    def loop():
        deadline = time.time() + 10
        server.timeout = 0.2
        while time.time() < deadline:
            if oauth._active_servers.get(provider_id) is not server:
                break
            status = oauth._auth_state.get(provider_id, {}).get("status")
            if status in ("code_received", "completed", "error", "canceled"):
                break
            server.handle_request()
        try:
            server.server_close()
        except Exception:
            pass

    t = threading.Thread(target=loop, daemon=True)
    oauth._active_threads[provider_id] = t
    t.start()
    return server, t


@pytest.fixture(autouse=True)
def _clean_oauth_state():
    """Each test gets a clean module-global oauth state."""
    oauth._auth_state.clear()
    oauth._active_servers.clear()
    oauth._active_threads.clear()
    yield
    # Tear down anything still listening so the next test gets clean ports.
    for pid in list(oauth._active_servers.keys()):
        oauth._stop_callback_server(pid)


def test_callback_response_has_connection_close_and_success_body():
    """Without Connection: close, the browser keeps the socket parked,
    blocking the serve loop's next tick — was the silent-failure root cause."""
    provider_id = "openai"
    port = _free_port()
    _start_handler_server(provider_id, port)

    conn = HTTPConnection("127.0.0.1", port, timeout=2)
    conn.request("GET", "/auth/callback?code=DUMMY&state=test-state")
    resp = conn.getresponse()
    body = resp.read()

    assert resp.status == 200
    assert resp.getheader("Connection", "").lower() == "close"
    assert b"Authorization successful" in body
    assert oauth._auth_state[provider_id]["status"] == "code_received"
    assert oauth._auth_state[provider_id]["code"] == "DUMMY"
    conn.close()


def test_cancel_endpoint_sets_canceled_status_and_frees_port():
    """GET /cancel is the cross-process knock that lets a sibling instance
    recover from a stuck server. It must mark state canceled and let the
    serve loop exit so the port is freed."""
    provider_id = "openai"
    port = _free_port()
    server, thread = _start_handler_server(provider_id, port)

    conn = HTTPConnection("127.0.0.1", port, timeout=2)
    conn.request("GET", "/cancel")
    resp = conn.getresponse()
    body = resp.read()
    assert resp.status == 200
    assert b"ok" in body
    conn.close()

    # The serve loop checks _active_servers each iteration — after /cancel
    # pops it, the loop should exit and close the socket within ~200ms.
    thread.join(timeout=3.0)
    assert not thread.is_alive(), "serve loop did not exit after /cancel"
    assert oauth._auth_state[provider_id]["status"] == "canceled"

    # Port must be free now — bind succeeds without retry.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
    finally:
        s.close()


def test_bind_with_cancel_retry_recovers_when_incumbent_yields():
    """Two QuantClaw flows on the same port: the second should ask the
    first to /cancel and successfully bind on retry. Mirrors the
    Codex-CLI-with-Codex-CLI scenario the user actually hits."""
    provider_id = "openai"
    port = _free_port()
    _start_handler_server(provider_id, port)

    handler = type(
        f"Handler2_{port}",
        (oauth._OAuthCallbackHandler,),
        {"provider_id": "openai-2", "code_verifier": "v2"},
    )

    t0 = time.time()
    server2 = oauth._bind_with_cancel_retry(port, handler)
    elapsed = time.time() - t0

    assert server2 is not None, "bind_with_cancel_retry returned None — incumbent didn't yield"
    # Should succeed within a few retries; cap loosely under the full
    # 10×200ms budget so we'd notice if it's actually exhausting.
    assert elapsed < 2.5, f"bind retry took too long: {elapsed:.2f}s"
    server2.server_close()


def test_bind_with_cancel_retry_returns_none_when_every_attempt_fails(monkeypatch):
    """When bind keeps raising OSError (e.g. port held by a process that
    doesn't honor /cancel), retry exhausts and returns None rather than
    propagating, so ``start_oauth_flow`` can surface a friendly error.

    We mock ``_ReusableHTTPServer`` to always raise rather than relying
    on real socket contention — Windows ``SO_REUSEADDR`` semantics let
    two sockets coexist on the same port, so a real-socket blocker test
    is not portable.
    """
    def _always_oserror(*args, **kwargs):
        raise OSError(98, "Address already in use")

    monkeypatch.setattr(oauth, "_ReusableHTTPServer", _always_oserror)
    monkeypatch.setattr(oauth, "_BIND_RETRY_ATTEMPTS", 3)
    monkeypatch.setattr(oauth, "_BIND_RETRY_DELAY_S", 0.01)

    handler = type("HandlerBlocked", (oauth._OAuthCallbackHandler,), {"provider_id": "x", "code_verifier": "v"})
    result = oauth._bind_with_cancel_retry(_free_port(), handler)
    assert result is None


def test_bind_with_cancel_retry_first_call_does_not_send_premature_cancel(monkeypatch):
    """If the first bind succeeds, we must not have probed /cancel — that
    would needlessly knock down a sibling process on a totally different
    port assignment. Guards against a future regression where someone
    'helpfully' adds a pre-emptive cancel."""
    cancel_calls: list[int] = []
    monkeypatch.setattr(oauth, "_send_cancel_to_port", lambda port: cancel_calls.append(port))

    handler = type("HandlerCleanBind", (oauth._OAuthCallbackHandler,), {"provider_id": "y", "code_verifier": "v"})
    server = oauth._bind_with_cancel_retry(_free_port(), handler)
    try:
        assert server is not None
        assert cancel_calls == [], f"unexpected /cancel probes: {cancel_calls}"
    finally:
        if server is not None:
            server.server_close()
