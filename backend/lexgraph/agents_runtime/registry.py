"""
Agent Registry - Central place to register and discover all LawGraph agents.

This allows the Orchestrator to dynamically route tasks and enables
the /api/agents endpoint for introspection.
"""

from lawgraph.agents_runtime.crews.legal_analyst import LegalAnalyst
from lawgraph.agents_runtime.crews.precedent_hunter import PrecedentHunter
from lawgraph.ingestionapp.services.scout import IngestionScout

# ... import other agents

AGENT_REGISTRY: dict[str, type] = {}


def register_agent(name: str, agent_class: type) -> None:
    """Register a new agent class."""
    AGENT_REGISTRY[name] = agent_class
    print(f"✅ Registered agent: {name}")


def register_all_agents() -> None:
    """Register all agents used in LawGraph AI."""
    register_agent("LegalAnalyst", LegalAnalyst)
    register_agent("PrecedentHunter", PrecedentHunter)
    register_agent("IngestionScout", IngestionScout)
    # register_agent("LogicWeaver", LogicWeaver)
    # register_agent("Educator", Educator)
    # register_agent("Orchestrator", Orchestrator)


def get_agent(name: str):
    """Retrieve an agent class by name."""
    return AGENT_REGISTRY.get(name)
