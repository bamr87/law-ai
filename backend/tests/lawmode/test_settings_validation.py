"""``LAWMODE_MODELS`` validation — spec 057 AC-6 and FR-2.

An Anthropic model override other than the three allowed ids must fail at
startup. The unit tests pin the rule; the subprocess tests at the bottom boot
a real Django process with the setting in its environment, because "at
startup" is a claim about ``django.setup()``, not about a function.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured

from law_ai.core import llm
from law_ai.lawmode.policy import (
    ALLOWED_ANTHROPIC_MODELS,
    ANTHROPIC_PROVIDERS,
    model_overrides,
    validate_model_overrides,
    validate_settings,
)

pytestmark = pytest.mark.unit

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_the_allowed_anthropic_ids_are_exactly_the_three_in_the_spec() -> None:
    assert set(ALLOWED_ANTHROPIC_MODELS) == {
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "claude-haiku-5-5",
    }
    assert set(ANTHROPIC_PROVIDERS) == {"claude_code", "anthropic_api"}


def test_lawmode_ships_with_no_model_override() -> None:
    """No default of its own: unset means the chain's configured models.

    Read from the declaration, so a developer's ``.env`` cannot change it.
    """
    from law_ai.settings import base

    assert base.env.scheme["LAWMODE_MODELS"] == (str, "")
    assert model_overrides() == {}


@pytest.mark.parametrize("empty", [None, "", "   ", {}, "{}"])
def test_an_empty_override_is_no_override(empty: Any) -> None:
    assert validate_model_overrides(empty) == {}


def test_the_setting_arrives_as_a_json_string_from_the_environment() -> None:
    raw = '{"claude_code": "claude-sonnet-5-5", "ollama": "llama3.1:8b"}'

    assert validate_model_overrides(raw) == {
        "claude_code": "claude-sonnet-5-5",
        "ollama": "llama3.1:8b",
    }


@pytest.mark.parametrize("bad", ["claude-opus-5-5", "{not json", "{'a': 'b'}"])
def test_malformed_json_is_a_configuration_error_not_a_traceback(bad: str) -> None:
    with pytest.raises(ImproperlyConfigured, match="not valid JSON"):
        validate_model_overrides(bad)


@pytest.mark.parametrize("provider", ANTHROPIC_PROVIDERS)
@pytest.mark.parametrize("model", ALLOWED_ANTHROPIC_MODELS)
def test_each_allowed_id_is_accepted_on_each_anthropic_tier(
    provider: str, model: str
) -> None:
    assert validate_model_overrides({provider: model}) == {provider: model}


@pytest.mark.parametrize("provider", ANTHROPIC_PROVIDERS)
@pytest.mark.parametrize(
    "model",
    [
        "gpt-4o",
        "grok-2-1212",
        "claude-opus-4-1",
        "claude-fable-5-1",
        "claude-3-5-sonnet-latest",
        "claude-opus-5-5-20261101",
        "CLAUDE-OPUS-5-5",
    ],
)
def test_any_other_anthropic_tier_model_is_rejected(provider: str, model: str) -> None:
    with pytest.raises(ImproperlyConfigured) as excinfo:
        validate_model_overrides({provider: model})

    message = str(excinfo.value)
    assert model in message
    for allowed in ALLOWED_ANTHROPIC_MODELS:
        assert allowed in message


@pytest.mark.parametrize("provider", ["openai", "gemini", "azure_openai", "grok", ""])
def test_a_provider_outside_the_chain_is_rejected(provider: str) -> None:
    """lawmode cannot be pointed at a vendor ``LLM_PROVIDER_CHAIN`` lacks."""
    assert provider not in llm.PROVIDER_REGISTRY

    with pytest.raises(ImproperlyConfigured, match="not a provider"):
        validate_model_overrides({provider: "claude-opus-5-5"})


def test_the_local_and_xai_tiers_take_the_operators_own_model_ids() -> None:
    overrides = {"ollama": "mistral:7b-instruct-q4_K_M", "xai": " grok-4.6 "}

    assert validate_model_overrides(overrides) == {
        "ollama": "mistral:7b-instruct-q4_K_M",
        "xai": "grok-4.6",
    }


def test_provider_keys_are_normalised() -> None:
    assert validate_model_overrides({" Claude_Code ": "claude-haiku-5-5"}) == {
        "claude_code": "claude-haiku-5-5"
    }


@pytest.mark.parametrize("bad", ['"claude-opus-5-5"', "[1]", ["claude_code"], 3])
def test_a_value_that_is_not_an_object_is_rejected(bad: Any) -> None:
    with pytest.raises(ImproperlyConfigured, match="JSON object"):
        validate_model_overrides(bad)


@pytest.mark.parametrize("bad", ["", "   ", None, 7, ["claude-opus-5-5"]])
def test_an_empty_or_non_string_model_id_is_rejected(bad: Any) -> None:
    with pytest.raises(ImproperlyConfigured, match="non-empty model id"):
        validate_model_overrides({"ollama": bad})


def test_the_setting_is_validated_on_every_read(settings: Any) -> None:
    settings.LAWMODE_MODELS = {"anthropic_api": "claude-sonnet-5-5"}
    assert model_overrides() == {"anthropic_api": "claude-sonnet-5-5"}

    settings.LAWMODE_MODELS = {"anthropic_api": "gpt-4o"}
    with pytest.raises(ImproperlyConfigured):
        model_overrides()
    with pytest.raises(ImproperlyConfigured):
        validate_settings()


def test_the_app_is_installed_and_validates_when_it_becomes_ready(
    settings: Any,
) -> None:
    config = apps.get_app_config("lawmode")
    assert config.name == "law_ai.lawmode"
    config.ready()  # the shipped default is valid

    settings.LAWMODE_MODELS = {"claude_code": "claude-opus-4-1"}
    with pytest.raises(ImproperlyConfigured, match="claude-opus-4-1"):
        config.ready()


# ---------------------------------------------------------------------------
# AC-6, for real: boot Django with the setting in the environment.
# ---------------------------------------------------------------------------


def _boot_django(lawmode_models: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "law_ai.settings.test",
        "LAWMODE_MODELS": lawmode_models,
    }
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup(); print('booted')"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    "lawmode_models",
    [
        '{"claude_code": "gpt-4o"}',
        '{"anthropic_api": "claude-opus-4-1"}',
        '{"openai": "gpt-4o"}',
        "{not json",
    ],
)
def test_a_disallowed_override_stops_django_at_startup(lawmode_models: str) -> None:
    result = _boot_django(lawmode_models)

    assert result.returncode != 0
    assert "booted" not in result.stdout
    assert "ImproperlyConfigured" in result.stderr
    assert "LAWMODE_MODELS" in result.stderr


@pytest.mark.slow
@pytest.mark.parametrize(
    "lawmode_models",
    [
        '{"claude_code": "claude-sonnet-5-5", "anthropic_api": "claude-haiku-5-5"}',
        "",  # set but blank: an operator clearing the override
    ],
)
def test_an_allowed_or_blank_override_boots(lawmode_models: str) -> None:
    result = _boot_django(lawmode_models)

    assert result.returncode == 0, result.stderr
    assert "booted" in result.stdout
