"""Library reading progress survives the audit log's rotation (BL-20260905-39).

Read state was replayed out of the JSONL audit tail on every request. That
tail is a bounded ring, so once a deployment's log rotated past a read event
the article un-marked itself server-side and the learner's progress went
backwards — invisible in a browser whose ``localStorage`` still remembered,
and immediately visible in a fresh one.

The event is still the audit trail. ``LsatArticleRead`` is the projection that
does not rotate, and these tests are about which one wins when they disagree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from law_ai.lsat.services.library import load_library

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

URL = "/api/lsat/library/read"


@pytest.fixture(autouse=True)
def audit_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "audit.jsonl"
    monkeypatch.setattr(settings, "AUDIT_PATH", str(target))
    return target


def _article() -> Any:
    return next(a for a in load_library().values() if a.sections)


def test_marking_an_article_writes_both_the_event_and_the_row(
    audit_file: Path,
) -> None:
    from law_ai.lsat.models import LsatArticleRead

    article = _article()
    res = APIClient().post(URL, {"article_id": article.id}, format="json")
    assert res.status_code == 200, res.content
    assert res.json()["read"] == [article.id]

    # The audit trail is unchanged — the projection is an addition.
    assert '"lsat_article_read"' in audit_file.read_text(encoding="utf-8")

    row = LsatArticleRead.objects.get(reader="instance", article_id=article.id)
    assert row.read is True
    assert row.kind == str(article.kind)
    assert row.sections == [str(s) for s in article.sections]


def test_progress_survives_the_audit_log_rotating_away(audit_file: Path) -> None:
    """The regression: a rotated log used to un-mark the article."""
    article = _article()
    client = APIClient()
    client.post(URL, {"article_id": article.id}, format="json")

    # Rotation, simulated exactly: the ring dropped every old line.
    audit_file.write_text("", encoding="utf-8")

    body = client.get(URL).json()
    assert body["read"] == [article.id], "read state must not depend on the tail"
    assert body["count"] == 1


def test_unmarking_survives_rotation_too(audit_file: Path) -> None:
    """The projection must not resurrect an article the learner un-marked."""
    from law_ai.lsat.models import LsatArticleRead

    article = _article()
    client = APIClient()
    client.post(URL, {"article_id": article.id}, format="json")
    client.post(URL, {"article_id": article.id, "read": False}, format="json")
    audit_file.write_text("", encoding="utf-8")

    assert client.get(URL).json() == {"read": [], "count": 0}
    # Never hard-deleted (constitution §4): the row records the un-mark.
    row = LsatArticleRead.objects.get(reader="instance", article_id=article.id)
    assert row.read is False
    assert LsatArticleRead.objects.count() == 1


def test_the_row_is_upserted_not_appended() -> None:
    from law_ai.lsat.models import LsatArticleRead

    article = _article()
    client = APIClient()
    for read in (True, False, True):
        client.post(URL, {"article_id": article.id, "read": read}, format="json")
    assert LsatArticleRead.objects.filter(article_id=article.id).count() == 1


def test_a_signed_in_learner_gets_their_own_progress() -> None:
    from django.contrib.auth import get_user_model

    from law_ai.lsat.models import LsatArticleRead

    article = _article()
    # Somebody else's progress, recorded deployment-wide.
    APIClient().post(URL, {"article_id": article.id}, format="json")

    learner = get_user_model().objects.create_user(
        username="reader", password="pw-123456"
    )
    client = APIClient()
    client.force_authenticate(user=learner)
    assert client.get(URL).json()["count"] == 0

    client.post(URL, {"article_id": article.id}, format="json")
    assert LsatArticleRead.objects.filter(reader=f"user:{learner.pk}").count() == 1


def test_an_unreachable_table_degrades_to_the_audit_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No Postgres is a dev state, not a lost bookmark."""
    from law_ai.lsat import models as lsat_models

    article = _article()
    client = APIClient()
    client.post(URL, {"article_id": article.id}, format="json")

    class _Broken:
        @property
        def objects(self) -> Any:
            raise RuntimeError("connection refused")

    monkeypatch.setattr(lsat_models, "LsatArticleRead", _Broken())
    # The JSONL replay still has the event, so the answer is unchanged.
    assert client.get(URL).json() == {"read": [article.id], "count": 1}


def test_stats_counts_the_projection_after_rotation(audit_file: Path) -> None:
    article = _article()
    client = APIClient()
    client.post(URL, {"article_id": article.id}, format="json")
    audit_file.write_text("", encoding="utf-8")

    body = client.get("/api/lsat/stats").json()
    assert body["articles_read"] == 1
    for section in article.sections:
        assert body["by_section"][str(section)]["articles_read"] == 1
