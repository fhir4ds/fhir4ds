"""Tests for NarrativeGenerator and AuditEngine."""

import pytest

from fhir4ds.dqm.narrative import NarrativeGenerator
from fhir4ds.dqm.audit import AuditEngine
from fhir4ds.dqm.types import AuditPersona


class TestNarrativeGenerator:
    def test_empty_evidence(self):
        ng = NarrativeGenerator()
        result = ng.generate("numerator", [], is_satisfied=True)
        assert isinstance(result, list)
        assert any("no supporting evidence" in f for f in result)

    def test_numerator_failure_rich(self):
        ng = NarrativeGenerator()
        fragments = ng.generate(
            "numerator",
            [
                {
                    "attribute": "value.ofType(Quantity).value",
                    "operator": ">",
                    "threshold": "7.0",
                    "findings": [
                        {"target": "Observation/obs-789", "value": "9.2"}
                    ],
                }
            ],
            is_satisfied=False,
        )
        narrative = " ".join(fragments)
        assert "9.2" in narrative
        assert "7.0" in narrative
        assert "Observation/obs-789" in narrative
        assert "Failed" in narrative
        ng = NarrativeGenerator()
        fragments = ng.generate(
            "numerator",
            [
                {
                    "operator": "exists",
                    "findings": [{"target": "Observation/obs-1"}],
                }
            ],
            is_satisfied=True,
        )
        narrative = " ".join(fragments)
        assert "Met numerator" in narrative
        assert "Observation/obs-1" in narrative

    def test_denominator_exclusion(self):
        ng = NarrativeGenerator()
        fragments = ng.generate(
            "denominator-exclusion",
            [
                {
                    "operator": "exists",
                    "findings": [{"target": "Condition/cond-1"}],
                }
            ],
            is_satisfied=True,
        )
        narrative = " ".join(fragments)
        assert "Excluded" in narrative
        assert "Condition/cond-1" in narrative

    def test_truncation_grouped_findings(self):
        ng = NarrativeGenerator()
        evidence = [
            {
                "operator": "exists",
                "findings": [{"target": f"Enc/{i}"} for i in range(3)],
            }
        ]
        fragments = ng.generate("initial-population", evidence, is_satisfied=True)
        narrative = " ".join(fragments)
        assert "(+2 more)" in narrative

    def test_custom_templates(self):
        class CustomNarrative(NarrativeGenerator):
            TEMPLATES = {"numerator": "Custom"}

        ng = CustomNarrative()
        fragments = ng.generate(
            "numerator",
            [
                {
                    "operator": "exists",
                    "findings": [{"target": "Obs/1"}],
                }
            ],
            is_satisfied=True,
        )
        assert any("Custom" in f for f in fragments)

    def test_absent_evidence_formats_correctly(self):
        ng = NarrativeGenerator()
        fragments = ng.generate(
            "numerator",
            [
                {
                    "attribute": "Condition",
                    "operator": "absent",
                    "threshold": "Diabetes ValueSet",
                    "findings": [{"target": "Condition"}],
                }
            ],
            is_satisfied=False,
        )
        narrative = " ".join(fragments)
        assert "No Condition found for Diabetes ValueSet" in narrative
        assert "Failed" in narrative

    def test_trace_appended_to_fragment(self):
        ng = NarrativeGenerator()
        fragments = ng.generate(
            "numerator",
            [
                {
                    "operator": "exists",
                    "trace": ["Initial Population", "Denominator"],
                    "findings": [{"target": "Encounter/enc-1"}],
                }
            ],
            is_satisfied=True,
        )
        narrative = " ".join(fragments)
        assert "Trace: Initial Population > Denominator" in narrative
        assert "Encounter/enc-1" in narrative

    def test_empty_trace_no_suffix(self):
        ng = NarrativeGenerator()
        fragments = ng.generate(
            "numerator",
            [
                {
                    "operator": "exists",
                    "trace": [],
                    "findings": [{"target": "Obs/1"}],
                }
            ],
            is_satisfied=True,
        )
        narrative = " ".join(fragments)
        assert "Trace:" not in narrative

    def test_comparison_op_display(self):
        ng = NarrativeGenerator()
        fragments = ng.generate(
            "numerator",
            [
                {
                    "attribute": "value",
                    "operator": ">",
                    "threshold": "7.0",
                    "findings": [
                        {"target": "Observation/obs-1", "value": "9.2"}
                    ],
                }
            ],
            is_satisfied=False,
        )
        narrative = " ".join(fragments)
        assert "greater than" in narrative

    def test_exists_op_display(self):
        ng = NarrativeGenerator()
        fragments = ng.generate(
            "numerator",
            [
                {
                    "operator": "exists",
                    "findings": [{"target": "Obs/1"}],
                }
            ],
            is_satisfied=True,
        )
        narrative = " ".join(fragments)
        assert "found" in narrative

    def test_returns_list_of_fragments(self):
        ng = NarrativeGenerator()
        fragments = ng.generate(
            "numerator",
            [
                {
                    "operator": "exists",
                    "findings": [{"target": "Obs/1"}],
                },
                {
                    "attribute": "value",
                    "operator": "<",
                    "threshold": "10",
                    "findings": [{"target": "Obs/2", "value": "5"}],
                },
            ],
            is_satisfied=True,
        )
        assert isinstance(fragments, list)
        assert len(fragments) == 3  # header + 2 logic groups

    def test_failure_templates_for_all_populations(self):
        ng = NarrativeGenerator()
        for pop in [
            "initial-population",
            "denominator",
            "denominator-exclusion",
            "denominator-exception",
            "numerator",
            "numerator-exclusion",
        ]:
            fragments = ng.generate(pop, [], is_satisfied=False)
            assert isinstance(fragments, list)
            assert len(fragments) == 1
            assert "no supporting evidence" in fragments[0]
            # Header should NOT be "Evidence" (the fallback) for known populations
            assert not fragments[0].startswith("Evidence:")

    def test_empty_findings_no_finding_line(self):
        """Guard: empty findings list produces no finding detail."""
        ng = NarrativeGenerator()
        fragments = ng.generate(
            "numerator",
            [{"operator": "exists", "findings": []}],
            is_satisfied=True,
        )
        narrative = " ".join(fragments)
        assert "Finding:" not in narrative

    def test_empty_strings_in_trace_filtered(self):
        """Empty strings in trace should be filtered out."""
        ng = NarrativeGenerator()
        fragments = ng.generate(
            "numerator",
            [
                {
                    "operator": "exists",
                    "trace": ["", "IP", "", "Numerator"],
                    "findings": [{"target": "Obs/1"}],
                }
            ],
            is_satisfied=True,
        )
        narrative = " ".join(fragments)
        assert "Trace: IP > Numerator" in narrative
        assert "> >" not in narrative

    def test_absent_uses_resource_type_from_trace(self):
        """absent operator should extract resource type from trace when attribute is None."""
        ng = NarrativeGenerator()
        fragments = ng.generate(
            "numerator",
            [
                {
                    "operator": "absent",
                    "threshold": "Essential Hypertension",
                    "trace": ["Condition: Essential Hypertension", "Has HTN"],
                    "findings": [{"target": "Condition"}],
                }
            ],
            is_satisfied=False,
        )
        narrative = " ".join(fragments)
        assert "No Condition found for Essential Hypertension" in narrative

    def test_three_findings_summary(self):
        """Group with 3 findings → first sample + (+2 more)."""
        ng = NarrativeGenerator()
        fragments = ng.generate(
            "numerator",
            [
                {
                    "operator": "exists",
                    "trace": ["Condition: HTN", "Initial Population"],
                    "findings": [
                        {"target": "Condition/c1"},
                        {"target": "Condition/c2"},
                        {"target": "Condition/c3"},
                    ],
                }
            ],
            is_satisfied=True,
        )
        narrative = " ".join(fragments)
        assert "Condition/c1" in narrative
        assert "(+2 more)" in narrative
        assert "Trace: Condition: HTN > Initial Population" in narrative


class TestAuditEngine:
    def test_exclusion_evidence_empty_when_not_excluded(self):
        engine = AuditEngine()
        row = {"denominator_exclusion": {"result": False, "evidence": [{"target": "x"}]}}
        result = engine.prune_evidence(row, "denominator-exclusion", AuditPersona.EXCLUSION)
        assert result == []

    def test_exclusion_evidence_present_when_excluded(self):
        engine = AuditEngine()
        row = {"denominator_exclusion": {"result": True, "evidence": [{"target": "x"}]}}
        result = engine.prune_evidence(row, "denominator-exclusion", AuditPersona.EXCLUSION)
        assert len(result) == 1
        assert result[0]["target"] == "x"

    def test_inclusion_evidence_always_present(self):
        engine = AuditEngine()
        row = {"initial_population": {"result": True, "evidence": [{"target": "y"}]}}
        result = engine.prune_evidence(row, "initial-population", AuditPersona.INCLUSION)
        assert len(result) == 1

    def test_numerator_evidence_always_present(self):
        engine = AuditEngine()
        row = {"numerator": {"result": False, "evidence": [{"target": "z"}]}}
        result = engine.prune_evidence(row, "numerator", AuditPersona.NUMERATOR)
        assert len(result) == 1

    def test_empty_evidence_list(self):
        engine = AuditEngine()
        row = {"numerator": {"result": True, "evidence": []}}
        result = engine.prune_evidence(row, "numerator", AuditPersona.NUMERATOR)
        assert result == []
