"""Unit tests for scripts/check_am1_eligible.py — the AM-1 auto-merge gate.

Safety-critical: AM-1 is the only class allowed to auto-merge (constitution
§12 I1 as amended by ADR 0004), so these tests focus on *rejecting* anything
that isn't a pure autonomy-proposed-test un-skip.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_am1_eligible.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_am1_eligible", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_PROPOSED = "backend/tests/autonomy/proposed/test_foo.proposed.py"


def _diff(path: str, body: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"index 1234567..89abcde 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,5 +1,4 @@\n" + body
    )


def test_eligible_pure_unskip():
    m = _load()
    body = (
        " import pytest\n"
        " \n"
        '-@pytest.mark.skip("autonomy-proposed")\n'
        " def test_foo():\n"
        "     assert True\n"
    )
    v = m.evaluate(_diff(_PROPOSED, body))
    assert v["eligible"] is True, v
    assert v["skip_decorators_removed"] == 1


def test_rejects_non_proposed_file():
    m = _load()
    body = '-@pytest.mark.skip("autonomy-proposed")\n def test_x(): ...\n'
    v = m.evaluate(_diff("backend/lawgraph/core/foo.py", body))
    assert v["eligible"] is False
    assert any("non-proposed file" in r for r in v["reasons"])


def test_rejects_added_code():
    m = _load()
    body = (
        '-@pytest.mark.skip("autonomy-proposed")\n'
        " def test_foo():\n"
        "+    do_something_new()\n"
        "     assert True\n"
    )
    v = m.evaluate(_diff(_PROPOSED, body))
    assert v["eligible"] is False
    assert any("removal-only" in r for r in v["reasons"])


def test_rejects_removed_real_code():
    m = _load()
    body = (
        '-@pytest.mark.skip("autonomy-proposed")\n'
        "-    assert legacy_behaviour()\n"
        " def test_foo():\n"
        "     assert True\n"
    )
    v = m.evaluate(_diff(_PROPOSED, body))
    assert v["eligible"] is False
    assert any("removed non-skip line" in r for r in v["reasons"])


def test_rejects_empty_diff():
    m = _load()
    v = m.evaluate("")
    assert v["eligible"] is False


def test_rejects_no_skip_removed():
    m = _load()
    body = " import pytest\n-\n def test_foo():\n     assert True\n"  # only a blank removed
    v = m.evaluate(_diff(_PROPOSED, body))
    assert v["eligible"] is False
    assert any("no autonomy-proposed skip" in r for r in v["reasons"])


def test_eligible_multiple_files_and_decorators():
    m = _load()
    f2 = "backend/tests/autonomy/proposed/test_bar.proposed.py"
    diff = _diff(
        _PROPOSED, '-@pytest.mark.skip("autonomy-proposed")\n def a(): ...\n'
    ) + _diff(f2, '-    @pytest.mark.skip("autonomy-proposed")\n def b(): ...\n')
    v = m.evaluate(diff)
    assert v["eligible"] is True, v
    assert v["skip_decorators_removed"] == 2
    assert set(v["files"]) == {_PROPOSED, f2}
