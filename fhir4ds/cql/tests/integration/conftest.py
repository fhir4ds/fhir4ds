"""pytest configuration for the CQL integration tests.

The hooks of the isolation plugin (FHIR4-103) are exposed here by name. A conftest this deep in
the tree must not declare ``pytest_plugins``: pytest refuses it outside a top-level conftest, and
a bare ``python -m pytest`` run starts at the repository root. An entry point is wrong too — it
would load the plugin into every pytest session that has the package installed.
"""

from fhir4ds.cql.tests.integration.ml_isolation import (
    pytest_addoption,
    pytest_configure,
    pytest_pycollect_makemodule,
    pytest_runtest_logreport,
    pytest_runtest_protocol,
    pytest_terminal_summary,
)

__all__ = [
    "pytest_addoption",
    "pytest_configure",
    "pytest_pycollect_makemodule",
    "pytest_runtest_logreport",
    "pytest_runtest_protocol",
    "pytest_terminal_summary",
]
