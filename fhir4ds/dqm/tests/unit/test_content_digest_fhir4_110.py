"""FHIR4-110 — a long run must be able to tell that its output moved.

The digest is insurance, not a fix for a demonstrated defect, so its own referees are the
point: an injected difference MUST be caught in one run (a digest that always matches is
worthless), and two clean runs of the same tree must agree on 5 consecutive attempts.
"""

from __future__ import annotations

import copy
import decimal
import json
import random
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fhir4ds.dqm.tests.conformance import content_digest as cd
from fhir4ds.dqm.tests.conformance import repeat_compare as rc

COLUMNS = ["patient_id", "Initial Population", "Denominator", "Numerator", "Evidence"]


def _rows() -> list[dict]:
    """Three patients as the conformance runner hands them over (pandas scalars included)."""
    return [
        {
            "patient_id": "p1",
            "Initial Population": True,
            "Denominator": np.bool_(True),
            "Numerator": False,
            "Evidence": np.array(["Encounter/b", "Encounter/a"]),
        },
        {
            "patient_id": "p2",
            "Initial Population": True,
            "Denominator": None,
            "Numerator": None,
            "Evidence": np.array(["Encounter/c"]),
        },
        {
            "patient_id": "p3",
            "Initial Population": False,
            "Denominator": np.nan,
            "Numerator": None,
            "Evidence": np.array([]),
        },
    ]


def _write_run(directory: Path, rows: list[dict], *, cells: bool = False) -> Path:
    """Lay a run directory out the way the CLI does."""
    directory.mkdir(parents=True, exist_ok=True)
    cd.write_digest_file(directory / rc.DIGEST_FILE, {"CMSx": cd.measure_content(rows)}, suite="t")
    if cells:
        (directory / "results").mkdir(exist_ok=True)
        payload = cd.text_rows(rows)
        with open(directory / "results" / "CMSx.cells.json", "w") as f:
            f.write(json.dumps({"columns": payload["columns"]}) + "\n")
            for row in payload["rows"]:
                f.write(json.dumps(row) + "\n")
    return directory


def _shuffled(rows: list[dict], seed: int) -> list[dict]:
    """The same patients in another row, column and list order."""
    out = copy.deepcopy(rows)
    rng = random.Random(seed)
    rng.shuffle(out)
    for row in out:
        items = list(row.items())
        rng.shuffle(items)
        row.clear()
        row.update(items)
        if len(row["Evidence"]):
            row["Evidence"] = np.array(sorted(row["Evidence"], reverse=True))
    return out


# --------------------------------------------------------------------------- the cells themselves

def test_canonical_keeps_types_apart_and_reads_pandas_nulls():
    assert cd.canonical(None) is None
    assert cd.canonical(np.nan) is None
    assert cd.canonical(pd.NaT) is None
    assert cd.canonical(pd.NA) is None
    assert cd.canonical(np.bool_(True)) is True
    assert cd.canonical(np.int64(3)) == 3
    assert cd.canonical(decimal.Decimal("1.50")) == {"__decimal__": "1.50"}
    assert cd.canonical(pd.Timestamp("2026-01-01")) == {"__datetime__": "2026-01-01T00:00:00"}
    assert cd.canonical(datetime(2026, 1, 1)) == {"__datetime__": "2026-01-01T00:00:00"}
    assert cd.canonical({"b": [2, 1], "a": 1}) == {"a": 1, "b": [2, 1]}
    assert cd.canonical(np.array(["only"])) == ["only"], "a one-element array is a list"
    assert cd.canonical(np.array(7)) == 7
    # A Decimal is not a float and a float is not an int: 1, 1.0 and Decimal("1.0") differ.
    assert len({cd.cell_texts(v)[0] for v in (1, 1.0, decimal.Decimal("1.0"), True, "1")}) == 5


def test_cell_text_uses_the_comparator_spelling():
    assert cd.cell_texts(None) == ("None", "None")
    assert cd.cell_texts(True) == ("true", "true")
    assert cd.cell_texts(["b", "a"]) == ('["b", "a"]', '["a", "b"]')
    assert cd.cell_texts("b") == ('"b"', '"b"')


def test_every_patient_row_and_column_is_one_cell():
    content = cd.measure_content(_rows())
    assert content["patients"] == 3
    assert content["cells"] == 3 * len(COLUMNS)
    assert content["columns"] == sorted(COLUMNS)
    assert set(content["by_column"]) == set(COLUMNS)
    # A patient present in two rows keeps both rows.
    assert cd.measure_content(_rows() + [dict(_rows()[0])])["cells"] == 4 * len(COLUMNS)


# --------------------------------------------------------------------------- the two referees

def test_an_injected_difference_is_caught_in_one_run():
    """One constant changed in one place: named, and called content — in a single run."""
    before = cd.measure_content(_rows())

    flipped = _rows()
    flipped[0]["Numerator"] = True
    after = cd.measure_content(flipped)
    assert cd.classify(before, after) == "content"
    moved = cd.compare_records({"CMSx": before}, {"CMSx": after})
    assert moved["moved"] == 1
    assert moved["counts"] == {"same": 0, "order": 0, "content": 1, "missing": 0}
    assert moved["measures"]["CMSx"]["moved_columns"] == ["Numerator"]

    longer = _rows()
    longer[1]["Evidence"] = np.array(["Encounter/c", "Encounter/z"])
    assert cd.compare_records({"CMSx": before}, {"CMSx": cd.measure_content(longer)})[
        "measures"
    ]["CMSx"]["moved_columns"] == ["Evidence"]

    smaller = _rows()
    smaller[2]["Initial Population"] = True
    assert cd.compare_records({"CMSx": before}, {"CMSx": cd.measure_content(smaller)})[
        "measures"
    ]["CMSx"]["moved_columns"] == ["Initial Population"]


def test_order_movement_is_not_content_movement():
    """The two causes must stay tellable apart (FHIR4-110 item 3)."""
    before = cd.measure_content(_rows())
    permuted = _rows()
    permuted[0]["Evidence"] = np.array(["Encounter/a", "Encounter/b"])
    after = cd.measure_content(permuted)
    assert before["digest_normalised"] == after["digest_normalised"]
    assert before["digest_exact"] != after["digest_exact"]
    assert cd.classify(before, after) == "order"
    assert cd.compare_records({"CMSx": before}, {"CMSx": after})["counts"]["order"] == 1


def test_two_clean_runs_agree_on_five_consecutive_attempts():
    """The same tree five times over: identical normalised digests, attempt after attempt."""
    reference = cd.measure_content(_rows())["digest_normalised"]
    for attempt in range(5):
        again = cd.measure_content(_shuffled(_rows(), seed=attempt))
        assert again["digest_normalised"] == reference, f"attempt {attempt + 1} moved"
        assert {name: col["digest_normalised"] for name, col in again["by_column"].items()} == {
            name: col["digest_normalised"]
            for name, col in cd.measure_content(_rows())["by_column"].items()
        }


def test_a_digest_that_always_matches_is_refused():
    """The referee's own control: different rows must never share a digest."""
    assert cd.measure_content(_rows())["digest_normalised"] != cd.measure_content(
        _rows()[:2]
    )["digest_normalised"]
    assert cd.measure_content([])["cells"] == 0


# --------------------------------------------------------------------------- a whole run

def test_suite_digest_ignores_measure_order_and_not_a_changed_measure():
    rows = _rows()
    first = cd.suite_content({"A": cd.measure_content(rows), "B": cd.measure_content(rows)})
    assert first == cd.suite_content({"B": cd.measure_content(rows), "A": cd.measure_content(rows)})
    changed = _rows()
    changed[2]["Denominator"] = True
    other = {"A": cd.measure_content(rows), "B": cd.measure_content(changed)}
    assert first["digest_normalised"] != cd.suite_content(other)["digest_normalised"]


def test_compare_records_reports_a_measure_missing_from_one_run():
    rows = cd.measure_content(_rows())
    report = cd.compare_records({"CMSx": rows}, {})
    assert report["counts"] == {"same": 0, "order": 0, "content": 0, "missing": 1}
    assert report["moved"] == 1


def test_load_record_reads_a_digest_file_and_a_gate_report(tmp_path: Path):
    measures = {"CMSx": cd.measure_content(_rows())}
    digest_file = tmp_path / rc.DIGEST_FILE
    cd.write_digest_file(digest_file, measures, suite="qi-core-2025")
    record = cd.load_record(digest_file)
    assert record["measures"] == measures
    assert record["suite"] == "qi-core-2025"
    assert record["digest"] == cd.suite_content(measures)

    report = tmp_path / "dqm_report.json"
    report.write_text(
        json.dumps(
            {
                "CMSx": {"accuracy_pct": 100.0, "content": measures["CMSx"]},
                "_summary": {"suite": "qi-core-2025", "content_digest": cd.suite_content(measures)},
            }
        )
    )
    assert cd.load_record(report) == record

    old = tmp_path / "old_report.json"
    old.write_text(json.dumps({"CMSx": {"accuracy_pct": 100.0}}))
    with pytest.raises(ValueError, match="no content digests"):
        cd.load_record(old)


# --------------------------------------------------------------------------- the repeat-compare helper

def test_compare_runs_names_the_column_and_the_cell_that_moved(tmp_path: Path):
    clean = _write_run(tmp_path / "run1", _rows(), cells=True)
    changed = _rows()
    changed[2]["Initial Population"] = True
    moved = _write_run(tmp_path / "run2", changed, cells=True)

    assert rc.compare_runs(clean, clean, cells=True)["measures"] == {"CMSx": {"class": "same"}}

    report = rc.compare_runs(clean, moved, cells=True)
    entry = report["measures"]["CMSx"]
    assert entry["class"] == "content"
    assert entry["moved_columns"] == ["Initial Population"]
    assert entry["cells"] == [
        {
            "column": "Initial Population",
            "kind": "boolean",
            "diff_cells": 1,
            "example": ["p3", "false", "true"],
        }
    ]
    assert report["moved"] == 1 and not report["failed"]

    # Without the cells the measure and its column are still named.
    plain = rc.compare_runs(clean, moved)
    assert plain["measures"]["CMSx"] == {"class": "content", "moved_columns": ["Initial Population"]}


def test_compare_runs_refuses_runs_that_did_not_digest_the_same_measures(tmp_path: Path):
    first = _write_run(tmp_path / "run1", _rows())
    cd.write_digest_file(tmp_path / "run2" / rc.DIGEST_FILE, {"Other": cd.measure_content(_rows())})
    report = rc.compare_runs(first, tmp_path / "run2")
    assert report["failed"] and "different measures" in report["problems"][0]
    missing = rc.compare_runs(first, tmp_path / "never-ran")
    assert missing["failed"] and "not a digest record" in missing["problems"][0]


def _fake_run_once(directory_name: str, rows: list[dict]):
    """Stand in for the CLI: lay out a run directory instead of starting a process."""

    def run_once(tree, suite, measures, output_dir, *, cell_digests=False, timeout_s=3600):
        _write_run(output_dir, rows, cells=cell_digests)
        return {
            "returncode": 0,
            "timed_out": False,
            "crashed": False,
            "markers": [],
            "record": cd.load_record(output_dir / rc.DIGEST_FILE),
            "record_error": None,
            "log": output_dir / "run.log",
        }

    return run_once


def test_repeat_compare_is_quiet_when_two_clean_runs_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    monkeypatch.setattr(rc, "run_once", _fake_run_once("clean", _rows()))
    status = rc.main(
        ["--measures", "CMSx", "--suite", "qi-core-2025", "--workdir", str(tmp_path / "w")]
    )
    assert status == 0
    out = capsys.readouterr().out
    assert "repeat-compare: 0 of 1 measure pair(s) moved" in out
    assert "CMSx: same" in out


def test_repeat_compare_fails_on_movement_and_never_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    calls: list[Path] = []
    changed = _rows()
    changed[1]["Evidence"] = np.array(["Encounter/c", "Encounter/z"])

    def run_once(tree, suite, measures, output_dir, *, cell_digests=False, timeout_s=3600):
        calls.append(output_dir)
        rows = _rows() if len(calls) % 2 else changed
        return _fake_run_once("x", rows)(tree, suite, measures, output_dir, cell_digests=cell_digests)

    monkeypatch.setattr(rc, "run_once", run_once)
    status = rc.main(
        ["--measures", "CMSx", "--runs", "2", "--attempts", "2", "--cell-digests",
         "--workdir", str(tmp_path / "w")]
    )
    assert status == 1
    assert len(calls) == 4, "two attempts of two runs: nothing is re-run to hide movement"
    out = capsys.readouterr().out
    assert out.count("CMSx: content (columns: Evidence)") == 2
    assert "repeat-compare: 2 of 2 measure pair(s) moved" in out
    assert "Evidence: value in 1 cell(s); example ['p2'" in out


def test_repeat_compare_reports_a_dead_run_as_not_answered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    def run_once(tree, suite, measures, output_dir, *, cell_digests=False, timeout_s=3600):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "run.log").write_text("Fatal Python error: Segmentation fault\n")
        return {
            "returncode": 139,
            "timed_out": False,
            "crashed": True,
            "markers": ["Fatal Python error", "Segmentation fault"],
            "record": None,
            "record_error": f"{output_dir / rc.DIGEST_FILE} is not a digest record",
            "log": output_dir / "run.log",
        }

    monkeypatch.setattr(rc, "run_once", run_once)
    status = rc.main(["--measures", "CMSx", "--workdir", str(tmp_path / "w")])
    assert status == 2, "a dead run is a failure, never 'no movement'"
    out = capsys.readouterr().out
    assert "a run did not answer" in out
    assert "run 1 died: exited 139 (Fatal Python error, Segmentation fault)" in out


def test_run_once_starts_a_fresh_process_with_a_fixed_hash_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    seen: dict[str, object] = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen.update(kwargs)
        _write_run(tmp_path / "out", _rows())
        seen["record"] = cd.load_record(tmp_path / "out" / rc.DIGEST_FILE)

        class Completed:
            returncode = 0

        return Completed()

    monkeypatch.setattr(rc.subprocess, "run", fake_run)
    run = rc.run_once(tmp_path, "qi-core-2025", ["CMSx"], tmp_path / "out", cell_digests=True)
    assert run["record"] == seen["record"] and not run["crashed"]
    assert seen["command"][1:3] == ["-m", "fhir4ds.dqm.tests.conformance.cli"]
    assert seen["command"][-1] == "--cell-digests"
    assert seen["cwd"] == tmp_path, "the process runs in the tree being measured"
    assert seen["env"]["PYTHONHASHSEED"] == "0"
