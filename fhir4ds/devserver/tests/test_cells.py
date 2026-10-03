"""Unit tests for the v2 cells layer: split, refs, closure, sessions."""

from __future__ import annotations

import pytest

from fhir4ds.devserver.cells import (
    CellSession,
    dependency_closure,
    refs_of,
    split_cells,
)

TEXT = """library Demo version '1.0.0'
using FHIR version '4.0.1'

context Patient

define Unmarked: Patient.gender

// # %% [name: AgeYears]
define AgeYears: Patient.birthDate

// # %% [name: Male]
define Male: Patient.gender = 'male'

// # %%
define MaleSeniors: Male and AgeYears < '1940-01-01'
"""


def test_split_basic():
    parsed = split_cells(TEXT)
    assert parsed.error is None
    assert [c.name for c in parsed.cells] == ["AgeYears", "Male", "MaleSeniors"]
    assert "Unmarked" in parsed.header
    assert "context Patient" in parsed.header
    assert all(not c.is_function for c in parsed.cells)


def test_split_function_cell():
    text = TEXT + "\n// # %%\ndefine function Twice(x Integer): x * 2\n"
    parsed = split_cells(text)
    assert parsed.error is None
    fn = [c for c in parsed.cells if c.is_function]
    assert len(fn) == 1 and fn[0].name == "Twice"


def test_split_duplicate_names_error():
    text = TEXT + "\n// # %%\ndefine Male: Patient.gender = 'other'\n"
    parsed = split_cells(text)
    assert parsed.error is not None and "duplicate" in parsed.error


def test_split_marker_label_mismatch_error():
    text = (
        "library D version '1.0.0'\n// # %% [name: Wrong]\ndefine Right: 1\n"
    )
    parsed = split_cells(text)
    assert parsed.error is not None and "does not match" in parsed.error


def test_split_non_define_cell_error():
    text = "library D version '1.0.0'\n// # %%\nlet x: 1\n"
    parsed = split_cells(text)
    assert parsed.error is not None and "define" in parsed.error


def test_refs_and_closure():
    refs = refs_of(TEXT)
    # Context identifier (Patient) is filtered from refs.
    assert "Patient" not in refs["Male"]
    assert set(refs["MaleSeniors"]) == {"Male", "AgeYears"}
    closure = dependency_closure(
        "MaleSeniors", refs, {"AgeYears", "Male", "MaleSeniors"}
    )
    assert set(closure) == {"AgeYears", "Male", "MaleSeniors"}
    assert closure[-1] == "MaleSeniors"  # target last (post-order)


def test_session_plan_modes():
    s = CellSession("Demo")
    s.sync(TEXT)
    assert s.plan("MaleSeniors", "cell") == ["MaleSeniors"]
    assert set(s.plan("MaleSeniors", "cell_deps")) == {
        "AgeYears",
        "Male",
        "MaleSeniors",
    }
    assert s.plan("MaleSeniors", "all") == ["AgeYears", "Male", "MaleSeniors"]
    assert s.plan("MaleSeniors", "to_here") == ["AgeYears", "Male", "MaleSeniors"]
    assert s.plan("Male", "to_here") == ["AgeYears", "Male"]
    with pytest.raises(ValueError):
        s.plan("Male", "bogus-mode")
    with pytest.raises(KeyError):
        s.plan("Nope", "cell")


def test_session_compose_includes_header():
    s = CellSession("Demo")
    s.sync(TEXT)
    composed = s.compose(s.plan("Male", "cell"))
    assert "Unmarked" in composed  # header defines ride along
    assert "context Patient" in composed
    assert "define Male:" in composed
    assert "MaleSeniors" not in composed


def test_session_deleted_cell_retention_and_drop():
    """Review-note pin: deleted cells stay STALE until a dependent rerun
    FAILS against the missing define — that failing rerun drops them."""
    s = CellSession("Demo")
    s.sync(TEXT)
    # Give Male a result as if it had run.
    from fhir4ds.devserver.cells import CellRecord, OK

    s.set_result("Male", CellRecord(status=OK, result={"rows": []}))
    # Delete the Male cell from the buffer.
    text2 = TEXT.replace("// # %% [name: Male]\ndefine Male: Patient.gender = 'male'\n\n", "")
    s.sync(text2)
    assert "Male" not in s.cells
    rec = s.get_result("Male")
    assert rec is not None and rec.status == "stale"  # retained, stale
    # MaleSeniors now depends on a deleted cell -> marked stale on sync.
    assert s.get_result("MaleSeniors").status in ("idle", "stale")
    # After a resync that also removes MaleSeniors' record via a fresh
    # session (server restart analog), retention ends.
    s2 = CellSession("Demo")
    s2.sync(text2)
    assert s2.get_result("Male") is None


def test_session_stale_on_dep_change():
    from fhir4ds.devserver.cells import CellRecord, OK

    s = CellSession("Demo")
    s.sync(TEXT)
    s.set_result("MaleSeniors", CellRecord(status=OK, result={}))
    # Edit the Male cell text; MaleSeniors must go stale.
    edited = TEXT.replace(
        "define Male: Patient.gender = 'male'",
        "define Male: Patient.gender = 'MALE'",
    )
    s.sync(edited)
    assert s.get_result("MaleSeniors").status == "stale"


def test_session_kernel_restart_marks_stale():
    from fhir4ds.devserver.cells import CellRecord, OK

    s = CellSession("Demo")
    s.sync(TEXT)
    s.set_result("Male", CellRecord(status=OK, result={}))
    s.mark_stale_all()
    assert s.get_result("Male").status == "stale"
