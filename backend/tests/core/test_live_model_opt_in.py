"""Live-model integration tests opt in explicitly, never via the ambient env.

bamr87/bamr87#253 (faults 2 & 3): ``test_run_autonomy_integration`` treated
the compose ``backend`` service's ``OLLAMA_BASE_URL`` as an opt-in, so the
nightly's plain ``make test-coverage`` ran two live autonomy cycles against a
7B on a CPU-only runner and failed after ~24 minutes. Both live modules must
read ``OLLAMA_INTEGRATION_URL`` and nothing else. Deterministic: no network,
the modules are re-imported under a controlled environment.
"""

from __future__ import annotations

import importlib
import sys

import pytest

_MODULES = (
    "tests.core.test_run_autonomy_integration",
    "tests.lsat.test_factory_ollama_integration",
)


def _fresh(name: str, monkeypatch: pytest.MonkeyPatch):
    # Drop the module from sys.modules *and* from its parent package, so
    # monkeypatch puts both back on teardown. Restoring only sys.modules left
    # `tests.lsat.test_factory_ollama_integration` (the package attribute)
    # pointing at the fresh copy, and test_factory_command's
    # `importlib.reload(mod)` then failed with "module ... not in sys.modules".
    parent, _, child = name.rpartition(".")
    package = importlib.import_module(parent)
    monkeypatch.delitem(sys.modules, name, raising=False)
    if hasattr(package, child):
        monkeypatch.delattr(package, child)
    return importlib.import_module(name)


@pytest.mark.parametrize("name", _MODULES)
def test_the_compose_base_url_alone_does_not_opt_in(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OLLAMA_INTEGRATION_URL", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")
    mod = _fresh(name, monkeypatch)
    assert mod._candidate_url() == ""
    assert mod._URL == ""


@pytest.mark.parametrize("name", _MODULES)
def test_the_explicit_integration_url_opts_in(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OLLAMA_INTEGRATION_URL", "http://ollama:11434")
    mod = _fresh(name, monkeypatch)
    assert mod._candidate_url() == "http://ollama:11434"
