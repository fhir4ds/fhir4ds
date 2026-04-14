"""
Audit macros for DuckDB — struct-based boolean + evidence propagation.

These macros are used by CQLToSQLTranslator(audit_mode=True) to propagate
evidence items through AND/OR/NOT connectives and to wrap scalar booleans.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

_EVIDENCE_STRUCT_TYPE = (
    'STRUCT(target VARCHAR, attribute VARCHAR, value VARCHAR, '
    'operator VARCHAR, threshold VARCHAR, trace VARCHAR[])[]'
)

AUDIT_MACROS_SQL = [
    # AND: merge evidence from both operands
    """CREATE OR REPLACE MACRO audit_and(a, b) AS (
        struct_pack(
            result   := struct_extract(a, 'result') AND struct_extract(b, 'result'),
            evidence := list_concat(
                COALESCE(struct_extract(a, 'evidence'), []),
                COALESCE(struct_extract(b, 'evidence'), [])
            )
        )
    )""",
    # OR (TRUE_BRANCH strategy — default): only true branch's evidence
    """CREATE OR REPLACE MACRO audit_or(a, b) AS (
        struct_pack(
            result   := struct_extract(a, 'result') OR struct_extract(b, 'result'),
            evidence := CASE
                WHEN struct_extract(a, 'result') THEN COALESCE(struct_extract(a, 'evidence'), [])
                WHEN struct_extract(b, 'result') THEN COALESCE(struct_extract(b, 'evidence'), [])
                ELSE list_concat(COALESCE(struct_extract(a, 'evidence'), []), COALESCE(struct_extract(b, 'evidence'), []))
            END
        )
    )""",
    # OR (ALL strategy): evidence from both branches regardless
    """CREATE OR REPLACE MACRO audit_or_all(a, b) AS (
        struct_pack(
            result   := struct_extract(a, 'result') OR struct_extract(b, 'result'),
            evidence := list_concat(
                COALESCE(struct_extract(a, 'evidence'), []),
                COALESCE(struct_extract(b, 'evidence'), [])
            )
        )
    )""",
    # NOT: invert result, preserve evidence
    """CREATE OR REPLACE MACRO audit_not(a) AS (
        struct_pack(
            result   := NOT struct_extract(a, 'result'),
            evidence := COALESCE(struct_extract(a, 'evidence'), [])
        )
    )""",
    # LEAF: wrap a scalar boolean with empty evidence
    f"""CREATE OR REPLACE MACRO audit_leaf(val) AS (
        struct_pack(
            result   := val,
            evidence := []::{_EVIDENCE_STRUCT_TYPE}
        )
    )""",
    # COMPARISON: capture comparison result with evidence (attribute, operands, operator)
    f"""CREATE OR REPLACE MACRO audit_comparison(result_val, op, lhs, rhs, ev_attr, target_id) AS (
        struct_pack(
            result   := result_val,
            evidence := list_value(struct_pack(
                target      := CAST(target_id AS VARCHAR),
                attribute   := CAST(ev_attr AS VARCHAR),
                value       := CAST(lhs AS VARCHAR),
                operator    := CAST(op AS VARCHAR),
                threshold   := CAST(rhs AS VARCHAR),
                trace       := CAST([] AS VARCHAR[])
            ))::{_EVIDENCE_STRUCT_TYPE}
        )
    )""",
    # COMPACT: Group evidence by (trace, attribute, operator, threshold)
    # This transforms a flat list of items into a list of logic groups with nested findings.
    # Uses DuckDB list_transform/list_filter/list_distinct to avoid UNNEST correlation issues.
    """CREATE OR REPLACE MACRO compact_audit(aud) AS (
        struct_pack(
            result := struct_extract(aud, 'result'),
            evidence := list_transform(
                list_distinct(list_transform(struct_extract(aud, 'evidence'), x -> {
                    'trace': x.trace,
                    'attribute': x.attribute,
                    'operator': x.operator,
                    'threshold': x.threshold
                })),
                g -> {
                    'trace': g.trace,
                    'attribute': g.attribute,
                    'operator': g.operator,
                    'threshold': g.threshold,
                    'findings': list_transform(
                        list_filter(struct_extract(aud, 'evidence'), x -> 
                            x.trace = g.trace AND 
                            x.attribute IS NOT DISTINCT FROM g.attribute AND 
                            x.operator = g.operator AND 
                            x.threshold IS NOT DISTINCT FROM g.threshold
                        ),
                        f -> {'target': f.target, 'value': f.value}
                    )
                }
            )
        )
    )""",
    # BREADCRUMB: Append a definition name to the trace of all evidence items.
    """CREATE OR REPLACE MACRO audit_breadcrumb(aud, def_name) AS (
        struct_pack(
            result := struct_extract(aud, 'result'),
            evidence := list_transform(
                COALESCE(struct_extract(aud, 'evidence'), []),
                _ev -> struct_pack(
                    target := _ev.target,
                    attribute := _ev.attribute,
                    value := _ev.value,
                    operator := _ev.operator,
                    threshold := _ev.threshold,
                    trace := list_append(COALESCE(_ev.trace, CAST([] AS VARCHAR[])), def_name)
                )
            )
        )
    )""",
]


def register_audit_macros(con: "duckdb.DuckDBPyConnection") -> None:
    """Register audit macros with a DuckDB connection."""
    for sql in AUDIT_MACROS_SQL:
        con.execute(sql)
