"""Unit tests for CQL variable UDFs."""

import duckdb

from ..udf.variable import clear_variables, registerVariableUdfs


def test_variable_state_is_connection_scoped():
    """Variables set on one connection should not leak into another."""
    clear_variables()

    con1 = duckdb.connect(":memory:")
    con2 = duckdb.connect(":memory:")

    registerVariableUdfs(con1)
    registerVariableUdfs(con2)

    con1.execute("SELECT setvariable('shared', 'one')")
    con2.execute("SELECT setvariable('shared', 'two')")

    assert con1.execute("SELECT getvariable('shared')").fetchone()[0] == "one"
    assert con2.execute("SELECT getvariable('shared')").fetchone()[0] == "two"


def test_clear_variables_targets_one_connection():
    """Clearing one connection should leave other registered connections intact."""
    clear_variables()

    con1 = duckdb.connect(":memory:")
    con2 = duckdb.connect(":memory:")

    registerVariableUdfs(con1)
    registerVariableUdfs(con2)

    con1.execute("SELECT setvariable('shared', 'left')")
    con2.execute("SELECT setvariable('shared', 'right')")

    clear_variables(con1)

    assert con1.execute("SELECT getvariable('shared')").fetchone()[0] == ""
    assert con2.execute("SELECT getvariable('shared')").fetchone()[0] == "right"
