"""Live-network drift smoke test for the Colorado statutes adapter.

BL-20260511-07 (resolves the overlap with BL-20260509-04). Every other test of
this parser runs against a frozen fixture
(``tests/ingestion/fixtures/co/title_18_article_3.html``), which means a
Justia markup change goes unnoticed until an ingestion run silently returns
zero sections. This test fetches **one** real title and re-runs the parser, so
upstream HTML drift surfaces as a failing nightly job instead of an empty
corpus.

Two outcomes, deliberately kept apart — conflating them is what made the first
version of this test carry no information:

* **Blocked or unreachable** (Cloudflare interstitial, 403/429/5xx, DNS or TLS
  failure) — the run learns nothing about Justia's *markup*, so it **skips**.
  law.justia.com currently answers every plain HTTP client with a 403 bot
  challenge, so this is the expected nightly outcome today.
* **Fetched, but the parse looks wrong** (zero sections, a truncated or
  malformed citation, an empty body) — that is drift, and it **fails loudly**.
  Because a block can no longer redden the job, the nightly step does not need
  ``continue-on-error`` and does not carry it.

The classifier and the shape assertions below are themselves covered by
``TestDriftHarness``, which runs in the ordinary suite: without that, the only
code path this file exercises on a normal day would be ``skip``.

Guardrails:

* Live fetch skipped unless ``LIVE_NETWORK=1`` — never runs in
  ``make test-backend`` (also excluded by the ``integration`` marker) nor in
  per-PR CI.
* One request per run. Do not loop titles: Justia's crawl-delay is the reason
  ``ColoradoStatutesAdapter.rate_limit_rps`` is 0.5.

Run it with ``make test-live-network``.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx
import pytest
from tenacity import RetryError

from law_ai.ingestionapp.services.colorado_statutes import ColoradoStatutesError
from law_ai.ingestionapp.sources import SOURCE_REGISTRY
from law_ai.ingestionapp.sources.colorado_statutes import ColoradoStatutesAdapter

live_only = pytest.mark.skipif(
    os.getenv("LIVE_NETWORK") != "1",
    reason="live upstream fetch — set LIVE_NETWORK=1 (nightly only)",
)

#: A CRS citation the parser may legitimately emit. Colorado uses decimal
#: *articles* ("18-1.3-401"), so the article part carries an optional decimal
#: too — asserting otherwise reported drift that was not there.
CITATION_RE = re.compile(r"^C\.R\.S\. § \d+[A-Z]?-\d+(\.\d+)?-\d+(\.\d+)?$")

#: Statuses that mean "we never saw Justia's markup". 403 is the live one: the
#: site sits behind a Cloudflare JS challenge that no plain HTTP client passes.
BLOCKED_STATUSES = frozenset({401, 403, 407, 408, 409, 429, 451, 500, 502, 503, 504})

_STATUS_RE = re.compile(r"colorado_statutes (\d{3}) for ")

#: CRS Title 18 (Criminal Code) — the title spec 016 shipped against.
TITLE = "18"


def blocked_reason(exc: BaseException) -> str | None:
    """Why *exc* means "never reached the markup", or ``None`` if it does not.

    A transport error, a retry exhaustion, or an HTTP status in
    :data:`BLOCKED_STATUSES` says nothing about Justia's HTML. Anything else —
    including a parse failure — is a real signal and must reach the report.
    """
    if isinstance(exc, (httpx.HTTPError, RetryError)):
        return f"upstream unreachable: {type(exc).__name__}: {exc}"
    if isinstance(exc, ColoradoStatutesError):
        match = _STATUS_RE.search(str(exc))
        if match and int(match.group(1)) in BLOCKED_STATUSES:
            return f"upstream refused the fetch (HTTP {match.group(1)})"
    return None


def fetch_or_skip(adapter: Any, title: str, *, limit: int) -> list[Any]:
    """One real fetch. Skip when blocked; let anything else fail the test."""
    try:
        return list(adapter.fetch(title, limit=limit))
    except Exception as exc:
        reason = blocked_reason(exc)
        if reason is None:
            raise
        pytest.skip(f"no drift signal available — {reason}")


def assert_sections_look_right(docs: list[Any], *, title: str = TITLE) -> None:
    """The drift assertions. Every failure here means Justia's markup moved."""
    assert docs, (
        f"colorado_statutes fetched CRS Title {title} but parsed no sections — "
        "either Justia's markup changed (update the CSS hooks in "
        "services/colorado_statutes.py and the frozen fixture) or the title "
        "page now lists articles instead of section bodies"
    )
    for doc in docs:
        assert doc.source_name == "colorado_statutes"
        assert CITATION_RE.match(doc.title), f"unexpected citation: {doc.title!r}"
        assert doc.text.strip(), f"empty body for {doc.title}"
        assert doc.metadata["title_id"] == title
        assert doc.metadata["section_id"].startswith("us-co/crs/")


@pytest.mark.integration
@pytest.mark.network
@live_only
def test_live_justia_fetch_still_parses() -> None:
    """One real fetch; drift shows up as zero sections or a shape mismatch."""
    adapter = ColoradoStatutesAdapter()
    docs = fetch_or_skip(adapter, TITLE, limit=5)
    assert_sections_look_right(docs)


@pytest.mark.integration
@pytest.mark.network
@live_only
def test_live_adapter_respects_its_registry_metadata() -> None:
    """The live adapter is the same object the registry hands the autonomy loop."""
    registered = SOURCE_REGISTRY["colorado_statutes"]
    assert isinstance(registered, ColoradoStatutesAdapter)
    assert registered.rate_limit_rps <= 1.0, "do not hammer Justia"


# ---------------------------------------------------------------------------
# The harness itself, exercised offline. A nightly run that always skips would
# otherwise never execute a line of the drift logic.
# ---------------------------------------------------------------------------


class _Doc:
    def __init__(self, title: str, text: str = "Body.", section: str = "18-3-102"):
        self.source_name = "colorado_statutes"
        self.title = title
        self.text = text
        self.metadata = {"title_id": TITLE, "section_id": f"us-co/crs/{section}"}


class _Adapter:
    """Stands in for the real adapter: replays one canned fetch outcome."""

    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome

    def fetch(self, title: str, *, limit: int = 10) -> list[Any]:
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return list(self._outcome)


class TestDriftHarness:
    def test_cloudflare_403_is_a_skip_not_a_failure(self) -> None:
        """The live outcome today: a block carries no information about markup."""
        exc = ColoradoStatutesError(
            "colorado_statutes 403 for /title-18/: <title>Just a moment...</title>"
        )
        assert blocked_reason(exc) == "upstream refused the fetch (HTTP 403)"
        # ``Skipped`` derives from BaseException, so this must be caught by
        # its own type — a bare ``Exception`` would let it skip the test that
        # is asserting the skip.
        with pytest.raises(pytest.skip.Exception, match="no drift signal"):
            fetch_or_skip(_Adapter(exc), TITLE, limit=5)

    def test_transport_failure_is_a_skip(self) -> None:
        assert blocked_reason(httpx.ConnectError("dns")) is not None
        assert blocked_reason(RetryError(last_attempt=None)) is not None  # type: ignore[arg-type]

    def test_a_parse_failure_is_never_swallowed(self) -> None:
        """Only *fetch* problems skip; anything else must reach the report."""
        assert blocked_reason(ValueError("bad html")) is None
        assert (
            blocked_reason(ColoradoStatutesError("colorado_statutes 404 for /x/"))
            is None
        )
        with pytest.raises(ValueError):
            fetch_or_skip(_Adapter(ValueError("bad html")), TITLE, limit=5)

    def test_zero_sections_from_a_good_fetch_fails_loudly(self) -> None:
        """The drift signal: Justia answered, the parser found nothing."""
        with pytest.raises(AssertionError, match="parsed no sections"):
            assert_sections_look_right([])

    def test_a_truncated_citation_fails_loudly(self) -> None:
        """`C.R.S. § 18-1.3` is the shape a broken section-number regex emits."""
        with pytest.raises(AssertionError, match="unexpected citation"):
            assert_sections_look_right([_Doc("C.R.S. § 18-1.3")])

    def test_an_empty_body_fails_loudly(self) -> None:
        with pytest.raises(AssertionError, match="empty body"):
            assert_sections_look_right([_Doc("C.R.S. § 18-3-102", text="   ")])

    def test_decimal_article_sections_are_accepted(self) -> None:
        """A real Title 18 fetch reaches article 1.3 — that is not drift."""
        assert_sections_look_right(
            [
                _Doc("C.R.S. § 18-3-102"),
                _Doc("C.R.S. § 18-1.3-401", section="18-1.3-401"),
            ]
        )
