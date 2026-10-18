"""The Law AI LLM layer — one Claude-first provider chain for the whole app.

Import this package, not a specific transport::

    from law_ai.core import llm

    result = await llm.agenerate(prompt, system=SYS, json_mode=True)
    payload = llm.loads_first_json(result.text)
    label = result.model_label            # "claude_code/claude-opus-5-5"

Token streaming is opt-in per call site (BL-20260811-20) — the same chain,
the same fallback, the same ``llm_call`` provenance event::

    async for chunk in llm.astream(prompt, agent="lsat_tutor"):
        render(chunk.text)            # chunk.model_label names the serving tier

The chain (``LLM_PROVIDER_CHAIN``, default
``claude_code,anthropic_api,xai,ollama``) tries Claude over an OAuth
subscription token first, Claude over ``ANTHROPIC_API_KEY`` second, xAI Grok
over a subscription OAuth token third, and the local Ollama model last. See
:mod:`law_ai.core.llm.router` for routing/fallback semantics and
:mod:`law_ai.core.llm.providers` for the transports.
"""

from __future__ import annotations

# Re-exported so chatty-model JSON handling has one home shared by every
# call site (the LSAT tutor, the content author, the analyst, the factory).
from law_ai.core.claude_code import (
    ClaudeCodeUnavailableError,
    ClaudeCredentialError,
    ClaudeRefusalError,
    loads_first_json,
    strip_code_fence,
)
from law_ai.core.llm.langchain import ChatProviderChain
from law_ai.core.llm.base import (
    LLMAttempt,
    LLMChunk,
    LLMProvider,
    LLMRequest,
    LLMPermanentError,
    LLMResult,
    LLMStreamInterrupted,
    LLMUnavailableError,
    LLMUsage,
    ProviderReply,
    usage_of,
)
from law_ai.core.llm.providers import (
    ANTHROPIC_API,
    CLAUDE_OAUTH,
    OLLAMA,
    PROVIDER_REGISTRY,
    XAI,
    AnthropicAPIProvider,
    ClaudeOAuthProvider,
    OllamaProvider,
    XaiProvider,
)
from law_ai.core.llm.router import (
    DEFAULT_CHAIN,
    ChainRunnable,
    agenerate,
    aroute,
    aroute_stream,
    astream,
    build_chain,
    build_runnable,
    chain_names,
    chain_status,
    classify_failure,
    estimate_cost_usd,
    generate,
    reset_permanent_failures,
)

__all__ = [
    "ANTHROPIC_API",
    "CLAUDE_OAUTH",
    "DEFAULT_CHAIN",
    "OLLAMA",
    "PROVIDER_REGISTRY",
    "XAI",
    "AnthropicAPIProvider",
    "ChainRunnable",
    "ChatProviderChain",
    "ClaudeCodeUnavailableError",
    "ClaudeCredentialError",
    "ClaudeOAuthProvider",
    "ClaudeRefusalError",
    "LLMAttempt",
    "LLMChunk",
    "LLMPermanentError",
    "LLMProvider",
    "LLMRequest",
    "LLMResult",
    "LLMStreamInterrupted",
    "LLMUnavailableError",
    "LLMUsage",
    "OllamaProvider",
    "ProviderReply",
    "XaiProvider",
    "agenerate",
    "aroute",
    "aroute_stream",
    "astream",
    "build_chain",
    "build_runnable",
    "chain_names",
    "chain_status",
    "classify_failure",
    "estimate_cost_usd",
    "generate",
    "loads_first_json",
    "reset_permanent_failures",
    "strip_code_fence",
    "usage_of",
]
