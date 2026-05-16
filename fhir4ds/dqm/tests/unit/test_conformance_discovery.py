import json

from fhir4ds.dqm.tests.conformance.cli import (
    _extract_population_definitions,
    _extract_population_definitions_from_report,
)


def test_extract_population_definitions_from_multigroup_report() -> None:
    report = {
        "group": [
            {
                "population": [
                    {"code": {"coding": [{"code": "numerator"}]}},
                    {"code": {"coding": [{"code": "initial-population"}]}},
                    {"code": {"coding": [{"code": "denominator"}]}},
                ],
            },
            {
                "population": [
                    {"code": {"coding": [{"code": "denominator-exclusion"}]}},
                    {"code": {"coding": [{"code": "initial-population"}]}},
                    {"code": {"coding": [{"code": "denominator"}]}},
                ],
            },
        ],
    }

    assert _extract_population_definitions_from_report(report) == [
        "Initial Population 1",
        "Denominator 1",
        "Numerator 1",
        "Initial Population 2",
        "Denominator 2",
        "Denominator Exclusion 2",
    ]


def test_extract_population_definitions_uses_first_valid_report(tmp_path) -> None:
    first_case = tmp_path / "case-a"
    second_case = tmp_path / "case-b"
    first_case.mkdir()
    second_case.mkdir()

    first_report = {
        "group": [
            {
                "population": [
                    {"code": {"coding": [{"code": "initial-population"}]}},
                    {"code": {"coding": [{"code": "denominator"}]}},
                    {"code": {"coding": [{"code": "numerator"}]}},
                ],
            },
        ],
    }
    second_report = {
        "group": [
            {
                "population": [
                    {"code": {"coding": [{"code": "denominator-exception"}]}},
                ],
            },
        ],
    }
    (first_case / "MeasureReport-first.json").write_text(json.dumps(first_report))
    (second_case / "MeasureReport-second.json").write_text(json.dumps(second_report))

    assert _extract_population_definitions(tmp_path) == [
        "Initial Population",
        "Denominator",
        "Numerator",
    ]
