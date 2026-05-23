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
