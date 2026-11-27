import json

import pytest

from fhir4ds.dqm.tests.conformance.cli import (
    _discover_measures,
    _extract_population_definitions,
    _extract_population_definitions_from_report,
)
from fhir4ds.dqm.tests.conformance.config import SKIP_ON_FAILURE, get_suite_paths


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


def test_skip_on_failure_never_names_a_measure_the_suite_contains() -> None:
    """A ``SKIP_ON_FAILURE`` entry must not silently drop a measure that exists.

    The list is for measures known to hang or to be absent (``cli.py``). An entry that names a
    measure the suite DOES contain makes the gate run one measure fewer with nothing but a
    ``Skipping <id>`` line: that is how CMS139 stayed out of the US-Core gate as "Not in
    submodule" while passing 29/29, and the gate scored 73 of 74 measures. A measure that fails
    belongs in ``KNOWN_FAILURES`` with a reason; nothing that is present belongs here.
    """
    checked = []
    for suite in ("qi-core-2025", "us-core-2025"):
        if not get_suite_paths(suite)["tests_dir"].exists():
            continue  # fixture availability only: the content submodules are optional
        present = {measure.id.upper() for measure in _discover_measures(suite=suite)}
        assert present, f"{suite}: discovery found no measures"
        stale = sorted(name.upper() for name in SKIP_ON_FAILURE if name.upper() in present)
        assert not stale, (
            f"{suite}: SKIP_ON_FAILURE names measures the suite contains: {stale}. "
            "Remove the entry so the gate runs them, or record a failure in KNOWN_FAILURES."
        )
        checked.append(suite)
    if not checked:
        pytest.skip("no DQM content suite is checked out")
