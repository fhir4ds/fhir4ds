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
