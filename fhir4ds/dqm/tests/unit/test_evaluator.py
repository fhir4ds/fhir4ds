"""Tests for MeasureEvaluator."""

import json

import numpy as np
import pandas as pd
import pytest

from fhir4ds.dqm.evaluator import MeasureEvaluator
from fhir4ds.dqm.models import MeasureResult
from fhir4ds.dqm.types import (
    AuditMode,
    AuditPersona,
    GroupMap,
    PopulationEntry,
    PopulationMap,
    StratifierComponent,
    StratifierEntry,
    SupportingEvidenceDef,
)


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


def _make_stratified_measure_result():
    """Helper to build a MeasureResult with simple and composite stratifiers."""
    pop_map = PopulationMap(
        measure_id="payer-measure",
        cql_library_ref="http://example.com/Library/Payer",
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
                stratifiers=[
                    StratifierEntry(
                        stratifier_id="payer",
                        code_text="Payer Reporting Line",
                        cql_expression="Payer Reporting Line",
                    ),
                    StratifierEntry(
                        stratifier_id="payer-components",
                        code_text="Payer Components",
                        components=[
                            StratifierComponent(
                                component_id="plan",
                                code_text="Plan",
                                cql_expression="Plan Type",
                            ),
                            StratifierComponent(
                                component_id="line",
                                code_text="Line",
                                cql_expression="Reporting Line",
                            ),
                        ],
                    ),
                ],
            )
        ],
    )
    df = pd.DataFrame(
        {
            "patient_id": ["P1", "P2", "P3"],
            "initial_population": [True, True, True],
            "denominator": [True, True, True],
            "numerator": [True, False, True],
            "stratifier_1": ["Medicare", "Medicaid", "Medicare"],
            "stratifier_2_component_1": ["SNP", "Standard", "SNP"],
            "stratifier_2_component_2": ["Medicare", "Medicaid", "Medicare"],
        }
    )
    return MeasureResult(
        dataframe=df,
        populations={
            "initial_population": "Initial Population",
            "denominator": "Denominator",
            "numerator": "Numerator",
        },
        parameters={"Measurement Period": ("2026-01-01", "2026-12-31")},
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

    def test_summary_report_handles_array_population_values(self):
        """Collection-valued population cells should not raise truth-value errors."""
        df = pd.DataFrame(
            {
                "patient_id": ["P1", "P2"],
                "initial_population": [np.array([]), np.array(["enc-1"])],
                "denominator": [[], ["enc-1"]],
                "numerator": [[], ["enc-1"]],
            }
        )
        evaluator = MeasureEvaluator(conn=None)

        summary = evaluator.summary_report(df)

        assert summary["initial_population"] == 1
        assert summary["denominator"] == 1
        assert summary["numerator"] == 1
        assert summary["total_patients"] == 2

    def test_summary_report_applies_denominator_exclusion_before_numerator(self):
        """Excluded denominator patients must not contribute to numerator rate."""
        df = pd.DataFrame(
            {
                "patient_id": ["P_excluded_numer", "P_denominator_only"],
                "initial_population": [True, True],
                "denominator": [True, True],
                "denominator_exclusion": [True, False],
                "denominator_exception": [False, False],
                "numerator": [True, False],
                "numerator_exclusion": [False, False],
            }
        )
        evaluator = MeasureEvaluator(conn=None)
        summary = evaluator.summary_report(df)
        assert summary["denominator"] == 2
        assert summary["denominator_exclusion"] == 1
        assert summary["denominator_final"] == 1
        assert summary["numerator"] == 0
        assert summary["numerator_final"] == 0
        assert summary["performance_rate"] == 0.0

    def test_summary_report_applies_denominator_exception_only_when_not_numerator(self):
        """Denominator exceptions do not remove patients that satisfy numerator."""
        df = pd.DataFrame(
            {
                "patient_id": ["P_exception_numer", "P_denominator_only"],
                "initial_population": [True, True],
                "denominator": [True, True],
                "denominator_exclusion": [False, False],
                "denominator_exception": [True, False],
                "numerator": [True, False],
                "numerator_exclusion": [False, False],
            }
        )
        evaluator = MeasureEvaluator(conn=None)
        summary = evaluator.summary_report(df)
        assert summary["denominator"] == 2
        assert summary["denominator_exception"] == 0
        assert summary["denominator_final"] == 2
        assert summary["numerator"] == 1
        assert summary["numerator_final"] == 1
        assert summary["performance_rate"] == 0.5

    def test_summary_report_counts_measure_stratifiers(self):
        """MeasureResult summaries should include population counts by stratum."""
        evaluator = MeasureEvaluator(conn=None)
        summary = evaluator.summary_report(_make_stratified_measure_result())

        payer_strata = {
            stratum["text"]: stratum["population"]
            for stratum in summary["stratifiers"][0]["strata"]
        }

        assert payer_strata["Medicare"]["initial-population"] == 2
        assert payer_strata["Medicare"]["denominator"] == 2
        assert payer_strata["Medicare"]["numerator"] == 2
        assert payer_strata["Medicaid"]["initial-population"] == 1
        assert payer_strata["Medicaid"]["numerator"] == 0
        assert sum(
            counts["initial-population"] for counts in payer_strata.values()
        ) == summary["initial_population"]

        component_strata = summary["stratifiers"][1]["strata"]
        assert component_strata[0]["components"][0]["text"] == "SNP"
        assert component_strata[0]["components"][1]["text"] == "Medicare"
        assert component_strata[0]["population"]["initial-population"] == 2

    def test_prune_population_evidence_preserves_inclusion_evidence(self):
        """Evaluator pruning must pass the population column context to AuditEngine."""
        df = pd.DataFrame(
            {
                "initial_population": [
                    {
                        "result": True,
                        "evidence": [
                            {
                                "target": "Encounter/e1",
                                "operator": "exists",
                                "trace": ["Initial Population"],
                            }
                        ],
                    }
                ]
            }
        )
        evaluator = MeasureEvaluator(conn=None)

        pruned = evaluator._prune_population_evidence(df, _make_pop_map())
        evidence = pruned["initial_population"].iloc[0]["evidence"]

        assert evidence
        assert evidence[0]["operator"] == "exists"
        assert evidence[0]["findings"][0]["target"] == "Encounter/e1"

    def test_prune_population_evidence_applies_exclusion_persona(self):
        """Excluded rows keep exclusion evidence; non-excluded rows prune it."""
        pop_map = PopulationMap(
            measure_id="test-measure",
            cql_library_ref="http://example.com/Library/Test",
            groups=[
                GroupMap(
                    group_id="group-0",
                    population_basis="boolean",
                    populations=[
                        PopulationEntry(
                            population_code="denominator-exclusion",
                            group_id="group-0",
                            cql_expression="Denominator Exclusion",
                            audit_persona=AuditPersona.EXCLUSION,
                        ),
                    ],
                )
            ],
        )
        df = pd.DataFrame(
            {
                "denominator_exclusion": [
                    {"result": False, "evidence": [{"target": "Condition/no"}]},
                    {"result": True, "evidence": [{"target": "Condition/yes"}]},
                ]
            }
        )
        evaluator = MeasureEvaluator(conn=None)

        pruned = evaluator._prune_population_evidence(df, pop_map)

        assert pruned["denominator_exclusion"].iloc[0]["evidence"] == []
        kept = pruned["denominator_exclusion"].iloc[1]["evidence"]
        assert kept[0]["findings"][0]["target"] == "Condition/yes"


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

    def test_to_measure_report_preserves_authored_group_id(self):
        """MeasureReport group should link back to authored Measure.group.id."""
        evaluator = MeasureEvaluator(conn=None)
        mr = _make_measure_result()
        mr.pop_map.groups[0].source_group_id = "primary"

        report = evaluator.to_measure_report(
            mr, period_start="2024-01-01", period_end="2024-12-31"
        )

        assert report["group"][0]["id"] == "primary"

    def test_individual_measure_report_includes_supporting_evidence(self):
        """Individual MeasureReport should serialize authored supporting evidence."""
        evaluator = MeasureEvaluator(conn=None)
        mr = _make_measure_result()
        pop = mr.pop_map.groups[0].populations[1]
        pop.source_population_id = "denominator"
        pop.supporting_evidence = [
            SupportingEvidenceDef(
                name="QualifyingEncounter",
                cql_expression="Qualifying Encounter",
                description="The encounter that qualified the patient.",
                code={
                    "coding": [
                        {
                            "system": "http://example.org/evidence",
                            "code": "qualifying-encounter",
                        }
                    ]
                },
            )
        ]
        mr.dataframe = pd.DataFrame(
            {
                "patient_id": ["P1"],
                "initial_population": [True],
                "denominator": [True],
                "numerator": [False],
                "evidence_QualifyingEncounter": [
                    {"resourceType": "Encounter", "id": "enc-1"}
                ],
            }
        )

        report = evaluator.to_measure_report(
            mr,
            period_start="2024-01-01",
            period_end="2024-12-31",
            report_type="individual",
        )

        assert report["subject"]["reference"] == "Patient/P1"
        assert report["meta"]["profile"] == [
            "http://hl7.org/fhir/us/davinci-deqm/StructureDefinition/indv-measurereport-deqm"
        ]
        denominator = next(
            population
            for population in report["group"][0]["population"]
            if population["code"]["coding"][0]["code"] == "denominator"
        )
        support = next(
            ext
            for ext in denominator["extension"]
            if ext["url"] == "http://hl7.org/fhir/StructureDefinition/cqf-supportingEvidence"
        )
        assert {"url": "name", "valueCode": "QualifyingEncounter"} in support["extension"]
        assert {
            "url": "value",
            "valueReference": {"reference": "Encounter/enc-1"},
        } in support["extension"]

    def test_individual_measure_report_unwraps_audit_supporting_evidence(self):
        """Supporting evidence should not serialize internal audit trace fields."""
        evaluator = MeasureEvaluator(conn=None)
        mr = _make_measure_result()
        pop = mr.pop_map.groups[0].populations[1]
        pop.supporting_evidence = [
            SupportingEvidenceDef(
                name="HasBirthDate",
                cql_expression="Has Birth Date",
            )
        ]
        mr.dataframe = pd.DataFrame(
            {
                "patient_id": ["P1"],
                "initial_population": [True],
                "denominator": [True],
                "numerator": [False],
                "evidence_HasBirthDate": [
                    {
                        "result": True,
                        "evidence": [
                            {
                                "target": "Patient/P1",
                                "attribute": "birthDate",
                                "trace": ["Has Birth Date"],
                            }
                        ],
                    }
                ],
            }
        )

        report = evaluator.to_measure_report(
            mr,
            period_start="2024-01-01",
            period_end="2024-12-31",
            report_type="individual",
        )

        denominator = next(
            population
            for population in report["group"][0]["population"]
            if population["code"]["coding"][0]["code"] == "denominator"
        )
        support = next(
            ext
            for ext in denominator["extension"]
            if ext["url"] == "http://hl7.org/fhir/StructureDefinition/cqf-supportingEvidence"
        )
        assert {"url": "value", "valueBoolean": True} in support["extension"]
        assert "trace" not in json.dumps(support)

    def test_individual_measure_report_requires_one_patient(self):
        """Individual MeasureReport should not silently summarize multiple patients."""
        evaluator = MeasureEvaluator(conn=None)
        mr = _make_measure_result()

        from fhir4ds.dqm.errors import DQMError
        with pytest.raises(DQMError, match="exactly one patient"):
            evaluator.to_measure_report(
                mr,
                period_start="2024-01-01",
                period_end="2024-12-31",
                report_type="individual",
            )

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

    def test_to_measure_report_includes_stratifiers(self):
        """MeasureReport output should carry configured stratifier strata."""
        evaluator = MeasureEvaluator(conn=None)
        report = evaluator.to_measure_report(_make_stratified_measure_result())

        stratifiers = report["group"][0]["stratifier"]
        payer_stratifier = stratifiers[0]
        assert payer_stratifier["id"] == "payer"
        assert payer_stratifier["code"]["text"] == "Payer Reporting Line"

        medicare = next(
            stratum
            for stratum in payer_stratifier["stratum"]
            if stratum["value"]["text"] == "Medicare"
        )
        medicare_counts = {
            pop["code"]["coding"][0]["code"]: pop["count"]
            for pop in medicare["population"]
        }
        assert medicare_counts["initial-population"] == 2
        assert medicare_counts["numerator"] == 2

        component = stratifiers[1]["stratum"][0]["component"]
        assert component[0]["value"]["text"] == "SNP"
        assert component[1]["value"]["text"] == "Medicare"


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
