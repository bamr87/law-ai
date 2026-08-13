"""Prompt templates + registry (spec 036).

This directory holds the versioned prompt markdown files (``<name>.v<N>.md``,
``legal_workflow/*.md``) and the code that enumerates and mirrors them into
the self-hosted Arize Phoenix prompt store. The markdown files are the
canonical prompt source; Phoenix is a read-only mirror.
"""

from law_ai.agents_runtime.prompts.registry import LocalPrompt, iter_local_prompts

__all__ = ["LocalPrompt", "iter_local_prompts"]
