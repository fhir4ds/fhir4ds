"""Boundary-parity regression tests (2026-09 escape analysis).

Doctrine (GLOBAL_RULES.md 'Adapter-Parity and Probe Doctrine'): every
operations capability with a core-engine equivalent must produce equal
results on a shared fixture. These tests pin the historical escape
class — adapter seams that unit probes on either side missed:

- evaluate_library (ops envelope, browser/CLI/MCP path) vs
  MeasureEvaluator (dqm engine path) — the BF-001 hardcoded-includes
  class. Both paths translate the SAME CMS69-style library-with-includes
  and must agree on population rows.
- Envelope-field coverage — DatasetSpec.valueset_paths (QA-026) is
  exercised here as the canonical dead-on-arrival guard: every public
  envelope field must have at least one live caller in tests.
- Caller-shape replay — parameters arrive from JSON as LISTS; the
  tuple spelling is the Python convenience only (QA-025).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import duckdb
import pytest

from fhir4ds.operations.envelopes import DatasetSpec, LibraryText

MAIN_CQL = """library ParityMain version '1.0.0'
using FHIR version '4.0.1'
include ParityDep version '1.0.0' called Dep
context Patient
define "Initial Population": exists ([Patient])
define "Flag": Dep."Is Male"
"""

DEP_CQL = """library ParityDep version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Is Male": Patient.gender = 'male'
"""

PATIENTS = [
    {"resourceType": "Patient", "id": "pm1", "gender": "male"},
    {"resourceType": "Patient", "id": "pf1", "gender": "female"},
]


def _registered_conn() -> duckdb.DuckDBPyConnection:
    """Connection carrying the fhirpath UDFs both paths require."""
    con = duckdb.connect()
    from fhir4ds.fhirpath.duckdb import register_fhirpath

    register_fhirpath(con)
    from fhir4ds.cql.duckdb import register

    register(con, include_fhirpath=False)
    return con


def _load_fixture(con: duckdb.DuckDBPyConnection) -> None:
    from fhir4ds.cql import FHIRDataLoader

    loader = FHIRDataLoader(con)
    for resource in PATIENTS:
        loader.load_resource(resource)


class TestEvaluateLibraryParity:
    """ops envelope vs MeasureEvaluator on one library-with-includes fixture."""

    def test_ops_path_matches_engine_path_on_includes(self) -> None:
        """The BF-001 class: the ops path must resolve the include chain
        identically to the engine path and produce the same rows."""
        from fhir4ds.operations import evaluate_library
        from fhir4ds.dqm import MeasureEvaluator

        main = LibraryText(name="ParityMain", text=MAIN_CQL, version="1.0.0")
        dep = LibraryText(name="ParityDep", text=DEP_CQL, version="1.0.0")

        con_ops = _registered_conn()
        _load_fixture(con_ops)
        ops_rows = evaluate_library(
            [main, dep], main,
            DatasetSpec(resources=PATIENTS),
            con_ops,
            output_columns={"IP": "Initial Population", "Flag": "Flag"},
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "ParityMain.cql").write_text(MAIN_CQL)
            (tmp_path / "ParityDep.cql").write_text(DEP_CQL)
            measure = {
                "resourceType": "Measure", "id": "parity",
                "library": ["http://x/Library/ParityMain"],
                "group": [{"population": [
                    {"code": {"coding": [{"code": "initial-population"}]},
                     "criteria": {"expression": "Initial Population"}},
                ]}],
            }
            con_eng = _registered_conn()
            _load_fixture(con_eng)
            evaluator = MeasureEvaluator(con_eng)
            result = evaluator.evaluate(
                measure_bundle=measure,
                cql_library_path=str(tmp_path / "ParityMain.cql"),
                include_paths=[str(tmp_path)],
            )
            engine_ip = {
                row["patient_id"]: bool(row["initial_population"])
                for row in result.dataframe.to_dict("records")
            }

        assert ops_rows.ok, [str(d.message) for d in ops_rows.diagnostics]
        ops_ip = {row["patient_id"]: bool(row["IP"]) for row in ops_rows.rows}
        assert ops_ip == engine_ip == {"pm1": True, "pf1": True}

        # Flag routes through the include: male True / female False —
        # a broken include chain (BF-001 class) yields all-false or
        # a typed unresolved-library error instead.
        ops_flag = {row["patient_id"]: bool(row["Flag"]) for row in ops_rows.rows}
        assert ops_flag == {"pm1": True, "pf1": False}

    def test_json_list_parameter_shape_is_first_class(self) -> None:
        """QA-025 class: the browser contract sends parameters as JSON
        arrays; the ops path must accept that spelling natively."""
        from fhir4ds.operations import evaluate_library

        main = LibraryText(
            name="ParityMain", text=MAIN_CQL, version="1.0.0"
        )
        dep = LibraryText(name="ParityDep", text=DEP_CQL, version="1.0.0")
        con = _registered_conn()
        _load_fixture(con)
        result = evaluate_library(
            [main, dep], main,
            DatasetSpec(resources=PATIENTS),
            con,
            # LIST spelling — the JSON/browser shape, not the tuple
            # convenience
            parameters={"Measurement Period": ["2026-01-01T00:00:00.0", "2026-12-31T23:59:59.999"]},
            output_columns={"IP": "Initial Population"},
        )
        assert result.ok, [str(d.message) for d in result.diagnostics]

    def test_valueset_paths_envelope_field_alive(self) -> None:
        """QA-026 class: envelope-field coverage guard — DatasetSpec
        fields must never become advertised-but-dead."""
        from fhir4ds.operations import load_dataset

        vs = {
            "resourceType": "ValueSet", "id": "parity-vs",
            "url": "http://parity.test/vs",
            "expansion": {"contains": [
                {"system": "http://parity.test", "code": "c1"},
                {"system": "http://parity.test", "code": "c2"},
            ]},
        }
        con = _registered_conn()
        with tempfile.TemporaryDirectory() as tmp:
            vs_path = Path(tmp) / "vs.json"
            vs_path.write_text(json.dumps(vs))
            result = load_dataset(DatasetSpec(valueset_paths=[str(vs_path)]), con)
        assert result.ok, [str(d.message) for d in result.diagnostics]
        count = con.execute(
            "SELECT count(*) FROM valueset_codes WHERE valueset_url = 'http://parity.test/vs'"
        ).fetchone()[0]
        assert count == 2
