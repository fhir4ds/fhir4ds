"""Unit tests for the VSAC terminology adapter (mocked HTTP — no network).

Live-integration smoke tests live at the bottom of this file, gated
behind ``FHIR4DS_VSAC_LIVE=1`` AND a resolvable API key; CI runs only
the mocked units by default.
"""

from __future__ import annotations

import io
import json
import os
import time
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

from fhir4ds.cql.terminology.vsac_adapter import (
    DEFAULT_VSAC_BASE_URL,
    MAX_PAGES,
    VCACTerminologyEndpoint,
    clear_vsac_cache,
)
from fhir4ds.cql.terminology.types import CodeRef

OFFICE_VISIT_CANONICAL = (
    "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1001"
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _Response:
    def __init__(self, payload: object, status: int = 200):
        self._data = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _bundle(entries: list[dict]) -> dict:
    return {"resourceType": "Bundle", "type": "searchset", "entry": [{"resource": e} for e in entries]}


def _vs(version: str, vs_id: str | None = None) -> dict:
    return {
        "resourceType": "ValueSet",
        "id": vs_id or f"2.16.840.1.113883.3.464.1003.101.12.1001-{version}",
        "url": OFFICE_VISIT_CANONICAL,
        "version": version,
    }


def _expansion(codes: list[tuple[str, str]], total: int | None = None) -> dict:
    return {
        "resourceType": "ValueSet",
        "expansion": {
            "total": total if total is not None else len(codes),
            "contains": [
                {"system": system, "code": code, "display": f"d-{code}"} for system, code in codes
            ],
        },
    }


def _urlopen_side_effect(routes: list[tuple[int, object]]):
    """Return a urlopen double serving routes[i] for the i-th request."""
    calls = iter(routes)

    def _fake(request, timeout=None):  # noqa: ANN001
        assert request.get_header("Accept") == "application/fhir+json"
        auth = request.get_header("Authorization") or ""
        assert auth.startswith("Basic "), "Basic auth header missing"
        which = next(calls)
        status, payload = which
        if status >= 400:
            body = json.dumps(payload).encode("utf-8")
            raise urllib.error.HTTPError(
                request.full_url, status, "err", {}, io.BytesIO(body)
            )
        return _Response(payload, status)

    return _fake


@pytest.fixture()
def cache_tmp(tmp_path: Path) -> Path:
    return tmp_path / "vsac-cache"


@pytest.fixture()
def endpoint(cache_tmp: Path) -> VCACTerminologyEndpoint:
    return VCACTerminologyEndpoint(
        api_key="test-key",
        cache_dir=cache_tmp,
        cache_ttl_seconds=3600,
    )


# ---------------------------------------------------------------------------
# expand(): version resolution + paging
# ---------------------------------------------------------------------------


def test_expand_unversioned_url_picks_newest_and_pages(endpoint: VCACTerminologyEndpoint):
    page1_codes = [("http://snomed.info/sct", f"s{i}") for i in range(1000)]
    page2_codes = [("urn:oid:2.16.840.1.113883.6.12", f"c{i}") for i in range(16)]
    routes = [
        (200, _bundle([_vs("20180310"), _vs("20170101")])),  # newest first
        (200, _expansion(page1_codes, total=1016)),
        (200, _expansion(page2_codes, total=1016)),
    ]
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect(routes)):
        codes = endpoint.expand(OFFICE_VISIT_CANONICAL)

    assert len(codes) == 1016
    # SNOMED module normalization: expansion systems already base form.
    assert codes[0] == CodeRef("http://snomed.info/sct", "s0", "d-s0")
    # CPT OID resolves to its canonical URL via SystemResolver.
    assert codes[1000].system == "http://www.ama-assn.org/go/cpt"


def test_expand_versioned_canonical_matches_exact_version(endpoint: VCACTerminologyEndpoint):
    routes = [
        (200, _bundle([_vs("20180310"), _vs("20170101")])),
        (200, _expansion([("http://loinc.org", "1")])),
    ]
    url = f"{OFFICE_VISIT_CANONICAL}|20170101"
    seen_urls: list[str] = []
    handler = _urlopen_side_effect(routes)  # ONE iterator for all calls

    def recording(request, timeout=None):  # noqa: ANN001
        seen_urls.append(request.full_url)
        return handler(request, timeout)

    with mock.patch("urllib.request.urlopen", side_effect=recording):
        codes = endpoint.expand(url)
    assert codes == [CodeRef("http://loinc.org", "1", "d-1")]
    # VSAC url= search ignores the pipe suffix — query uses the BASE url.
    assert "%7C" not in seen_urls[0] and "20170101" not in seen_urls[0]


def test_expand_versioned_canonical_missing_version_raises(endpoint: VCACTerminologyEndpoint):
    routes = [(200, _bundle([_vs("20180310")]))]
    url = f"{OFFICE_VISIT_CANONICAL}|19990101"
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect(routes)):
        with pytest.raises(Exception, match="value set not found"):
            endpoint.expand(url)


def test_expand_dedupes_normalized_system_code_pairs(endpoint: VCACTerminologyEndpoint):
    routes = [
        (200, _bundle([_vs("20180310")])),
        (
            200,
            _expansion(
                [
                    ("http://snomed.info/sct/731000124108", "A"),
                    ("http://snomed.info/sct", "A"),  # same code after normalization
                    ("http://snomed.info/sct", "B"),
                ]
            ),
        ),
    ]
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect(routes)):
        codes = endpoint.expand(OFFICE_VISIT_CANONICAL)
    assert [(c.system, c.code) for c in codes] == [
        ("http://snomed.info/sct", "A"),
        ("http://snomed.info/sct", "B"),
    ]


def test_expand_large_set_pages_until_total(endpoint: VCACTerminologyEndpoint):
    def page_codes(page: int) -> list[tuple[str, str]]:
        return [("s", f"{page}-{i}") for i in range(1000)]  # unique per page

    routes = [(200, _bundle([_vs("20180310")]))]
    routes += [(200, _expansion(page_codes(p), total=2500)) for p in range(2)]
    routes.append((200, _expansion(page_codes(2)[:500], total=2500)))
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect(routes)):
        codes = endpoint.expand(OFFICE_VISIT_CANONICAL)
    assert len(codes) == 2500


def test_expand_runaway_cap(endpoint: VCACTerminologyEndpoint):
    routes = [(200, _bundle([_vs("20180310")]))]
    # total never satisfied (claims 1_000_000) -> cap at MAX_PAGES; codes
    # are UNIQUE PER PAGE so the (system, code) dedupe cannot collapse them.
    routes += [
        (200, _expansion([(f"s{p}", str(i)) for i in range(1000)], total=1_000_000))
        for p in range(MAX_PAGES)
    ]
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect(routes)):
        codes = endpoint.expand(OFFICE_VISIT_CANONICAL)
    assert len(codes) == MAX_PAGES * 1000


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_expand_auth_failure_message_has_no_key(endpoint: VCACTerminologyEndpoint):
    routes = [
        (
            401,
            {"resourceType": "OperationOutcome", "issue": [{"diagnostics": "bad key"}]},
        )
    ]
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect(routes)):
        with pytest.raises(Exception, match="authentication failed") as exc_info:
            endpoint.expand(OFFICE_VISIT_CANONICAL)
    assert "test-key" not in str(exc_info.value)


def test_expand_not_found(endpoint: VCACTerminologyEndpoint):
    routes = [(200, _bundle([]))]
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect(routes)):
        with pytest.raises(Exception, match="value set not found"):
            endpoint.expand(OFFICE_VISIT_CANONICAL)


def test_expand_server_error_includes_status_and_diagnostics_head(endpoint: VCACTerminologyEndpoint):
    routes = [(500, {"resourceType": "OperationOutcome", "issue": [{"diagnostics": "boom" * 100}]})]
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect(routes)):
        with pytest.raises(Exception, match="HTTP 500") as exc_info:
            endpoint.expand(OFFICE_VISIT_CANONICAL)
    assert "boom" in str(exc_info.value)
    assert len(str(exc_info.value)) < 400  # diagnostics head only


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def test_cache_roundtrip_skips_second_fetch(endpoint: VCACTerminologyEndpoint, cache_tmp: Path):
    routes = [
        (200, _bundle([_vs("20180310")])),
        (200, _expansion([("http://loinc.org", "1")])),
    ]
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect(routes)):
        first = endpoint.expand(OFFICE_VISIT_CANONICAL)
    # Second call: NO routes left -> any HTTP attempt raises StopIteration.
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect([])):
        second = endpoint.expand(OFFICE_VISIT_CANONICAL)
    assert first == second
    assert list(cache_tmp.glob("*.json")), "cache file written"


def test_cache_expiry_refetches(tmp_path: Path):
    ep = VCACTerminologyEndpoint(
        api_key="k",
        cache_dir=tmp_path / "c",
        cache_ttl_seconds=0.0,  # always revalidate
    )
    routes = [
        (200, _bundle([_vs("20180310")])),
        (200, _expansion([("http://loinc.org", "1")])),
        (200, _bundle([_vs("20180310")])),
        (200, _expansion([("http://loinc.org", "1")])),
    ]
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect(routes)):
        ep.expand(OFFICE_VISIT_CANONICAL)
        ep.expand(OFFICE_VISIT_CANONICAL)  # must refetch (TTL 0)


def test_cache_corrupt_entry_deleted_and_refetched(endpoint: VCACTerminologyEndpoint, cache_tmp: Path):
    # Seed a corrupt cache file at the exact key.
    import hashlib

    key = hashlib.sha256(OFFICE_VISIT_CANONICAL.encode()).hexdigest()
    (cache_tmp).mkdir(parents=True, exist_ok=True)
    (cache_tmp / f"{key}.json").write_text("{not-json", encoding="utf-8")

    routes = [
        (200, _bundle([_vs("20180310")])),
        (200, _expansion([("http://loinc.org", "1")])),
    ]
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect(routes)):
        codes = endpoint.expand(OFFICE_VISIT_CANONICAL)
    assert codes == [CodeRef("http://loinc.org", "1", "d-1")]
    # The file got replaced with valid JSON.
    payload = json.loads((cache_tmp / f"{key}.json").read_text())
    assert payload["codes"] == [["http://loinc.org", "1", "d-1"]]


def test_negative_results_not_cached(endpoint: VCACTerminologyEndpoint, cache_tmp: Path):
    routes = [(200, _bundle([]))]
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect(routes)):
        with pytest.raises(Exception):
            endpoint.expand(OFFICE_VISIT_CANONICAL)
    assert not list(cache_tmp.glob("*.json"))


def test_clear_cache(endpoint: VCACTerminologyEndpoint, cache_tmp: Path):
    routes = [
        (200, _bundle([_vs("20180310")])),
        (200, _expansion([("http://loinc.org", "1")])),
    ]
    with mock.patch("urllib.request.urlopen", side_effect=_urlopen_side_effect(routes)):
        endpoint.expand(OFFICE_VISIT_CANONICAL)
    assert endpoint.clear_cache() == 1
    assert not list(cache_tmp.glob("*.json"))


# ---------------------------------------------------------------------------
# search no-ops + intensional
# ---------------------------------------------------------------------------


def test_search_noops(endpoint: VCACTerminologyEndpoint):
    assert endpoint.search_text("asthma") == []
    assert endpoint.search_batch(["a", "b"]) == [[], []]


def test_expand_intensional_enumerated_only(endpoint: VCACTerminologyEndpoint):
    vs = {
        "compose": {
            "include": [
                {
                    "system": "http://snomed.info/sct/731000124108",
                    "concept": [{"code": "195967001", "display": "Asthma"}],
                }
            ]
        }
    }
    codes = endpoint.expand_intensional(vs)
    assert codes == [CodeRef("http://snomed.info/sct", "195967001", "Asthma")]


@pytest.mark.parametrize(
    "include",
    [
        {"system": "s", "filter": [{"property": "concept", "op": "is-a", "value": "x"}]},
        {"system": "s", "valueSet": ["http://example.com/other"]},
    ],
)
def test_expand_intensional_rejects_server_side_shapes(
    endpoint: VCACTerminologyEndpoint, include: dict
):
    with pytest.raises(Exception, match="intensional"):
        endpoint.expand_intensional({"compose": {"include": [include]}})


def test_expand_intensional_non_dict_rejected(endpoint: VCACTerminologyEndpoint):
    with pytest.raises(ValueError, match="dict"):
        endpoint.expand_intensional(["not", "a", "dict"])


# ---------------------------------------------------------------------------
# Config / key handling
# ---------------------------------------------------------------------------


def test_api_key_resolution_priority(monkeypatch):
    monkeypatch.setenv("FHIR4DS_VSAC_API_KEY", "env-key")
    monkeypatch.setenv("UMLS_API_KEY", "uml-key")
    assert VCACTerminologyEndpoint()._api_key() == "env-key"
    assert VCACTerminologyEndpoint(api_key="explicit")._api_key() == "explicit"
    monkeypatch.delenv("FHIR4DS_VSAC_API_KEY")
    assert VCACTerminologyEndpoint()._api_key() == "uml-key"


def test_missing_api_key_error_names_no_secret(monkeypatch):
    monkeypatch.delenv("FHIR4DS_VSAC_API_KEY", raising=False)
    monkeypatch.delenv("UMLS_API_KEY", raising=False)
    with pytest.raises(Exception, match="API key not found"):
        VCACTerminologyEndpoint()._api_key()


def test_default_base_url(endpoint: VCACTerminologyEndpoint):
    assert endpoint._base_url == DEFAULT_VSAC_BASE_URL


# ---------------------------------------------------------------------------
# Live smoke (opt-in; skipped without env flag + key)
# ---------------------------------------------------------------------------


def _live_enabled() -> bool:
    if os.getenv("FHIR4DS_VSAC_LIVE") != "1":
        return False
    return bool(os.getenv("FHIR4DS_VSAC_API_KEY") or os.getenv("UMLS_API_KEY"))


@pytest.mark.skipif(not _live_enabled(), reason="live VSAC smoke requires FHIR4DS_VSAC_LIVE=1 + key")
def test_live_office_visit_expansion(tmp_path: Path):
    ep = VCACTerminologyEndpoint(cache_dir=tmp_path / "live-cache")
    codes = ep.expand(OFFICE_VISIT_CANONICAL + "|20180310")
    assert len(codes) == 22
    systems = {c.system for c in codes}
    assert len(systems) == 2  # SNOMED + CPT (OID-form)


@pytest.mark.skipif(not _live_enabled(), reason="live VSAC smoke requires FHIR4DS_VSAC_LIVE=1 + key")
def test_live_unknown_canonical_raises(tmp_path: Path):
    ep = VCACTerminologyEndpoint(cache_dir=tmp_path / "live-cache")
    with pytest.raises(Exception, match="value set not found"):
        ep.expand("http://example.com/no-such-valueset")
