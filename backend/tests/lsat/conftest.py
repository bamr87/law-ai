"""Shared fixtures for LSAT service + factory tests (spec 024)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from django.conf import settings


@pytest.fixture()
def factory_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    """Isolated stores + sandboxed bank for factory tests (NOT autouse).

    Mirrors test_proposals' isolation pattern: audit log, proposal store, and
    factory artifacts all point at the test tmp dir, and the bank data dir is
    a per-test copy so nothing mutates checked-in fixtures. Yields a
    FactoryConfig rooted in the tmp dir.
    """
    from law_ai.lsat.factory.config import FactoryConfig
    from law_ai.lsat.services import bank as bank_mod

    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        settings, "LSAT_PROPOSALS_DIR", str(tmp_path / "proposals"), raising=False
    )
    monkeypatch.setattr(
        settings, "LSAT_FACTORY_DIR", str(tmp_path / "factory"), raising=False
    )

    real_data_dir = bank_mod.DATA_DIR
    sandbox = tmp_path / "lsat_data"
    sandbox.mkdir()
    for name in (
        "lr_bank.json",
        "rc_bank.json",
        "lg_bank.json",
        "concepts.json",
        "passages.json",
        "sections.json",
        # The factory plans for the writing library too (BL-20260831-28), so
        # a sandboxed run needs its files as well.
        "writing_prompts.json",
        "writing_rubrics.json",
    ):
        src = real_data_dir / name
        if src.is_file():
            (sandbox / name).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8"
            )
    monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)

    def _clear() -> None:
        from law_ai.lsat.services.writing import reset_writing_caches

        reset_writing_caches()
        bank_mod.load_bank.cache_clear()
        bank_mod.load_concepts.cache_clear()
        bank_mod.load_passages.cache_clear()
        bank_mod.load_sections.cache_clear()

    _clear()
    yield FactoryConfig(output_dir=tmp_path / "factory")
    _clear()
