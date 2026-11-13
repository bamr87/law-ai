"""lawmode policy: jurisdictions, severity gating, and the model-override rule.

Ported from ``lawmode/lawmode/config.py`` (``PolicyConfig``) and
``lawmode/.lawmode/policy.yaml``. The YAML's values are the Python defaults
below and operators override them through Django settings; reading a
per-repository ``.lawmode/policy.yaml`` needs a YAML parser the backend does
not depend on directly, so it waits for BL-20261112-10.

``LLMConfig`` — lawmode's own provider, model and API-key settings — is not
ported. lawmode has no provider and no model default here: a review runs on
whatever ``LLM_PROVIDER_CHAIN`` is configured to use (constitution §1). The
one model knob is ``LAWMODE_MODELS``, an optional per-provider pin for lawmode
calls, and :func:`validate_model_overrides` is what keeps it inside the rules:
only providers that exist in the chain, and on the Anthropic tiers only the
ids in :data:`ALLOWED_ANTHROPIC_MODELS`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Literal

from django.core.exceptions import ImproperlyConfigured
from pydantic import BaseModel, ConfigDict, Field, field_validator

from law_ai.core.llm import ANTHROPIC_API, CLAUDE_OAUTH, PROVIDER_REGISTRY
from law_ai.core.settings_proxy import settings_proxy as settings
from law_ai.lawmode.schemas import Severity

#: What the policy asks for at a severity. ``block`` and ``require_approval``
#: both mean "a human decides" — the names are kept from lawmode's policy file,
#: but nothing here blocks or passes a change on its own (spec 057 FR-5).
GatingAction = Literal["block", "require_approval", "comment"]

GATED_ACTIONS: frozenset[str] = frozenset({"block", "require_approval"})

DEFAULT_JURISDICTIONS: tuple[str, ...] = ("US", "EU", "UK")

DEFAULT_SEVERITY_GATING: dict[str, GatingAction] = {
    "critical": "block",
    "high": "require_approval",
    "medium": "comment",
    "low": "comment",
}

#: Severities no policy can take away from a human. PRD §5.8 says critical and
#: high findings go to the HITL queue without qualification, so a policy may
#: add medium or low to the gate but cannot set these two to ``comment`` — that
#: would be a configuration-shaped way around the gate (constitution §5).
ALWAYS_GATED: tuple[Severity, ...] = (Severity.CRITICAL, Severity.HIGH)

#: The chain tiers that serve Anthropic models.
ANTHROPIC_PROVIDERS: tuple[str, ...] = (CLAUDE_OAUTH, ANTHROPIC_API)

#: The only ids ``LAWMODE_MODELS`` may name for an Anthropic tier (spec 057
#: FR-2). Unset, lawmode inherits the tier's own configured model.
ALLOWED_ANTHROPIC_MODELS: tuple[str, ...] = (
    "claude-opus-5-5",
    "claude-sonnet-5-5",
    "claude-haiku-5-5",
)


class PolicyConfig(BaseModel):
    """Policy configuration for risk gating.

    >>> policy = PolicyConfig(severity_gating={"medium": "require_approval"})
    >>> policy.requires_review(Severity.MEDIUM), policy.requires_review(Severity.LOW)
    (True, False)
    """

    model_config = ConfigDict(extra="forbid")

    jurisdictions: list[str] = Field(
        default_factory=lambda: list(DEFAULT_JURISDICTIONS)
    )
    severity_gating: dict[str, GatingAction] = Field(
        default_factory=lambda: dict(DEFAULT_SEVERITY_GATING)
    )
    domains: list[str] = Field(default_factory=list)

    @field_validator("severity_gating")
    @classmethod
    def _complete_gating(
        cls, value: dict[str, GatingAction]
    ) -> dict[str, GatingAction]:
        """Reject unknown severities; fill the ones left out from the defaults.

        A partial override must not quietly un-gate the severities it does not
        mention, so those keep their default action. Critical and high cannot
        be un-gated at all (:data:`ALWAYS_GATED`).
        """
        known = {severity.value.lower() for severity in Severity}
        gating = {key.strip().lower(): action for key, action in value.items()}
        unknown = sorted(set(gating) - known)
        if unknown:
            raise ValueError(
                f"unknown severity in severity_gating: {', '.join(unknown)} "
                f"(expected {', '.join(sorted(known))})"
            )
        merged: dict[str, GatingAction] = {**DEFAULT_SEVERITY_GATING, **gating}
        ungated = [
            severity.value.lower()
            for severity in ALWAYS_GATED
            if merged[severity.value.lower()] not in GATED_ACTIONS
        ]
        if ungated:
            raise ValueError(
                f"severity_gating cannot set {', '.join(ungated)} to 'comment': "
                "critical and high findings always go to a human"
            )
        return merged

    def action_for(self, severity: Severity) -> GatingAction:
        """The policy's action for ``severity``.

        >>> PolicyConfig().action_for(Severity.CRITICAL)
        'block'
        """
        return self.severity_gating[severity.value.lower()]

    def requires_review(self, severity: Severity) -> bool:
        """True when a finding at ``severity`` goes to a human.

        >>> PolicyConfig().requires_review(Severity.MEDIUM)
        False
        """
        return self.action_for(severity) in GATED_ACTIONS


def _configured_jurisdictions() -> list[str]:
    raw = getattr(settings, "LAWMODE_JURISDICTIONS", None)
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = raw.split(",")
    if not isinstance(raw, list | tuple):
        raise ImproperlyConfigured(
            "LAWMODE_JURISDICTIONS must be a list of jurisdiction codes "
            f"(for example US,EU,UK), not {type(raw).__name__}"
        )
    jurisdictions: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ImproperlyConfigured(
                "LAWMODE_JURISDICTIONS must contain only strings; "
                f"got {type(item).__name__}"
            )
        code = item.strip()
        if code and code not in jurisdictions:
            jurisdictions.append(code)
    return jurisdictions


def load_policy() -> PolicyConfig:
    """The policy for this deployment: Python defaults plus settings.

    ``LAWMODE_JURISDICTIONS`` replaces the default jurisdictions when it names
    any; an empty value means the defaults.

    >>> load_policy().severity_gating["critical"]
    'block'
    """
    return PolicyConfig(
        jurisdictions=_configured_jurisdictions() or list(DEFAULT_JURISDICTIONS)
    )


def validate_model_overrides(raw: object) -> dict[str, str]:
    """Check a ``LAWMODE_MODELS`` value and return it as provider → model id.

    Takes the setting as it arrives — a JSON string from the environment, or a
    mapping from a settings override — and treats a blank one as no override.

    Raises :class:`~django.core.exceptions.ImproperlyConfigured` for a key that
    is not a provider in the chain (lawmode cannot reach a vendor the chain
    does not have) and for an Anthropic-tier model outside
    :data:`ALLOWED_ANTHROPIC_MODELS`. The xAI and Ollama tiers take whatever
    model id the operator runs there.

    >>> validate_model_overrides({"claude_code": "claude-sonnet-5-5"})
    {'claude_code': 'claude-sonnet-5-5'}
    >>> validate_model_overrides(None)
    {}
    """
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ImproperlyConfigured(
                f"LAWMODE_MODELS is not valid JSON ({exc.msg}); expected an "
                'object such as {"claude_code": "claude-sonnet-5-5"}'
            ) from exc
    if raw is None or raw == {}:
        return {}
    if not isinstance(raw, Mapping):
        raise ImproperlyConfigured(
            "LAWMODE_MODELS must be a JSON object mapping a chain provider to "
            f"a model id, not {type(raw).__name__}"
        )

    overrides: dict[str, str] = {}
    for key, value in raw.items():
        provider = str(key).strip().lower()
        if provider not in PROVIDER_REGISTRY:
            raise ImproperlyConfigured(
                f"LAWMODE_MODELS names {key!r}, which is not a provider in "
                f"LLM_PROVIDER_CHAIN ({', '.join(PROVIDER_REGISTRY)}). lawmode "
                "has no provider of its own and cannot add a vendor."
            )
        if not isinstance(value, str) or not value.strip():
            raise ImproperlyConfigured(
                f"LAWMODE_MODELS[{provider!r}] must be a non-empty model id"
            )
        model = value.strip()
        if provider in ANTHROPIC_PROVIDERS and model not in ALLOWED_ANTHROPIC_MODELS:
            raise ImproperlyConfigured(
                f"LAWMODE_MODELS[{provider!r}] is {model!r}; the Anthropic tiers "
                f"accept only {', '.join(ALLOWED_ANTHROPIC_MODELS)} for lawmode. "
                "Remove the override to use the tier's own configured model."
            )
        overrides[provider] = model
    return overrides


def model_overrides() -> dict[str, str]:
    """The validated ``LAWMODE_MODELS`` setting, ready for ``llm.agenerate``.

    Validated on every read, not only at startup, so a value changed after
    boot still cannot hand the chain a model id the rule forbids.

    >>> model_overrides()
    {}
    """
    return validate_model_overrides(getattr(settings, "LAWMODE_MODELS", None))


def validate_settings() -> None:
    """Validate every lawmode setting; called from ``LawmodeConfig.ready()``.

    >>> validate_settings()
    """
    model_overrides()
    load_policy()
