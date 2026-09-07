"""SOURCE_REGISTRY — central allow-listed adapter registry (spec 018 T-006).

Usage::

    from law_ai.ingestionapp.sources import SOURCE_REGISTRY
    adapter = SOURCE_REGISTRY["courtlistener"]

    docs = await adapter.afetch("Brown v. Board")   # inside an event loop
    docs = list(adapter.fetch("Brown v. Board"))    # from a plain thread

``afetch`` is the primitive adapters implement (BL-20260511-08); ``fetch`` is
the base class's sync shim and raises when called from a running loop.
"""

from __future__ import annotations

from law_ai.ingestionapp.sources.base import RawDoc, SourceAdapter
from law_ai.ingestionapp.sources.courtlistener import CourtListenerAdapter
from law_ai.ingestionapp.sources.colorado_statutes import ColoradoStatutesAdapter
from law_ai.ingestionapp.sources.denver_municipal_code import (
    DenverMunicipalCodeAdapter,
)
from law_ai.ingestionapp.sources.statute_scout import StatuteScoutAdapter

# Registry is a plain dict; ``AUTONOMY_ALLOWED_SOURCES`` is the runtime
# allow-list (constitution §12 invariant I2). Adapters are registered here
# but only used when their name appears in the allow-list setting.
SOURCE_REGISTRY: dict[str, SourceAdapter] = {
    CourtListenerAdapter.name: CourtListenerAdapter(),
    ColoradoStatutesAdapter.name: ColoradoStatutesAdapter(),
    # BL-20260509-05. requires_human_approval=True, so registering it cannot
    # by itself put a municipal ordinance in the graph.
    DenverMunicipalCodeAdapter.name: DenverMunicipalCodeAdapter(),
    StatuteScoutAdapter.name: StatuteScoutAdapter(),
}

__all__ = ["SOURCE_REGISTRY", "RawDoc", "SourceAdapter"]
