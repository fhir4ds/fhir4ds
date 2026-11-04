"""The slim entry point: ``python -m fhir4ds.serve``.

The ``fhir4ds`` console script imports every subcommand at startup, and the
``dqm`` one needs pandas (the optional ``[measures]`` extra). A ``[serve]``-only
install — the container image — therefore has to start the surface through this
module. These tests pin that contract in a subprocess, because the failure mode
(``ModuleNotFoundError: No module named 'pandas'``) only appears when pandas is
genuinely absent.
"""

from __future__ import annotations

import subprocess
import sys


def test_module_entrypoint_exposes_the_serve_options():
    result = subprocess.run(
        [sys.executable, "-m", "fhir4ds.serve", "--help"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    for flag in ("--host", "--port", "--data-root", "--resources", "--no-cql-facade"):
        assert flag in result.stdout, f"{flag} missing from --help"


def test_module_entrypoint_does_not_import_pandas():
    """Importing the entry point must not pull the measures extra."""
    probe = (
        "import sys; import fhir4ds.serve.__main__; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] == 'pandas'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == "[]", result.stdout


def test_serve_extra_import_error_is_actionable_v22_qa008():
    """Without fastapi, importing serve.app names the missing extra (V22-QA-008).

    Runs in a subprocess: this suite imports fhir4ds.serve.app everywhere, so
    an in-process import would hit the cached module and skip the guard.
    """
    import subprocess
    import sys
    from pathlib import Path

    code = (
        "import sys\n"
        "sys.modules['fastapi'] = None\n"  # blocks the import machinery
        "try:\n"
        "    import fhir4ds.serve.app\n"
        "    print('unexpected: import succeeded')\n"
        "except RuntimeError as exc:\n"
        "    print('RuntimeError:', exc)\n"
    )
    repo_root = str(Path(__file__).resolve().parents[3])
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=repo_root
    )
    assert "fhir4ds-v2[serve]" in result.stdout, (result.stdout, result.stderr)
    assert "unexpected" not in result.stdout
