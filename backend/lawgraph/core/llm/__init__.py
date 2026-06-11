"""Unified, audited LLM access layer (spec 024).

Public surface::

    from lawgraph.core.llm import (
        LLMClient, LLMClientAdapter, LLMError,
        LLMResponseError, LLMUnavailableError,
        get_llm_client, reset_llm_client,
    )
"""

from lawgraph.core.llm.adapter import LLMClientAdapter
from lawgraph.core.llm.client import (
    LLMClient,
    LLMError,
    LLMResponseError,
    LLMUnavailableError,
    get_llm_client,
    reset_llm_client,
)

__all__ = [
    "LLMClient",
    "LLMClientAdapter",
    "LLMError",
    "LLMResponseError",
    "LLMUnavailableError",
    "get_llm_client",
    "reset_llm_client",
]
