"""QA-D10-002 (v0.0.25 Domain 10): base-install CLI resilience.

The installed ``fhir4ds`` console script must work on a vanilla
``pip install fhir4ds-v2`` — without the optional [measures]/[serve]
extras. ``fhir4ds/cli/dqm.py`` used to import ``fhir4ds.dqm.batch``
(→ evaluator → pandas) at module import time, so ``fhir4ds --help``
crashed with ``ModuleNotFoundError: No module named 'pandas'`` before
argparse could even run. The heavy imports are now lazy, mirroring the
pattern ``fhir4ds/cli/serve.py`` uses for the [serve] extra.

These tests simulate the missing-extra environment by poisoning
``sys.modules['pandas'] = None`` (an import of a ``None``-valued entry
raises ImportError) in a subprocess, so the test environment's real
pandas cannot mask the defect.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_POISON = "import sys; sys.modules['pandas'] = None"


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", _POISON + "\n" + code],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_cli_help_works_without_measures_extra():
    """`fhir4ds --help` (and module import) must not need pandas."""
    result = _run(
        "from fhir4ds.cli.main import main\n"
        "rc = main(['--help'])\n"
        "assert rc == 2, rc\n"  # argparse help path returns 2 via print_help
    )
    assert result.returncode == 0, result.stderr
    assert "ModuleNotFoundError" not in result.stderr


def test_dqm_subcommand_parser_works_without_measures_extra():
    """Subcommand parsing (including dqm) succeeds; only running fails."""
    result = _run(
        "from fhir4ds.cli.main import main\n"
        "rc = main(['dqm'])\n"
        "assert rc == 2, rc\n"  # no subcommand -> actionable message, rc 2
    )
    assert result.returncode == 0, result.stderr
    assert "requires a subcommand" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr


def test_dqm_run_reports_actionable_error_without_measures_extra():
    """Running a real dqm command without pandas prints the install hint."""
    result = _run(
        "from fhir4ds.cli.main import main\n"
        "rc = main(['dqm', 'run', '--measure', 'x', '--library', '/nope'])\n"
        "assert rc == 2, rc\n"
    )
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert "ModuleNotFoundError" not in combined
    assert "[measures]" in combined, combined
    assert "pip install" in combined, combined


def test_dqm_backends_load_with_pandas_present():
    """Control: with pandas available the lazy loader resolves everything."""
    from fhir4ds.cli import dqm

    dqm._load_dqm_backends()
    for name in dqm._BACKEND_NAMES:
        assert callable(dqm.__dict__.get(name)), f"{name} not loaded"
