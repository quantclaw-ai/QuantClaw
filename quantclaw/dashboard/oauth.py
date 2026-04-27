"""OAuth flows for AI model providers (OpenAI, Anthropic, Google Gemini)."""
from __future__ import annotations
import asyncio
import hashlib
import base64
import logging
import os
import secrets
import json
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from typing import Optional
import time

import httpx

logger = logging.getLogger(__name__)


class _ReusableHTTPServer(HTTPServer):
    """HTTPServer that re-binds cleanly after a previous flow exits.

    Without ``allow_reuse_address`` the port can sit in TIME_WAIT for a
    minute or two on Windows after the previous flow's socket closes,
    which silently broke retries (new bind raised OSError in the daemon
    thread, frontend polled forever).
    """

    allow_reuse_address = True

CREDENTIALS_PATH = Path("data/oauth_credentials.json")

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _load_credentials() -> dict:
    if CREDENTIALS_PATH.exists():
        return json.loads(CREDENTIALS_PATH.read_text())
    return {}

def _save_credentials(creds: dict):
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_PATH.write_text(json.dumps(creds, indent=2))


# ── Provider configs ──

PROVIDERS = {
    "openai": {
        "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
        "authorize_url": "https://auth.openai.com/oauth/authorize",
        "token_url": "https://auth.openai.com/oauth/token",
        "redirect_uri": "http://localhost:1455/auth/callback",
        "callback_port": 1455,
        "callback_path": "/auth/callback",
        "scopes": "openid profile email offline_access",
        "extra_params": {
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
        },
        "token_content_type": "form",
    },
    "anthropic": {
        "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e",
        "authorize_url": "https://claude.ai/oauth/authorize",
        "token_url": "https://platform.claude.com/v1/oauth/token",
        "redirect_uri": "http://localhost:53692/callback",
        "callback_port": 53692,
        "callback_path": "/callback",
        "scopes": "org:create_api_key user:profile user:inference",
        "extra_params": {"code": "true"},
        "token_content_type": "json",
    },
    # Google OAuth — read from env. The published Gemini CLI installed-app
    # credentials work here; set them in .env (see .env.example). Empty
    # strings mean "not configured" and the OAuth flow will refuse to start.
    "google": {
        "client_id": os.environ.get("GEMINI_OAUTH_CLIENT_ID", ""),
        "client_secret": os.environ.get("GEMINI_OAUTH_CLIENT_SECRET", ""),
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "redirect_uri": "http://localhost:8085/oauth2callback",
        "callback_port": 8085,
        "callback_path": "/oauth2callback",
        "scopes": "https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile",
        "extra_params": {"access_type": "offline", "prompt": "consent"},
        "token_content_type": "form",
    },
}

# Global state for in-progress auth
_auth_state: dict[str, dict] = {}
# Active callback servers, keyed by provider — kept so we can shut down a
# stale flow before starting a new one (otherwise the new bind hits an
# already-listening socket and fails).
_active_servers: dict[str, HTTPServer] = {}
# Thread refs, keyed by provider — needed so we can ``join`` after popping
# the server, ensuring the listening socket is fully closed before the new
# flow tries to bind to the same port.
_active_threads: dict[str, Thread] = {}


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handles the OAuth redirect callback."""

    provider_id: str = ""
    code_verifier: str = ""

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        code = qs.get("code", [None])[0]

        if code:
            _auth_state[self.provider_id] = {
                "code": code,
                "code_verifier": self.code_verifier,
                "status": "code_received",
                "timestamp": time.time(),
            }
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"""
            <html><body style="background:#030712;color:#f59e0b;display:flex;align-items:center;justify-content:center;height:100vh;font-family:system-ui;flex-direction:column">
            <h1 style="font-size:2rem">&#10003; Authorization successful</h1>
            <p style="color:#9ca3af">You can close this window and return to QuantClaw.</p>
            <script>setTimeout(()=>window.close(),3000)</script>
            </body></html>
            """)
        else:
            error = qs.get("error", ["unknown"])[0]
            _auth_state[self.provider_id] = {"status": "error", "error": error}
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<html><body>Error: {error}</body></html>".encode())

    def log_message(self, format, *args):
        pass  # Suppress server logs


def _stop_callback_server(provider_id: str) -> None:
    """Stop the running callback server and wait for its socket to close.

    The serving thread polls ``_active_servers`` between short
    ``handle_request`` waits; popping the entry causes it to exit and
    close the socket itself on the next tick (≤1s). We then ``join`` the
    thread so the new flow's bind doesn't race against the old socket
    teardown — without this, retries on the same port hit EADDRINUSE on
    Windows even with SO_REUSEADDR set.
    """
    _active_servers.pop(provider_id, None)
    thread = _active_threads.pop(provider_id, None)
    if thread is not None and thread.is_alive():
        thread.join(timeout=3.0)


def start_oauth_flow(provider_id: str) -> dict:
    """Start OAuth flow: generate PKCE, start callback server, return auth URL.

    The dashboard frontend opens the URL in a new tab via ``window.open``
    once it receives this response. We do NOT call ``webbrowser.open``
    here — on Windows that shells out to ShellExecuteW and can block the
    HTTP response for minutes (cold browser starts, profile sync, AV).
    """
    if provider_id not in PROVIDERS:
        return {"error": f"Unknown provider: {provider_id}"}

    # If a previous flow for the same provider is still listening, close it
    # so the new server can bind to the same port. Without this, a retry
    # (or a stale flow from a crashed/canceled previous attempt) would hit
    # OSError and the user would be stuck on "Waiting for authorization…".
    _stop_callback_server(provider_id)

    config = PROVIDERS[provider_id]

    # Generate PKCE
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = _b64url(hashlib.sha256(code_verifier.encode()).digest())
    state = secrets.token_hex(16)

    # Build authorization URL
    params = {
        "client_id": config["client_id"],
        "response_type": "code",
        "redirect_uri": config["redirect_uri"],
        "scope": config["scopes"],
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        **config.get("extra_params", {}),
    }
    auth_url = f"{config['authorize_url']}?{urlencode(params)}"

    # Try to bind synchronously so a port-in-use failure surfaces in the
    # HTTP response instead of dying silently in the background thread.
    handler = type(
        f"Handler_{provider_id}",
        (_OAuthCallbackHandler,),
        {"provider_id": provider_id, "code_verifier": code_verifier},
    )
    try:
        server = _ReusableHTTPServer(("127.0.0.1", config["callback_port"]), handler)
    except OSError as e:
        msg = (
            f"Could not bind OAuth callback server on port "
            f"{config['callback_port']}: {e}. Another process (a previous "
            f"QuantClaw run, Codex CLI, or Claude CLI) may be holding the "
            f"port — close it and try again."
        )
        logger.error(msg)
        _auth_state[provider_id] = {"status": "error", "error": msg}
        return {"error": msg}

    _active_servers[provider_id] = server
    _auth_state[provider_id] = {"status": "waiting", "state": state}

    # Serve in background until either a callback arrives, the flow is
    # canceled, or the 5-min timeout elapses. ``serve_forever`` lets us
    # absorb stray requests (favicon, health-checks) without exiting.
    def run_callback_server():
        deadline = time.time() + 300
        try:
            server.timeout = 1
            while time.time() < deadline:
                if _active_servers.get(provider_id) is not server:
                    break  # we were superseded or canceled
                state_now = _auth_state.get(provider_id, {}).get("status")
                if state_now in ("code_received", "completed", "error"):
                    break
                server.handle_request()
        except Exception as exc:
            logger.exception("OAuth callback server crashed for %s", provider_id)
            _auth_state[provider_id] = {"status": "error", "error": str(exc)}
        finally:
            try:
                server.server_close()
            except Exception:
                pass
            # Only clear if this is still the current server (avoid wiping a
            # newer flow that already replaced us).
            if _active_servers.get(provider_id) is server:
                _active_servers.pop(provider_id, None)
                # If we exited without receiving a code, mark as timed out
                # so the frontend stops spinning.
                if _auth_state.get(provider_id, {}).get("status") == "waiting":
                    _auth_state[provider_id] = {
                        "status": "error",
                        "error": "Authorization timed out — no callback received within 5 minutes.",
                    }

    thread = Thread(target=run_callback_server, daemon=True)
    _active_threads[provider_id] = thread
    thread.start()

    return {
        "status": "ready",
        "provider": provider_id,
        "auth_url": auth_url,
    }


def cancel_oauth_flow(provider_id: str) -> dict:
    """Cancel an in-flight OAuth flow and free the callback port."""
    _stop_callback_server(provider_id)
    if _auth_state.get(provider_id, {}).get("status") == "waiting":
        _auth_state[provider_id] = {"status": "canceled"}
    return {"status": "canceled", "provider": provider_id}


async def exchange_token(provider_id: str) -> dict:
    """Exchange authorization code for access token."""
    if provider_id not in PROVIDERS:
        return {"error": f"Unknown provider: {provider_id}"}

    state = _auth_state.get(provider_id, {})
    if state.get("status") != "code_received":
        return {"error": "No authorization code received yet", "status": state.get("status", "unknown")}

    config = PROVIDERS[provider_id]
    code = state["code"]
    code_verifier = state["code_verifier"]

    # Exchange code for token
    token_data = {
        "grant_type": "authorization_code",
        "client_id": config["client_id"],
        "code": code,
        "redirect_uri": config["redirect_uri"],
        "code_verifier": code_verifier,
    }

    # Anthropic uses state in token exchange
    if provider_id == "anthropic":
        token_data["state"] = code_verifier

    # Google needs client_secret
    if "client_secret" in config:
        token_data["client_secret"] = config["client_secret"]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if config["token_content_type"] == "json":
                resp = await client.post(
                    config["token_url"],
                    json=token_data,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
            else:
                resp = await client.post(
                    config["token_url"],
                    data=token_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

            if resp.status_code != 200:
                return {"error": f"Token exchange failed: {resp.status_code}", "detail": resp.text}

            tokens = resp.json()

            # Save credentials
            creds = _load_credentials()
            cred_data = {
                "access_token": tokens.get("access_token", ""),
                "refresh_token": tokens.get("refresh_token", ""),
                "expires_at": int(time.time() + tokens.get("expires_in", 3600) - 300),
                "provider": provider_id,
            }

            # For Google: resolve identity (personal OAuth — no project discovery)
            if provider_id == "google" and cred_data["access_token"]:
                try:
                    identity = await _resolve_google_identity(cred_data["access_token"])
                    if identity.get("email"):
                        cred_data["email"] = identity["email"]
                except Exception:
                    pass

            creds[provider_id] = cred_data
            _save_credentials(creds)

            # Clear auth state
            _auth_state[provider_id] = {"status": "completed"}

            return {
                "status": "authenticated",
                "provider": provider_id,
                "has_refresh_token": bool(tokens.get("refresh_token")),
            }

    except Exception as e:
        return {"error": str(e)}


async def refresh_token(provider_id: str) -> Optional[str]:
    """Refresh an expired access token. Returns new access token or None."""
    creds = _load_credentials()
    provider_creds = creds.get(provider_id)
    if not provider_creds or not provider_creds.get("refresh_token"):
        return None

    config = PROVIDERS.get(provider_id)
    if not config:
        return None

    token_data = {
        "grant_type": "refresh_token",
        "client_id": config["client_id"],
        "refresh_token": provider_creds["refresh_token"],
    }

    if "client_secret" in config:
        token_data["client_secret"] = config["client_secret"]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if config["token_content_type"] == "json":
                resp = await client.post(config["token_url"], json=token_data,
                    headers={"Content-Type": "application/json", "Accept": "application/json"})
            else:
                resp = await client.post(config["token_url"], data=token_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"})

            if resp.status_code == 200:
                tokens = resp.json()
                provider_creds["access_token"] = tokens["access_token"]
                provider_creds["expires_at"] = int(time.time() + tokens.get("expires_in", 3600) - 300)
                if tokens.get("refresh_token"):
                    provider_creds["refresh_token"] = tokens["refresh_token"]
                _save_credentials(creds)
                return tokens["access_token"]
    except Exception:
        pass

    return None


async def _resolve_google_identity(access_token: str) -> dict:
    """Resolve Google user identity after OAuth (personal mode — skip project discovery per OpenClaw PR #61260)."""
    result = {"email": ""}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v1/userinfo?alt=json",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code == 200:
                result["email"] = resp.json().get("email", "")
    except Exception:
        pass
    return result


def get_access_token(provider_id: str) -> Optional[str]:
    """Get stored access token for a provider, or None if not authenticated."""
    creds = _load_credentials()
    provider_creds = creds.get(provider_id)
    if not provider_creds:
        return None
    return provider_creds.get("access_token")


def get_auth_status(provider_id: str) -> dict:
    """Check if a provider is authenticated."""
    creds = _load_credentials()
    provider_creds = creds.get(provider_id)

    if not provider_creds:
        # Check if auth flow is in progress
        flow_state = _auth_state.get(provider_id, {})
        return {
            "authenticated": False,
            "flow_status": flow_state.get("status", "none"),
            "error": flow_state.get("error"),
        }

    expired = provider_creds.get("expires_at", 0) < time.time()
    return {
        "authenticated": True,
        "expired": expired,
        "has_refresh_token": bool(provider_creds.get("refresh_token")),
        "provider": provider_id,
    }


def disconnect_provider(provider_id: str) -> dict:
    """Remove stored credentials for a provider."""
    creds = _load_credentials()
    if provider_id in creds:
        del creds[provider_id]
        _save_credentials(creds)
    if provider_id in _auth_state:
        del _auth_state[provider_id]
    return {"status": "disconnected", "provider": provider_id}
