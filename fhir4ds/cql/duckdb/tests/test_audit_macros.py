"""Tests for audit macros — audit_and, audit_or, audit_not, audit_or_all, audit_leaf."""

import duckdb
import pytest

from ..macros.audit import register_audit_macros


@pytest.fixture
def conn():
    """DuckDB in-memory connection with audit macros registered."""
    con = duckdb.connect(":memory:")
    register_audit_macros(con)
    yield con
    con.close()


def _ev(target: str = "x", operator: str = "exists", threshold: str = "E") -> str:
    """Build an evidence struct_pack literal."""
    return (
        f"struct_pack(target:='{target}', attribute:=CAST(NULL AS VARCHAR), "
        f"value:=CAST(NULL AS VARCHAR), operator:='{operator}', threshold:='{threshold}', "
        f"trace:=CAST([] AS VARCHAR[]))"
    )


def _audit_struct(result: bool, evidence_sql: str) -> str:
    """Build an audit struct literal."""
    r = "true" if result else "false"
    return f"struct_pack(result:={r}, evidence:=[{evidence_sql}])"


class TestAuditAnd:
    def test_merges_evidence(self, conn):
        a = _audit_struct(True, _ev("x"))
        b = _audit_struct(True, _ev("y"))
        row = conn.execute(f"SELECT audit_and({a}, {b})").fetchone()[0]
        assert row["result"] is True
        assert len(row["evidence"]) == 2
        ids = {e["target"] for e in row["evidence"]}
        assert ids == {"x", "y"}

    def test_false_result(self, conn):
        a = _audit_struct(True, _ev("x"))
        b = _audit_struct(False, _ev("y"))
        row = conn.execute(f"SELECT audit_and({a}, {b})").fetchone()[0]
        assert row["result"] is False
        assert len(row["evidence"]) == 2


class TestAuditOr:
    def test_short_circuits_true_branch(self, conn):
        a = _audit_struct(True, _ev("x"))
        b = _audit_struct(False, _ev("y"))
        row = conn.execute(f"SELECT audit_or({a}, {b})").fetchone()[0]
        assert row["result"] is True
        # Only true branch evidence
        assert len(row["evidence"]) == 1
        assert row["evidence"][0]["target"] == "x"

    def test_second_branch_true(self, conn):
        a = _audit_struct(False, _ev("x"))
        b = _audit_struct(True, _ev("y"))
        row = conn.execute(f"SELECT audit_or({a}, {b})").fetchone()[0]
        assert row["result"] is True
        assert len(row["evidence"]) == 1
        assert row["evidence"][0]["target"] == "y"

    def test_both_false_merges(self, conn):
        a = _audit_struct(False, _ev("x"))
        b = _audit_struct(False, _ev("y"))
        row = conn.execute(f"SELECT audit_or({a}, {b})").fetchone()[0]
        assert row["result"] is False
        assert len(row["evidence"]) == 2


class TestAuditOrAll:
    def test_returns_both_branches(self, conn):
        a = _audit_struct(True, _ev("x"))
        b = _audit_struct(False, _ev("y"))
        row = conn.execute(f"SELECT audit_or_all({a}, {b})").fetchone()[0]
        assert row["result"] is True
        assert len(row["evidence"]) == 2


class TestAuditNot:
    def test_inverts_result(self, conn):
        a = _audit_struct(True, _ev("x"))
        row = conn.execute(f"SELECT audit_not({a})").fetchone()[0]
        assert row["result"] is False
        assert len(row["evidence"]) == 1

    def test_preserves_evidence(self, conn):
        a = _audit_struct(False, _ev("x"))
        row = conn.execute(f"SELECT audit_not({a})").fetchone()[0]
        assert row["result"] is True
        assert row["evidence"][0]["target"] == "x"


class TestAuditLeaf:
    def test_true_empty_evidence(self, conn):
        row = conn.execute("SELECT audit_leaf(true)").fetchone()[0]
        assert row["result"] is True
        assert row["evidence"] == []

    def test_false_empty_evidence(self, conn):
        row = conn.execute("SELECT audit_leaf(false)").fetchone()[0]
        assert row["result"] is False
        assert row["evidence"] == []

    def test_null_result(self, conn):
        row = conn.execute("SELECT audit_leaf(NULL::BOOLEAN)").fetchone()[0]
        assert row["result"] is None
        assert row["evidence"] == []


class TestAuditComparison:
    def test_true_comparison(self, conn):
        row = conn.execute(
            "SELECT audit_comparison(9.2 > 7.0, '>', 9.2, 7.0, 'value.ofType(Quantity).value', NULL)"
        ).fetchone()[0]
        assert row["result"] is True
        assert len(row["evidence"]) == 1
        ev = row["evidence"][0]
        assert ev["attribute"] == "value.ofType(Quantity).value"
        assert ev["value"] == "9.2"
        assert ev["operator"] == ">"
        assert ev["threshold"] == "7.0"
        assert ev["trace"] == []
        assert ev["target"] is None

    def test_false_comparison(self, conn):
        row = conn.execute(
            "SELECT audit_comparison(3.0 > 7.0, '>', 3.0, 7.0, 'value.ofType(Quantity).value', NULL)"
        ).fetchone()[0]
        assert row["result"] is False
        assert len(row["evidence"]) == 1
        ev = row["evidence"][0]
        assert ev["value"] == "3.0"

    def test_null_attribute(self, conn):
        row = conn.execute(
            "SELECT audit_comparison(true, '=', 'a', 'a', NULL, NULL)"
        ).fetchone()[0]
        assert row["result"] is True
        assert len(row["evidence"]) == 1
        ev = row["evidence"][0]
        assert ev["attribute"] is None
        assert ev["target"] is None

    def test_null_operands(self, conn):
        row = conn.execute(
            "SELECT audit_comparison(NULL::BOOLEAN, '=', NULL, NULL, NULL, NULL)"
        ).fetchone()[0]
        assert row["result"] is None
        assert len(row["evidence"]) == 1

    def test_target_populated(self, conn):
        """When target_id is provided, it populates the target field."""
        row = conn.execute(
            "SELECT audit_comparison(9.2 > 7.0, '>', 9.2, 7.0, 'value', 'Observation/bp-123')"
        ).fetchone()[0]
        assert row["result"] is True
        ev = row["evidence"][0]
        assert ev["target"] == "Observation/bp-123"
        assert ev["value"] == "9.2"


class TestTraceFieldPassthrough:
    """Verify that the trace field passes through audit_and/or/not without loss."""

    def _ev_with_trace(self, target: str, trace_list: list[str]) -> str:
        """Build evidence struct_pack with populated trace."""
        trace_sql = ", ".join(f"'{v}'" for v in trace_list)
        return (
            f"struct_pack(target:='{target}', attribute:=CAST(NULL AS VARCHAR), "
            f"value:=CAST(NULL AS VARCHAR), operator:='exists', threshold:='E', "
            f"trace:=CAST([{trace_sql}] AS VARCHAR[]))"
        )

    def test_and_preserves_trace(self, conn):
        a = _audit_struct(True, self._ev_with_trace("x", ["DefA"]))
        b = _audit_struct(True, self._ev_with_trace("y", ["DefB", "DefC"]))
        row = conn.execute(f"SELECT audit_and({a}, {b})").fetchone()[0]
        assert row["evidence"][0]["trace"] == ["DefA"]
        assert row["evidence"][1]["trace"] == ["DefB", "DefC"]

    def test_or_preserves_trace(self, conn):
        a = _audit_struct(True, self._ev_with_trace("x", ["Numerator"]))
        b = _audit_struct(False, self._ev_with_trace("y", []))
        row = conn.execute(f"SELECT audit_or({a}, {b})").fetchone()[0]
        assert row["evidence"][0]["trace"] == ["Numerator"]

    def test_not_preserves_trace(self, conn):
        a = _audit_struct(True, self._ev_with_trace("x", ["IP", "Denom"]))
        row = conn.execute(f"SELECT audit_not({a})").fetchone()[0]
        assert row["evidence"][0]["trace"] == ["IP", "Denom"]
