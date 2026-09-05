"""xAI OAuth credential lifecycle — acquisition, storage, rotation (spec 050).

Constitution §1 as amended 2026-09-04 ([ADR 0007](../../../docs/adr/0007-xai-runtime-provider.md))
sanctions xAI as chain tier 3, authenticated by a **subscription** OAuth token
rather than an API key. xAI does not document that flow; the shape implemented
here is the one Kilo Code ships in the open (``packages/opencode/src/plugin/xai.ts``
in Kilo-Org/kilocode), which in turn reuses the public Grok-CLI desktop client
that xAI's auth server allowlists.

Two grants, both landing in the same credential store:

* **Device code** (RFC 8628) — the default. Needs no inbound path to this
  process, which is what makes it the right primary for a Docker-first repo:
  ``127.0.0.1:56121`` inside the backend container is not the operator's
  browser loopback, and the redirect URI is fixed by the client registration
  so it cannot be re-pointed at the host.
* **Loopback PKCE** — the opt-in for logging in from a host that has a browser.

This module deliberately knows nothing about chat completions; the transport
lives in :mod:`law_ai.core.xai` and provider selection in
:mod:`law_ai.core.llm.router`.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import fcntl
import hashlib
import json
import logging
import math
import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpx

from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("law_ai.core.xai_oauth")

PROVIDER_NAME = "xai"

#: Public Grok-CLI desktop client. xAI's auth server rejects this flow from
#: non-allowlisted clients, so — like every other open implementation — we
#: reuse the client id xAI ships for desktop OAuth rather than registering our
#: own (spec 050 NG4). xAI can revoke it at any time; that degrades to an
#: ordinary tier failure, never a 500 (NFR-COMPAT-1).
CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
SCOPE = "openid profile email offline_access grok-cli:access api:access"

DEVICE_CODE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

#: The loopback redirect is part of the client's registration, so the host and
#: port are not ours to choose.
OAUTH_HOST = "127.0.0.1"
OAUTH_PORT = 56121
OAUTH_REDIRECT_PATH = "/callback"
REDIRECT_URI = f"http://{OAUTH_HOST}:{OAUTH_PORT}{OAUTH_REDIRECT_PATH}"

#: Refresh a little before the token actually dies so a single long tool call
#: does not have to recover from a mid-flight 401.
ACCESS_TOKEN_REFRESH_SKEW_S = 120.0

# Device-code polling bounds (RFC 8628 §3.5).
_DEVICE_DEFAULT_INTERVAL_S = 5.0
_DEVICE_MIN_INTERVAL_S = 1.0
_DEVICE_SLOW_DOWN_INCREMENT_S = 5.0
_DEVICE_DEFAULT_EXPIRES_S = 300.0

_TOKEN_REQUEST_TIMEOUT_S = 30.0
_LOOPBACK_TIMEOUT_S = 300.0

#: Collapses concurrent refreshes inside one process before they reach the
#: cross-process file lock. The file lock is the load-bearing guard; this just
#: avoids a stampede of coroutines queueing on it.
_refresh_lock = asyncio.Lock()


class XaiAuthError(RuntimeError):
    """Raised when no usable xAI credential can be obtained.

    Never carries a token value: the message reaches logs and the health
    endpoint (NFR-SEC-1).
    """


@dataclass(frozen=True)
class Credentials:
    """One xAI OAuth credential set. ``expires_at`` is a Unix timestamp."""

    access: str
    refresh: str
    expires_at: float

    def is_expiring(self, skew_s: float = ACCESS_TOKEN_REFRESH_SKEW_S) -> bool:
        """True when this credential should be refreshed before the next call.

        Two independent signals, because neither is reliable alone: the stored
        deadline (xAI does not always return ``expires_in``) and the access
        token's own ``exp`` claim (absent on opaque, non-JWT tokens).
        """
        if self.expires_at <= time.time() + max(0.0, skew_s):
            return True
        return _jwt_is_expiring(self.access, skew_s)


@dataclass(frozen=True)
class DeviceCode:
    """The device-authorization response the operator acts on."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None = None
    expires_in: float | None = None
    interval: float | None = None

    @property
    def browser_url(self) -> str:
        """The URL to open — the pre-filled one when xAI supplied it."""
        return self.verification_uri_complete or self.verification_uri


# ---------------------------------------------------------------------------
# Endpoints (overridable so tests never touch the network)
# ---------------------------------------------------------------------------


def auth_base_url() -> str:
    return str(getattr(settings, "XAI_AUTH_BASE_URL", "https://auth.x.ai")).rstrip("/")


def authorize_url() -> str:
    return f"{auth_base_url()}/oauth2/authorize"


def token_url() -> str:
    return f"{auth_base_url()}/oauth2/token"


def device_authorization_url() -> str:
    return f"{auth_base_url()}/oauth2/device/code"


def _form_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "User-Agent": "law-ai",
    }


# ---------------------------------------------------------------------------
# JWT helper — scheduling only, never a trust decision
# ---------------------------------------------------------------------------


def _jwt_is_expiring(token: str, skew_s: float) -> bool:
    """True iff *token* is a JWT whose ``exp`` falls inside the skew window.

    The signature is deliberately **not** verified. The only thing this value
    decides is whether to refresh early; someone able to forge it wins nothing
    but an unnecessary token request. Anything that is not a decodable JWT
    returns ``False``, which defers to the stored deadline and, ultimately, to
    the reactive 401 path in :mod:`law_ai.core.xai`.
    """
    parts = token.split(".")
    if len(parts) < 2:
        return False
    payload = parts[1].replace("-", "+").replace("_", "/")
    payload += "=" * (-len(payload) % 4)
    try:
        claims = json.loads(base64.b64decode(payload).decode("utf-8"))
    except Exception:
        return False
    exp = claims.get("exp") if isinstance(claims, dict) else None
    if not isinstance(exp, (int, float)):
        return False
    return float(exp) <= time.time() + max(0.0, skew_s)


def _positive_seconds(value: Any, default: float) -> float:
    """Normalize a server-supplied seconds value, rejecting NaN/None/negatives.

    Without this a ``NaN`` interval slips through ``or default`` (NaN is a
    float), reaches ``sleep(NaN)`` and busy-loops until the hard deadline.
    """
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(seconds) or seconds <= 0:
        return default
    return seconds


# ---------------------------------------------------------------------------
# Credential store
# ---------------------------------------------------------------------------


def credentials_path() -> Path:
    """Where the rotating credential set lives (``XAI_CREDENTIALS_PATH``).

    Relative paths resolve against the process cwd — ``/app`` in Docker, which
    is ``./backend`` on the host — the same convention ``AUDIT_PATH`` uses, so
    a login inside the container lands in the mounted ``backend/.xai/``.
    """
    configured = (
        str(getattr(settings, "XAI_CREDENTIALS_PATH", "") or "").strip()
        or ".xai/credentials.json"
    )
    return Path(configured)


def _env_seed() -> Credentials | None:
    """Credentials supplied directly by settings, for deployments without a file.

    Lets CI or a container image inject a token set without running the login
    flow. The file, once written, wins — it is the one that stays current as
    xAI rotates the refresh token.
    """
    access = str(getattr(settings, "XAI_ACCESS_TOKEN", "") or "").strip()
    refresh = str(getattr(settings, "XAI_REFRESH_TOKEN", "") or "").strip()
    if not refresh:
        return None
    # No stored deadline for a seeded pair: treat it as already expiring so the
    # first use refreshes and writes a real file with a real expiry.
    return Credentials(access=access, refresh=refresh, expires_at=0.0)


def load_credentials() -> Credentials | None:
    """Read the stored credential set, falling back to the settings seed."""
    path = credentials_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _env_seed()
    if not isinstance(raw, dict):
        return _env_seed()
    refresh = str(raw.get("refresh") or "")
    if not refresh:
        return _env_seed()
    return Credentials(
        access=str(raw.get("access") or ""),
        refresh=refresh,
        expires_at=float(raw.get("expires_at") or 0.0),
    )


def save_credentials(creds: Credentials) -> None:
    """Persist *creds* atomically at mode 0600 (NFR-SEC-1).

    Written to a temp file in the same directory and ``os.replace``d, so a
    crash mid-write can never leave a half-token behind for another process
    to read.
    """
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    payload = {
        "access": creds.access,
        "refresh": creds.refresh,
        "expires_at": creds.expires_at,
    }
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def is_configured() -> bool:
    """True iff some credential set is available to try."""
    return load_credentials() is not None


def unconfigured_reason() -> str | None:
    """Explain the absence of a credential, for the router and the dashboard."""
    if is_configured():
        return None
    return (
        "no xAI credentials (run `make xai-login`, or set XAI_REFRESH_TOKEN); "
        "the chain will fall back to Ollama"
    )


# ---------------------------------------------------------------------------
# Refresh (cross-process single-flight)
# ---------------------------------------------------------------------------


def _lock_path() -> Path:
    # A sibling lock file, never the credentials file itself: save_credentials
    # replaces that path, so a lock held on its inode would guard nothing.
    path = credentials_path()
    return path.with_name(f"{path.name}.lock")


def _acquire_lock() -> Any:
    """Take the exclusive cross-process refresh lock (blocking)."""
    lock_file = _lock_path()
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_file, "a+")  # noqa: SIM115 - released by _release_lock
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except OSError:
        handle.close()
        raise
    return handle


def _release_lock(handle: Any) -> None:
    with contextlib.suppress(OSError):
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    with contextlib.suppress(OSError):
        handle.close()


async def _post_token(data: dict[str, str]) -> dict[str, Any]:
    """POST the token endpoint and return the parsed body.

    Error bodies are surfaced without the request form, so a refresh token can
    never reach a log line through an exception message (NFR-SEC-1).
    """
    async with httpx.AsyncClient(timeout=_TOKEN_REQUEST_TIMEOUT_S) as client:
        response = await client.post(token_url(), data=data, headers=_form_headers())
    if response.status_code >= 400:
        detail = response.text[:200] if response.text else ""
        raise XaiAuthError(
            f"xAI token request failed ({response.status_code})"
            + (f": {detail}" if detail else "")
        )
    body = response.json()
    if not isinstance(body, dict):
        raise XaiAuthError("xAI token response was not a JSON object")
    return body


def _credentials_from_token_response(
    body: dict[str, Any], *, previous_refresh: str = ""
) -> Credentials:
    """Build a credential set from a token response, keeping the old refresh
    token when xAI did not rotate one in."""
    access = str(body.get("access_token") or "")
    if not access:
        raise XaiAuthError("xAI token response carried no access_token")
    refresh = str(body.get("refresh_token") or "") or previous_refresh
    if not refresh:
        raise XaiAuthError("xAI token response carried no refresh_token")
    expires_in = _positive_seconds(body.get("expires_in"), 3600.0)
    return Credentials(
        access=access, refresh=refresh, expires_at=time.time() + expires_in
    )


async def refresh_credentials(
    current: Credentials, *, stale_access: str | None = None
) -> Credentials:
    """Exchange the refresh token for a new pair and persist the result.

    xAI **rotates** the refresh token on every use, so the old one is dead the
    moment this returns. The exclusive file lock is what stops daphne and a
    Celery worker from each spending the same token and invalidating the
    other; whoever loses the race re-reads under the lock and takes the winner's
    fresh credential instead of replaying a consumed one.

    ``stale_access`` names a token the caller has just seen rejected (a 401).
    That is the case where "the stored credential still looks valid" is exactly
    wrong — the deadline says fine, the server says otherwise — so the freshness
    shortcut becomes "did somebody else already replace *this* token?" rather
    than "does the stored one look unexpired?".
    """
    async with _refresh_lock:
        handle = await asyncio.to_thread(_acquire_lock)
        try:
            stored = load_credentials()
            if stored is not None:
                if stale_access is not None:
                    if stored.access and stored.access != stale_access:
                        # Another process rotated after our 401 — use theirs.
                        return stored
                elif not stored.is_expiring():
                    # Another process refreshed while we waited for the lock.
                    return stored
            token_source = stored or current
            body = await _post_token(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": token_source.refresh,
                    "client_id": CLIENT_ID,
                }
            )
            refreshed = _credentials_from_token_response(
                body, previous_refresh=token_source.refresh
            )
            save_credentials(refreshed)
            logger.info("xAI access token refreshed")
            return refreshed
        finally:
            await asyncio.to_thread(_release_lock, handle)


async def access_token(*, stale_access: str | None = None) -> str:
    """Return a usable access token, refreshing first when it is due.

    Pass ``stale_access`` after a 401 to force a refresh past a credential that
    merely *looks* unexpired.

    Raises :class:`XaiAuthError` when nothing is configured, which the provider
    turns into a skipped tier rather than a failed request.
    """
    creds = load_credentials()
    if creds is None:
        raise XaiAuthError(unconfigured_reason() or "no xAI credentials")
    if stale_access is not None or creds.is_expiring():
        creds = await refresh_credentials(creds, stale_access=stale_access)
    if not creds.access:
        raise XaiAuthError("xAI credential has no access token")
    return creds.access


# ---------------------------------------------------------------------------
# Device-code grant (RFC 8628) — the Docker-friendly path
# ---------------------------------------------------------------------------


async def request_device_code() -> DeviceCode:
    """Start the device-authorization grant."""
    async with httpx.AsyncClient(timeout=_TOKEN_REQUEST_TIMEOUT_S) as client:
        response = await client.post(
            device_authorization_url(),
            data={"client_id": CLIENT_ID, "scope": SCOPE},
            headers=_form_headers(),
        )
    if response.status_code >= 400:
        raise XaiAuthError(
            f"xAI device code request failed ({response.status_code})"
            + (f": {response.text[:200]}" if response.text else "")
        )
    body = response.json()
    if not isinstance(body, dict):
        raise XaiAuthError("xAI device code response was not a JSON object")
    missing = [
        key
        for key in ("device_code", "user_code", "verification_uri")
        if not body.get(key)
    ]
    if missing:
        raise XaiAuthError(
            "xAI device code response is missing " + ", ".join(sorted(missing))
        )
    return DeviceCode(
        device_code=str(body["device_code"]),
        user_code=str(body["user_code"]),
        verification_uri=str(body["verification_uri"]),
        verification_uri_complete=(
            str(body["verification_uri_complete"])
            if body.get("verification_uri_complete")
            else None
        ),
        expires_in=body.get("expires_in"),
        interval=body.get("interval"),
    )


async def poll_device_token(
    device: DeviceCode,
    *,
    sleep: Any = None,
    now: Any = None,
) -> Credentials:
    """Long-poll the token endpoint until the operator approves (RFC 8628 §3.5).

    ``authorization_pending`` keeps the current interval, ``slow_down`` widens
    it, and everything else is terminal. ``sleep``/``now`` are injectable so the
    tests can exercise every branch without real waits.
    """
    _sleep = sleep or asyncio.sleep
    _now = now or time.monotonic
    deadline = _now() + _positive_seconds(device.expires_in, _DEVICE_DEFAULT_EXPIRES_S)
    interval = max(
        _positive_seconds(device.interval, _DEVICE_DEFAULT_INTERVAL_S),
        _DEVICE_MIN_INTERVAL_S,
    )

    while _now() < deadline:
        async with httpx.AsyncClient(timeout=_TOKEN_REQUEST_TIMEOUT_S) as client:
            response = await client.post(
                token_url(),
                data={
                    "grant_type": DEVICE_CODE_GRANT_TYPE,
                    "client_id": CLIENT_ID,
                    "device_code": device.device_code,
                },
                headers=_form_headers(),
            )
        if response.status_code < 400:
            body = response.json()
            creds = _credentials_from_token_response(body)
            save_credentials(creds)
            return creds

        try:
            error_body = response.json()
        except ValueError:
            error_body = {}
        error = (
            str(error_body.get("error") or "") if isinstance(error_body, dict) else ""
        )

        if error == "authorization_pending":
            await _sleep(min(interval, max(0.0, deadline - _now())))
            continue
        if error == "slow_down":
            interval += _DEVICE_SLOW_DOWN_INCREMENT_S
            await _sleep(min(interval, max(0.0, deadline - _now())))
            continue
        if error in {"access_denied", "authorization_denied"}:
            raise XaiAuthError("xAI device authorization was denied")
        if error == "expired_token":
            raise XaiAuthError("xAI device code expired — run the login again")
        detail = ""
        if isinstance(error_body, dict):
            detail = str(error_body.get("error_description") or error or "")
        raise XaiAuthError(
            f"xAI device token exchange failed ({response.status_code})"
            + (f": {detail}" if detail else "")
        )

    raise XaiAuthError("xAI device authorization timed out")


# ---------------------------------------------------------------------------
# Loopback PKCE grant — opt-in, for a host with a browser
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Pkce:
    verifier: str
    challenge: str


def _generate_pkce() -> _Pkce:
    verifier = secrets.token_urlsafe(64)[:64]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return _Pkce(verifier=verifier, challenge=challenge)


def build_authorize_url(pkce: _Pkce, state: str, nonce: str) -> str:
    """Assemble the consent URL.

    ``plan=generic`` opts the consent screen into xAI's generic OAuth plan
    tier — without it the auth server rejects loopback OAuth from this client.
    ``referrer`` is best-effort attribution in xAI's own logs.
    """
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge": pkce.challenge,
        "code_challenge_method": "S256",
        "state": state,
        "nonce": nonce,
        "plan": "generic",
        "referrer": "law-ai",
    }
    return f"{authorize_url()}?{urllib.parse.urlencode(params)}"


class _CallbackHandler(BaseHTTPRequestHandler):
    """One-shot handler that captures ``?code=&state=`` and closes the page."""

    code: str | None = None
    state: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != OAUTH_REDIRECT_PATH:
            self.send_response(404)
            self.end_headers()
            return
        query = urllib.parse.parse_qs(parsed.query)

        def first(key: str) -> str | None:
            values = query.get(key)
            return values[0] if values else None

        _CallbackHandler.code = first("code")
        _CallbackHandler.state = first("state")
        _CallbackHandler.error = first("error")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<!doctype html><title>Law AI</title>"
            b"<p>xAI authorization received. You can close this window.</p>"
        )

    def log_message(self, format: str, *args: Any) -> None:
        # Silence the default stderr access log: the query string carries the
        # authorization code (NFR-SEC-1).
        return


def _serve_one_callback(timeout_s: float) -> tuple[str | None, str | None, str | None]:
    """Run the loopback server for exactly one request."""
    _CallbackHandler.code = None
    _CallbackHandler.state = None
    _CallbackHandler.error = None
    server = HTTPServer((OAUTH_HOST, OAUTH_PORT), _CallbackHandler)
    server.timeout = timeout_s
    try:
        server.handle_request()
    finally:
        server.server_close()
    return _CallbackHandler.code, _CallbackHandler.state, _CallbackHandler.error


async def loopback_login(*, open_browser: Any = None) -> tuple[str, Credentials]:
    """Run the loopback PKCE grant, returning the consent URL and the tokens.

    The URL is returned as well as opened so a caller can print it — the whole
    point of the alternate path is that the operator may be looking at a
    different screen than the one this process can reach.
    """
    pkce = _generate_pkce()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    url = build_authorize_url(pkce, state, nonce)

    if open_browser is not None:
        open_browser(url)

    code, returned_state, error = await asyncio.to_thread(
        _serve_one_callback, _LOOPBACK_TIMEOUT_S
    )
    if error:
        raise XaiAuthError(f"xAI authorization failed: {error}")
    if not code:
        raise XaiAuthError("xAI authorization timed out waiting for the callback")
    if returned_state != state:
        # A mismatched state means the callback did not come from the request
        # we started; treating it as ours would be the CSRF this check exists
        # to prevent.
        raise XaiAuthError("xAI authorization state mismatch — refusing the callback")

    body = await _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "code_verifier": pkce.verifier,
        }
    )
    creds = _credentials_from_token_response(body)
    save_credentials(creds)
    return url, creds


__all__ = [
    "ACCESS_TOKEN_REFRESH_SKEW_S",
    "CLIENT_ID",
    "PROVIDER_NAME",
    "REDIRECT_URI",
    "SCOPE",
    "Credentials",
    "DeviceCode",
    "XaiAuthError",
    "access_token",
    "build_authorize_url",
    "credentials_path",
    "is_configured",
    "load_credentials",
    "loopback_login",
    "poll_device_token",
    "refresh_credentials",
    "request_device_code",
    "save_credentials",
    "unconfigured_reason",
]
