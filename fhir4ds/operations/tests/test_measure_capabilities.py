"""Measure/MeasureReport capability tests (FEATURE_CLEANROOM_MEASURE_REPORTS).

Covers: bootstrap + explicit mapping, duplicate/unknown-code rejection,
MeasureParser round-trip, report<->rows round-trip, Bundle import with
unknown-code skip diagnostics, flatten_view staging + default VD, and
the pandas-free import invariant (SO-1).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from fhir4ds import create_connection
from fhir4ds.operations import (
    DEFAULT_MEASURE_REPORT_VIEW,
    POPULATION_ORDER,
    flatten_view,
    measure_from_definitions,
    measure_population_map,
    measure_report_from_rows,
    output_columns_from_measure,
    rows_from_measure_reports,
)
from fhir4ds.operations.envelopes import LibraryText

REPO = Path(__file__).resolve().parents[3]

DEMO_CQL = """library Demo version '1.0.0'
using FHIR version '4.0.1'

define "Initial Population":
  true

define "Denominator":
  true

define "Has Name":
  true
"""


def _lib() -> LibraryText:
    return LibraryText(name="Demo", text=DEMO_CQL)


def _mapping() -> list[dict[str, str]]:
    return [
        {"define": "Initial Population", "code": "initial-population"},
        {"define": "Denominator", "code": "denominator"},
    ]


def _measure() -> dict:
    return measure_from_definitions(
        [_lib()], _lib(), mapping=_mapping()
    ).measure


class TestMeasureFromDefinitions:
    def test_bootstrap_mode_returns_no_populations(self):
        result = measure_from_definitions([_lib()], _lib())
        assert result.ok
        assert result.measure["group"][0]["population"] == []
        assert result.mapping == ()

    def test_explicit_mapping_builds_measure(self):
        result = measure_from_definitions([_lib()], _lib(), mapping=_mapping())
        assert result.ok
        pops = result.measure["group"][0]["population"]
        assert [p["criteria"]["expression"] for p in pops] == [
            "Initial Population",
            "Denominator",
        ]
        assert pops[0]["code"]["coding"][0]["code"] == "initial-population"
        assert pops[0]["criteria"]["language"] == "text/cql-identifier"

    def test_population_basis_extension_and_group_id(self):
        measure = _measure()
        group = measure["group"][0]
        assert group["id"] == "group-1"
        ext = group["extension"][0]
        assert ext["url"].endswith("cqfm-populationBasis")
        assert ext["valueCode"] == "boolean"

    def test_unknown_define_rejected(self):
        result = measure_from_definitions(
            [_lib()],
            _lib(),
            mapping=[{"define": "Nope", "code": "initial-population"}],
        )
        assert not result.ok
        assert result.diagnostics[0].code == "input_error"
        assert "Nope" in result.diagnostics[0].message

    def test_duplicate_population_code_rejected(self):
        result = measure_from_definitions(
            [_lib()],
            _lib(),
            mapping=[
                {"define": "Initial Population", "code": "initial-population"},
                {"define": "Denominator", "code": "initial-population"},
            ],
        )
        assert not result.ok
        assert "duplicate" in result.diagnostics[0].message

    def test_unknown_population_code_rejected(self):
        result = measure_from_definitions(
            [_lib()],
            _lib(),
            mapping=[{"define": "Initial Population", "code": "bogus-population"}],
        )
        assert not result.ok
        assert result.diagnostics[0].data["expected"] == list(POPULATION_ORDER)

    def test_round_trips_through_measure_parser(self):
        """INV-3/INV-4: the built Measure parses back via DQM MeasureParser."""
        pairs, diag = measure_population_map(_measure())
        assert diag is None
        assert pairs == [
            ("initial-population", "Initial Population"),
            ("denominator", "Denominator"),
        ]

    def test_output_columns_from_measure(self):
        cols = output_columns_from_measure(_measure())
        assert cols == {
            "initial_population": "Initial Population",
            "denominator": "Denominator",
        }

    def test_non_measure_resource_rejected(self):
        pairs, diag = measure_population_map({"resourceType": "Patient"})
        assert pairs == []
        assert diag is not None
        assert diag.code == "input_error"


class TestMeasureReportRoundTrip:
    def _rows(self):
        return [
            {"patient_id": "p1", "initial_population": True, "denominator": True},
            {"patient_id": "p2", "initial_population": False, "denominator": True},
        ]

    def test_report_from_rows_membership_counts(self):
        result = measure_report_from_rows(
            _measure(), self._rows(), ["patient_id", "initial_population", "denominator"]
        )
        assert result.ok
        by_pid = {r["subject"]["reference"]: r for r in result.reports}
        assert set(by_pid) == {"Patient/p1", "Patient/p2"}
        p1_groups = by_pid["Patient/p1"]["group"]
        counts = {
            g["population"][0]["code"]["coding"][0]["code"]: g["population"][0]["count"]
            for g in p1_groups
        }
        assert counts == {"initial-population": 1, "denominator": 1}
        p2_counts = {
            g["population"][0]["code"]["coding"][0]["code"]: g["population"][0]["count"]
            for g in by_pid["Patient/p2"]["group"]
        }
        assert p2_counts == {"initial-population": 0, "denominator": 1}
        assert by_pid["Patient/p1"]["type"] == "individual"
        assert by_pid["Patient/p1"]["status"] == "complete"

    def test_period_carried(self):
        result = measure_report_from_rows(
            _measure(),
            self._rows(),
            ["patient_id", "initial_population"],
            period_start="2026-01-01",
            period_end="2026-12-31",
        )
        assert result.reports[0]["period"] == {
            "start": "2026-01-01",
            "end": "2026-12-31",
        }

    def test_round_trip_lossless(self):
        """INV-4: reports -> rows restores the membership booleans."""
        reports = measure_report_from_rows(
            _measure(), self._rows(), ["patient_id", "initial_population", "denominator"]
        )
        back = rows_from_measure_reports(
            list(reports.reports),
            population_codes=["initial-population", "denominator"],
        )
        assert back.ok
        assert list(back.columns) == [
            "patient_id",
            "initial_population",
            "denominator",
        ]
        rows = {r["patient_id"]: r for r in back.rows}
        assert rows["p1"]["initial_population"] is True
        assert rows["p2"]["initial_population"] is False
        assert rows["p2"]["denominator"] is True

    def test_bundle_import_and_unknown_code_skipped(self):
        reports = measure_report_from_rows(
            _measure(), self._rows(), ["patient_id", "initial_population"]
        )
        # Simulate MADiE-style report with an extra population code.
        extra = json.loads(json.dumps(reports.reports[0]))
        extra["group"].append(
            {
                "id": "g2",
                "population": [
                    {
                        "code": {
                            "coding": [
                                {"system": "x", "code": "measure-population-exclusion"}
                            ]
                        },
                        "count": 1,
                    }
                ],
            }
        )
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": r} for r in [*reports.reports[1:], extra]
            ],
        }
        result = rows_from_measure_reports(
            bundle, population_codes=["initial-population", "denominator"]
        )
        assert result.ok
        rows = {r["patient_id"]: r for r in result.rows}
        assert rows["p1"]["initial_population"] is True
        # info diagnostic names the skipped code
        assert any(
            d.severity == "info" and "measure-population-exclusion" in json.dumps(d.data)
            for d in result.diagnostics
        )

    def test_malformed_reports_rejected(self):
        with pytest.raises(Exception):
            rows_from_measure_reports({"resourceType": "Patient"})
        with pytest.raises(Exception):
            rows_from_measure_reports("nope")
        missing_subject = {
            "resourceType": "MeasureReport",
            "group": [],
        }
        with pytest.raises(Exception):
            rows_from_measure_reports(missing_subject)


class TestFlattenView:
    def test_default_vd_flattens_reports(self):
        reports = measure_report_from_rows(
            _measure(),
            [
                {"patient_id": "p1", "initial_population": True, "denominator": True},
                {"patient_id": "p2", "initial_population": False, "denominator": True},
            ],
            ["patient_id", "initial_population", "denominator"],
        )
        conn = create_connection()
        try:
            result = flatten_view(
                DEFAULT_MEASURE_REPORT_VIEW, list(reports.reports), conn
            )
            assert result.ok, [d.message for d in result.diagnostics]
            assert list(result.columns) == [
                "patient_id",
                "group_id",
                "population_code",
                "population_count",
            ]
            got = {(r["patient_id"], r["population_code"]): r["population_count"] for r in result.rows}
            assert got[("Patient/p1", "initial-population")] == 1
            assert got[("Patient/p2", "initial-population")] == 0
            # staging table dropped (SO-3)
            tables = conn.execute("SHOW TABLES").fetchall()
            assert not any("__cleanroom_flatten_src" in str(t) for t in tables)
        finally:
            conn.close()

    def test_invalid_vd_typed_diagnostic(self):
        conn = create_connection()
        try:
            result = flatten_view({"resource": "Bogus"}, [{"resourceType": "Bogus"}], conn)
            assert not result.ok
            assert result.diagnostics
        finally:
            conn.close()


class TestPandasFreeImports:
    def test_dqm_parser_importable_without_pandas(self):
        """SO-1: parser/types surface imports with pandas blocked.

        Runs a subprocess with a meta-path blocker so no earlier import
        in this process can satisfy the dependency.
        """
        probe = (
            "import sys\n"
            "class _B:\n"
            "    def find_module(self, name, path=None):\n"
            "        if name in ('pandas','numpy') or name.startswith(('pandas.','numpy.')):\n"
            "            return self\n"
            "    def load_module(self, name):\n"
            "        raise ImportError('blocked: '+name)\n"
            "sys.meta_path.insert(0, _B())\n"
            "from fhir4ds.dqm.parser import MeasureParser\n"
            "from fhir4ds.dqm.types import PopulationMap\n"
            "print('OK')\n"
        )
        out = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            cwd=str(REPO),
            env={"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin"},
            timeout=120,
        )
        assert out.returncode == 0, out.stderr
        assert "OK" in out.stdout

    def test_operations_module_has_no_pandas_imports(self):
        import fhir4ds.operations.capabilities.measure as m
        import inspect

        src = inspect.getsource(m)
        assert "import pandas" not in src
        assert "import numpy" not in src
