"""Gate-integrity tests for the official CQL conformance runner (FHIR4-45).

The CQL gate could report a PASS while testing NOTHING. Three defects stacked:

1. ``fhir4ds/cql/tests/official/cql-tests`` was a gitlink with no
   ``.gitmodules`` entry, so a fresh CI checkout or ``git worktree add``
   materialised an EMPTY directory.
2. ``run_cql.py::main`` printed "Error: CQL tests directory not found" and
   then ``return``-ed, i.e. exited **0**, leaving the previously committed
   ``conformance/reports/cql_report.json`` untouched.
3. ``run_all.py`` discarded the child's exit status and summarised whatever
   report was on disk, so those stale numbers were reported as a pass.

These tests pin the corrected contract at both layers:

* ``run_cql.main()`` returns a NON-ZERO exit code when the corpus is absent,
  empty, or materially incomplete, and the stale report can no longer be read
  as a pass (it is replaced by an explicit integrity-failure report).
* ``run_all.run_script()`` reports a child that failed, and also a child that
  exited 0 *without rewriting its report* (the stale-read pattern that
  AGENTS.md records once reporting a stale DQM report as 47/47).

Every test here is fast: the failure paths return before DuckDB is touched,
and the single success path runs a one-test synthetic corpus.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "conformance" / "scripts"
RUN_CQL_PATH = SCRIPTS_DIR / "run_cql.py"
RUN_ALL_PATH = SCRIPTS_DIR / "run_all.py"


def _load(path: Path, name: str):
    """Import a conformance script by path (they are not a package)."""
    if str(SCRIPTS_DIR) not in sys.path:
        # Appended, not inserted: the runners import their sibling
        # conformance_log module and appending cannot shadow anything.
        sys.path.append(str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_cql = _load(RUN_CQL_PATH, "fhir4ds_conformance_run_cql_fhir4_45")
run_all = _load(RUN_ALL_PATH, "fhir4ds_conformance_run_all_fhir4_45")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ONE_TEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<tests xmlns="http://hl7.org/fhirpath/tests" name="Synthetic" version="1.0">
    <group name="Arithmetic">
        <test name="OnePlusOne">
            <expression>1 + 1</expression>
            <output>2</output>
        </test>
    </group>
</tests>
"""


def _write_corpus(corpus_dir: Path, files: int = 1) -> Path:
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for index in range(files):
        (corpus_dir / f"Synthetic{index}.xml").write_text(ONE_TEST_XML, encoding="utf-8")
    return corpus_dir


def _write_manifest(path: Path, xml_files: int, tests: int, pin: str = "0" * 40) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "upstream": "https://github.com/cqframework/cql-tests",
                "pin": pin,
                "xml_file_count": xml_files,
                "test_count": tests,
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def cql_env(tmp_path, monkeypatch):
    """Point the CQL runner at temp corpus/report/manifest paths."""
    corpus = tmp_path / "corpus"
    report = tmp_path / "reports" / "cql_report.json"
    manifest = tmp_path / "corpus_manifest.json"
    monkeypatch.setenv("FHIR4DS_CQL_TESTS_DIR", str(corpus))
    monkeypatch.setenv("FHIR4DS_CQL_REPORT", str(report))
    monkeypatch.setenv("FHIR4DS_CQL_MANIFEST", str(manifest))
    # The shared conformance log must never be touched by a unit test.
    monkeypatch.setenv("FHIR4DS_CONFORMANCE_LOG", str(tmp_path / "conformance.log"))
    return corpus, report, manifest


def _seed_stale_pass(report: Path) -> None:
    """Write a report that looks like a 100% pass from a previous run."""
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "CqlArithmeticFunctionsTest.xml": {
                    "tests": [{"name": "StaleCell", "result": {"passed": True}}]
                }
            }
        ),
        encoding="utf-8",
    )


def _passed_through(report: Path) -> tuple[int, int]:
    """(passed, total) as run_all.get_summary would count them."""
    data = json.loads(report.read_text(encoding="utf-8"))
    passed = total = 0
    for suite in data.values():
        for test in suite.get("tests", []):
            total += 1
            if test.get("result", {}).get("passed"):
                passed += 1
    return passed, total


# ---------------------------------------------------------------------------
# run_cql: corpus absent / empty / partial / normal
# ---------------------------------------------------------------------------


def test_absent_corpus_exits_nonzero_and_cannot_leave_stale_pass(cql_env):
    """FHIR4-45 (a): a missing corpus is a loud failure, not exit 0."""
    _corpus, report, manifest = cql_env
    _write_manifest(manifest, xml_files=16, tests=2043)
    _seed_stale_pass(report)

    exit_code = run_cql.main([])

    assert exit_code != 0, "absent corpus must not exit 0 (silent pass)"
    assert report.exists(), "the stale report must be replaced, not left in place"
    passed, total = _passed_through(report)
    assert passed == 0, f"stale passing cells survived: {passed}/{total}"
    assert total > 0, "an explicit failure report must be readable by run_all"


def test_absent_corpus_message_names_the_remedy(cql_env, capsys):
    """The error must say what to do, not just that something is missing."""
    corpus, _report, manifest = cql_env
    _write_manifest(manifest, xml_files=16, tests=2043)

    run_cql.main([])

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert str(corpus) in output, "the message must name the corpus path"
    lowered = output.lower()
    assert any(
        token in lowered for token in ("git checkout", "git submodule", "re-clone", "clone")
    ), f"the message must name an actionable remedy; got: {output}"


def test_empty_corpus_is_a_failure_not_a_zero_test_pass(cql_env):
    """A present-but-empty corpus silently tests nothing; it must fail too."""
    corpus, report, manifest = cql_env
    corpus.mkdir(parents=True, exist_ok=True)
    _write_manifest(manifest, xml_files=16, tests=2043)
    _seed_stale_pass(report)

    exit_code = run_cql.main([])

    assert exit_code != 0, "an empty corpus must not report a pass"
    passed, total = _passed_through(report)
    assert passed == 0 and total > 0


def test_materially_partial_corpus_is_a_failure(cql_env, capsys):
    """1 of 16 expected files is a partial corpus, not a smaller green gate."""
    corpus, report, manifest = cql_env
    _write_corpus(corpus, files=1)
    _write_manifest(manifest, xml_files=16, tests=2043)
    _seed_stale_pass(report)

    exit_code = run_cql.main([])

    assert exit_code != 0, "a partial corpus must fail rather than shrink the gate"
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "16" in output and "1" in output, f"message must name expected vs found: {output}"
    passed, _total = _passed_through(report)
    assert passed == 0


def test_present_corpus_still_runs_and_rewrites_the_report(cql_env):
    """The normal path keeps working and reports real numbers."""
    corpus, report, manifest = cql_env
    _write_corpus(corpus, files=1)
    _write_manifest(manifest, xml_files=1, tests=1)
    _seed_stale_pass(report)

    exit_code = run_cql.main([])

    assert exit_code == 0, "a present, complete corpus must pass the integrity gate"
    passed, total = _passed_through(report)
    assert (passed, total) == (1, 1), f"expected the synthetic cell to run: {passed}/{total}"
    assert "StaleCell" not in report.read_text(encoding="utf-8")


def test_corpus_manifest_is_the_single_source_of_truth():
    """The shipped manifest must match the shipped vendored corpus."""
    manifest = run_cql.load_manifest()
    assert manifest is not None, "the shipped corpus manifest must exist and parse"
    corpus = run_cql.default_corpus_dir()
    files = sorted(corpus.glob("*.xml"))
    assert files, f"vendored corpus is missing from this checkout: {corpus}"
    assert len(files) == manifest["xml_file_count"], (
        f"manifest pins {manifest['xml_file_count']} XML files, corpus has {len(files)}; "
        "refresh the manifest with the pin"
    )


# ---------------------------------------------------------------------------
# run_all: child failures and stale reports must reach the master status
# ---------------------------------------------------------------------------

_FAKE_CHILD = """\
import json
import sys
from pathlib import Path

mode = sys.argv[1]
report = Path(sys.argv[2])

if mode == "exit_nonzero":
    print("child exploded")
    sys.exit(3)
elif mode == "stale":
    # Exits 0 without rewriting the report: the stale-read pattern.
    sys.exit(0)
elif mode == "empty":
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({}), encoding="utf-8")
elif mode == "good":
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"f.xml": {"tests": [{"name": "c", "result": {"passed": True}}]}}),
        encoding="utf-8",
    )
"""


@pytest.fixture()
def fake_child(tmp_path):
    script = tmp_path / "fake_child.py"
    script.write_text(_FAKE_CHILD, encoding="utf-8")
    return script


def test_run_all_reports_a_child_that_exits_nonzero(fake_child, tmp_path):
    """A crashing child cannot be swallowed into a green summary."""
    report = tmp_path / "report.json"
    outcome = run_all.run_script("Fake", fake_child, report, ("exit_nonzero", str(report)))
    assert outcome.ok is False
    assert "3" in (outcome.reason or ""), outcome.reason


def test_run_all_detects_a_child_that_left_a_stale_report(fake_child, tmp_path):
    """Exit 0 + untouched report is the stale-read bug; it must fail."""
    report = tmp_path / "report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"old.xml": {"tests": [{"name": "old", "result": {"passed": True}}]}}),
        encoding="utf-8",
    )

    outcome = run_all.run_script("Fake", fake_child, report, ("stale", str(report)))

    assert outcome.ok is False, "a child that did not rewrite its report must not count as a pass"
    assert "stale" in (outcome.reason or "").lower(), outcome.reason


def test_run_all_rejects_a_suite_that_collected_zero_tests(fake_child, tmp_path):
    """A suite that ran nothing is an infrastructure failure, not 0/0 pass."""
    report = tmp_path / "report.json"
    outcome = run_all.run_script("Fake", fake_child, report, ("empty", str(report)))
    assert outcome.ok is False
    assert "0" in (outcome.reason or "") or "no tests" in (outcome.reason or "").lower()


def test_run_all_accepts_a_healthy_suite(fake_child, tmp_path):
    """The freshness/aggregation guards must not fire on a normal child."""
    report = tmp_path / "report.json"
    outcome = run_all.run_script("Fake", fake_child, report, ("good", str(report)))
    assert outcome.ok is True, outcome.reason
