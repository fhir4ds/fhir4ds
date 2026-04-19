"""Tests for MeasureEvaluator."""

import pytest
import pandas as pd

from fhir4ds.dqm.evaluator import MeasureEvaluator
from fhir4ds.dqm.models import MeasureResult
from fhir4ds.dqm.types import AuditMode, GroupMap, PopulationEntry, PopulationMap, AuditPersona


def _make_pop_map(measure_url="http://example.com/Library/Test"):
    """Helper to build a minimal PopulationMap for testing exports."""
    return PopulationMap(
        measure_id="test-measure",
        cql_library_ref=measure_url,
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


def _make_result_df():
    """Helper to build a sample result DataFrame."""
    return pd.DataFrame(
        {
            "patient_id": ["P1", "P2", "P3"],
            "initial_population": [True, True, True],
            "denominator": [True, True, False],
            "numerator": [True, False, False],
        }
    )


def _make_measure_result():
    """Helper to build a MeasureResult for testing."""
    pop_map = _make_pop_map()
    df = _make_result_df()
    return MeasureResult(
        dataframe=df,
        populations={
            "initial_population": "Initial Population",
            "denominator": "Denominator",
            "numerator": "Numerator",
        },
        parameters={"Measurement Period": ("2024-01-01", "2024-12-31")},
        measure_url=pop_map.cql_library_ref,
        pop_map=pop_map,
    )


class TestMeasureEvaluatorValidation:
    """Test input validation."""

    def test_generate_narratives_requires_audit(self):
        """generate_narratives=True with audit=False must raise ValueError."""
        # We can test this without a real connection since validation happens first
        evaluator = MeasureEvaluator(conn=None)
        with pytest.raises(ValueError, match="Narratives require audit=True"):
            evaluator.evaluate(
                measure_bundle={"resourceType": "Measure", "id": "test", "group": [{}]},
                cql_library_path="/nonexistent.cql",
                audit=False,
                generate_narratives=True,
            )

    def test_measure_file_not_found(self):
        evaluator = MeasureEvaluator(conn=None)
        with pytest.raises(FileNotFoundError):
            evaluator.evaluate(
                measure_bundle="/nonexistent/measure.json",
                cql_library_path="/nonexistent.cql",
            )

    def test_summary_report_basic(self):
        """Test summary report with mock data."""
        import pandas as pd

        df = pd.DataFrame(
            {
                "patient_id": ["P1", "P2", "P3", "P4"],
                "initial_population": [True, True, True, True],
                "denominator": [True, True, True, False],
                "denominator_exclusion": [False, False, True, False],
                "denominator_exception": [False, False, False, False],
                "numerator": [True, False, False, False],
                "numerator_exclusion": [False, False, False, False],
            }
        )
        evaluator = MeasureEvaluator(conn=None)
        summary = evaluator.summary_report(df)
        assert summary["initial_population"] == 4
        assert summary["denominator"] == 3
        assert summary["denominator_exclusion"] == 1
        assert summary["denominator_final"] == 2  # 3 - 1 - 0
        assert summary["numerator"] == 1
        assert summary["numerator_final"] == 1
        assert summary["performance_rate"] == 0.5  # 1/2
        assert summary["total_patients"] == 4


class TestToMeasureReport:
    """Tests for to_measure_report()."""

    def test_to_measure_report_with_measure_result(self):
        """to_measure_report should accept a MeasureResult directly."""
        evaluator = MeasureEvaluator(conn=None)
        mr = _make_measure_result()
        report = evaluator.to_measure_report(
            mr, period_start="2024-01-01", period_end="2024-12-31"
        )
        assert report["resourceType"] == "MeasureReport"
        assert report["status"] == "complete"
        assert report["type"] == "summary"
        assert report["measure"] == "http://example.com/Library/Test"
        assert report["period"]["start"] == "2024-01-01"
        assert report["period"]["end"] == "2024-12-31"
        assert len(report["group"]) == 1
        pop_codes = [
            p["code"]["coding"][0]["code"] for p in report["group"][0]["population"]
        ]
        assert "initial-population" in pop_codes
        assert "denominator" in pop_codes
        assert "numerator" in pop_codes

    def test_to_measure_report_legacy_dataframe(self):
        """to_measure_report should still work with a plain DataFrame (legacy)."""
        evaluator = MeasureEvaluator(conn=None)
        pop_map = _make_pop_map()
        evaluator._last_pop_map = pop_map
        evaluator._last_parameters = {"Measurement Period": ("2024-01-01", "2024-12-31")}
        df = _make_result_df()
        report = evaluator.to_measure_report(df)
        assert report["resourceType"] == "MeasureReport"
        assert report["measure"] == "http://example.com/Library/Test"

    def test_to_measure_report_no_prior_evaluate_raises(self):
        """to_measure_report with a DataFrame and no prior evaluate() must raise."""
        evaluator = MeasureEvaluator(conn=None)
        from fhir4ds.dqm.errors import DQMError
        with pytest.raises(DQMError, match="No evaluation has been run"):
            evaluator.to_measure_report(_make_result_df())

    def test_to_measure_report_period_from_parameters(self):
        """Period should fall back to Measurement Period in parameters."""
        evaluator = MeasureEvaluator(conn=None)
        mr = _make_measure_result()
        report = evaluator.to_measure_report(mr)
        assert report["period"]["start"] == "2024-01-01"
        assert report["period"]["end"] == "2024-12-31"

    def test_to_measure_report_performance_rate_extension(self):
        """Summary reports should include a performanceRate extension."""
        evaluator = MeasureEvaluator(conn=None)
        mr = _make_measure_result()
        report = evaluator.to_measure_report(mr, period_start="2024-01-01", period_end="2024-12-31")
        assert "extension" in report
        ext = report["extension"][0]
        assert "performanceRate" in ext["url"]
        assert isinstance(ext["valueDecimal"], float)


class TestToCsv:
    """Tests for to_csv()."""

    def test_to_csv_with_dataframe(self, tmp_path):
        """to_csv should write a valid CSV from a DataFrame."""
        evaluator = MeasureEvaluator(conn=None)
        df = _make_result_df()
        csv_path = tmp_path / "output.csv"
        result_path = evaluator.to_csv(df, csv_path)
        assert result_path == csv_path
        assert csv_path.exists()
        content = csv_path.read_text()
        assert "patient_id" in content
        assert "P1" in content

    def test_to_csv_with_measure_result(self, tmp_path):
        """to_csv should accept a MeasureResult and write its DataFrame."""
        evaluator = MeasureEvaluator(conn=None)
        mr = _make_measure_result()
        csv_path = tmp_path / "result.csv"
        result_path = evaluator.to_csv(mr, csv_path)
        assert result_path == csv_path
        loaded = pd.read_csv(csv_path)
        assert list(loaded.columns) == list(mr.dataframe.columns)
        assert len(loaded) == 3


class TestMeasureResultDataclass:
    """Tests for the MeasureResult dataclass."""

    def test_measure_result_fields(self):
        """MeasureResult should have the expected fields."""
        mr = _make_measure_result()
        assert isinstance(mr.dataframe, pd.DataFrame)
        assert isinstance(mr.populations, dict)
        assert isinstance(mr.parameters, dict)
        assert mr.measure_url == "http://example.com/Library/Test"
        assert mr.pop_map is not None

    def test_measure_result_defaults(self):
        """MeasureResult should have sensible defaults."""
        mr = MeasureResult(
            dataframe=pd.DataFrame(),
            populations={},
            parameters={},
        )
        assert mr.measure_url is None
        assert mr.pop_map is None

    def test_summary_report_accepts_measure_result(self):
        """summary_report should accept a MeasureResult."""
        evaluator = MeasureEvaluator(conn=None)
        mr = _make_measure_result()
        summary = evaluator.summary_report(mr)
        assert summary["initial_population"] == 3
        assert summary["numerator"] == 1
        assert summary["total_patients"] == 3


class TestAuditModeEnum:
    """Tests for the AuditMode enum and its integration with evaluate()."""

    def test_audit_mode_values(self):
        """AuditMode should have exactly three values."""
        assert AuditMode.NONE == "none"
        assert AuditMode.POPULATION == "population"
        assert AuditMode.FULL == "full"

    def test_audit_mode_from_string(self):
        """AuditMode should be constructible from string values."""
        assert AuditMode("none") == AuditMode.NONE
        assert AuditMode("population") == AuditMode.POPULATION
        assert AuditMode("full") == AuditMode.FULL

    def test_audit_mode_invalid_string(self):
        """Invalid string should raise ValueError."""
        with pytest.raises(ValueError):
            AuditMode("invalid")

    def test_backward_compat_audit_true_defaults_to_full(self):
        """audit=True with default audit_mode should resolve to FULL mode.

        Verified by checking that narratives don't raise (which requires audit).
        """
        evaluator = MeasureEvaluator(conn=None)
        # audit=True alone should enable audit mode — narrative validation
        # checks the resolved mode. If it resolved to NONE, this would raise.
        with pytest.raises(FileNotFoundError):
            # We expect FileNotFoundError (CQL file missing), NOT ValueError.
            # ValueError would mean audit mode resolved to NONE incorrectly.
            evaluator.evaluate(
                measure_bundle={"resourceType": "Measure", "id": "test", "group": [{}]},
                cql_library_path="/nonexistent.cql",
                audit=True,
                generate_narratives=True,
            )

    def test_audit_mode_full_overrides_audit_false(self):
        """audit_mode='full' should work even when audit=False."""
        evaluator = MeasureEvaluator(conn=None)
        # audit_mode="full" takes precedence; narratives should not raise ValueError
        with pytest.raises(FileNotFoundError):
            evaluator.evaluate(
                measure_bundle={"resourceType": "Measure", "id": "test", "group": [{}]},
                cql_library_path="/nonexistent.cql",
                audit=False,
                audit_mode="full",
                generate_narratives=True,
            )

    def test_audit_mode_none_with_narratives_raises(self):
        """audit_mode='none' with generate_narratives=True must raise ValueError."""
        evaluator = MeasureEvaluator(conn=None)
        with pytest.raises(ValueError, match="Narratives require audit=True"):
            evaluator.evaluate(
                measure_bundle={"resourceType": "Measure", "id": "test", "group": [{}]},
                cql_library_path="/nonexistent.cql",
                audit_mode="none",
                generate_narratives=True,
            )

    def test_audit_mode_population_allows_narratives(self):
        """audit_mode='population' should allow narratives (no ValueError)."""
        evaluator = MeasureEvaluator(conn=None)
        with pytest.raises(FileNotFoundError):
            evaluator.evaluate(
                measure_bundle={"resourceType": "Measure", "id": "test", "group": [{}]},
                cql_library_path="/nonexistent.cql",
                audit_mode="population",
                generate_narratives=True,
            )

    def test_audit_mode_exported_from_package(self):
        """AuditMode should be importable from the top-level package."""
        from fhir4ds.dqm import AuditMode as AM
        assert AM is AuditMode


class TestFilterToIp:
    """Tests for the filter_to_ip parameter."""

    def test_filter_removes_non_ip_rows_no_audit(self):
        """filter_to_ip should remove rows where initial_population is False."""
        evaluator = MeasureEvaluator(conn=None)
        df = pd.DataFrame({
            "patient_id": ["P1", "P2", "P3", "P4"],
            "initial_population": [True, False, True, False],
            "denominator": [True, False, True, False],
        })
        filtered = evaluator._filter_to_initial_population(df, AuditMode.NONE)
        assert len(filtered) == 2
        assert list(filtered["patient_id"]) == ["P1", "P3"]

    def test_filter_with_audit_structs(self):
        """filter_to_ip should unwrap audit structs correctly."""
        evaluator = MeasureEvaluator(conn=None)
        df = pd.DataFrame({
            "patient_id": ["P1", "P2", "P3"],
            "initial_population": [
                {"result": True, "evidence": []},
                {"result": False, "evidence": []},
                {"result": True, "evidence": [{"type": "Encounter"}]},
            ],
        })
        filtered = evaluator._filter_to_initial_population(df, AuditMode.FULL)
        assert len(filtered) == 2
        assert list(filtered["patient_id"]) == ["P1", "P3"]

    def test_filter_with_population_audit_structs(self):
        """filter_to_ip should work with population-only audit structs."""
        evaluator = MeasureEvaluator(conn=None)
        df = pd.DataFrame({
            "patient_id": ["P1", "P2"],
            "initial_population": [
                {"result": True, "evidence": []},
                {"result": False, "evidence": []},
            ],
        })
        filtered = evaluator._filter_to_initial_population(df, AuditMode.POPULATION)
        assert len(filtered) == 1
        assert filtered["patient_id"].iloc[0] == "P1"

    def test_filter_noop_when_no_ip_column(self):
        """filter_to_ip should be a no-op when there's no initial_population column."""
        evaluator = MeasureEvaluator(conn=None)
        df = pd.DataFrame({
            "patient_id": ["P1", "P2"],
            "denominator": [True, False],
        })
        filtered = evaluator._filter_to_initial_population(df, AuditMode.NONE)
        assert len(filtered) == 2  # unchanged

    def test_filter_resets_index(self):
        """Filtered DataFrame should have a reset index."""
        evaluator = MeasureEvaluator(conn=None)
        df = pd.DataFrame({
            "patient_id": ["P1", "P2", "P3"],
            "initial_population": [False, True, True],
        })
        filtered = evaluator._filter_to_initial_population(df, AuditMode.NONE)
        assert list(filtered.index) == [0, 1]  # reset, not [1, 2]
