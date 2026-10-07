"""The embedded scanner (spec 055): its status, the upload door, and the routing.

The library is stubbed throughout — the suite has no OCR engine and must not need one.
What is under test is everything around it: the feature flag, the install check, what an
upload may be, how a page is routed to each door, and that the embedded path is honest
about being OCR-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from law_ai.ingestionapp.services import ocrmd_plugin as plug
from tests.agents.test_lsat_source_extractor import (
    PAGE_TEXT,
    _extract_payload,
    _llm_result,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _fake_scan(
    path: Path, doc: str, *, max_pages: int | None = None
) -> plug.ScanResult:
    return plug.ScanResult(
        document=doc,
        engine="rapidocr@3.0",
        pages=[
            {
                "ocrmd": 1,
                "kind": "page",
                "text": PAGE_TEXT,
                "provenance": {
                    "tool": "ocrmd",
                    "document": doc,
                    "page": 1,
                    "page_id": "feedface",
                    "status": "unverified",
                    "llm_model": "",
                    "image_url": "",
                    "page_url": "",
                    "store_root": "/app/var/ocrmd",
                },
                "document": {"slug": doc},
            }
        ],
    )


@pytest.fixture
def on(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The plug-in enabled and 'installed', the scanner stubbed."""
    settings.ENABLE_OCRMD = True
    monkeypatch.setattr(plug, "installed", lambda: True)
    monkeypatch.setattr(plug, "scan_file", _fake_scan)


def _upload(name: str = "page.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, PNG, content_type="image/png")


class TestEnvelopeModel:
    def test_default_title_prefers_the_printed_label(self) -> None:
        env = plug.Envelope.model_validate(
            {
                "text": "x",
                "provenance": {"document": "d", "page": 4, "page_label": "iv"},
                "document": {"title": "A Book"},
            }
        )
        assert env.default_title() == "A Book, p. iv"
        env = plug.Envelope.model_validate(
            {"text": "x", "provenance": {"document": "d", "page": 4}}
        )
        assert env.default_title() == "d, page 4"

    def test_is_envelope_tells_the_shapes_apart(self) -> None:
        assert plug.is_envelope({"text": "x", "ocrmd": 1})
        assert plug.is_envelope({"text": "x", "provenance": {}})
        assert not plug.is_envelope({"source_text": "x"})

    def test_caveats_name_what_a_reviewer_should_know(self) -> None:
        prov = plug.Provenance(llm_model="", status="suspect", unresolved=3)
        text = " | ".join(prov.caveats())
        assert (
            "one reading only" in text and "suspect" in text and "3 unresolved" in text
        )
        assert plug.Provenance(llm_model="m", status="verified").caveats() == []

    def test_descriptor_and_option_shapes(self) -> None:
        d = plug.descriptor(
            "n", "desc", [plug.option("k", "enum", choices=["a"], default="a")]
        )
        assert d["ocrmd_sink"] == 1 and d["accepts"] == ["page", "region"]
        assert d["options"][0] == {
            "key": "k",
            "type": "enum",
            "label": "k",
            "choices": ["a"],
            "default": "a",
        }


class TestStatus:
    def test_off_and_absent_by_default(self) -> None:
        res = APIClient().get("/api/ingestion/ocrmd/status")
        assert res.status_code == 200, res.content
        body = res.json()
        assert body["enabled"] is False and body["installed"] is False
        assert set(body["doors"]) == {"lsat", "matter", "scan"}
        assert "OCR only" in body["llm"]

    def test_library_refuses_when_off_or_absent(
        self, settings: Any, monkeypatch: Any
    ) -> None:
        with pytest.raises(plug.OcrmdUnavailable, match="ENABLE_OCRMD"):
            plug.library()
        settings.ENABLE_OCRMD = True
        monkeypatch.setattr(plug, "installed", lambda: False)
        with pytest.raises(plug.OcrmdUnavailable, match="INSTALL_OCRMD=1"):
            plug.library()


class TestScanFile:
    def test_the_library_is_driven_ocr_only_and_closed(
        self, settings: Any, monkeypatch: Any, tmp_path: Path
    ) -> None:
        calls: list[Any] = []

        class Page:
            sequence = 1
            frontmatter = {"ocr": {"engine": "rapidocr@3.0"}}

        class Report:
            pages = [Page()]
            duplicates = 0
            rejected = 0
            unreadable: list[str] = []

        class FakeLibrary:
            def ingest(self, paths: Any, doc: str, **kw: Any) -> Report:
                calls.append(("ingest", list(paths), doc, kw))
                return Report()

            def envelope(self, doc: str, seq: int) -> dict[str, Any]:
                return {
                    "ocrmd": 1,
                    "kind": "page",
                    "text": "hello",
                    "document": {"slug": doc},
                    "provenance": {
                        "document": doc,
                        "page": seq,
                        "page_id": "p1",
                        "image_url": "http://scanner/x",
                        "page_url": "http://scanner/y",
                    },
                }

            def close(self) -> None:
                calls.append(("close",))

        monkeypatch.setattr(plug, "library", FakeLibrary)
        out = plug.scan_file(tmp_path / "p.png", "up", max_pages=5)
        assert calls[0][0] == "ingest" and calls[0][3] == {"llm": False}
        assert calls[-1] == ("close",)
        assert out.engine == "rapidocr@3.0" and "OCR only" in out.summary()
        prov = out.pages[0]["provenance"]
        assert prov["image_url"] == "" and prov["page_url"] == "" and prov["store_root"]


class TestScanRoute:
    def test_off_is_503(self) -> None:
        res = APIClient().post(
            "/api/ingestion/ocrmd/scan", {"file": _upload()}, format="multipart"
        )
        assert res.status_code == 503 and "ENABLE_OCRMD" in res.json()["detail"]

    def test_absent_is_503(self, settings: Any, monkeypatch: Any) -> None:
        settings.ENABLE_OCRMD = True
        monkeypatch.setattr(plug, "installed", lambda: False)
        res = APIClient().post(
            "/api/ingestion/ocrmd/scan", {"file": _upload()}, format="multipart"
        )
        assert res.status_code == 503 and "INSTALL_OCRMD" in res.json()["detail"]

    def test_what_an_upload_may_be(self, on: None) -> None:
        client = APIClient()
        assert (
            client.post("/api/ingestion/ocrmd/scan", {}, format="multipart").status_code
            == 422
        )
        res = client.post(
            "/api/ingestion/ocrmd/scan",
            {"file": _upload("notes.txt")},
            format="multipart",
        )
        assert res.status_code == 422 and "unsupported" in res.json()["detail"]
        res = client.post(
            "/api/ingestion/ocrmd/scan",
            {"file": _upload(), "doc": "bad slug!"},
            format="multipart",
        )
        assert res.status_code == 422
        res = client.post(
            "/api/ingestion/ocrmd/scan",
            {"file": _upload(), "options": "{not json"},
            format="multipart",
        )
        assert res.status_code == 422
        res = client.post(
            "/api/ingestion/ocrmd/scan",
            {"file": _upload(), "target": "elsewhere"},
            format="multipart",
        )
        assert res.status_code == 422

    def test_a_page_is_read_and_returned_honestly(self, on: None) -> None:
        res = APIClient().post(
            "/api/ingestion/ocrmd/scan",
            {"file": _upload(), "doc": "uploads"},
            format="multipart",
        )
        assert res.status_code == 200, res.content
        body = res.json()
        assert body["llm"] == "none" and body["engine"] == "rapidocr@3.0"
        assert body["pages"][0]["page_id"] == "feedface"
        assert body["pages"][0]["status"] == "unverified"
        assert "transit proposal" in body["pages"][0]["text"]
        assert body["routed"] == [None]
        assert "OCR only" in body["summary"]

    def test_routed_to_the_lsat_door(
        self, on: None, tmp_path: Path, settings: Any
    ) -> None:
        settings.LSAT_PROPOSALS_DIR = str(tmp_path)
        with patch(
            "law_ai.core.llm.agenerate",
            new=AsyncMock(return_value=_llm_result(_extract_payload())),
        ):
            res = APIClient().post(
                "/api/ingestion/ocrmd/scan",
                {
                    "file": _upload(),
                    "target": "lsat",
                    "options": '{"hint": "question 15"}',
                },
                format="multipart",
            )
        assert res.status_code == 200, res.content
        routed = res.json()["routed"][0]
        assert routed["door"] == "lsat"
        assert routed["summary"].startswith("1 question(s) queued")
        assert routed["items"][0]["status"] == "pending"

    def test_routed_to_a_matter_needs_a_signed_in_owner(self, on: None) -> None:
        anon = APIClient().post(
            "/api/ingestion/ocrmd/scan",
            {"file": _upload(), "target": "matter:smith"},
            format="multipart",
        )
        assert anon.status_code == 401
        owner = get_user_model().objects.create_user(
            username="ada", password="pw-12345678"
        )
        client = APIClient()
        client.force_authenticate(user=owner)
        assert (
            client.post(
                "/api/ingestion/ocrmd/scan",
                {"file": _upload(), "target": "matter:nope"},
                format="multipart",
            ).status_code
            == 404
        )
        made = client.post(
            "/api/matters", {"name": "Smith lease"}, format="json"
        ).json()
        res = client.post(
            "/api/ingestion/ocrmd/scan",
            {"file": _upload(), "target": f"matter:{made['slug']}"},
            format="multipart",
        )
        assert res.status_code == 200, res.content
        routed = res.json()["routed"][0]
        assert routed["door"] == "matter" and routed["summary"].startswith(
            "filed as document"
        )
        # the embedded scanner's single reading is named to whoever files it
        assert any("one reading only" in w for w in routed["warnings"])


class TestCommand:
    def test_refuses_when_off(self, tmp_path: Path) -> None:
        with pytest.raises(CommandError, match="ENABLE_OCRMD"):
            call_command("ocrmd_scan", str(tmp_path))

    def test_scans_and_reports(self, on: None, tmp_path: Path, capsys: Any) -> None:
        (tmp_path / "p.png").write_bytes(PNG)
        call_command("ocrmd_scan", str(tmp_path), "--doc", "up")
        out = capsys.readouterr().out
        assert "p.png: 1 page(s) read into 'up'" in out and "OCR only" in out

    def test_a_matter_target_needs_a_user(self, on: None, tmp_path: Path) -> None:
        (tmp_path / "p.png").write_bytes(PNG)
        with pytest.raises(CommandError, match="--user"):
            call_command("ocrmd_scan", str(tmp_path), "--target", "matter:x")
