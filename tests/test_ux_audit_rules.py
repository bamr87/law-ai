"""Unit tests for the reduced-motion rule in scripts/ux_audit.py — BL-20260906-72.

`HomeMotion.test.tsx` renders five sampled components, so it proves those five
and nothing else: a sixth file could re-introduce an unguarded `animate-*` and
no gate would notice. R15 makes the whole of `frontend/app`, `frontend/components`
and the static export the contract instead.

These pin the decision, not the sweep — the sweep itself is `make lint-specs`,
which runs the script over the real tree.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def audit_script(repo_root: Path) -> ModuleType:
    """Import the script by path — scripts/ is not an importable package."""
    path = repo_root / "scripts" / "ux_audit.py"
    spec = importlib.util.spec_from_file_location("_ux_audit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: `Audit` is a dataclass, and dataclasses resolve
    # their own annotations through `sys.modules[cls.__module__]`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _findings(script: ModuleType, source: str) -> list[str]:
    audit = script.Audit()
    script.rule_reduced_motion(Path("Fake.tsx"), source.split("\n"), audit)
    return [f.message for f in audit.findings if f.rule == "R15"]


def test_r15_is_a_declared_rule(audit_script: ModuleType) -> None:
    assert ("R15", "every animate-* utility opts out of reduced motion") in (
        audit_script.RULES
    )


def test_a_bare_animate_utility_is_a_finding(audit_script: ModuleType) -> None:
    found = _findings(audit_script, '<div className="h-8 animate-pulse rounded" />')
    assert len(found) == 1
    assert "animate-pulse" in found[0]


def test_motion_reduce_opt_out_satisfies_the_rule(audit_script: ModuleType) -> None:
    source = '<div className="animate-pulse motion-reduce:animate-none" />'
    assert _findings(audit_script, source) == []


def test_motion_safe_prefix_satisfies_the_rule(audit_script: ModuleType) -> None:
    source = '<div className="motion-safe:animate-spin" />'
    assert _findings(audit_script, source) == []


def test_animate_none_alone_is_not_an_animation(audit_script: ModuleType) -> None:
    assert _findings(audit_script, '<div className="animate-none" />') == []


def test_the_real_tree_satisfies_r15(repo_root: Path, audit_script: ModuleType) -> None:
    """Every animation shipped today already opts out — keep it that way."""
    offenders: list[str] = []
    roots = [
        repo_root / "frontend" / "app",
        repo_root / "frontend" / "components",
        repo_root / "lsat-static" / "app",
        repo_root / "lsat-static" / "components",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.tsx")):
            text = path.read_text(encoding="utf-8")
            if audit_script.EXEMPT_RE.search(text):
                continue
            for message in _findings(audit_script, text):
                offenders.append(f"{path.relative_to(repo_root)}: {message}")
    assert not offenders, offenders
