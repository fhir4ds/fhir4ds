"""FHIR4-103 — ML test modules run in a child process, and a crash is a failure in their own step.

These tests drive the isolation plugin end to end. Each one starts a REAL inner pytest run in a
temporary project whose conftest loads the plugin, and gives that run a module carrying
``pytest.mark.ml`` that misbehaves in a controlled way. The inner run's own children are real
processes, so a segfault here is a segfault, not a mock of one.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from _pytest.pytester import Pytester

from fhir4ds.cql.tests.integration import ml_isolation

pytest_plugins = ["pytester"]

REPO_ROOT = Path(__file__).resolve().parents[4]
ML_MODULE = Path(__file__).with_name("test_medterm4ds_in_process.py")

POISONED_MODULE = """
    import ctypes
    import os
    import signal

    import pytest

    pytestmark = pytest.mark.ml

    def test_runs_first():
        pass

    def test_dies():
        # This crash is DELIBERATE, so it must not leave a core file on the owner's disk
        # (WSL captures one per fault, about 0.6 GB each; ``ulimit -c 0`` does not stop it).
        # Only this process is made non-dumpable, right before the fault: a real crash
        # anywhere else keeps its core, which is evidence.
        ctypes.CDLL("libc.so.6").prctl(4, 0, 0, 0, 0)  # PR_SET_DUMPABLE = 4, value 0
        os.kill(os.getpid(), signal.SIGSEGV)

    def test_is_never_reached():
        pass
"""


@pytest.fixture
def project(pytester: Pytester, monkeypatch: pytest.MonkeyPatch) -> Pytester:
    """An inner project that loads the plugin; its children must be able to import ``fhir4ds``.

    ``pytester`` points HOME at its own temporary directory, so an inner Python no longer sees a
    pytest installed in the user site. pytest's own directory therefore travels on PYTHONPATH.
    """
    pytest_home = str(Path(pytest.__file__).resolve().parent.parent)
    pythonpath = os.pathsep.join(
        part
        for part in (str(REPO_ROOT), pytest_home, os.environ.get("PYTHONPATH", ""))
        if part
    )
    monkeypatch.setenv("PYTHONPATH", pythonpath)
    monkeypatch.delenv(ml_isolation.CHILD_ENV, raising=False)
    pytester.makeconftest('pytest_plugins = ["fhir4ds.cql.tests.integration.ml_isolation"]\n')
    return pytester


def test_a_crashing_ml_module_fails_in_its_own_step(project: Pytester):
    """The point of the card: the crash is reported on the ML tests and nothing else goes down."""
    project.makepyfile(test_poison=POISONED_MODULE, test_unrelated="def test_sibling(): pass")
    result = project.runpytest_subprocess("-v")

    # A normal failing session, not a dead one. The unrelated test ran and passed, and so did the
    # ML test that finished before the crash: its verdict was recorded, and a crash must not
    # rewrite what already happened.
    assert result.ret == 1
    result.assert_outcomes(passed=2, failed=2)
    # Patterns in output order (the plugin's terminal summary comes last).
    result.stdout.fnmatch_lines(
        [
            "*test_poison.py::test_runs_first PASSED*",
            "*test_poison.py::test_dies FAILED*",
            "*test_poison.py::test_is_never_reached FAILED*",
            "*test_unrelated.py::test_sibling PASSED*",
            "*the test process for this module died: Segmentation fault*",
        ]
    )


def test_a_child_that_leaves_no_results_fails_its_tests(project: Pytester):
    """A hard exit before the report is written is a failure with a reason, never a silent pass."""
    project.makepyfile(
        test_exits="""
        import os

        import pytest

        pytestmark = pytest.mark.ml

        def test_runs_first():
            pass

        def test_leaves():
            os._exit(3)
        """
    )
    result = project.runpytest_subprocess()
    assert result.ret == 1
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*exited with status 3 without reporting a failed test*"])


def test_the_parent_never_imports_the_ml_module(project: Pytester):
    """Collection goes through the child: an import that crashes there fails the tests, not the run."""
    project.makepyfile(
        test_broken="""
        import os

        import pytest

        pytestmark = pytest.mark.ml

        raise ImportError("the ML stack cannot be imported")
        """
    )
    result = project.runpytest_subprocess("-v")
    assert result.ret == 1
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*<collection> FAILED*", "*could not collect this module*"])


def test_a_real_failure_keeps_its_own_message(project: Pytester):
    """Isolation must not hide what the test itself said."""
    project.makepyfile(
        test_fails="""
        import pytest

        pytestmark = pytest.mark.ml

        def test_assertion():
            assert 1 == 2
        """
    )
    result = project.runpytest_subprocess()
    assert result.ret == 1
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*assert 1 == 2*"])


def test_a_module_skipped_at_import_stays_a_skip(project: Pytester):
    """An optional dependency that is absent is still reported the way pytest reports it."""
    project.makepyfile(
        test_needs_stack="""
        import pytest

        pytestmark = pytest.mark.ml

        pytest.importorskip("no_such_ml_stack_fhir4_103")

        def test_needs_it():
            pass
        """
    )
    isolated = project.runpytest_subprocess("-rs")
    plain = project.runpytest_subprocess("-rs", "--ml-in-process")
    # The same verdict as the same module would get in the shared process, isolation or not.
    assert isolated.ret == plain.ret
    isolated.stdout.fnmatch_lines(["*no_such_ml_stack_fhir4_103*"])
    plain.stdout.fnmatch_lines(["*no_such_ml_stack_fhir4_103*"])


def test_isolated_tests_run_in_a_child_unless_asked_otherwise(project: Pytester):
    project.makepyfile(
        test_where="""
        import os

        import pytest

        pytestmark = pytest.mark.ml

        def test_runs_in_the_child():
            assert "FHIR4DS_ML_SUBPROCESS" in os.environ
        """
    )
    assert project.runpytest_subprocess().ret == 0
    assert project.runpytest_subprocess("--ml-in-process").ret == 1


def test_the_ml_module_is_marked_and_this_process_never_imported_it(
    request: pytest.FixtureRequest,
):
    """The marker is read from the source; the stack is not in this process unless isolation is off."""
    assert ml_isolation.module_is_ml(ML_MODULE)
    assert not ml_isolation.module_is_ml(Path(__file__))
    if request.config.getoption(ml_isolation.OPT_IN_PROCESS):
        pytest.skip("isolation is off for this run")
    assert "medterm4ds" not in sys.modules
    assert "torch" not in sys.modules
