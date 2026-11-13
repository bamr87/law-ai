"""lawmode policy: defaults ported from policy.yaml, overridden by settings.

Rewritten from ``lawmode/tests/test_config.py``. The original's first
assertion was ``config.llm.provider == "openai"``; the port's equivalent is
that the policy has no model configuration at all.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured
from pydantic import ValidationError

from law_ai.lawmode import policy as policy_mod
from law_ai.lawmode.policy import PolicyConfig, load_policy
from law_ai.lawmode.schemas import Severity

pytestmark = pytest.mark.unit


def test_defaults_are_the_ones_lawmodes_policy_yaml_shipped() -> None:
    policy = PolicyConfig()

    assert policy.jurisdictions == ["US", "EU", "UK"]
    assert policy.severity_gating == {
        "critical": "block",
        "high": "require_approval",
        "medium": "comment",
        "low": "comment",
    }
    assert policy.domains == []


def test_the_policy_carries_no_model_configuration() -> None:
    """lawmode's LLMConfig (provider, model, api_key) was not ported."""
    assert set(PolicyConfig.model_fields) == {
        "jurisdictions",
        "severity_gating",
        "domains",
    }
    with pytest.raises(ValidationError):
        PolicyConfig.model_validate({"llm": {"provider": "openai", "model": "gpt-4o"}})
    for name in ("LLMConfig", "LawModeConfig"):
        assert not hasattr(policy_mod, name)


def test_critical_and_high_go_to_a_human_by_default() -> None:
    policy = PolicyConfig()

    assert policy.requires_review(Severity.CRITICAL) is True
    assert policy.requires_review(Severity.HIGH) is True
    assert policy.requires_review(Severity.MEDIUM) is False
    assert policy.requires_review(Severity.LOW) is False


def test_block_and_require_approval_both_mean_human_review() -> None:
    policy = PolicyConfig(
        severity_gating={"medium": "block", "low": "require_approval"}
    )

    assert policy.action_for(Severity.MEDIUM) == "block"
    assert policy.requires_review(Severity.MEDIUM) is True
    assert policy.requires_review(Severity.LOW) is True


def test_a_partial_override_does_not_ungate_what_it_leaves_out() -> None:
    policy = PolicyConfig(severity_gating={"medium": "require_approval"})

    assert policy.requires_review(Severity.MEDIUM) is True
    assert policy.requires_review(Severity.CRITICAL) is True
    assert policy.requires_review(Severity.HIGH) is True
    assert policy.requires_review(Severity.LOW) is False
    assert set(policy.severity_gating) == {"critical", "high", "medium", "low"}


def test_severity_keys_are_case_insensitive() -> None:
    policy = PolicyConfig(severity_gating={" Medium ": "block"})

    assert policy.requires_review(Severity.MEDIUM) is True


@pytest.mark.parametrize(
    "gating",
    [
        {"critical": "comment"},
        {"high": "comment"},
        {"Critical": "comment", "high": "comment"},
    ],
)
def test_no_policy_can_take_critical_or_high_away_from_a_human(
    gating: dict[str, Any],
) -> None:
    """PRD §5.8: critical and high go to HITL. A setting is not a way round."""
    with pytest.raises(ValidationError, match="always go to a human"):
        PolicyConfig(severity_gating=gating)


def test_critical_and_high_may_swap_between_the_two_gated_actions() -> None:
    policy = PolicyConfig(
        severity_gating={"critical": "require_approval", "high": "block"}
    )

    assert policy.requires_review(Severity.CRITICAL) is True
    assert policy.requires_review(Severity.HIGH) is True


@pytest.mark.parametrize(
    "gating",
    [{"catastrophic": "block"}, {"high": "auto_approve"}, {"high": "pass"}],
)
def test_unknown_severity_or_action_is_rejected(gating: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PolicyConfig(severity_gating=gating)


def test_load_policy_uses_the_setting(settings: Any) -> None:
    settings.LAWMODE_JURISDICTIONS = ["US-CA", " EU ", "US-CA", ""]

    assert load_policy().jurisdictions == ["US-CA", "EU"]


def test_load_policy_accepts_a_comma_separated_string(settings: Any) -> None:
    settings.LAWMODE_JURISDICTIONS = "US-CA, EU"

    assert load_policy().jurisdictions == ["US-CA", "EU"]


@pytest.mark.parametrize("empty", [[], "", None])
def test_an_empty_setting_means_the_defaults(settings: Any, empty: Any) -> None:
    settings.LAWMODE_JURISDICTIONS = empty

    assert load_policy().jurisdictions == ["US", "EU", "UK"]


@pytest.mark.parametrize("bad", [42, {"US": True}, ["US", 7]])
def test_a_malformed_jurisdiction_setting_is_a_configuration_error(
    settings: Any, bad: Any
) -> None:
    settings.LAWMODE_JURISDICTIONS = bad

    with pytest.raises(ImproperlyConfigured, match="LAWMODE_JURISDICTIONS"):
        load_policy()


def test_the_shipped_settings_default_matches_the_python_default() -> None:
    """Read from the declaration, so a developer's ``.env`` cannot change it."""
    from law_ai.settings import base

    cast, default = base.env.scheme["LAWMODE_JURISDICTIONS"]
    assert cast is list
    assert default == list(policy_mod.DEFAULT_JURISDICTIONS) == ["US", "EU", "UK"]
    assert load_policy() == PolicyConfig()
