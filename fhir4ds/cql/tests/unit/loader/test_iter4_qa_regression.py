"""Iteration 4 / Domain 6 — regression tests for QA-006..QA-010.

Each test exercises one fix surgically:

* QA-006: ``NotesPipeline.extract_conditions_batch`` rejects non-list inputs.
* QA-007: ``NotesPipelineConfig`` / ``AutoCoderConfig`` reject non-positive
  ``workers``/``batch_size`` at construction time (frozen dataclass).
* QA-008: ``FHIRDataLoader.load_bundle`` enforces FHIR R4 ``Bundle.type``
  1..1 cardinality and rejects unknown BundleType codes.
* QA-009: ``FHIRDataLoader.load_ndjson(strict=True)`` validates per-line
  FHIR shape with line-number attribution.
* QA-010: ``FHIRDataLoader.load_resources`` dedup emits a WARNING when a
  source/derived ``(id, resourceType)`` collision overwrites an earlier row.
"""

from __future__ import annotations

import json
import logging
import sys
import types

import duckdb
import pytest

from fhir4ds.cql.loader.auto_coder import AutoCoderConfig
from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader
from fhir4ds.cql.loader.notes_pipeline import (
    NotesPipeline,
    NotesPipelineConfig,
)


@pytest.fixture
def duckdb_con():
    con = duckdb.connect()
    yield con
    con.close()


@pytest.fixture
def loader(duckdb_con):
    return FHIRDataLoader(duckdb_con)


# ======================================================================
# QA-006: extract_conditions_batch rejects non-list inputs
# ======================================================================


def test_qa006_extract_conditions_batch_rejects_string():
    """String input must raise TypeError, not character-iterate silently."""
    pipe = NotesPipeline(NotesPipelineConfig())
    with pytest.raises(TypeError, match="Expected list of FHIR resource dicts"):
        pipe.extract_conditions_batch("ClinicalImpression")  # type: ignore[arg-type]


def test_qa006_extract_conditions_batch_rejects_dict():
    """Dict input must raise TypeError with actionable message."""
    pipe = NotesPipeline(NotesPipelineConfig())
    with pytest.raises(TypeError, match="Expected list of FHIR resource dicts"):
        pipe.extract_conditions_batch({"a": 1})  # type: ignore[arg-type]


def test_qa006_extract_conditions_batch_rejects_generator():
    """Generator input must raise TypeError (no len/slice)."""
    pipe = NotesPipeline(NotesPipelineConfig())

    def gen():
        yield {"resourceType": "Patient", "id": "p1"}

    with pytest.raises(TypeError, match="Expected list of FHIR resource dicts"):
        pipe.extract_conditions_batch(gen())  # type: ignore[arg-type]


def test_qa006_extract_conditions_batch_accepts_list():
    """List input still works — guard is non-breaking for correct callers."""
    pipe = NotesPipeline(NotesPipelineConfig())
    # Empty list short-circuits before any medterm4ds import.
    assert pipe.extract_conditions_batch([]) == []


# ======================================================================
# QA-007: NotesPipelineConfig / AutoCoderConfig validate non-positive knobs
# ======================================================================


@pytest.mark.parametrize("workers", [0, -1, -10])
def test_qa007_notes_pipeline_config_rejects_non_positive_workers(workers):
    with pytest.raises(ValueError, match="workers must be a positive int"):
        NotesPipelineConfig(workers=workers)


@pytest.mark.parametrize("batch_size", [0, -1, -10])
def test_qa007_notes_pipeline_config_rejects_non_positive_batch_size(batch_size):
    with pytest.raises(ValueError, match="batch_size must be a positive int"):
        NotesPipelineConfig(batch_size=batch_size)


def test_qa007_notes_pipeline_config_rejects_negative_parallel_threshold():
    with pytest.raises(ValueError, match="parallel_threshold"):
        NotesPipelineConfig(parallel_threshold=-1)


@pytest.mark.parametrize("workers", [0, -1])
def test_qa007_auto_coder_config_rejects_non_positive_workers(workers):
    with pytest.raises(ValueError, match="workers must be a positive int"):
        AutoCoderConfig(workers=workers)


@pytest.mark.parametrize("batch_size", [0, -1])
def test_qa007_auto_coder_config_rejects_non_positive_batch_size(batch_size):
    with pytest.raises(ValueError, match="batch_size must be a positive int"):
        AutoCoderConfig(batch_size=batch_size)


def test_qa007_default_configs_still_construct():
    """Default-constructed configs must still work — guard is non-breaking."""
    assert NotesPipelineConfig().workers == 1
    assert NotesPipelineConfig().batch_size == 1
    assert AutoCoderConfig().workers == 1
    assert AutoCoderConfig().batch_size == 1


# ======================================================================
# QA-008: Bundle.type 1..1 cardinality enforcement
# ======================================================================


def test_qa008_load_bundle_rejects_missing_type(loader):
    """Bundle without ``type`` field violates FHIR R4 1..1 cardinality."""
    with pytest.raises(ValueError, match=r"Bundle\.type is required"):
        loader.load_bundle({"resourceType": "Bundle"})


def test_qa008_load_bundle_rejects_empty_type(loader):
    with pytest.raises(ValueError, match=r"Bundle\.type is required"):
        loader.load_bundle({"resourceType": "Bundle", "type": ""})


def test_qa008_load_bundle_rejects_non_string_type(loader):
    with pytest.raises(ValueError, match=r"Bundle\.type is required"):
        loader.load_bundle({"resourceType": "Bundle", "type": 123})


def test_qa008_load_bundle_rejects_unknown_type(loader):
    """Bundle.type must be in the FHIR R4 BundleType valueset."""
    with pytest.raises(ValueError, match="not a valid FHIR R4 BundleType"):
        loader.load_bundle(
            {"resourceType": "Bundle", "type": "not-a-bundle-type"}
        )


@pytest.mark.parametrize(
    "bundle_type",
    [
        "document",
        "message",
        "transaction",
        "transaction-response",
        "batch",
        "batch-response",
        "history",
        "searchset",
        "collection",
    ],
)
def test_qa008_load_bundle_accepts_all_valid_bundle_types(loader, bundle_type):
    """All 9 FHIR R4 BundleType codes load without error."""
    bundle = {
        "resourceType": "Bundle",
        "type": bundle_type,
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "p1"}},
        ],
    }
    assert loader.load_bundle(bundle) == 1


# ======================================================================
# QA-009: load_ndjson strict=True validates FHIR shape per-line with
# line-number attribution
# ======================================================================


def test_qa009_load_ndjson_strict_includes_line_number(loader, tmp_path):
    """strict=True must include the 1-based line number for FHIR-shape errors."""
    ndjson = tmp_path / "bad.ndjson"
    ndjson.write_text(
        '{"resourceType": "Patient", "id": "p1"}\n'
        '{"id": "missing-resource-type"}\n'
        '{"resourceType": "Patient", "id": "p2"}\n'
    )
    with pytest.raises(ValueError, match=r"Invalid FHIR resource at line 2"):
        loader.load_ndjson(str(ndjson), strict=True)


def test_qa009_load_ndjson_strict_no_partial_load(loader, tmp_path):
    """On strict=True failure, the resources table must remain empty."""
    ndjson = tmp_path / "bad.ndjson"
    ndjson.write_text(
        '{"resourceType": "Patient", "id": "p1"}\n'
        '{"id": "missing-resource-type"}\n'
    )
    with pytest.raises(ValueError):
        loader.load_ndjson(str(ndjson), strict=True)
    assert loader.count() == 0


def test_qa009_load_ndjson_strict_rejects_non_object_json(loader, tmp_path):
    """strict=True must reject valid-JSON-but-not-an-object lines with attribution."""
    ndjson = tmp_path / "arr.ndjson"
    ndjson.write_text(
        '{"resourceType": "Patient", "id": "p1"}\n'
        '[1, 2, 3]\n'
    )
    with pytest.raises(ValueError, match=r"line 2"):
        loader.load_ndjson(str(ndjson), strict=True)


def test_qa009_load_ndjson_strict_rejects_nan_with_attribution(loader, tmp_path):
    """NaN-bearing lines (valid JSON5, invalid FHIR) must attribute to the line."""
    ndjson = tmp_path / "nan.ndjson"
    ndjson.write_text(
        '{"resourceType": "Patient", "id": "p1"}\n'
        '{"resourceType": "Observation", "id": "o1", "value": NaN}\n'
    )
    with pytest.raises(ValueError, match=r"line 2"):
        loader.load_ndjson(str(ndjson), strict=True)


def test_qa009_load_ndjson_non_strict_still_skips_invalid(loader, tmp_path):
    """strict=False still warns + skips — parity preserved."""
    ndjson = tmp_path / "mixed.ndjson"
    ndjson.write_text(
        '{"resourceType": "Patient", "id": "p1"}\n'
        '{"id": "missing-resource-type"}\n'
        '{"resourceType": "Patient", "id": "p2"}\n'
    )
    count = loader.load_ndjson(str(ndjson), strict=False)
    assert count == 2


# ======================================================================
# QA-010: load_resources dedup emits WARNING on source/derived collision
# ======================================================================


def test_qa010_dedup_source_collision_logs_warning(loader, caplog):
    """Source-source duplicate id emits WARNING (was DEBUG)."""
    with caplog.at_level(
        logging.WARNING, logger="fhir4ds.cql.loader.fhir_loader"
    ):
        loader.load_resources([
            {"resourceType": "Patient", "id": "p1"},
            {"resourceType": "Patient", "id": "p1", "name": [{"text": "dup"}]},
        ])
    assert any(
        "Duplicate resource Patient/p1" in r.message
        and r.levelno == logging.WARNING
        for r in caplog.records
    )


def test_qa010_dedup_source_does_not_log_when_unique(loader, caplog):
    """No duplicate-warning when ids are unique."""
    caplog.set_level(logging.WARNING)
    loader.load_resources([
        {"resourceType": "Patient", "id": "p1"},
        {"resourceType": "Patient", "id": "p2"},
    ])
    # No WARNING records about duplicates.
    assert not any(
        "Duplicate resource" in r.message for r in caplog.records
    )
