# Plan: LangChain/LangGraph first-class + AO-SDLC guide reimplementation

- **Spec**: [spec.md](spec.md)
- **Status**: shipped

## Architecture

```
LangGraph StateGraph (LegalWorkflow, TopicFrontier, future graphs)
        │  ainvoke(prompt) → AIMessage
        ▼
core/llm/langchain.py  ChatProviderChain(BaseChatModel)   ← spec 035
        │  router.agenerate(...)
        ▼
core/llm/router.py     ordered chain, provenance           ← spec 034
        ▼
claude_code (OAuth) → anthropic_api (key) → ollama (local)
```

**Why a custom `BaseChatModel` instead of `langchain-anthropic`.** The chain's Claude transport authenticates two ways (OAuth bearer + beta header, or `x-api-key`), enforces the no-sampling-params rule, raises on refusal/truncation, and writes chain-level provenance. Wrapping the *router* — not one vendor SDK — keeps all of that in one place and gives LangChain consumers the fallback tiers for free. A vendor adapter would sit beside the chain, not in front of it, and would bypass the audit trail.

**Why the deps move to core.** The default engine (LangGraph), its checkpointer (boot-provisioned), and the chain's Ollama tier (langchain-ollama transport in `agents_runtime/llm.py`) are all load-bearing in the shipped container. "Optional extra" was a fiction the Dockerfile papered over; CI's clean-install smoke now proves the honest layout.

**Why compose gains `POSTGRES_URL`.** The checkpointer deliberately reads its own URL (async driver, separate pool) rather than Django's `DATABASE_URL`. Compose overrode only the latter, so `.env`'s host-oriented value leaked into containers and `ensure_schema()` — log-only by design — silently skipped. The fix is one explicit override per service, mirroring `DATABASE_URL`.

## Key decisions

| Decision | Rationale |
|---|---|
| Message folding: single human turn verbatim, multi-turn as labeled transcript | The graphs prompt per-node with one string; transcripts keep sent history honest rather than silently dropping it |
| `_generate` (sync) delegates to `router.generate`, which refuses inside a running loop | Same contract as the rest of the chain: blocking the event loop stalls the worker |
| Keep `ChainRunnable` | Non-LangChain call sites still use it; deleting it would churn spec-034 code for no gain |
| Phoenix/OTel stays optional | The app degrades cleanly without tracing; that is what an extra is for |
| Guide rewritten in place, v2.0, same filename | History preserved in git; v1's aspirational claims retired explicitly rather than deleted silently |

## E2E validation script (repeatable)

The LangGraph validation from spec §10 — a two-node StateGraph over `ChatProviderChain` with the repo's Postgres checkpointer:

```python
# docker compose run -T --rm backend python manage.py shell < e2e.py
import asyncio, uuid
from typing_extensions import TypedDict
from langgraph.graph import END, StateGraph
from law_ai.core.llm import ChatProviderChain

class S(TypedDict, total=False):
    question: str; answer: str; model_label: str

model = ChatProviderChain(agent="spec035_e2e_validation")

async def ask(state: S) -> S:
    reply = await model.ainvoke("In one short sentence: what did Marbury v. Madison establish?")
    return {"answer": reply.content,
            "model_label": reply.response_metadata.get("model_label", "?")}

g = StateGraph(S); g.add_node("ask", ask); g.set_entry_point("ask"); g.add_edge("ask", END)

async def main():
    from law_ai.agents_runtime.checkpointer import ensure_schema
    from law_ai.agents_runtime.graphs.runtime import build_checkpointer
    await ensure_schema()
    thread = f"spec035-{uuid.uuid4()}"
    async with build_checkpointer() as saver:
        app = g.compile(checkpointer=saver)
        out = await app.ainvoke({"question": "marbury"},
                                config={"configurable": {"thread_id": thread}})
        snap = await app.aget_state({"configurable": {"thread_id": thread}})
    assert out["model_label"].startswith("claude_code/")
    assert snap.values.get("answer")
    print("E2E_OK", out["model_label"])

asyncio.run(main())
```

## Test strategy

- `tests/core/test_llm_langchain.py`: BaseChatModel subclassing, message folding (system/single/multi-turn/list-parts), AIMessage metadata incl. fallback labeling, `_coerce_text` compatibility with the default engine. Router stubbed — routing itself is spec 034's suite.
- Existing `legal_workflow` tests keep passing via their DI `llm_factory` seams; the default factory is covered by the compatibility test.
- Live validation is manual-but-scripted (§9 of the guide) — deliberately not in CI, since it spends real API budget.
