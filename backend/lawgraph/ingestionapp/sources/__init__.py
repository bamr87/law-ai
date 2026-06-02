"""SOURCE_REGISTRY — central allow-listed adapter registry (spec 018 T-006).

Usage::

    from lawgraph.ingestionapp.sources import SOURCE_REGISTRY
    adapter = SOURCE_REGISTRY["courtlistener"]
    docs = list(adapter.fetch("Brown v. Board"))
"""

from __future__ import annotations

from lawgraph.ingestionapp.sources.base import RawDoc, SourceAdapter
from lawgraph.ingestionapp.sources.courtlistener import CourtListenerAdapter
from lawgraph.ingestionapp.sources.colorado_statutes import ColoradoStatutesAdapter
from lawgraph.ingestionapp.sources.statute_scout import StatuteScoutAdapter

# Registry is a plain dict; ``AUTONOMY_ALLOWED_SOURCES`` is the runtime
# allow-list (constitution §12 invariant I2). Adapters are registered here
# but only used when their name appears in the allow-list setting.
SOURCE_REGISTRY: dict[str, SourceAdapter] = {
    CourtListenerAdapter.name: CourtListenerAdapter(),
    ColoradoStatutesAdapter.name: ColoradoStatutesAdapter(),
    StatuteScoutAdapter.name: StatuteScoutAdapter(),
}

__all__ = ["SOURCE_REGISTRY", "RawDoc", "SourceAdapter"]
