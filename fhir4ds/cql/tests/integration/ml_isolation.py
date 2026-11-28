"""Keep ML-touching test modules out of the shared pytest process (FHIR4-103).

``test_medterm4ds_in_process.py`` imports a native ML stack (torch, faiss, spaCy, ...). In this
workspace that stack is ABI-broken (numpy 2.x against packages built for numpy 1.x), so once it
is loaded a later allocation anywhere in the process can segfault or exhaust memory. The crash
then surfaces inside whichever unrelated test allocates next, and the suite reports an
``INTERNALERROR`` or dies with a signal — a verdict about the test infrastructure, not about the
code under test.

This plugin keeps every module whose top-level ``pytestmark`` carries ``pytest.mark.ml`` out of
the process that runs the rest of the suite:

- collection: the module's tests are listed by a CHILD pytest process (``--collect-only``), so
  the parent never imports the module;
- run: the module is run ONCE by a child pytest process that records every verdict in a results
  file as soon as it exists, and the parent replays each recorded outcome for that item. A
  verdict reached before a crash is therefore kept; a file written only at the end (JUnit) would
  lose it.

The failure mode is honest by construction. The ML tests either work, or fail in their own step
with the child's text, and every test the child did not report FAILS with the reason the child
stopped (segfault, abort, fatal Python error, no results, timeout). Nothing is retried, and no
other test is taken down.

``--ml-in-process`` turns the isolation off; the marker is then only a label.
"""

from __future__ import annotations

import ast
import json
import os
import signal
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from _pytest.outcomes import Failed, Skipped, XFailed
from _pytest.reports import TestReport
from _pytest.runner import CallInfo
from _pytest.terminal import TerminalReporter

MARKER = "ml"
OPT_IN_PROCESS = "--ml-in-process"
OPT_TIMEOUT = "--ml-child-timeout"
CHILD_ENV = "FHIR4DS_ML_SUBPROCESS"
#: Child side only: the file the child appends each verdict to.
RESULTS_ENV = "FHIR4DS_ML_RESULTS"
DEFAULT_TIMEOUT_S = 1800.0

#: The directory that has to be importable for the children to import ``fhir4ds``.
REPO_ROOT = Path(__file__).resolve().parents[4]

#: Ways a child can die that pytest itself can never report; keyed by its exit status.
CRASH_STATUS = {
    -int(signal.SIGSEGV): "Segmentation fault (signal 11)",
    -int(signal.SIGABRT): "Aborted (signal 6)",
    139: "Segmentation fault (exit status 139)",
    134: "Aborted (exit status 134)",
}
CRASH_MARKERS = ("Fatal Python error", "Segmentation fault")


# -- the marker, read without importing the module ---------------------------------------------


def _names_marked(node: ast.AST, marker: str) -> bool:
    """True when ``pytest.mark.<marker>`` appears in the expression (alone, in a list, with ``|``)."""
    for attribute in ast.walk(node):
        if (
            isinstance(attribute, ast.Attribute)
            and attribute.attr == marker
            and isinstance(attribute.value, ast.Attribute)
            and attribute.value.attr == "mark"
        ):
            return True
    return False


def module_is_ml(path: Path) -> bool:
    """True when the module's top-level ``pytestmark`` carries ``pytest.mark.ml``.

    The file is PARSED, never imported: importing it is exactly what the parent must not do.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return False
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            targets, value = statement.targets, statement.value
        elif isinstance(statement, ast.AnnAssign):
            targets, value = [statement.target], statement.value
        else:
            continue
        if value is None:
            continue
        if any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in targets):
            if _names_marked(value, MARKER):
                return True
    return False


# -- child processes -----------------------------------------------------------------------------


@dataclass
class ChildResult:
    returncode: int
    output: str
    timed_out: bool = False


def _child_env(results: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(part for part in (str(REPO_ROOT), existing) if part)
    env[CHILD_ENV] = "1"
    env.pop(RESULTS_ENV, None)
    if results is not None:
        env[RESULTS_ENV] = str(results)
    return env


def _text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def _run_child(
    arguments: list[str],
    timeout_s: float,
    *,
    bare: bool = False,
    results: Path | None = None,
) -> ChildResult:
    """Run pytest in a child process. A timeout kills the child and is reported, never raised.

    ``bare`` drops the repository's ``addopts``: the listing child needs pytest's plain
    node-id output, and ``-v`` in ``addopts`` would print a tree instead.
    """
    command = [sys.executable, "-m", "pytest", *arguments]
    command += ["-o", "addopts=", "-p", "no:benchmark"] if bare else []
    command += ["-p", "no:cacheprovider"]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            cwd=os.getcwd(),
            env=_child_env(results),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as error:
        return ChildResult(
            returncode=0,
            output=_text(error.stdout) + _text(error.stderr),
            timed_out=True,
        )
    return ChildResult(
        returncode=completed.returncode, output=(completed.stdout or "") + (completed.stderr or "")
    )


def _tail(output: str, lines: int = 15) -> str:
    kept = [line for line in output.splitlines() if line.strip()][-lines:]
    return "\n".join(kept)


def _stopped(result: ChildResult, timeout_s: float, results_read: bool, any_failed: bool) -> str:
    """Why tests the child did not report must fail; empty when it ran to the end."""
    if result.timed_out:
        return f"the test process for this module timed out after {timeout_s:g} s and was killed"
    crash = CRASH_STATUS.get(result.returncode)
    if crash is None:
        for line in result.output.splitlines():
            if any(marker in line for marker in CRASH_MARKERS):
                crash = line.strip()
                break
    if crash is not None:
        return f"the test process for this module died: {crash}"
    if not results_read:
        return (
            "the test process for this module exited with status "
            f"{result.returncode} and produced no results\n{_tail(result.output)}"
        )
    if result.returncode != 0 and not any_failed:
        return (
            f"the test process for this module exited with status {result.returncode} "
            "without reporting a failed test\n" + _tail(result.output)
        )
    return ""


# -- verdicts


@dataclass
class Outcome:
    status: str  # passed | failed | skipped
    text: str = ""
    xfail: bool = False
    duration: float = 0.0


@dataclass
class Listing:
    nodeids: list[str] = field(default_factory=list)
    skipped: str = ""  # the module was skipped at import (e.g. an optional dependency)
    failed: str = ""  # the child could not list the module
    exit_status: int = 0


def _truncate(text: str, head: int = 3000, tail: int = 1000) -> str:
    if len(text) <= head + tail + 80:
        return text
    return f"{text[:head]}\n... {len(text) - head - tail} characters omitted ...\n{text[-tail:]}"


def _record(report: pytest.TestReport) -> dict[str, object]:
    """One verdict of the child, as written to the results file."""
    longrepr = "" if report.longrepr is None else str(report.longrepr)
    # pytest sets ``wasxfail`` on a report only for an expected failure or an unexpected pass.
    wasxfail = getattr(report, "wasxfail", None)
    return {
        "nodeid": report.nodeid,
        "status": "skipped" if report.skipped else "failed" if report.failed else "passed",
        "xfail": wasxfail is not None,
        "text": _truncate(str(wasxfail) if report.skipped and wasxfail else longrepr),
        "duration": report.duration,
    }


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Child side: record every verdict the moment it exists, so a later crash cannot erase it."""
    path = os.environ.get(RESULTS_ENV)
    if not path or (report.passed and report.when != "call"):
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(_record(report)) + "\n")
        handle.flush()


_RANK = {"passed": 0, "skipped": 1, "failed": 2}


def _read_results(path: Path) -> dict[str, Outcome] | None:
    """The child's verdicts keyed by the node id after the file; None when it wrote no file."""
    if not path.exists():
        return None
    outcomes: dict[str, Outcome] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
            status = entry["status"]
            rank = _RANK[status]
        except (ValueError, KeyError, TypeError):
            continue  # the half-written line of a child that died mid-write
        suffix = str(entry["nodeid"]).split("::", 1)[-1]
        kept = outcomes.get(suffix)
        if kept is None or rank >= _RANK[kept.status]:
            outcomes[suffix] = Outcome(
                status, str(entry["text"]), bool(entry["xfail"]), float(entry["duration"])
            )
    return outcomes


def list_tests(path: Path, timeout_s: float = DEFAULT_TIMEOUT_S) -> Listing:
    """Have a child list the module's tests. The parent never imports the module."""
    result = _run_child([str(path), "--collect-only", "-q", "-rs"], timeout_s, bare=True)
    listing = Listing(exit_status=result.returncode)
    listing.nodeids = [
        line.strip()
        for line in result.output.splitlines()
        if "::" in line
        and line.split("::")[0].strip().endswith(path.name)
        and " " not in line.strip()
    ]
    if listing.nodeids:
        return listing
    for line in result.output.splitlines():
        if line.startswith("SKIPPED"):
            listing.skipped = line
            return listing
    listing.failed = (
        f"the test process could not collect this module (status {result.returncode})\n"
        + _tail(result.output)
        if not result.timed_out
        else f"the test process could not collect this module: timed out after {timeout_s:g} s"
    )
    return listing


def run_module(path: Path, timeout_s: float = DEFAULT_TIMEOUT_S) -> tuple[dict[tuple[str, str], Outcome], str]:
    """Run the module once in a child; return its outcomes and the reason any test was not reported."""
    with tempfile.TemporaryDirectory(prefix="fhir4ds-ml-") as scratch:
        results = Path(scratch) / "results.jsonl"
        result = _run_child([str(path)], timeout_s, results=results)
        outcomes = _read_results(results)
    if outcomes is None:
        return {}, _stopped(result, timeout_s, False, False)
    any_failed = any(outcome.status == "failed" for outcome in outcomes.values())
    return outcomes, _stopped(result, timeout_s, True, any_failed)


# -- the collector and the item


class _Verdict:
    """What the terminal shows for a failed or skipped isolated test: the child's own text."""

    def __init__(self, text: str) -> None:
        self.text = text

    def __repr__(self) -> str:
        return self.text

    def toterminal(self, out) -> None:
        for line in (self.text.rstrip("\n") or "the test process reported nothing").splitlines():
            out.line(line)


class MLItem(pytest.Item):
    """A test of an ``ml`` module. It is never run in this process."""

    def __init__(self, *, name: str, suffix: str = "", verdict: Outcome | None = None, **kwargs: object) -> None:
        super().__init__(name=name, **kwargs)
        self.add_marker(pytest.mark.ml)
        #: The node id after the file (``Class::test`` or ``test``): the child's verdicts are keyed by it.
        self.suffix = suffix
        #: Set only for the one item that stands for a module the child could not list.
        self.verdict = verdict

    def runtest(self) -> None:
        raise AssertionError("an ml test runs only in its child process")

    def reportinfo(self):
        return self.path, 0, self.name

    def repr_failure(self, excinfo, style=None):
        if excinfo.errisinstance(AssertionError):
            return str(excinfo.value)
        return super().repr_failure(excinfo, style=style)


class MLModule(pytest.File):
    """An ``ml`` module, collected through a child so the parent never imports it."""

    def collect(self) -> Iterable[pytest.Item]:
        listing = list_tests(self.path, _timeout(self.config))
        if listing.nodeids:
            for nodeid in listing.nodeids:
                suffix = nodeid.split("::", 1)[1]
                parts = suffix.split("::")
                yield MLItem.from_parent(self, name=parts[-1], suffix=suffix, nodeid=f"{self.nodeid}::{suffix}")
        elif listing.skipped:
            pytest.skip(listing.skipped, allow_module_level=True)
        else:
            yield MLItem.from_parent(
                self,
                name="<collection>",
                nodeid=f"{self.nodeid}::<collection>",
                verdict=Outcome("failed", listing.failed),
            )


# -- replaying a child's verdict through the normal report machinery


def _call(when: str, outcome: Outcome | None) -> CallInfo:
    def run() -> None:
        if outcome is None:
            return
        if outcome.status == "failed":
            raise Failed(outcome.text)
        if outcome.status == "skipped":
            raise XFailed(outcome.text) if outcome.xfail else Skipped(outcome.text)

    return CallInfo.from_call(run, when=when)


def _reports(item: MLItem, outcome: Outcome) -> Iterator[TestReport]:
    for when in ("setup", "call", "teardown"):
        report = TestReport.from_item_and_call(item, _call(when, outcome if when == "call" else None))
        if when == "call":
            report.duration = outcome.duration
            if report.failed:
                report.longrepr = _Verdict(outcome.text)
        yield report


def _emit(item: MLItem, outcome: Outcome) -> None:
    ihook = item.ihook
    ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
    for report in _reports(item, outcome):
        ihook.pytest_runtest_logreport(report=report)
    ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)


def _timeout(config: pytest.Config) -> float:
    return float(config.getoption(OPT_TIMEOUT))


_RUNS: dict[Path, tuple[dict[tuple[str, str], Outcome], str]] = {}
_SUMMARY: dict[str, str] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("fhir4ds", "fhir4ds test infrastructure")
    group.addoption(
        OPT_IN_PROCESS,
        action="store_true",
        default=False,
        help="run ml-marked tests in this process instead of a child process (FHIR4-103)",
    )
    group.addoption(
        OPT_TIMEOUT,
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help=f"seconds an ml module's child process may take (default: {DEFAULT_TIMEOUT_S:g})",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{MARKER}: imports the native ML stack; the module is collected and run in a child "
        "process (FHIR4-103)",
    )


def _in_child() -> bool:
    return os.environ.get(CHILD_ENV) == "1"


def _isolation_off(config: pytest.Config) -> bool:
    return _in_child() or bool(config.getoption(OPT_IN_PROCESS))


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makemodule(module_path: Path, parent):
    """Claim ``ml`` modules before pytest's python collector can import them."""
    if _isolation_off(parent.config) or not module_is_ml(module_path):
        return None
    return MLModule.from_parent(parent, path=module_path)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> bool | None:
    if not isinstance(item, MLItem) or _isolation_off(item.config):
        return None
    if item.path not in _RUNS:
        _RUNS[item.path] = run_module(item.path, _timeout(item.config))
    if item.verdict is not None:
        outcome = item.verdict
    else:
        outcomes, reason = _RUNS[item.path]
        reported = outcomes.get(item.suffix)
        outcome = reported if reported is not None else Outcome(
            "failed", reason or "the test process did not report this test"
        )
    _emit(item, outcome)
    return True


def pytest_terminal_summary(
    terminalreporter: TerminalReporter, exitstatus: int, config: pytest.Config
) -> None:
    if not _RUNS:
        return
    terminalreporter.section("ML modules (run in child processes)")
    for path, (outcomes, reason) in _RUNS.items():
        counts = {status: sum(o.status == status for o in outcomes.values()) for status in ("passed", "failed", "skipped")}
        terminalreporter.write_line(
            f"{path}: {counts['passed']} passed, {counts['failed']} failed, "
            f"{counts['skipped']} skipped"
        )
        if reason:
            for line in reason.splitlines():
                terminalreporter.write_line(f"  {line}")
