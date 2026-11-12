"""Unit tests for DependencyResolver."""

import pytest
from pathlib import Path
import json

from ...dependency import DependencyResolver, ResolutionError, ResolutionContext


def test_resolve_cql_library(tmp_path):
    """Test resolving a CQL library from file."""
    # Create a test CQL file
    cql_file = tmp_path / "TestLibrary.cql"
    cql_file.write_text("""
library TestLibrary version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "TestDefine": true
""")

    resolver = DependencyResolver(paths=[tmp_path])
    lib = resolver.resolve_library("TestLibrary")

    assert lib is not None
    assert lib.name == "TestLibrary"
    assert lib.cql_text is not None


def test_resolve_library_by_url(tmp_path):
    """Test resolving a FHIR Library resource by URL."""
    # Create a FHIR Library resource
    lib_file = tmp_path / "TestLib.json"
    lib_file.write_text(json.dumps({
        "resourceType": "Library",
        "url": "http://example.org/Library/TestLib",
        "name": "TestLib",
        "version": "1.0.0",
        "status": "active",
        "type": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/library-type", "code": "logic-library"}]
        },
        "content": []
    }))

    resolver = DependencyResolver(paths=[tmp_path])

    # Resolve by URL
    lib = resolver.resolve_library("http://example.org/Library/TestLib")
    assert lib is not None
    assert lib.name == "TestLib"

    # Resolve by name
    lib_by_name = resolver.resolve_library("TestLib")
    assert lib_by_name is not None
    assert lib_by_name.name == "TestLib"


def test_resolve_valueset(tmp_path):
    """Test resolving a ValueSet from JSON file."""
    vs_file = tmp_path / "TestValueSet.json"
    vs_file.write_text(json.dumps({
        "resourceType": "ValueSet",
        "url": "http://example.org/ValueSet/Test",
        "version": "1.0.0",
        "name": "TestValueSet",
        "status": "active",
        "expansion": {
            "contains": [
                {"system": "http://loinc.org", "code": "12345", "display": "Test Code"}
            ]
        }
    }))

    resolver = DependencyResolver(paths=[tmp_path])
    vs = resolver.resolve_valueset("http://example.org/ValueSet/Test")

    assert vs is not None
    assert vs.url == "http://example.org/ValueSet/Test"
    assert len(vs.codes) == 1
    assert vs.codes[0]["code"] == "12345"
    assert vs.codes[0]["system"] == "http://loinc.org"


def test_resolve_valueset_from_compose(tmp_path):
    """Test resolving a ValueSet from compose.include instead of expansion."""
    vs_file = tmp_path / "ComposeValueSet.json"
    vs_file.write_text(json.dumps({
        "resourceType": "ValueSet",
        "url": "http://example.org/ValueSet/Compose",
        "status": "active",
        "compose": {
            "include": [
                {
                    "system": "http://snomed.info/sct",
                    "concept": [
                        {"code": "123456", "display": "First Code"},
                        {"code": "789012", "display": "Second Code"}
                    ]
                }
            ]
        }
    }))

    resolver = DependencyResolver(paths=[tmp_path])
    vs = resolver.resolve_valueset("http://example.org/ValueSet/Compose")

    assert vs is not None
    assert len(vs.codes) == 2
    assert vs.codes[0]["system"] == "http://snomed.info/sct"
    assert vs.codes[1]["code"] == "789012"


def test_build_context_recursive(tmp_path):
    """Test building context with recursive dependency resolution."""
    # Create main library
    main_lib = tmp_path / "Main.cql"
    main_lib.write_text("""
library Main version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1'
context Patient
define "Test": true
""")

    # Create dependency library
    dep_lib = tmp_path / "FHIRHelpers.cql"
    dep_lib.write_text("""
library FHIRHelpers version '4.0.1'
using FHIR version '4.0.1'
define "Helper": 'helper'
""")

    resolver = DependencyResolver(paths=[tmp_path])
    context = resolver.build_context("Main")

    assert "Main" in context.libraries
    assert "FHIRHelpers" in context.libraries


def test_cycle_detection(tmp_path):
    """Test that circular dependencies are detected."""
    # Create libraries with circular dependency
    lib_a = tmp_path / "LibA.cql"
    lib_a.write_text("""
library LibA version '1.0.0'
using FHIR version '4.0.1'
include LibB version '1.0.0'
define "A": true
""")

    lib_b = tmp_path / "LibB.cql"
    lib_b.write_text("""
library LibB version '1.0.0'
using FHIR version '4.0.1'
include LibA version '1.0.0'
define "B": true
""")

    resolver = DependencyResolver(paths=[tmp_path])

    with pytest.raises(ResolutionError, match="Circular dependency"):
        resolver.build_context("LibA")


def test_resolve_library_not_found(tmp_path):
    """Test resolving a library that doesn't exist."""
    resolver = DependencyResolver(paths=[tmp_path])

    lib = resolver.resolve_library("NonExistent")
    assert lib is None


def test_resolve_valueset_not_found(tmp_path):
    """Test resolving a valueset that doesn't exist."""
    resolver = DependencyResolver(paths=[tmp_path])

    vs = resolver.resolve_valueset("http://example.org/ValueSet/NonExistent")
    assert vs is None


def test_build_context_library_not_found(tmp_path):
    """Test building context for a library that doesn't exist."""
    resolver = DependencyResolver(paths=[tmp_path])

    with pytest.raises(ResolutionError, match="Library not found"):
        resolver.build_context("NonExistent")


def test_index_bundle(tmp_path):
    """Test indexing resources from a FHIR Bundle."""
    bundle_file = tmp_path / "bundle.json"
    bundle_file.write_text(json.dumps({
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "ValueSet",
                    "url": "http://example.org/ValueSet/InBundle",
                    "status": "active"
                }
            },
            {
                "resource": {
                    "resourceType": "Library",
                    "url": "http://example.org/Library/InBundle",
                    "name": "InBundleLib",
                    "status": "active",
                    "type": {
                        "coding": [{"system": "http://terminology.hl7.org/CodeSystem/library-type", "code": "logic-library"}]
                    },
                    "content": []
                }
            }
        ]
    }))

    resolver = DependencyResolver(paths=[tmp_path])

    # Both resources should be indexed
    vs = resolver.resolve_valueset("http://example.org/ValueSet/InBundle")
    assert vs is not None

    lib = resolver.resolve_library("http://example.org/Library/InBundle")
    assert lib is not None
    assert lib.name == "InBundleLib"


def test_resolve_measure(tmp_path):
    """Test resolving a FHIR Measure resource."""
    measure_file = tmp_path / "TestMeasure.json"
    measure_file.write_text(json.dumps({
        "resourceType": "Measure",
        "url": "http://example.org/Measure/Test",
        "name": "TestMeasure",
        "version": "1.0.0",
        "status": "active",
        "library": ["http://example.org/Library/TestLib"],
        "group": [
            {
                "population": [
                    {
                        "code": {"coding": [{"code": "initial-population"}]},
                        "criteria": {"expression": "InInitialPopulation"}
                    }
                ]
            }
        ]
    }))

    resolver = DependencyResolver(paths=[tmp_path])
    measure = resolver.resolve_measure("http://example.org/Measure/Test")

    assert measure is not None
    assert measure.name == "TestMeasure"
    assert len(measure.library_urls) == 1
    assert len(measure.population_criteria) == 1


def test_extract_cql_from_library(tmp_path):
    """Test extracting CQL from a FHIR Library resource."""
    import base64

    cql_content = """
library Extracted version '1.0.0'
using FHIR version '4.0.1'
define "Test": true
"""
    encoded_cql = base64.b64encode(cql_content.encode()).decode()

    lib_file = tmp_path / "WithCQL.json"
    lib_file.write_text(json.dumps({
        "resourceType": "Library",
        "url": "http://example.org/Library/WithCQL",
        "name": "WithCQL",
        "status": "active",
        "content": [
            {
                "contentType": "text/cql",
                "data": encoded_cql
            }
        ]
    }))

    resolver = DependencyResolver(paths=[tmp_path])
    lib = resolver.resolve_library("WithCQL")

    assert lib is not None
    assert lib.cql_text is not None
    assert "library Extracted" in lib.cql_text


def test_multiple_paths(tmp_path):
    """Test resolver with multiple search paths."""
    path1 = tmp_path / "path1"
    path2 = tmp_path / "path2"
    path1.mkdir()
    path2.mkdir()

    # Create library in path1
    lib1 = path1 / "Lib1.cql"
    lib1.write_text("library Lib1 version '1.0.0'\ndefine \"A\": true")

    # Create library in path2
    lib2 = path2 / "Lib2.cql"
    lib2.write_text("library Lib2 version '1.0.0'\ndefine \"B\": true")

    resolver = DependencyResolver(paths=[path1, path2])

    assert resolver.resolve_library("Lib1") is not None
    assert resolver.resolve_library("Lib2") is not None


def test_recursive_path_scan(tmp_path):
    """Test that resolver scans subdirectories recursively."""
    subdir = tmp_path / "subdir" / "nested"
    subdir.mkdir(parents=True)

    cql_file = subdir / "Nested.cql"
    cql_file.write_text("library Nested version '1.0.0'\ndefine \"X\": true")

    resolver = DependencyResolver(paths=[tmp_path])
    lib = resolver.resolve_library("Nested")

    assert lib is not None
    assert lib.name == "Nested"


def test_resolver_valueset_uses_shared_fhir_r4_extraction(tmp_path):
    """Iteration 5 / Domain 6 HISTORIAN.

    `_index_valueset` used to carry its own copy of the ValueSet extraction
    (flat expansion only, compose.exclude ignored). It now delegates to
    `fhir4ds.cql.valueset_codes` so the resolver and `FHIRDataLoader` cannot
    drift: hierarchical expansions are flattened and compose.exclude removes
    codes.
    """
    vs_file = tmp_path / "HierValueSet.json"
    vs_file.write_text(json.dumps({
        "resourceType": "ValueSet",
        "url": "http://example.org/ValueSet/Hier",
        "status": "active",
        "expansion": {"contains": [
            {"system": "http://snomed.info/sct", "code": "parent", "contains": [
                {"system": "http://snomed.info/sct", "code": "child"},
            ]},
        ]},
    }))
    resolver = DependencyResolver(paths=[tmp_path])
    vs = resolver.resolve_valueset("http://example.org/ValueSet/Hier")
    assert vs is not None
    assert [c["code"] for c in vs.codes] == ["parent", "child"]


def test_resolver_valueset_honors_compose_exclude(tmp_path):
    vs_file = tmp_path / "ExclValueSet.json"
    vs_file.write_text(json.dumps({
        "resourceType": "ValueSet",
        "url": "http://example.org/ValueSet/Excl",
        "status": "active",
        "compose": {
            "include": [{"system": "http://snomed.info/sct", "concept": [
                {"code": "A"}, {"code": "B"}]}],
            "exclude": [{"system": "http://snomed.info/sct", "concept": [
                {"code": "B"}]}],
        },
    }))
    resolver = DependencyResolver(paths=[tmp_path])
    vs = resolver.resolve_valueset("http://example.org/ValueSet/Excl")
    assert vs is not None
    assert [c["code"] for c in vs.codes] == ["A"]


def test_resolver_records_bad_valueset_file_without_aborting(tmp_path):
    """Iteration 10 / Domain 8 SKEPTIC.

    Delegating `_index_valueset` to the shared extractor made a malformed
    ValueSet file abort `DependencyResolver(paths=[corpus])` with an
    unattributed TypeError — one bad file blocked the whole corpus. The sibling
    indexers warn+skip; ValueSets now do the same but RECORD the failure
    (url -> "<path>: <cause>") because a silent skip under-reports membership.
    """
    good = tmp_path / "Good.json"
    good.write_text(json.dumps({
        "resourceType": "ValueSet", "url": "http://ex.org/VS/good", "status": "active",
        "compose": {"include": [{"system": "s", "concept": [{"code": "ok"}]}]},
    }))
    bad = tmp_path / "Bad.json"
    bad.write_text(json.dumps({
        "resourceType": "ValueSet", "url": "http://ex.org/VS/bad", "status": "active",
        "expansion": {"contains": "not-a-list"},
    }))

    resolver = DependencyResolver(paths=[tmp_path])  # must not raise

    assert resolver.resolve_valueset("http://ex.org/VS/good").codes == [
        {"system": "s", "code": "ok", "display": None}]
    assert resolver.resolve_valueset("http://ex.org/VS/bad") is None
    recorded = resolver.valueset_index_errors["http://ex.org/VS/bad"]
    assert "Bad.json" in recorded
    assert "must be a list" in recorded
