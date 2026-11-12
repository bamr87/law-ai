"""Static guard: lawmode has no provider of its own (spec 057 FR-2, AC-2).

The imported ``lawmode/`` tree defaulted to an OpenAI model through
``langchain-openai`` and called Grok over raw ``requests``. None of that may
come back in the folded app, and "it is not there today" is not a guarantee —
so this reads the source the way the issue's acceptance check greps it:

    git grep -n "openai\\|gpt-4o\\|requests" backend/law_ai/lawmode   # empty

and adds the structural half: no ``llm`` package, no transport import, and no
Anthropic model id in code beyond the three the spec allows.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

import law_ai.core.llm as chain
import law_ai.lawmode
from law_ai.lawmode.policy import ALLOWED_ANTHROPIC_MODELS

pytestmark = pytest.mark.unit

LAWMODE_DIR = Path(law_ai.lawmode.__file__).resolve().parent
BACKEND_DIR = LAWMODE_DIR.parents[1]
PROMPT_DIR = LAWMODE_DIR.parent / "agents_runtime" / "prompts" / "lawmode"

#: Case-insensitive. The first three are the issue's acceptance criterion; the
#: rest are the other pieces of lawmode's provider layer that were dropped.
FORBIDDEN = (
    "openai",
    "gpt-4o",
    "requests",
    "langchain_openai",
    "langchain-openai",
    "langchain_anthropic",
    "langchain-anthropic",
    "grok-2-1212",
    "gemini",
    "api_key",
)

#: Everything the app may import, by exact module name. An allow-list rather
#: than a list of known-bad names: an HTTP client, a vendor SDK, a transport
#: module or a new wrapper library all fail the same way — by not being here.
#: ``law_ai.core.llm`` is the chain's front door; nothing beneath it is listed.
ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "collections.abc",
        "datetime",
        "enum",
        "hashlib",
        "json",
        "logging",
        "pathlib",
        "re",
        "time",
        "typing",
        "uuid",
        "django.apps",
        "django.core.exceptions",
        "pydantic",
        "law_ai.core.llm",
        "law_ai.core.provenance",
        "law_ai.core.settings_proxy",
        "law_ai.lawmode",
        "law_ai.lawmode.policy",
        "law_ai.lawmode.schemas",
    }
)


def _resolved(module: str, name: str) -> str:
    """The module an imported name really is.

    ``from law_ai.core import xai`` imports the module ``law_ai.core.xai``,
    and ``from law_ai.core.llm import router`` a module beneath the chain's
    front door; both are spelled out so the allow-list sees them.
    """
    if module == "law_ai.core":
        return f"law_ai.core.{name}"
    if module == "law_ai.core.llm" and name not in chain.__all__:
        return f"law_ai.core.llm.{name}"
    return module


def _imports(path: Path) -> set[str]:
    """Every module a file imports, at any depth in the file."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            found |= {_resolved(node.module or "", alias.name) for alias in node.names}
    return found


MODEL_ID = re.compile(r"claude-[a-z0-9][a-z0-9.\-]*")


def _text_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".md", ".txt", ".json", ".yaml"}
    )


def test_the_guard_is_looking_at_real_files() -> None:
    names = {
        path.relative_to(LAWMODE_DIR).as_posix() for path in _text_files(LAWMODE_DIR)
    }

    assert {
        "__init__.py",
        "apps.py",
        "schemas.py",
        "policy.py",
        "disclaimer.md",
        "services/review.py",
        "services/artifacts.py",
    } <= names
    assert (PROMPT_DIR / "review.v1.md").is_file()


@pytest.mark.parametrize("token", FORBIDDEN)
def test_the_token_appears_nowhere_in_the_app_or_its_prompts(token: str) -> None:
    offenders = [
        path.relative_to(BACKEND_DIR).as_posix()
        for path in _text_files(LAWMODE_DIR) + _text_files(PROMPT_DIR)
        if token in path.read_text(encoding="utf-8").lower()
    ]

    assert offenders == [], f"{token!r} found in {offenders}"


def test_lawmodes_own_llm_package_was_not_ported() -> None:
    assert not (LAWMODE_DIR / "llm").exists()
    assert not (LAWMODE_DIR / "llm.py").exists()
    assert not (LAWMODE_DIR / "github").exists()


def test_no_module_reaches_a_model_except_through_the_chain() -> None:
    offenders = {
        path.relative_to(LAWMODE_DIR).as_posix(): sorted(
            _imports(path) - ALLOWED_IMPORTS
        )
        for path in LAWMODE_DIR.rglob("*.py")
        if _imports(path) - ALLOWED_IMPORTS
    }

    assert offenders == {}


@pytest.mark.parametrize(
    "source",
    [
        "import httpx",
        "import requests",
        "import http.client",
        "import litellm",
        "from crewai import LLM",
        "from langchain_openai import ChatOpenAI",
        "from law_ai.core import claude_code",
        "from law_ai.core import llm, xai",
        "from law_ai.core.llm.providers import OllamaProvider",
        "from law_ai.core.llm import router",
        "from law_ai.core.llm import agenerate, providers",
        "import law_ai.core.claude_code",
        "def f():\n    import anthropic",
    ],
)
def test_the_import_guard_catches_a_way_round_the_chain(
    tmp_path: Path, source: str
) -> None:
    """The guard is only worth having if these would actually fail it."""
    module = tmp_path / "sneaky.py"
    module.write_text(source + "\n", encoding="utf-8")

    assert _imports(module) - ALLOWED_IMPORTS


@pytest.mark.parametrize(
    "source",
    [
        "from law_ai.core import llm",
        "from law_ai.core.llm import ANTHROPIC_API, PROVIDER_REGISTRY",
        "from law_ai.core.provenance import provenance",
    ],
)
def test_the_import_guard_lets_the_sanctioned_entry_points_through(
    tmp_path: Path, source: str
) -> None:
    module = tmp_path / "fine.py"
    module.write_text(source + "\n", encoding="utf-8")

    assert _imports(module) <= ALLOWED_IMPORTS


def test_the_review_calls_the_chains_entry_point() -> None:
    source = (LAWMODE_DIR / "services" / "review.py").read_text(encoding="utf-8")

    assert "from law_ai.core import llm" in source
    assert "llm.agenerate(" in source
    assert "provenance.log_agent_call(" in source


def test_the_only_anthropic_model_ids_in_code_are_the_allowed_three() -> None:
    named: set[str] = set()
    for path in _text_files(LAWMODE_DIR) + _text_files(PROMPT_DIR):
        named |= set(MODEL_ID.findall(path.read_text(encoding="utf-8")))

    assert named == set(ALLOWED_ANTHROPIC_MODELS)


def test_only_the_policy_names_a_model_at_all() -> None:
    """A model id anywhere else would be a default by another name."""
    naming = {
        path.relative_to(LAWMODE_DIR).as_posix()
        for path in LAWMODE_DIR.rglob("*.py")
        if MODEL_ID.search(path.read_text(encoding="utf-8"))
    }

    assert naming == {"policy.py"}


def test_the_backend_did_not_gain_lawmodes_dropped_dependencies() -> None:
    """NFR-DEP-1: the port adds no dependency, least of all these."""
    project = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text())["project"]
    declared = list(project["dependencies"])
    for extra in project.get("optional-dependencies", {}).values():
        declared += extra
    names = {re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].lower() for spec in declared}

    assert not names & {
        "openai",
        "langchain-openai",
        "langchain-anthropic",
        "requests",
        "click",
        "rich",
        "gitpython",
        "pyyaml",
    }
