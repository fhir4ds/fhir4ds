"""FHIR4-110 — the content digest's referees, through the real pipeline.

The digest is insurance, not a fix for a demonstrated defect, so its own referees are the
point (FHIR4-110):

- a deliberately injected difference (ONE constant changed) MUST be caught in one run;
- two clean runs of the same tree MUST produce identical normalised digests on 5 consecutive
  attempts.

The first referee goes through the translator and the engine on a three-patient dataset and
needs no content package. The second runs the conformance CLI itself, twice per attempt, each
time in a fresh process, and is skipped only when the content suite is not checked out.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fhir4ds.dqm.tests.conformance import content_digest as cd
from fhir4ds.dqm.tests.conformance import repeat_compare as rc

REPO_ROOT = Path(__file__).resolve().parents[4]

COLUMNS = {
    "Initial Population": "Initial Population",
    "Observation Count": "Observation Count",
    "Two Or More": "Two Or More",
}

# The injected constant is ``__N__``: the threshold one define compares a count against.
LIBRARY = """library DigestReferee version '1.0'
using FHIR version '4.0.1'
context Patient
define "Observations": [Observation]
define "Observation Count": Count("Observations")
define "Two Or More": "Observation Count" >= __N__
define "Initial Population": Patient.active
"""

_PATIENT = '{"resourceType":"Patient","id":"%s","active":true}'
_OBSERVATION = (
    '{"resourceType":"Observation","id":"o%d","status":"final",'
    '"subject":{"reference":"Patient/%s"}}'
)
# p1 has two observations, p2 three, p3 none: a threshold of 2 and of 3 differ on p1 alone.
DATA = [("p1", 2), ("p2", 3), ("p3", 0)]


def _evaluate(threshold: int) -> list[dict]:
    """Translate and execute the library, and return rows as the conformance runner does."""
    import fhir4ds
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    con = fhir4ds.create_connection()
    try:
        con.execute(
            "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, "
            "patient_ref VARCHAR)"
        )
        for patient, count in DATA:
            con.execute(
                "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                [patient, "Patient", _PATIENT % patient, patient],
            )
            for index in range(count):
                con.execute(
                    "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                    [f"o{index}", "Observation", _OBSERVATION % (index, patient), patient],
                )
        library = parse_cql(LIBRARY.replace("__N__", str(threshold)))
        translator = CQLToSQLTranslator(connection=con, library_loader=lambda *args: None)
        translator.translate_library(library)
        sql = translator.translate_library_to_population_sql(library=library, output_columns=COLUMNS)
        return con.execute(sql).df().to_dict("records")
    finally:
        con.close()


def _tiers(rows: list[dict]) -> list[bool | None]:
    return [row["Two Or More"] for row in sorted(rows, key=lambda row: row["patient_id"])]


def test_an_injected_constant_is_caught_in_one_run():
    """One constant, one cell: the digest moves, names the column, and the cell is p1."""
    two, three = _evaluate(2), _evaluate(3)

    # The referee is real, not vacuous: the constant really changes one patient's answer.
    assert _tiers(two) == [True, True, False]
    assert _tiers(three) == [False, True, False]

    before, after = cd.measure_content(two), cd.measure_content(three)
    assert cd.classify(before, after) == "content"
    report = cd.compare_records({"DigestReferee": before}, {"DigestReferee": after})
    assert report["measures"]["DigestReferee"]["moved_columns"] == ["Two Or More"]

    # The same cells through the comparator the repeat-compare helper uses.
    first, second = cd.text_rows(two), cd.text_rows(three)
    from fhir4ds.operations.tests.wasm_parity import tier_c

    diffs, same_patients = tier_c.compare(first["columns"], first["rows"], second["rows"])
    assert same_patients
    assert diffs == {
        "Two Or More": {
            "kind": "boolean",
            "diff_cells": 1,
            "desktop_true": 2,
            "wasm_true": 1,
            "example": ["p1", "true", "false"],
        }
    }


def test_one_tree_answers_the_same_twice_in_a_row():
    """No constant changed: the two evaluations share both digests (values, not counts)."""
    first, second = _evaluate(2), _evaluate(2)
    assert cd.classify(cd.measure_content(first), cd.measure_content(second)) == "same"


@pytest.mark.slow
def test_five_clean_run_pairs_of_one_real_measure_agree(capsys: pytest.CaptureFixture):
    """The conformance CLI itself, twice per attempt, five attempts, fresh process each time."""
    from fhir4ds.dqm.tests.conformance.cli import _discover_measures

    try:
        discovered = {measure.id for measure in _discover_measures(suite="qi-core-2025")}
    except Exception as error:  # environment: the content suite is not checked out
        pytest.skip(f"qi-core-2025 content is not checked out ({type(error).__name__})")
    if "CMS68" not in discovered:
        pytest.skip("qi-core-2025 content is not checked out")

    status = rc.main(
        ["--suite", "qi-core-2025", "--measures", "CMS68", "--runs", "2", "--attempts", "5",
         "--tree", str(REPO_ROOT)]
    )
    out = capsys.readouterr().out
    assert status == 0, out
    assert out.count("CMS68: same") == 5
    assert "repeat-compare: 0 of 5 measure pair(s) moved" in out
    # Five pairs, and every pair printed one normalised digest for each of its two runs.
    assert out.count("normalised digest: run 1 ") == 5
