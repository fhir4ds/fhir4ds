"""Tests for DQM artifact resolvers."""

from __future__ import annotations

import base64
import json
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

from fhir4ds.dqm.artifacts import FileArtifactResolver, HapiArtifactResolver
from fhir4ds.dqm.config import DQMConfigError


def test_file_artifact_resolver_loads_measure_and_cql(tmp_path: Path):
    measure_path = tmp_path / "Measure-TestMeasure.json"
    cql_path = tmp_path / "TestMeasure.cql"
    measure_path.write_text(json.dumps({"resourceType": "Measure", "id": "TestMeasure"}))
    cql_path.write_text("library TestMeasure\n")

    resolver = FileArtifactResolver()

    measure = resolver.resolve_measure(measure_path)
    library = resolver.resolve_library(cql_path)

    assert measure.resource["id"] == "TestMeasure"
    assert measure.source_id.startswith("file:")
    assert library.text == "library TestMeasure\n"
    assert library.name == "TestMeasure"


def test_file_artifact_resolver_loads_library_resource_dict():
    cql = "library Inline\n"
    library_resource = {
        "resourceType": "Library",
        "id": "Inline",
        "name": "Inline",
        "content": [
            {
                "contentType": "text/cql",
                "data": base64.b64encode(cql.encode()).decode(),
            }
        ],
    }

    library = FileArtifactResolver().resolve_library(library_resource)

    assert library.text == cql
    assert library.name == "Inline"


def test_file_artifact_resolver_resolves_transitive_valuesets(tmp_path: Path):
    primary_cql = """library Primary
include HelperLibrary version '1.0.0' called Helper
valueset "Primary": 'http://example.com/ValueSet/primary' version '2025'
"""
    helper_cql = """library HelperLibrary version '1.0.0'
valueset "Helper": 'http://example.com/ValueSet/helper' version '2024'
"""
    (tmp_path / "HelperLibrary-1.0.0.cql").write_text(helper_cql)
    valueset_dir = tmp_path / "valuesets"
    valueset_dir.mkdir()
    (valueset_dir / "valuesets.json").write_text(
        json.dumps(
            {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "ValueSet",
                            "id": "primary",
                            "url": "http://example.com/ValueSet/primary",
                            "version": "2025",
                            "expansion": {
                                "contains": [{"system": "x", "code": "primary"}]
                            },
                        }
                    },
                    {
                        "resource": {
                            "resourceType": "ValueSet",
                            "id": "helper",
                            "url": "http://example.com/ValueSet/helper",
                            "version": "2024",
                            "compose": {
                                "include": [
                                    {
                                        "system": "x",
                                        "concept": [{"code": "helper"}],
                                    }
                                ]
                            },
                        }
                    },
                ],
            }
        )
    )

    resolver = FileArtifactResolver(
        include_paths=[tmp_path],
        valueset_paths=[valueset_dir],
    )

    valuesets = resolver.resolve_valuesets_for_cql(primary_cql)

    assert [(valueset["url"], valueset["version"]) for valueset in valuesets] == [
        ("http://example.com/ValueSet/helper", "2024"),
        ("http://example.com/ValueSet/primary", "2025"),
    ]


def test_file_artifact_resolver_rejects_missing_valueset(tmp_path: Path):
    cql = "valueset \"Missing\": 'http://example.com/ValueSet/missing'"
    valueset_dir = tmp_path / "valuesets"
    valueset_dir.mkdir()

    resolver = FileArtifactResolver(valueset_paths=[valueset_dir])

    with pytest.raises(DQMConfigError, match="ValueSet not found in files"):
        resolver.resolve_valuesets_for_cql(cql)


def test_file_artifact_resolver_rejects_ambiguous_unversioned_valueset(tmp_path: Path):
    valueset_url = "http://example.com/ValueSet/shared"
    for version in ("2024", "2025"):
        (tmp_path / f"vs-{version}.json").write_text(
            json.dumps(
                {
                    "resourceType": "ValueSet",
                    "id": f"shared-{version}",
                    "url": valueset_url,
                    "version": version,
                    "expansion": {"contains": [{"system": "x", "code": version}]},
                }
            )
        )
    resolver = FileArtifactResolver(valueset_paths=[tmp_path])

    with pytest.raises(DQMConfigError, match="ambiguous"):
        resolver.resolve_valuesets_for_cql(
            "valueset \"Shared\": 'http://example.com/ValueSet/shared'"
        )


def test_hapi_artifact_resolver_extracts_library_cql(monkeypatch):
    cql = "library TestMeasure\n"
    library_resource = {
        "resourceType": "Library",
        "id": "TestMeasure",
        "name": "TestMeasure",
        "url": "http://example.com/Library/TestMeasure",
        "content": [
            {
                "contentType": "text/cql",
                "data": base64.b64encode(cql.encode()).decode(),
            }
        ],
    }
    measure_resource = {
        "resourceType": "Measure",
        "id": "TestMeasure",
        "library": ["http://example.com/Library/TestMeasure"],
    }

    resolver = HapiArtifactResolver("http://hapi.test/fhir")

    def fake_read_json(url: str) -> dict[str, Any]:
        if url.endswith("/Measure/TestMeasure"):
            return measure_resource
        if "Library?url=http%3A%2F%2Fexample.com%2FLibrary%2FTestMeasure" in url:
            return {"resourceType": "Bundle", "entry": [{"resource": library_resource}]}
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(resolver, "_read_json", fake_read_json)

    measure = resolver.resolve_measure("TestMeasure")
    library = resolver.resolve_library(measure=measure.resource)

    assert measure.resource is measure_resource
    assert library.text == cql
    assert library.url == "http://example.com/Library/TestMeasure"


def test_hapi_artifact_resolver_resolves_canonical_measure_and_related_library(
    monkeypatch,
):
    cql = "library Related version '2025'\n"
    measure_resource = {
        "resourceType": "Measure",
        "id": "MeasureByCanonical",
        "url": "http://example.com/Measure/MeasureByCanonical",
        "version": "2025",
        "relatedArtifact": [
            {
                "type": "depends-on",
                "resource": "http://example.com/Library/Related|2025",
            }
        ],
    }
    library_resource = {
        "resourceType": "Library",
        "id": "Related",
        "name": "Related",
        "url": "http://example.com/Library/Related",
        "version": "2025",
        "content": [
            {
                "contentType": "text/cql",
                "data": base64.b64encode(cql.encode()).decode(),
            }
        ],
    }
    resolver = HapiArtifactResolver("http://hapi.test/fhir")
    requested: list[str] = []

    def fake_read_json(url: str) -> dict[str, Any]:
        requested.append(url)
        if "/Measure?" in url:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            assert query["url"] == ["http://example.com/Measure/MeasureByCanonical"]
            assert query["version"] == ["2025"]
            return {"resourceType": "Bundle", "entry": [{"resource": measure_resource}]}
        if "/Library?" in url:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            assert query["url"] == ["http://example.com/Library/Related"]
            assert query["version"] == ["2025"]
            return {"resourceType": "Bundle", "entry": [{"resource": library_resource}]}
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(resolver, "_read_json", fake_read_json)

    measure = resolver.resolve_measure(
        "http://example.com/Measure/MeasureByCanonical|2025"
    )
    library = resolver.resolve_library(measure=measure.resource)

    assert measure.resource["id"] == "MeasureByCanonical"
    assert library.text == cql
    assert any("/Measure?" in url for url in requested)
    assert any("/Library?" in url for url in requested)


def test_hapi_artifact_resolver_expands_unexpanded_valueset(monkeypatch):
    cql = "valueset \"Diabetes\": 'http://example.com/ValueSet/diabetes'"
    resolver = HapiArtifactResolver("http://hapi.test/fhir")
    requested: list[str] = []

    def fake_read_json(url: str) -> dict[str, Any]:
        requested.append(url)
        if "/ValueSet?" in url:
            return {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "ValueSet",
                            "id": "diabetes",
                            "url": "http://example.com/ValueSet/diabetes",
                        }
                    }
                ],
            }
        if "/ValueSet/$expand?" in url:
            return {
                "resourceType": "ValueSet",
                "id": "diabetes",
                "url": "http://example.com/ValueSet/diabetes",
                "expansion": {"contains": [{"system": "x", "code": "y"}]},
            }
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(resolver, "_read_json", fake_read_json)

    valuesets = resolver.resolve_valuesets_for_cql(cql)

    assert valuesets[0]["expansion"]["contains"][0]["code"] == "y"
    assert any("/ValueSet/$expand?" in url for url in requested)


def test_hapi_artifact_resolver_loads_included_library_valuesets(monkeypatch):
    cql = """library Primary
include HelperLibrary called Helper
valueset "Primary": 'http://example.com/ValueSet/primary'
"""
    helper_cql = """library HelperLibrary
valueset "Helper": 'http://example.com/ValueSet/helper'
"""
    helper_resource = {
        "resourceType": "Library",
        "id": "HelperLibrary",
        "name": "HelperLibrary",
        "content": [
            {
                "contentType": "text/cql",
                "data": base64.b64encode(helper_cql.encode()).decode(),
            }
        ],
    }
    resolver = HapiArtifactResolver("http://hapi.test/fhir")

    def fake_read_json(url: str) -> dict[str, Any]:
        if url.endswith("/Library/HelperLibrary"):
            return helper_resource
        if "/ValueSet?" in url:
            valueset_url = url.split("url=", 1)[1]
            decoded = urllib.parse.unquote(valueset_url)
            return {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "ValueSet",
                            "id": decoded.rsplit("/", 1)[-1],
                            "url": decoded,
                            "expansion": {"contains": [{"system": "x", "code": "y"}]},
                        }
                    }
                ],
            }
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(resolver, "_read_json", fake_read_json)

    valuesets = resolver.resolve_valuesets_for_cql(cql)

    assert [valueset["url"] for valueset in valuesets] == [
        "http://example.com/ValueSet/helper",
        "http://example.com/ValueSet/primary",
    ]


def test_hapi_artifact_resolver_respects_include_and_valueset_versions(monkeypatch):
    cql = """library Primary
include HelperLibrary version '1.0.0' called Helper
valueset "Primary": 'http://example.com/ValueSet/primary' version '2025'
"""
    helper_cql = """library HelperLibrary version '1.0.0'
valueset "Helper": 'http://example.com/ValueSet/helper' version '2024'
"""
    helper_resource = {
        "resourceType": "Library",
        "id": "HelperLibrary",
        "name": "HelperLibrary",
        "version": "1.0.0",
        "content": [
            {
                "contentType": "text/cql",
                "data": base64.b64encode(helper_cql.encode()).decode(),
            }
        ],
    }
    resolver = HapiArtifactResolver("http://hapi.test/fhir")
    requested: list[str] = []

    def fake_read_json(url: str) -> dict[str, Any]:
        requested.append(url)
        if "/Library?" in url:
            assert "name=HelperLibrary" in url
            assert "version=1.0.0" in url
            return {"resourceType": "Bundle", "entry": [{"resource": helper_resource}]}
        if "/ValueSet?" in url:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            valueset_url = query["url"][0]
            version = query["version"][0]
            return {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "ValueSet",
                            "id": valueset_url.rsplit("/", 1)[-1],
                            "url": valueset_url,
                            "version": version,
                            "expansion": {"contains": [{"system": "x", "code": version}]},
                        }
                    }
                ],
            }
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(resolver, "_read_json", fake_read_json)

    valuesets = resolver.resolve_valuesets_for_cql(cql)
    resolver.resolve_valuesets_for_cql(cql)

    assert [(valueset["url"], valueset["version"]) for valueset in valuesets] == [
        ("http://example.com/ValueSet/helper", "2024"),
        ("http://example.com/ValueSet/primary", "2025"),
    ]
    assert sum(1 for url in requested if "/ValueSet?" in url) == 2


def test_hapi_artifact_resolver_sends_headers_and_timeout(monkeypatch):
    import fhir4ds.dqm.artifacts as artifacts

    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return b'{"resourceType":"Bundle","entry":[]}'

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(artifacts.urllib.request, "urlopen", fake_urlopen)

    resolver = HapiArtifactResolver(
        "http://hapi.test/fhir",
        headers={"Authorization": "Bearer token", "X-Test": "yes"},
        timeout_seconds=12.5,
    )
    with pytest.raises(FileNotFoundError):
        resolver._search_one("ValueSet", {"url": "http://example.com/vs"})

    request, timeout = requests[0]
    assert timeout == 12.5
    assert request.headers["Authorization"] == "Bearer token"
    assert request.headers["X-test"] == "yes"
    assert request.headers["Accept"] == "application/fhir+json"


def test_hapi_artifact_resolver_requires_expanded_valueset(monkeypatch):
    cql = "valueset \"Diabetes\": 'http://example.com/ValueSet/diabetes'"
    resolver = HapiArtifactResolver("http://hapi.test/fhir")

    def fake_read_json(url: str) -> dict[str, Any]:
        if "/ValueSet?" in url:
            return {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "ValueSet",
                            "id": "diabetes",
                            "url": "http://example.com/ValueSet/diabetes",
                        }
                    }
                ],
            }
        if "/ValueSet/$expand?" in url:
            return {
                "resourceType": "ValueSet",
                "id": "diabetes",
                "url": "http://example.com/ValueSet/diabetes",
            }
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(resolver, "_read_json", fake_read_json)

    with pytest.raises(DQMConfigError, match="requires an expanded ValueSet"):
        resolver.resolve_valuesets_for_cql(cql)


def test_hapi_artifact_resolver_falls_back_to_instance_valueset_expand(monkeypatch):
    cql = "valueset \"Diabetes\": 'http://example.com/ValueSet/diabetes'"
    resolver = HapiArtifactResolver("http://hapi.test/fhir")
    requested: list[str] = []

    def fake_read_json(url: str) -> dict[str, Any]:
        requested.append(url)
        if "/ValueSet?" in url:
            return {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "ValueSet",
                            "id": "diabetes",
                            "url": "http://example.com/ValueSet/diabetes",
                        }
                    }
                ],
            }
        if "/ValueSet/$expand?" in url:
            raise FileNotFoundError(url)
        if url.endswith("/ValueSet/diabetes/$expand"):
            return {
                "resourceType": "ValueSet",
                "id": "diabetes",
                "url": "http://example.com/ValueSet/diabetes",
                "expansion": {"contains": [{"system": "x", "code": "fallback"}]},
            }
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(resolver, "_read_json", fake_read_json)

    valuesets = resolver.resolve_valuesets_for_cql(cql)

    assert valuesets[0]["expansion"]["contains"][0]["code"] == "fallback"
    assert requested[-1].endswith("/ValueSet/diabetes/$expand")
