"""Unit tests for the UMLS terminology adapter (mocked HTTP — no network).

Live-integration smoke tests live at the bottom of this file, gated
behind ``FHIR4DS_UMLS_LIVE=1`` AND a resolvable API key; CI runs only
the mocked units by default.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

from fhir4ds.cql.terminology.umls_adapter import (
    ROOT_SOURCE_TO_SYSTEM,
    UMLSTerminologyEndpoint,
    UMLSTerminologyEndpointError,
    clear_umls_cache,
)
from fhir4ds.cql.terminology.types import CodeRef


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _Response:
    def __init__(self, payload: object, status: int = 200):
        self._data = json.dumps(payload).encode("utf-8") if not isinstance(payload, bytes) else payload

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _search_payload(*entries: dict) -> dict:
    return {
        "pageSize": len(entries),
        "pageNumber": 1,
        "result": {"classType": "searchResults", "results": list(entries)},
    }


def _atoms_payload(*atoms: dict) -> dict:
    # UTS atoms use the same result wrapper; some versions return a bare list.
    return {"result": {"classType": "atoms", "results": list(atoms)}}


_MI_CUI = {"ui": "C0027051", "rootSource": "MTH", "uri": "x", "name": "Myocardial Infarction"}


def _mi_atoms() -> tuple[dict, ...]:
    return (
        {
            "classType": "Atom",
            "ui": "A1",
            "rootSource": "SNOMEDCT_US",
            "termType": "PT",
            "language": "ENG",
            "name": "Myocardial infarction (disorder)",
            "code": "https://uts-ws.nlm.nih.gov/rest/content/current/source/SNOMEDCT_US/22298006",
        },
        {
            "classType": "Atom",
            "ui": "A2",
            "rootSource": "MDRARA",
            "termType": "LLT",
            "language": "ARA",
            "name": "arabic label",
            "code": "https://uts-ws.nlm.nih.gov/rest/content/current/source/MDRARA/100",
        },
        {
            "classType": "Atom",
            "ui": "A3",
            "rootSource": "MTH",
            "termType": "PT",
            "language": "ENG",
            "name": "metathesaurus preferred",
            "code": "mth-code",
        },
        {
            "classType": "Atom",
            "ui": "A4",
            "rootSource": "ICD10CM",
            "termType": "PT",
            "language": "ENG",
            "name": "Acute myocardial infarction",
            "code": "I21",
        },
        # duplicate SNOMED code via a different term type — deduped
        {
            "classType": "Atom",
            "ui": "A5",
            "rootSource": "SNOMEDCT_US",
            "termType": "SY",
            "language": "ENG",
            "name": "MI",
            "code": "22298006",
        },
    )


def _make_endpoint(tmp_path: Path, **kwargs) -> UMLSTerminologyEndpoint:
    kwargs.setdefault("api_key", "test-key")
    kwargs.setdefault("cache_dir", tmp_path / "umls-cache")
    return UMLSTerminologyEndpoint(**kwargs)


# ---------------------------------------------------------------------------
# search_text
# ---------------------------------------------------------------------------


class TestSearchText:
    def test_search_extracts_codes_and_dedupes(self, tmp_path):
        ep = _make_endpoint(tmp_path)
        calls: list[str] = []

        def fake_urlopen(request, timeout=None):
            url = request.full_url
            calls.append(url)
            if "/search/" in url:
                return _Response(_search_payload(_MI_CUI))
            assert "/atoms" in url
            return _Response(_atoms_payload(*_mi_atoms()))

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            results = ep.search_text("myocardial infarction")

        assert len(calls) == 2  # search + one atoms fetch
        systems = {(r.system, r.code) for r in results}
        assert ("http://snomed.info/sct", "22298006") in systems
        assert ("http://hl7.org/fhir/sid/icd-10-cm", "I21") in systems
        # MTH excluded, only ONE snomed entry (dedup), no MDRARA (non-ENG
        # atoms filtered server-side by language=ENG but belt-and-braces:
        # mapped-source gate keeps it out regardless)
        snomed = [r for r in results if r.system == "http://snomed.info/sct"]
        assert len(snomed) == 1
        assert all(r.system != "" for r in results)

    def test_search_api_key_rides_as_query_param(self, tmp_path):
        ep = _make_endpoint(tmp_path)
        seen: dict[str, str] = {}

        def fake_urlopen(request, timeout=None):
            from urllib.parse import urlparse, parse_qs

            parsed = urlparse(request.full_url)
            seen.update({k: v[0] for k, v in parse_qs(parsed.query).items()})
            assert request.get_header("Authorization") is None  # no Basic auth
            return _Response(_search_payload())

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            ep.search_text("x")
        assert seen.get("apiKey") == "test-key"
        assert seen.get("string") == "x"
        assert seen.get("searchType") == "words"

    def test_search_exact_mode_maps_search_type(self, tmp_path):
        ep = _make_endpoint(tmp_path)

        def fake_urlopen(request, timeout=None):
            assert "searchType=exact" in request.full_url
            return _Response(_search_payload())

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            ep.search_text("x", mode="exact")

    def test_search_system_filter_uses_root_source(self, tmp_path):
        ep = _make_endpoint(tmp_path)

        def fake_urlopen(request, timeout=None):
            if "/search/" in request.full_url:
                return _Response(_search_payload(_MI_CUI))
            return _Response(_atoms_payload(*_mi_atoms()))

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            results = ep.search_text("mi", "http://snomed.info/sct")
        assert results
        assert {r.system for r in results} == {"http://snomed.info/sct"}

    def test_search_root_source_abbreviation_category(self, tmp_path):
        ep = _make_endpoint(tmp_path)

        def fake_urlopen(request, timeout=None):
            if "/search/" in request.full_url:
                return _Response(_search_payload(_MI_CUI))
            return _Response(_atoms_payload(*_mi_atoms()))

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            results = ep.search_text("mi", "LOINC")
        assert results == []

    def test_search_empty_or_blank_query_returns_empty(self, tmp_path):
        ep = _make_endpoint(tmp_path)
        with mock.patch("urllib.request.urlopen") as m:
            assert ep.search_text("") == []
            assert ep.search_text("   ") == []
            m.assert_not_called()

    def test_search_handles_bare_list_payload(self, tmp_path):
        ep = _make_endpoint(tmp_path)

        def fake_urlopen(request, timeout=None):
            if "/search/" in request.full_url:
                return _Response([_MI_CUI])  # bare-list shape
            return _Response(list(_mi_atoms()))  # bare-list atoms

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            results = ep.search_text("mi")
        assert ("http://snomed.info/sct", "22298006") in {(r.system, r.code) for r in results}

    def test_uri_code_field_parsed_to_plain_code(self, tmp_path):
        ep = _make_endpoint(tmp_path)

        def fake_urlopen(request, timeout=None):
            if "/search/" in request.full_url:
                return _Response(_search_payload(_MI_CUI))
            return _Response(
                _atoms_payload(
                    {
                        "rootSource": "LOINC",
                        "termType": "PT",
                        "language": "ENG",
                        "name": "Heart rate",
                        "code": "https://uts-ws.nlm.nih.gov/rest/content/current/source/LOINC/8867-4",
                    }
                )
            )

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            results = ep.search_text("heart rate")
        assert len(results) == 1
        assert results[0].code == "8867-4"

    def test_search_ranks_first_cui_codes_first(self, tmp_path):
        ep = _make_endpoint(tmp_path)
        cui1 = dict(_MI_CUI)
        cui2 = {"ui": "C0001", "rootSource": "MTH", "name": "Other"}

        def fake_urlopen(request, timeout=None):
            if "/search/" in request.full_url:
                return _Response(_search_payload(cui1, cui2))
            if "/C0027051/" in request.full_url:
                return _Response(
                    _atoms_payload(
                        {
                            "rootSource": "SNOMEDCT_US",
                            "termType": "PT",
                            "language": "ENG",
                            "name": "MI",
                            "code": "22298006",
                        }
                    )
                )
            return _Response(
                _atoms_payload(
                    {
                        "rootSource": "LOINC",
                        "termType": "PT",
                        "language": "ENG",
                        "name": "Later",
                        "code": "LP1",
                    }
                )
            )

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            results = ep.search_text("mi")
        assert results[0].code == "22298006"
        assert results[1].code == "LP1"


# ---------------------------------------------------------------------------
# Errors / key handling
# ---------------------------------------------------------------------------


class TestErrors:
    def test_missing_key_raises_typed_error(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FHIR4DS_UMLS_API_KEY", raising=False)
        monkeypatch.delenv("UMLS_API_KEY", raising=False)
        ep = UMLSTerminologyEndpoint(cache_dir=tmp_path / "c")
        with pytest.raises(UMLSTerminologyEndpointError, match="UMLS API key not found"):
            ep.search_text("x")

    def test_key_resolution_priority(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FHIR4DS_UMLS_API_KEY", "env-specific")
        monkeypatch.setenv("UMLS_API_KEY", "env-generic")
        # constructor arg wins
        ep = _make_endpoint(tmp_path)
        assert ep._api_key() == "test-key"
        # FHIR4DS_UMLS_API_KEY beats UMLS_API_KEY
        ep2 = UMLSTerminologyEndpoint(cache_dir=tmp_path / "c2")
        assert ep2._api_key() == "env-specific"
        monkeypatch.delenv("FHIR4DS_UMLS_API_KEY")
        ep3 = UMLSTerminologyEndpoint(cache_dir=tmp_path / "c3")
        assert ep3._api_key() == "env-generic"

    def test_http_401_raises_auth_error_without_key_leak(self, tmp_path):
        ep = _make_endpoint(tmp_path, api_key="SECRET-KEY-VALUE")

        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, 401, "Unauthorized", hdrs=None, fp=io_bytestring(b"nope")
            )

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(UMLSTerminologyEndpointError, match="authentication failed"):
                ep.search_text("x")

    def test_error_messages_never_contain_the_key(self, tmp_path):
        ep = _make_endpoint(tmp_path, api_key="SECRET-KEY-VALUE")

        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, 500, "Server Error", hdrs=None, fp=io_bytestring(b"boom")
            )

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(UMLSTerminologyEndpointError) as excinfo:
                ep.search_text("x")
        assert "SECRET-KEY-VALUE" not in str(excinfo.value)

    def test_network_error_raises_typed(self, tmp_path):
        ep = _make_endpoint(tmp_path)

        def fake_urlopen(request, timeout=None):
            raise urllib.error.URLError("connection refused")

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(UMLSTerminologyEndpointError, match="network error"):
                ep.search_text("x")

    def test_is_healthy_never_raises(self, tmp_path):
        ep = _make_endpoint(tmp_path)

        def fake_urlopen(request, timeout=None):
            raise urllib.error.URLError("down")

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            assert ep.is_healthy() is False

    def test_is_healthy_true_on_success(self, tmp_path):
        ep = _make_endpoint(tmp_path)
        with mock.patch("urllib.request.urlopen", return_value=_Response(_search_payload())):
            assert ep.is_healthy() is True


def io_bytestring(data: bytes):
    import io

    return io.BytesIO(data)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolSurface:
    def test_expand_is_documented_noop(self, tmp_path):
        ep = _make_endpoint(tmp_path)
        assert ep.expand("http://example.org/ValueSet/X") == []

    def test_expand_intensional_is_documented_noop(self, tmp_path):
        ep = _make_endpoint(tmp_path)
        assert ep.expand_intensional({"compose": {}}) == []

    def test_search_batch_maps_queries(self, tmp_path):
        ep = _make_endpoint(tmp_path)

        def fake_urlopen(request, timeout=None):
            if "/search/" in request.full_url:
                return _Response(_search_payload())
            return _Response(_atoms_payload())

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            out = ep.search_batch(["a", "b"])
        assert out == [[], []]

    def test_search_result_dataclass_fields(self, tmp_path):
        ep = _make_endpoint(tmp_path)

        def fake_urlopen(request, timeout=None):
            if "/search/" in request.full_url:
                return _Response(_search_payload(_MI_CUI))
            return _Response(
                _atoms_payload(
                    {
                        "rootSource": "SNOMEDCT_US",
                        "termType": "PT",
                        "language": "ENG",
                        "name": "Myocardial infarction (disorder)",
                        "code": "22298006",
                    }
                )
            )

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            results = ep.search_text("mi")
        r = results[0]
        assert r.system == "http://snomed.info/sct"
        assert r.code == "22298006"
        assert r.display == "Myocardial infarction (disorder)"
        assert r.score == 1.0  # first CUI
        assert isinstance(r, CodeRef.__class__) or hasattr(r, "system")


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------


class TestCache:
    def _fetching_endpoint(self, tmp_path):
        ep = _make_endpoint(tmp_path)
        counter = {"n": 0}

        def fake_urlopen(request, timeout=None):
            if "/search/" in request.full_url:
                return _Response(_search_payload(_MI_CUI))
            counter["n"] += 1
            return _Response(_atoms_payload(*_mi_atoms()))

        return ep, fake_urlopen, counter

    def test_atoms_cached_across_searches(self, tmp_path):
        ep, fake, counter = self._fetching_endpoint(tmp_path)
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            ep.search_text("mi")
            ep.search_text("mi again")
        assert counter["n"] == 1  # atoms fetched once; search always live

    def test_cache_expiry_refetches(self, tmp_path):
        ep, fake, counter = self._fetching_endpoint(tmp_path)
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            ep.search_text("mi")
        # expire every cache file by rewriting expires_at into the past
        for path in (tmp_path / "umls-cache").glob("*.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["expires_at"] = time.time() - 1
            path.write_text(json.dumps(doc), encoding="utf-8")
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            ep.search_text("mi")
        assert counter["n"] == 2

    def test_corrupt_cache_entry_refetches(self, tmp_path):
        ep, fake, counter = self._fetching_endpoint(tmp_path)
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            ep.search_text("mi")
        for path in (tmp_path / "umls-cache").glob("*.json"):
            path.write_text("{not json", encoding="utf-8")
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            results = ep.search_text("mi")
        assert counter["n"] == 2
        assert results  # refetch succeeded

    def test_ttl_zero_always_revalidates(self, tmp_path):
        ep = _make_endpoint(tmp_path, cache_ttl_seconds=0)
        counter = {"n": 0}

        def fake_urlopen(request, timeout=None):
            if "/search/" in request.full_url:
                return _Response(_search_payload(_MI_CUI))
            counter["n"] += 1
            return _Response(_atoms_payload(*_mi_atoms()))

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            ep.search_text("mi")
            ep.search_text("mi")
        assert counter["n"] == 2

    def test_clear_cache_removes_files(self, tmp_path):
        ep, fake, _ = self._fetching_endpoint(tmp_path)
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            ep.search_text("mi")
        assert any((tmp_path / "umls-cache").glob("*.json"))
        removed = ep.clear_cache()
        assert removed >= 1
        assert not any((tmp_path / "umls-cache").glob("*.json"))


# ---------------------------------------------------------------------------
# Root-source map
# ---------------------------------------------------------------------------


class TestSystemMap:
    def test_common_sources_mapped(self):
        assert ROOT_SOURCE_TO_SYSTEM["SNOMEDCT_US"] == "http://snomed.info/sct"
        assert ROOT_SOURCE_TO_SYSTEM["LOINC"] == "http://loinc.org"
        assert ROOT_SOURCE_TO_SYSTEM["ICD10CM"] == "http://hl7.org/fhir/sid/icd-10-cm"
        assert ROOT_SOURCE_TO_SYSTEM["RXNORM"] == "http://www.nlm.nih.gov/research/umls/rxnorm"
        assert ROOT_SOURCE_TO_SYSTEM["CPT"] == "http://www.ama-assn.org/go/cpt"

    def test_unmapped_sources_dropped(self, tmp_path):
        ep = _make_endpoint(tmp_path)

        def fake_urlopen(request, timeout=None):
            if "/search/" in request.full_url:
                return _Response(_search_payload(_MI_CUI))
            return _Response(
                _atoms_payload(
                    {
                        "rootSource": "MSH",
                        "termType": "PT",
                        "language": "ENG",
                        "name": "some mesh heading",
                        "code": "D009203",
                    }
                )
            )

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            assert ep.search_text("mi") == []


# ---------------------------------------------------------------------------
# LIVE smoke tests (opt-in only)
# ---------------------------------------------------------------------------


class TestLiveUmls:
    """Gated behind FHIR4DS_UMLS_LIVE=1 + a key; skipped in CI."""

    def _live_endpoint(self) -> UMLSTerminologyEndpoint | None:
        if os.environ.get("FHIR4DS_UMLS_LIVE") != "1":
            return None
        key = os.environ.get("FHIR4DS_UMLS_API_KEY") or os.environ.get("UMLS_API_KEY")
        if not key:
            return None
        return UMLSTerminologyEndpoint(api_key=key)

    def test_live_myocardial_infarction_snomed(self):
        ep = self._live_endpoint()
        if ep is None:
            pytest.skip("FHIR4DS_UMLS_LIVE=1 and UMLS_API_KEY required")
        results = ep.search_text("myocardial infarction", "http://snomed.info/sct")
        assert ("http://snomed.info/sct", "22298006") in {(r.system, r.code) for r in results}

    def test_live_myocardial_infarction_all_systems(self):
        ep = self._live_endpoint()
        if ep is None:
            pytest.skip("FHIR4DS_UMLS_LIVE=1 and UMLS_API_KEY required")
        results = ep.search_text("myocardial infarction")
        systems = {r.system for r in results}
        assert "http://snomed.info/sct" in systems
        assert "http://hl7.org/fhir/sid/icd-10-cm" in systems
