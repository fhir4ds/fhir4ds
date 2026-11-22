"""D8 HISTORIAN v0.0.26 — terminology error-contract regressions (QA-D8H-001/002).

Section-walk findings from the Domain 8 HISTORIAN launch:
  QA-D8H-001  HTTPTerminologyEndpoint(non-str) leaked a raw
              ``AttributeError`` from ``urlparse`` (INV-9 fail-fast gap).
  QA-D8H-002  TerminologyEndpoint protocol methods accepted wrong-type
              arguments silently: HTTP ``expand(None)`` attempted a live
              network call with ``url=None``, in-process ``expand``/
              ``search_text`` swallowed medterm4ds's own TypeError and
              returned ``[]`` (silent empty membership), and
              ``search_batch(123)`` leaked raw TypeError downstream.
"""

from __future__ import annotations

import pytest

duckdb = pytest.importorskip("duckdb")


# ---------------------------------------------------------------- QA-D8H-001
class TestHttpEndpointConstructorTypeError:
    def test_non_str_base_url_raises_type_error(self):
        from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint

        with pytest.raises(TypeError, match="base_url must be a str"):
            HTTPTerminologyEndpoint(123)

    def test_bad_scheme_still_value_error(self):
        from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint

        with pytest.raises(ValueError, match="http"):
            HTTPTerminologyEndpoint("ftp://x/fhir")


# ---------------------------------------------------------------- QA-D8H-002
class _ProtocolTypeGuardCases:
    """Shared wrong-type-argument contract for both adapters.

    HTTP adapter is pointed at an unroutable host with a tiny timeout so a
    missing guard would surface as a network attempt (ConnectError) rather
    than a TypeError. In-process adapter is constructed live (medterm4ds
    is a test dependency here); a missing guard returned ``[]``.
    """


class TestHttpAdapterProtocolTypeGuards:
    @pytest.fixture()
    def ep(self):
        from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint

        return HTTPTerminologyEndpoint("http://127.0.0.1:1/fhir", timeout_seconds=0.2)

    @pytest.mark.parametrize("bad", [None, 123, {"url": "x"}])
    def test_expand_wrong_type(self, ep, bad):
        with pytest.raises(TypeError, match="valueset_url"):
            ep.expand(bad)

    @pytest.mark.parametrize("bad", [None, 123])
    def test_search_text_wrong_query_type(self, ep, bad):
        with pytest.raises(TypeError, match="query"):
            ep.search_text(bad, "condition")

    def test_search_text_wrong_category_type(self, ep):
        with pytest.raises(TypeError, match="category"):
            ep.search_text("flu", 123)

    @pytest.mark.parametrize("bad", [None, 123, [("a",)], "not-a-list"])
    def test_search_batch_wrong_queries_type(self, ep, bad):
        with pytest.raises(TypeError, match="queries"):
            ep.search_batch(bad)


class TestInProcessAdapterProtocolTypeGuards:
    @pytest.fixture()
    def ep(self):
        from fhir4ds.cql.terminology.in_process_adapter import (
            InProcessTerminologyEndpoint,
        )

        return InProcessTerminologyEndpoint()

    @pytest.mark.parametrize("bad", [None, 123, {"url": "x"}])
    def test_expand_wrong_type(self, ep, bad):
        with pytest.raises(TypeError, match="valueset_url"):
            ep.expand(bad)

    @pytest.mark.parametrize("bad", [None, 123])
    def test_search_text_wrong_query_type(self, ep, bad):
        with pytest.raises(TypeError, match="query"):
            ep.search_text(bad, "condition")

    def test_search_text_wrong_category_type(self, ep):
        with pytest.raises(TypeError, match="category"):
            ep.search_text("flu", 123)

    @pytest.mark.parametrize("bad", [None, 123, [("a",)], "not-a-list"])
    def test_search_batch_wrong_queries_type(self, ep, bad):
        with pytest.raises(TypeError, match="queries"):
            ep.search_batch(bad)


