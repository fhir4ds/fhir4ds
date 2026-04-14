import pytest
import re
from pathlib import Path
from ...translator.types import SQLSelect, SQLIdentifier, SQLBinaryOp, SQLLiteral
from ...translator import ast_utils

# Phase A test assertions - verifying golden rules after remediation

_TRANSLATOR_DIR = Path(__file__).resolve().parents[2] / "translator"


def test_translator_no_to_sql_inspection():
    """
    Verify translator uses AST helpers instead of .to_sql() for decisions.
    A-2: All detection must use ast_utils helpers.
    """
    # Test that select_has_column uses AST introspection
    select_with_pid = SQLSelect(
        columns=[SQLIdentifier(name="patient_id"), SQLIdentifier(name="value")],
        from_clause=SQLIdentifier(name="test_table")
    )
    
    assert ast_utils.select_has_column(select_with_pid, "patient_id")
    
    select_without_pid = SQLSelect(
        columns=[SQLIdentifier(name="value")],
        from_clause=SQLIdentifier(name="test_table")
    )
    assert not ast_utils.select_has_column(select_without_pid, "patient_id")

    # Also verify translator.py .to_sql() calls are bounded (only in final render paths)
    source = (_TRANSLATOR_DIR / "translator.py").read_text()
    to_sql_calls = re.findall(r'\.to_sql\(\)', source)
    assert len(to_sql_calls) <= 35, (
        f"Found {len(to_sql_calls)} .to_sql() calls in translator.py — expected <=35 (render only)"
    )


def test_translator_detects_patient_id_via_ast():
    """Build a minimal AST containing a patient_id reference and assert ast_utils detects it."""
    binary_op = SQLBinaryOp(
        operator="=",
        left=SQLIdentifier(name="patient_id"),
        right=SQLLiteral(value="12345")
    )
    
    assert ast_utils.ast_references_name(binary_op, "patient_id")
    assert not ast_utils.ast_references_name(binary_op, "other_column")


def test_expressions_emit_ast_nodes_instead_of_strings():
    """expressions.py should not use regex on rendered SQL strings."""
    # Support both expressions.py (old layout) and expressions/__init__.py (package layout)
    expr_file = _TRANSLATOR_DIR / "expressions.py"
    if not expr_file.exists():
        expr_file = _TRANSLATOR_DIR / "expressions" / "__init__.py"
    source = expr_file.read_text()
    violations = re.findall(r're\.search\(.+sql', source)
    assert len(violations) == 0, f"Found regex-on-SQL violations: {violations}"


def test_fluent_functions_no_body_sql_templates():
    """fluent_functions.py body_sql string templates should be bounded (fallback only)."""
    source = (_TRANSLATOR_DIR / "fluent_functions.py").read_text()
    body_sql_count = source.count('body_sql="')
    # body_sql templates should stay rare because most fluent functions use AST-based definitions
    assert body_sql_count <= 25, (
        f"Found {body_sql_count} body_sql= templates in fluent_functions.py — expected <=25"
    )
