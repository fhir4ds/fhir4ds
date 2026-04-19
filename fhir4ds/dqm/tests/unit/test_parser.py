"""Tests for MeasureParser."""

import json
import logging
import pytest
from pathlib import Path

from fhir4ds.dqm.parser import MeasureParser
from fhir4ds.dqm.errors import MeasureParseError


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TESTS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "tests"
DQM_2026_MEASURES = TESTS_DIR / "data" / "dqm-content-qicore-2026" / "input" / "resources" / "measure"
ECQ_2025_BUNDLES = TESTS_DIR / "data" / "ecqm-content-qicore-2025" / "bundles" / "mat"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


class TestMeasureParserBasic:
    """Basic parsing tests."""

    def test_parse_no_group_raises(self):
        with pytest.raises(MeasureParseError, match="no group element"):
            MeasureParser().parse({"resourceType": "Measure", "id": "empty"})

    def test_parse_no_measure_in_bundle_raises(self):
        bundle = {
            "resourceType": "Bundle",
            "entry": [{"resource": {"resourceType": "Library", "id": "lib-1"}}],
        }
        with pytest.raises(MeasureParseError, match="No Measure resource found"):
            MeasureParser().parse(bundle)

    def test_parse_minimal_measure(self):
        measure = {
            "resourceType": "Measure",
            "id": "test-measure",
            "library": ["http://example.com/Library/TestLib"],
            "group": [
                {
                    "population": [
                        {
                            "code": {
                                "coding": [
                                    {
                                        "system": "http://terminology.hl7.org/CodeSystem/measure-population",
                                        "code": "initial-population",
                                    }
                                ]
                            },
                            "criteria": {"language": "text/cql-identifier", "expression": "Initial Population"},
                        }
                    ]
                }
            ],
        }
        pop_map = MeasureParser().parse(measure)
        assert pop_map.measure_id == "test-measure"
        assert pop_map.cql_library_ref == "http://example.com/Library/TestLib"
        assert len(pop_map.groups) == 1
        assert len(pop_map.groups[0].populations) == 1
        assert pop_map.groups[0].populations[0].cql_expression == "Initial Population"
        assert pop_map.groups[0].populations[0].population_code == "initial-population"

    def test_parse_multi_group_measure(self):
        measure = {
            "resourceType": "Measure",
            "id": "multi-group",
            "library": ["http://example.com/Library/TestLib"],
            "group": [
                {
                    "id": "group-1",
                    "population": [
                        {
                            "code": {"coding": [{"code": "initial-population"}]},
                            "criteria": {"expression": "IP Group 1"},
                        }
                    ],
                },
                {
                    "id": "group-2",
                    "population": [
                        {
                            "code": {"coding": [{"code": "initial-population"}]},
                            "criteria": {"expression": "IP Group 2"},
                        }
                    ],
                },
            ],
        }
        pop_map = MeasureParser().parse(measure)
        assert len(pop_map.groups) == 2
        assert pop_map.groups[0].group_id == "group-1"
        assert pop_map.groups[1].group_id == "group-2"
        assert pop_map.groups[0].populations[0].cql_expression == "IP Group 1"
        assert pop_map.groups[1].populations[0].cql_expression == "IP Group 2"

    def test_population_basis_default_boolean(self):
        measure = {
            "resourceType": "Measure",
            "id": "test",
            "group": [
                {
                    "population": [
                        {
                            "code": {"coding": [{"code": "initial-population"}]},
                            "criteria": {"expression": "IP"},
                        }
                    ]
                }
            ],
        }
        pop_map = MeasureParser().parse(measure)
        assert pop_map.groups[0].population_basis == "boolean"

    def test_population_basis_encounter(self):
        measure = {
            "resourceType": "Measure",
            "id": "test",
            "group": [
                {
                    "extension": [
                        {
                            "url": "http://hl7.org/fhir/us/cqfmeasures/StructureDefinition/cqfm-populationBasis",
                            "valueCode": "Encounter",
                        }
                    ],
                    "population": [
                        {
                            "code": {"coding": [{"code": "initial-population"}]},
                            "criteria": {"expression": "IP"},
                        }
                    ],
                }
            ],
        }
        pop_map = MeasureParser().parse(measure)
        assert pop_map.groups[0].population_basis == "Encounter"

    def test_unknown_population_code_ignored(self):
        measure = {
            "resourceType": "Measure",
            "id": "test",
            "group": [
                {
                    "population": [
                        {
                            "code": {"coding": [{"code": "unknown-code"}]},
                            "criteria": {"expression": "Whatever"},
                        },
                        {
                            "code": {"coding": [{"code": "initial-population"}]},
                            "criteria": {"expression": "IP"},
                        },
                    ]
                }
            ],
        }
        pop_map = MeasureParser().parse(measure)
        assert len(pop_map.groups[0].populations) == 1
        assert pop_map.groups[0].populations[0].population_code == "initial-population"


@pytest.mark.skipif(
    not DQM_2026_MEASURES.exists(),
    reason="Benchmarking fixtures not available",
)
class TestMeasureParserSupportingEvidence:
    """Tests against real SupportingEvidenceExample measure."""

    def test_parse_supporting_evidence_example(self):
        measure = _load_json(DQM_2026_MEASURES / "Measure-SupportingEvidenceExample.json")
        pop_map = MeasureParser().parse(measure)
        assert pop_map.measure_id == "SupportingEvidenceExample"
        assert len(pop_map.groups) == 1

        group = pop_map.groups[0]
        denom = next(
            p for p in group.populations if p.population_code == "denominator"
        )
        assert len(denom.supporting_evidence) == 19

    def test_parse_supporting_evidence_names(self):
        measure = _load_json(DQM_2026_MEASURES / "Measure-SupportingEvidenceExample.json")
        pop_map = MeasureParser().parse(measure)
        group = pop_map.groups[0]
        denom = next(p for p in group.populations if p.population_code == "denominator")
        # Evidence should have non-empty names and expressions
        for ev in denom.supporting_evidence:
            assert ev.cql_expression, f"Empty cql_expression for evidence '{ev.name}'"


@pytest.mark.skipif(
    not ECQ_2025_BUNDLES.exists(),
    reason="Benchmarking fixtures not available",
)
class TestMeasureParserCMS0334:
    """Tests against real CMS0334 bundle (older measure, no evidence extensions)."""

    def test_parse_bundle_extracts_measure(self):
        bundle = _load_json(
            ECQ_2025_BUNDLES / "CMS0334FHIR-R2-MeasureExport" / "CMS0334FHIR-v0.6.000-FHIR.json"
        )
        pop_map = MeasureParser().parse(bundle)
        assert pop_map.measure_id == "CMS0334FHIRPCCesareanBirth"

    def test_parse_older_measure_no_evidence(self):
        bundle = _load_json(
            ECQ_2025_BUNDLES / "CMS0334FHIR-R2-MeasureExport" / "CMS0334FHIR-v0.6.000-FHIR.json"
        )
        pop_map = MeasureParser().parse(bundle)
        numer = next(
            p for p in pop_map.groups[0].populations if p.population_code == "numerator"
        )
        assert numer.supporting_evidence == []

    def test_cms0334_populations(self):
        bundle = _load_json(
            ECQ_2025_BUNDLES / "CMS0334FHIR-R2-MeasureExport" / "CMS0334FHIR-v0.6.000-FHIR.json"
        )
        pop_map = MeasureParser().parse(bundle)
        codes = {p.population_code for p in pop_map.groups[0].populations}
        assert "initial-population" in codes
        assert "denominator" in codes
        assert "numerator" in codes


class TestMeasureParserWarnings:
    """Tests for parser logging and edge cases."""

    def test_no_library_ref_returns_none_and_warns(self, caplog):
        """_extract_cql_library_ref returns None and logs when no library found."""
        measure = {
            "resourceType": "Measure",
            "id": "no-lib",
            "group": [
                {
                    "population": [
                        {
                            "code": {"coding": [{"code": "initial-population"}]},
                            "criteria": {"expression": "IP"},
                        }
                    ]
                }
            ],
        }
        with caplog.at_level(logging.WARNING, logger="dqm_py.parser"):
            pop_map = MeasureParser().parse(measure)
        assert pop_map.cql_library_ref is None
        assert any("no cql library reference" in r.getMessage().lower() for r in caplog.records)

    def test_empty_expression_dropped_with_warning(self, caplog):
        """Populations with empty CQL expressions are dropped with a warning."""
        measure = {
            "resourceType": "Measure",
            "id": "empty-expr",
            "group": [
                {
                    "population": [
                        {
                            "code": {"coding": [{"code": "initial-population"}]},
                            "criteria": {"expression": ""},
                        },
                        {
                            "code": {"coding": [{"code": "denominator"}]},
                            "criteria": {"expression": "Denom"},
                        },
                    ]
                }
            ],
        }
        with caplog.at_level(logging.WARNING, logger="dqm_py.parser"):
            pop_map = MeasureParser().parse(measure)
        assert len(pop_map.groups[0].populations) == 1
        assert pop_map.groups[0].populations[0].population_code == "denominator"
        assert any("dropping population" in r.message.lower() for r in caplog.records)

    def test_population_basis_requires_full_url(self):
        """_extract_population_basis should match the full canonical URL, not just suffix."""
        measure = {
            "resourceType": "Measure",
            "id": "test-basis",
            "group": [
                {
                    "extension": [
                        {
                            "url": "http://example.com/custom/populationBasis",
                            "valueCode": "Encounter",
                        }
                    ],
                    "population": [
                        {
                            "code": {"coding": [{"code": "initial-population"}]},
                            "criteria": {"expression": "IP"},
                        }
                    ],
                }
            ],
        }
        pop_map = MeasureParser().parse(measure)
        # Should default to "boolean" since the URL is not the canonical one
        assert pop_map.groups[0].population_basis == "boolean"
