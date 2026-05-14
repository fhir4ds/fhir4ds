from fhir4ds.cql.translator.types import (
    CTEDefinition,
    SQLAlias,
    SQLBinaryOp,
    SQLFragment,
    SQLIdentifier,
    SQLExists,
    SQLJoin,
    SQLLiteral,
    SQLNull,
    SQLQualifiedIdentifier,
    SQLSelect,
    SQLSubquery,
)


def test_deduplicate_lateral_aliases_keeps_projection_stable():
    long_table_name = "Procedure: " + ("Anesthesia Procedure List " * 8).strip()
    repeated = SQLSubquery(
        query=SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["p", "resource"])],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name=long_table_name),
                alias="p",
                implicit_alias=True,
            ),
            where=SQLBinaryOp(
                left=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                operator="=",
                right=SQLQualifiedIdentifier(parts=["enc", "patient_id"]),
            ),
        )
    )
    where = SQLBinaryOp(
        left=SQLBinaryOp(left=repeated, operator="IS NOT", right=SQLNull()),
        operator="AND",
        right=SQLBinaryOp(left=repeated, operator="IS NOT", right=SQLNull()),
    )
    cte_query = SQLSelect(
        columns=[
            SQLQualifiedIdentifier(parts=["enc", "patient_id"]),
            SQLQualifiedIdentifier(parts=["enc", "resource"]),
        ],
        from_clause=SQLAlias(expr=SQLIdentifier(name="Encounter"), alias="enc", implicit_alias=True),
        joins=[SQLJoin(join_type="CROSS", table=SQLIdentifier(name="Other"), alias="o")],
        where=where,
    )
    fragment = SQLFragment(
        main_query=SQLSelect(columns=[SQLIdentifier(name="*")], from_clause=SQLIdentifier(name="Example")),
        ctes=[CTEDefinition(name="Example", query=cte_query)],
    )

    fragment.deduplicate_lateral_aliases(min_occurrences=2)
    sql = fragment.to_sql()

    cte_select = fragment.ctes[0].query
    assert len(cte_select.columns) == 2
    assert "CROSS JOIN LATERAL" in sql
    assert sql.count("Anesthesia Procedure List") == 8
    assert "_lat0.value IS NOT NULL AND _lat0.value IS NOT NULL" in sql


def test_deduplicate_lateral_aliases_recurses_inside_exists():
    long_table_name = "Procedure: " + ("Mechanical Ventilation " * 8).strip()
    repeated = SQLSubquery(
        query=SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["p", "resource"])],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name=long_table_name),
                alias="p",
                implicit_alias=True,
            ),
            where=SQLBinaryOp(
                left=SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                operator="=",
                right=SQLQualifiedIdentifier(parts=["enc", "patient_id"]),
            ),
        )
    )
    inner_where = SQLBinaryOp(
        left=SQLBinaryOp(left=repeated, operator="IS NOT", right=SQLNull()),
        operator="AND",
        right=SQLBinaryOp(left=repeated, operator="IS NOT", right=SQLNull()),
    )
    exists = SQLExists(
        subquery=SQLSubquery(
            query=SQLSelect(
                columns=[SQLLiteral(value=1)],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name="Observation"),
                    alias="obs",
                    implicit_alias=True,
                ),
                where=inner_where,
            )
        )
    )
    cte_query = SQLSelect(
        columns=[
            SQLQualifiedIdentifier(parts=["enc", "patient_id"]),
            SQLQualifiedIdentifier(parts=["enc", "resource"]),
        ],
        from_clause=SQLAlias(expr=SQLIdentifier(name="Encounter"), alias="enc", implicit_alias=True),
        where=exists,
    )
    fragment = SQLFragment(
        main_query=SQLSelect(columns=[SQLIdentifier(name="*")], from_clause=SQLIdentifier(name="Example")),
        ctes=[CTEDefinition(name="Example", query=cte_query)],
    )

    fragment.deduplicate_lateral_aliases(min_occurrences=2)
    sql = fragment.to_sql()

    cte_select = fragment.ctes[0].query
    assert len(cte_select.columns) == 2
    assert "EXISTS (SELECT 1 FROM Observation obs CROSS JOIN LATERAL" in sql
    assert sql.count("Mechanical Ventilation") == 8
    assert "_lat0.value IS NOT NULL AND _lat0.value IS NOT NULL" in sql


def test_deduplicate_lateral_aliases_rewrites_projection_expressions():
    long_table_name = "Observation: " + ("Carbon Dioxide Partial Pressure " * 8).strip()
    repeated = SQLSubquery(
        query=SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["obs", "resource"])],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name=long_table_name),
                alias="obs",
                implicit_alias=True,
            ),
            where=SQLBinaryOp(
                left=SQLQualifiedIdentifier(parts=["obs", "patient_id"]),
                operator="=",
                right=SQLQualifiedIdentifier(parts=["enc", "patient_id"]),
            ),
        )
    )
    cte_query = SQLSelect(
        columns=[
            SQLQualifiedIdentifier(parts=["enc", "patient_id"]),
            SQLAlias(
                expr=SQLBinaryOp(left=repeated, operator="=", right=repeated),
                alias="same_observation",
            ),
        ],
        from_clause=SQLAlias(expr=SQLIdentifier(name="Encounter"), alias="enc", implicit_alias=True),
    )
    fragment = SQLFragment(
        main_query=SQLSelect(columns=[SQLIdentifier(name="*")], from_clause=SQLIdentifier(name="Example")),
        ctes=[CTEDefinition(name="Example", query=cte_query)],
    )

    fragment.deduplicate_lateral_aliases(min_occurrences=2)
    sql = fragment.to_sql()

    cte_select = fragment.ctes[0].query
    assert len(cte_select.columns) == 2
    assert "FROM Encounter enc CROSS JOIN LATERAL" in sql
    assert sql.count("Carbon Dioxide Partial Pressure") == 8
    assert "_lat0.value = _lat0.value AS same_observation" in sql
