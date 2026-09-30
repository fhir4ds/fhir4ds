"""Live-shape replay regression tests (2026-09 escape analysis).

Doctrine (GLOBAL_RULES.md 'Adapter-Parity and Probe Doctrine'):
fixtures must replay caller shapes, not author-convenient shapes. The
live SQL->pandas boundary emits np.ndarray object cells of STRINGS for
LIST()-projected population columns -- QA-021/022/027 all escaped
because unit fixtures built python bool lists instead. These tests pin
the live shapes through the PUBLIC summary_report path so the decoding
layer can never again be green against a shape the runtime never
produces, and one end-to-end case builds cells through the REAL
evaluate() path.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from fhir4ds.dqm.evaluator import MeasureEvaluator
from fhir4ds.dqm.models import MeasureResult


def _pop_map():
    from fhir4ds.dqm.types import (
        AuditPersona,
        GroupMap,
        PopulationEntry,
        PopulationMap,
    )

    return PopulationMap(
        measure_id="shape-replay",
        cql_library_ref="http://x/Library/ShapeReplay",
        groups=[
            GroupMap(
                group_id="group-0",
                population_basis="boolean",
                populations=[
                    PopulationEntry(
                        population_code="initial-population",
                        group_id="group-0",
                        cql_expression="Initial Population",
                        audit_persona=AuditPersona.INCLUSION,
                    ),
                    PopulationEntry(
                        population_code="denominator",
                        group_id="group-0",
                        cql_expression="Denominator",
                        audit_persona=AuditPersona.INCLUSION,
                    ),
                    PopulationEntry(
                        population_code="numerator",
                        group_id="group-0",
                        cql_expression="Numerator",
                        audit_persona=AuditPersona.NUMERATOR,
                    ),
                ],
            )
        ],
    )


def _single_cell_summary(cell) -> bool:
    """Run one cell through the public summary_report path (the QA-021/
    QA-027 decoding lives in the _population_mask closure inside it)."""
    frame = pd.DataFrame(
        {
            "patient_id": ["p0"],
            "initial_population": [cell],
            "denominator": [False],
            "numerator": [False],
        }
    )
    result = MeasureResult(
        dataframe=frame,
        populations={
            "initial_population": "Initial Population",
            "denominator": "Denominator",
            "numerator": "Numerator",
        },
        parameters={},
        measure_url=_pop_map().cql_library_ref,
        pop_map=_pop_map(),
    )
    return bool(MeasureEvaluator(conn=None).summary_report(result)["initial_population"])


class TestLiveShapeReplay:
    """QA-021/027 class: cells as the live path emits them."""

    @staticmethod
    def _nd(cell):
        """Wrap a python list as the ndarray cell pandas stores for a
        DuckDB LIST()-projected column (the LIVE shape)."""
        return np.array(cell, dtype=object)

    def test_string_bool_ndarray_cells_decode_by_value(self) -> None:
        """['true']/['false'] STRING ndarray cells: false must NOT count
        (presence semantics is for resource evidence, not booleans)."""
        assert _single_cell_summary(self._nd(["true"])) is True
        assert _single_cell_summary(self._nd(["false"])) is False
        assert _single_cell_summary(self._nd([])) is False

    def test_python_bool_list_cells_decode_by_value(self) -> None:
        """QA-021 original shape still guarded: [True]/[False] lists."""
        assert _single_cell_summary([True]) is True
        assert _single_cell_summary([False]) is False
        assert _single_cell_summary([]) is False

    def test_resource_reference_strings_keep_presence_semantics(self) -> None:
        """['Encounter/e1'] evidence arrays stay truthy by presence."""
        assert _single_cell_summary(self._nd(["Encounter/e1"])) is True
        assert _single_cell_summary(self._nd([])) is False

    def test_boolean_string_python_lists_decode_by_value(self) -> None:
        """QA-027 list-branch shape: ['TRUE'] with whitespace/case."""
        assert _single_cell_summary([" TRUE "]) is True
        assert _single_cell_summary(["False"]) is False

    def test_e2e_raw_boolean_defines_end_to_end(self) -> None:
        """Full pipeline: raw-Boolean CQL defines lower to LIST()
        projections; summary counts must exclude false patients."""
        cql = """library ShapeReplay
using FHIR version '4.0.1'
context Patient
define "Initial Population": exists ([Patient])
define "Denominator": Patient.active
define "Numerator": Patient.active
"""
        measure = {
            "resourceType": "Measure",
            "id": "shape-replay",
            "library": ["http://x/Library/ShapeReplay"],
            "group": [
                {
                    "population": [
                        {"code": {"coding": [{"code": "initial-population"}]},
                         "criteria": {"expression": "Initial Population"}},
                        {"code": {"coding": [{"code": "denominator"}]},
                         "criteria": {"expression": "Denominator"}},
                        {"code": {"coding": [{"code": "numerator"}]},
                         "criteria": {"expression": "Numerator"}},
                    ]
                }
            ],
        }
        from fhir4ds.cql import FHIRDataLoader
        from fhir4ds.cql.duckdb import register
        from fhir4ds.fhirpath.duckdb import register_fhirpath

        con = duckdb.connect()
        register_fhirpath(con)
        register(con, include_fhirpath=False)
        loader = FHIRDataLoader(con)
        loader.load_resource({"resourceType": "Patient", "id": "ra1", "active": True})
        loader.load_resource({"resourceType": "Patient", "id": "ra2", "active": False})
        loader.load_resource({"resourceType": "Patient", "id": "ra3", "active": True})

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shape.cql"
            path.write_text(cql)
            evaluator = MeasureEvaluator(conn=con)
            result = evaluator.evaluate(
                measure_bundle=measure, cql_library_path=str(path)
            )
        summary = evaluator.summary_report(result)
        assert summary["initial_population"] == 3
        assert summary["denominator"] == 2
        assert summary["numerator"] == 2
