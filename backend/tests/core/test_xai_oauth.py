"""Tests for the xAI OAuth credential lifecycle (spec 050).

Constitution §1 as amended 2026-09-04 sanctions xAI as chain tier 3 with
subscription-OAuth auth. What matters here is the *credential contract*: the
RFC 8628 polling branches, atomic 0600 storage, and — the one that actually
bites in production — that a rotated refresh token is persisted and never
replayed. No real network: every token call goes through an httpx
MockTransport.
"""

from __future__ import annotations

import base64
import json
import stat
import time
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from law_ai.core import xai_oauth


@pytest.fixture
def store(tmp_path, settings) -> Any:
    """Point the credential store at a temp file for the duration of a test."""
    path = tmp_path / "xai" / "credentials.json"
    settings.XAI_CREDENTIALS_PATH = str(path)
    settings.XAI_ACCESS_TOKEN = ""
    settings.XAI_REFRESH_TOKEN = ""
    return path


def _mock_transport(handler: Any) -> Any:
    """Patch httpx.AsyncClient so every request goes to *handler*."""
    real_client = httpx.AsyncClient

    def _factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    return patch("httpx.AsyncClient", _factory)


def _jwt(exp: float) -> str:
    """A JWT-shaped token with the given ``exp`` — signature intentionally junk."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode()
    return f"header.{payload.rstrip('=')}.signature"


# ---------------------------------------------------------------------------
# Credential store
# ---------------------------------------------------------------------------


class TestCredentialStore:
    def test_round_trip(self, store) -> None:
        creds = xai_oauth.Credentials(
            access="a", refresh="r", expires_at=time.time() + 3600
        )
        xai_oauth.save_credentials(creds)
        loaded = xai_oauth.load_credentials()
        assert loaded is not None
        assert (loaded.access, loaded.refresh) == ("a", "r")

    def test_file_is_owner_only(self, store) -> None:
        """Tokens on disk must not be world-readable (NFR-SEC-1)."""
        xai_oauth.save_credentials(
            xai_oauth.Credentials(access="a", refresh="r", expires_at=0.0)
        )
        mode = stat.S_IMODE(store.stat().st_mode)
        assert mode == 0o600

    def test_missing_file_is_unconfigured(self, store) -> None:
        assert xai_oauth.load_credentials() is None
        assert xai_oauth.is_configured() is False
        assert "xai-login" in (xai_oauth.unconfigured_reason() or "")

    def test_settings_seed_is_used_when_no_file(self, store, settings) -> None:
        settings.XAI_REFRESH_TOKEN = "seeded"
        loaded = xai_oauth.load_credentials()
        assert loaded is not None
        assert loaded.refresh == "seeded"
        # A seeded pair carries no deadline, so it must refresh before first use.
        assert loaded.is_expiring() is True

    def test_corrupt_file_falls_back_to_seed(self, store, settings) -> None:
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text("{not json", encoding="utf-8")
        settings.XAI_REFRESH_TOKEN = "seeded"
        loaded = xai_oauth.load_credentials()
        assert loaded is not None and loaded.refresh == "seeded"


class TestExpiry:
    def test_stored_deadline_drives_refresh(self) -> None:
        soon = xai_oauth.Credentials(
            access="a", refresh="r", expires_at=time.time() + 5
        )
        later = xai_oauth.Credentials(
            access="a", refresh="r", expires_at=time.time() + 9999
        )
        assert soon.is_expiring() is True
        assert later.is_expiring() is False

    def test_jwt_exp_drives_refresh_when_deadline_is_stale(self) -> None:
        """The stored deadline can be optimistic; the token's own claim wins."""
        creds = xai_oauth.Credentials(
            access=_jwt(time.time() + 5), refresh="r", expires_at=time.time() + 9999
        )
        assert creds.is_expiring() is True

    def test_opaque_token_defers_to_stored_deadline(self) -> None:
        creds = xai_oauth.Credentials(
            access="not-a-jwt", refresh="r", expires_at=time.time() + 9999
        )
        assert creds.is_expiring() is False


# ---------------------------------------------------------------------------
# Refresh + rotation
# ---------------------------------------------------------------------------


class TestRefresh:
    async def test_rotated_refresh_token_is_persisted(self, store) -> None:
        """xAI rotates on every use — losing the new token means re-login."""
        xai_oauth.save_credentials(
            xai_oauth.Credentials(access="old", refresh="r1", expires_at=0.0)
        )
        seen: list[dict[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(dict(httpx.QueryParams(request.content.decode())))
            return httpx.Response(
                200,
                json={
                    "access_token": "new",
                    "refresh_token": "r2",
                    "expires_in": 3600,
                },
            )

        with _mock_transport(handler):
            token = await xai_oauth.access_token()

        assert token == "new"
        assert seen[0]["refresh_token"] == "r1"
        stored = xai_oauth.load_credentials()
        assert stored is not None and stored.refresh == "r2"

    async def test_response_without_rotation_keeps_old_refresh(self, store) -> None:
        xai_oauth.save_credentials(
            xai_oauth.Credentials(access="old", refresh="r1", expires_at=0.0)
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"access_token": "new", "expires_in": 60})

        with _mock_transport(handler):
            await xai_oauth.access_token()

        stored = xai_oauth.load_credentials()
        assert stored is not None and stored.refresh == "r1"

    async def test_second_refresh_reuses_the_first_result(self, store) -> None:
        """The lock must collapse a concurrent refresh, not replay a dead token.

        The second call finds a fresh credential on disk under the lock and
        returns it instead of spending the (already consumed) refresh token.
        """
        xai_oauth.save_credentials(
            xai_oauth.Credentials(access="old", refresh="r1", expires_at=0.0)
        )
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                200,
                json={"access_token": "new", "refresh_token": "r2", "expires_in": 3600},
            )

        stale = xai_oauth.Credentials(access="old", refresh="r1", expires_at=0.0)
        with _mock_transport(handler):
            await xai_oauth.refresh_credentials(stale)
            await xai_oauth.refresh_credentials(stale)

        assert calls == 1

    async def test_rejected_refresh_raises_auth_error(self, store) -> None:
        xai_oauth.save_credentials(
            xai_oauth.Credentials(access="old", refresh="dead", expires_at=0.0)
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "invalid_grant"})

        with _mock_transport(handler), pytest.raises(xai_oauth.XaiAuthError):
            await xai_oauth.access_token()

    async def test_unconfigured_raises_rather_than_calling_out(self, store) -> None:
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("must not reach the network without a credential")

        with _mock_transport(handler), pytest.raises(xai_oauth.XaiAuthError):
            await xai_oauth.access_token()


# ---------------------------------------------------------------------------
# Device-code grant (RFC 8628 §3.5)
# ---------------------------------------------------------------------------


def _device(**kw: Any) -> xai_oauth.DeviceCode:
    return xai_oauth.DeviceCode(
        device_code=kw.get("device_code", "dc"),
        user_code=kw.get("user_code", "ABCD-1234"),
        verification_uri=kw.get("verification_uri", "https://x.ai/device"),
        verification_uri_complete=kw.get("verification_uri_complete"),
        expires_in=kw.get("expires_in", 60),
        interval=kw.get("interval", 5),
    )


class _Clock:
    """Monotonic stand-in that only advances when the polled sleep is awaited."""

    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += max(seconds, 0.001)


class TestDeviceCode:
    async def test_request_returns_the_operator_facing_fields(self, store) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "device_code": "dc",
                    "user_code": "WXYZ-9999",
                    "verification_uri": "https://x.ai/device",
                    "verification_uri_complete": "https://x.ai/device?code=WXYZ-9999",
                    "expires_in": 600,
                    "interval": 5,
                },
            )

        with _mock_transport(handler):
            device = await xai_oauth.request_device_code()

        assert device.user_code == "WXYZ-9999"
        assert device.browser_url.endswith("?code=WXYZ-9999")

    async def test_pending_then_success(self, store) -> None:
        clock = _Clock()
        responses = [
            httpx.Response(400, json={"error": "authorization_pending"}),
            httpx.Response(
                200,
                json={"access_token": "a", "refresh_token": "r", "expires_in": 3600},
            ),
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            return responses.pop(0)

        with _mock_transport(handler):
            creds = await xai_oauth.poll_device_token(
                _device(), sleep=clock.sleep, now=clock.now
            )

        assert creds.access == "a"
        # Approved credentials are written immediately, not left in memory.
        stored = xai_oauth.load_credentials()
        assert stored is not None and stored.refresh == "r"

    async def test_slow_down_widens_the_interval(self, store) -> None:
        clock = _Clock()
        responses = [
            httpx.Response(400, json={"error": "slow_down"}),
            httpx.Response(400, json={"error": "authorization_pending"}),
            httpx.Response(
                200,
                json={"access_token": "a", "refresh_token": "r", "expires_in": 60},
            ),
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            return responses.pop(0)

        with _mock_transport(handler):
            await xai_oauth.poll_device_token(
                _device(interval=5), sleep=clock.sleep, now=clock.now
            )

        assert clock.slept[0] == pytest.approx(10.0)  # 5 + the 5s increment
        assert clock.slept[1] == pytest.approx(10.0)  # stays widened

    @pytest.mark.parametrize(
        "error,message",
        [
            ("access_denied", "denied"),
            ("authorization_denied", "denied"),
            ("expired_token", "expired"),
        ],
    )
    async def test_terminal_errors_raise(self, store, error, message) -> None:
        clock = _Clock()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": error})

        with (
            _mock_transport(handler),
            pytest.raises(xai_oauth.XaiAuthError, match=message),
        ):
            await xai_oauth.poll_device_token(
                _device(), sleep=clock.sleep, now=clock.now
            )

    async def test_deadline_gives_up(self, store) -> None:
        clock = _Clock()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "authorization_pending"})

        with (
            _mock_transport(handler),
            pytest.raises(xai_oauth.XaiAuthError, match="timed out"),
        ):
            await xai_oauth.poll_device_token(
                _device(expires_in=12, interval=5),
                sleep=clock.sleep,
                now=clock.now,
            )

    async def test_garbage_interval_does_not_busy_loop(self, store) -> None:
        """A NaN interval slips past ``or default`` and would spin at zero delay."""
        clock = _Clock()
        responses = [
            httpx.Response(400, json={"error": "authorization_pending"}),
            httpx.Response(
                200,
                json={"access_token": "a", "refresh_token": "r", "expires_in": 60},
            ),
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            return responses.pop(0)

        with _mock_transport(handler):
            await xai_oauth.poll_device_token(
                _device(interval=float("nan")), sleep=clock.sleep, now=clock.now
            )

        assert clock.slept[0] >= 1.0


# ---------------------------------------------------------------------------
# Loopback PKCE
# ---------------------------------------------------------------------------


class TestAuthorizeUrl:
    def test_carries_pkce_and_the_generic_plan(self) -> None:
        pkce = xai_oauth._generate_pkce()
        url = xai_oauth.build_authorize_url(pkce, "state123", "nonce123")
        assert "code_challenge_method=S256" in url
        assert f"code_challenge={pkce.challenge}" in url
        # Without plan=generic the auth server rejects loopback OAuth here.
        assert "plan=generic" in url
        assert "state=state123" in url
        assert xai_oauth.CLIENT_ID in url

    def test_redirect_uri_is_the_registered_one(self) -> None:
        """The port is part of the client registration — not ours to change."""
        assert xai_oauth.REDIRECT_URI == "http://127.0.0.1:56121/callback"
