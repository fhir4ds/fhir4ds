"""v0.0.24 it7 (d3 SKEPTIC): stored-list define as a CQL query source.

`define L: {1,2}` followed by `L X where X = 1` previously lowered to
``SELECT * FROM "L" AS X`` — one row whose ``value`` column holds the
WHOLE list — so per-element predicates compared the list itself
(TRY_CAST([1,2] AS DOUBLE) -> NULL -> silently FALSE). The fix unnests
the stored list into one row per element with an element-value alias
binding. Covers scalar/tuple equality, tuple field navigation, Count
over a filtered stored list, and return+where combination.
"""
import unittest

import duckdb

from fhir4ds.cql import FHIRDataLoader, parse_cql
from fhir4ds.cql.duckdb import register
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

_PATIENT = {"resourceType": "Patient", "id": "p1", "birthDate": "1990-01-01"}


def _run_define_query(cql: str):
    con = duckdb.connect()
    register(con)
    FHIRDataLoader(con).load_resources([_PATIENT])
    lib = parse_cql(cql)
    translator = CQLToSQLTranslator(con)
    sql = translator.translate_library_to_population_sql(
        lib,
        output_columns={"R": "R"},
        parameters={"Measurement Period": ("2026-01-01", "2026-12-31")},
    )
    rows = con.execute(sql).fetchall()
    return rows[0][1] if rows else None


class TestStoredListQuerySource(unittest.TestCase):
    def test_scalar_where_over_stored_list_define(self):
        """exists(L X where X = 1) over define L: {1,2} must be TRUE."""
        value = _run_define_query(
            """
            library T using FHIR version '4.0.1'
            define L: { 1, 2 }
            define R: exists(L X where X = 1)
            """
        )
        self.assertIs(bool(value), True)

    def test_scalar_where_no_match_is_false(self):
        value = _run_define_query(
            """
            library T using FHIR version '4.0.1'
            define L: { 1, 2 }
            define R: exists(L X where X = 9)
            """
        )
        self.assertIs(bool(value), False)

    def test_tuple_equality_where_over_stored_list_define(self):
        value = _run_define_query(
            """
            library T using FHIR version '4.0.1'
            define L: { Tuple { a: 1 }, Tuple { a: 2 } }
            define R: exists(L X where X = Tuple { a: 1 })
            """
        )
        self.assertIs(bool(value), True)

    def test_tuple_field_navigation_where(self):
        """X.a property access on the element must bind the element VALUE."""
        value = _run_define_query(
            """
            library T using FHIR version '4.0.1'
            define L: { Tuple { a: 1 }, Tuple { a: 2 } }
            define R: exists(L X where X.a = 1)
            """
        )
        self.assertIs(bool(value), True)

    def test_count_over_filtered_stored_list_query(self):
        value = _run_define_query(
            """
            library T using FHIR version '4.0.1'
            define L: { 1, 2, 3 }
            define R: Count(L X where X > 1)
            """
        )
        self.assertEqual(int(value), 2)

    def test_return_and_where_combined(self):
        value = _run_define_query(
            """
            library T using FHIR version '4.0.1'
            define L: { 1, 2 }
            define R: exists(L X return X * 2 where X = 1)
            """
        )
        self.assertIs(bool(value), True)

    def test_plain_reference_unaffected(self):
        """exists(L) without a where keeps the pre-fix row semantics."""
        value = _run_define_query(
            """
            library T using FHIR version '4.0.1'
            define L: { 1, 2 }
            define R: exists(L)
            """
        )
        self.assertIs(bool(value), True)


if __name__ == "__main__":
    unittest.main()
