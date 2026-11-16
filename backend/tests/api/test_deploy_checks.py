"""Production deploy checks ``law_ai.E002`` / ``law_ai.E003`` and their boot guard.

BL-20261112-01 (#221): ``settings/prod.py`` inherits the public development
``SECRET_KEY`` and ``ALLOWED_HOSTS=["*"]`` from ``settings/base.py``. The key
signs API access tokens and LSAT answer-shuffle tokens, so production must
refuse it, the same way it already refuses an open router (``law_ai.E001``,
covered in ``test_agents.py``). The unit tests pin the rules; the subprocess
tests at the bottom run ``manage.py check --deploy`` against
``law_ai.settings.prod``, because "production refuses to boot" is a claim about
``django.setup()``, not about a function.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key

from law_ai.core import apps as core_apps
from law_ai.settings import base

BACKEND_DIR = Path(__file__).resolve().parents[2]
#: The development default ``settings/base.py`` actually ships, read from its
#: django-environ scheme rather than restated here.
BASE_DEFAULT_KEY: str = base.env.scheme["SECRET_KEY"][1]
EXPLICIT_HOSTS = ["law-ai.example.com"]
OTHER_ENVIRONMENTS = ["development", "test", "staging"]

WEAK_KEYS = [
    pytest.param(BASE_DEFAULT_KEY, id="base-default"),
    pytest.param(get_random_secret_key()[:49], id="shorter-than-50"),
    pytest.param("ab" * 30, id="fewer-than-5-unique"),
    pytest.param("django-insecure-" + get_random_secret_key(), id="insecure-prefix"),
    pytest.param("", id="empty"),
]


@pytest.fixture
def production(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Production with a strong key and explicit hosts: every check passes."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    # 50 characters exactly: the threshold is inclusive.
    monkeypatch.setattr(settings, "SECRET_KEY", get_random_secret_key())
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", EXPLICIT_HOSTS)
    return monkeypatch


# --- law_ai.E002: SECRET_KEY ---


@pytest.mark.parametrize("key", WEAK_KEYS)
def test_secret_key_check_flags_a_guessable_production_key(
    production: pytest.MonkeyPatch, key: str
) -> None:
    production.setattr(settings, "SECRET_KEY", key)

    messages = core_apps.check_secret_key_configured()

    assert [m.id for m in messages] == ["law_ai.E002"]
    assert messages[0].is_serious()


def test_secret_key_error_never_quotes_the_key(production: pytest.MonkeyPatch) -> None:
    key = get_random_secret_key()[:49]
    production.setattr(settings, "SECRET_KEY", key)

    (message,) = core_apps.check_secret_key_configured()

    assert key not in f"{message.msg} {message.hint}"


def test_secret_key_check_passes_a_strong_production_key(
    production: pytest.MonkeyPatch,
) -> None:
    assert len(settings.SECRET_KEY) == core_apps.SECRET_KEY_MIN_LENGTH
    assert core_apps.check_secret_key_configured() == []


@pytest.mark.parametrize("environment", OTHER_ENVIRONMENTS)
def test_secret_key_check_is_quiet_outside_production(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "SECRET_KEY", BASE_DEFAULT_KEY)
    assert core_apps.check_secret_key_configured() == []


def test_the_default_it_refuses_is_the_one_base_py_ships() -> None:
    """If base.py's development default changes, DEFAULT_SECRET_KEY must too."""
    assert core_apps.DEFAULT_SECRET_KEY == BASE_DEFAULT_KEY


# --- law_ai.E003: ALLOWED_HOSTS ---


@pytest.mark.parametrize("hosts", [["*"], ["law-ai.example.com", "*"]])
def test_allowed_hosts_check_flags_a_wildcard_in_production(
    production: pytest.MonkeyPatch, hosts: list[str]
) -> None:
    production.setattr(settings, "ALLOWED_HOSTS", hosts)

    messages = core_apps.check_allowed_hosts_configured()

    assert [m.id for m in messages] == ["law_ai.E003"]
    assert messages[0].is_serious()


@pytest.mark.parametrize(
    "hosts", [EXPLICIT_HOSTS, [".example.com", "localhost", "127.0.0.1"]]
)
def test_allowed_hosts_check_passes_explicit_hosts(
    production: pytest.MonkeyPatch, hosts: list[str]
) -> None:
    production.setattr(settings, "ALLOWED_HOSTS", hosts)
    assert core_apps.check_allowed_hosts_configured() == []


@pytest.mark.parametrize("environment", OTHER_ENVIRONMENTS)
def test_allowed_hosts_check_is_quiet_outside_production(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["*"])
    assert core_apps.check_allowed_hosts_configured() == []


# --- The boot guard: production refuses to start ---


def test_boot_guard_refuses_a_guessable_key_in_production(
    production: pytest.MonkeyPatch,
) -> None:
    production.setattr(settings, "SECRET_KEY", BASE_DEFAULT_KEY)

    with pytest.raises(ImproperlyConfigured, match=r"law_ai\.E002") as exc:
        core_apps.refuse_insecure_production_settings()
    assert "production" in str(exc.value)


def test_boot_guard_refuses_a_wildcard_host_in_production(
    production: pytest.MonkeyPatch,
) -> None:
    production.setattr(settings, "ALLOWED_HOSTS", ["*"])

    with pytest.raises(ImproperlyConfigured, match=r"law_ai\.E003"):
        core_apps.refuse_insecure_production_settings()


def test_boot_guard_names_every_problem_and_never_the_key(
    production: pytest.MonkeyPatch,
) -> None:
    production.setattr(settings, "SECRET_KEY", BASE_DEFAULT_KEY)
    production.setattr(settings, "ALLOWED_HOSTS", ["*"])

    with pytest.raises(ImproperlyConfigured) as exc:
        core_apps.refuse_insecure_production_settings()

    assert "law_ai.E002" in str(exc.value)
    assert "law_ai.E003" in str(exc.value)
    assert BASE_DEFAULT_KEY not in str(exc.value)


def test_boot_guard_lets_a_hardened_production_start(
    production: pytest.MonkeyPatch,
) -> None:
    core_apps.refuse_insecure_production_settings()  # must not raise


@pytest.mark.parametrize("environment", OTHER_ENVIRONMENTS)
def test_boot_guard_leaves_the_base_defaults_alone_outside_production(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    """Development and the test suite keep booting with no configuration."""
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "SECRET_KEY", BASE_DEFAULT_KEY)
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", ["*"])
    core_apps.refuse_insecure_production_settings()  # must not raise


def test_ready_refuses_production_even_after_a_first_init(
    production: pytest.MonkeyPatch,
) -> None:
    """The once-guard skips re-initialisation, never the security check."""
    production.setenv("LAWGRAPH_READY_ONCE", "1")
    production.setattr(settings, "SECRET_KEY", BASE_DEFAULT_KEY)

    with pytest.raises(ImproperlyConfigured, match=r"law_ai\.E002"):
        apps.get_app_config("core").ready()


def test_ready_lets_a_hardened_production_start(
    production: pytest.MonkeyPatch,
) -> None:
    production.setenv("LAWGRAPH_READY_ONCE", "1")
    apps.get_app_config("core").ready()  # must not raise


# --- For real: `manage.py check --deploy` on law_ai.settings.prod ---


def _check_deploy(
    secret_key: str, allowed_hosts: str
) -> subprocess.CompletedProcess[str]:
    """Run ``manage.py check --deploy`` in a fresh production process.

    ``LAWGRAPH_READY_ONCE`` is dropped so the child boots the way daphne does,
    and ``AGENT_API_KEY`` is set so ``law_ai.E001`` stays out of the picture.
    """
    env = {
        name: value
        for name, value in os.environ.items()
        if name not in {"LAWGRAPH_READY_ONCE", "ENVIRONMENT"}
    }
    env.update(
        DJANGO_SETTINGS_MODULE="law_ai.settings.prod",
        AGENT_API_KEY="deploy-check",
        SECRET_KEY=secret_key,
        ALLOWED_HOSTS=allowed_hosts,
    )
    return subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


@pytest.mark.slow
def test_production_refuses_to_boot_on_the_base_defaults() -> None:
    result = _check_deploy(BASE_DEFAULT_KEY, "*")

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "law_ai.E002" in result.stderr
    assert "law_ai.E003" in result.stderr


@pytest.mark.slow
def test_a_hardened_production_passes_check_deploy() -> None:
    """Spec 011 NFR-SEC-1: ``check --deploy`` exits 0 in prod settings."""
    # Hex, like `openssl rand -hex 32`: django-environ reads a value that
    # starts with "$" as a reference to another variable.
    result = _check_deploy(secrets.token_hex(32), "law-ai.example.com")

    assert result.returncode == 0, result.stderr
    assert "law_ai.E00" not in result.stdout + result.stderr
