"""v0.0.24 it8 (d3 HISTORIAN): interval-typed query-alias elements.

`{Interval[1,5], Interval[10,15]} I where I contains 3` (and the `3 in I`
mirror, inline or through a stored-list define) previously fell through
to DuckDB STRING contains — the bare alias element carries no interval
SQL shape, so contains/in lost interval routing and binder-errored (or
would silently substring-match when arg types aligned). The alias source
AST now drives interval recognition.
"""
import unittest

import duckdb

from fhir4ds.cql import FHIRDataLoader, parse_cql
from fhir4ds.cql.duckdb import register
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

_PATIENT = {"resourceType": "Patient", "id": "p1", "birthDate": "1990-01-01"}


def _run(cql: str):
    con = duckdb.connect()
    register(con)
    FHIRDataLoader(con).load_resources([_PATIENT])
    sql = CQLToSQLTranslator(con).translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={"R": "R"},
        parameters={"Measurement Period": ("2026-01-01", "2026-12-31")},
    )
    rows = con.execute(sql).fetchall()
    return rows[0][1] if rows else None


class TestIntervalAliasElements(unittest.TestCase):
    def test_inline_interval_contains(self):
        v = _run(
            "library T using FHIR version '4.0.1'\n"
            "define R: exists({ Interval[1, 5], Interval[10, 15] } I "
            "where I contains 3)"
        )
        self.assertIs(bool(v), True)

    def test_inline_interval_contains_no_match(self):
        v = _run(
            "library T using FHIR version '4.0.1'\n"
            "define R: exists({ Interval[1, 5], Interval[10, 15] } I "
            "where I contains 7)"
        )
        self.assertIs(bool(v), False)

    def test_inline_point_in_interval_element(self):
        v = _run(
            "library T using FHIR version '4.0.1'\n"
            "define R: exists({ Interval[1, 5] } I where 3 in I)"
        )
        self.assertIs(bool(v), True)

    def test_stored_list_interval_contains(self):
        v = _run(
            "library T using FHIR version '4.0.1'\n"
            "define L: { Interval[1, 5], Interval[10, 15] }\n"
            "define R: exists(L I where I contains 3)"
        )
        self.assertIs(bool(v), True)

    def test_stored_list_point_in_interval_element(self):
        v = _run(
            "library T using FHIR version '4.0.1'\n"
            "define L: { Interval[1, 5], Interval[10, 15] }\n"
            "define R: exists(L I where 12 in I)"
        )
        self.assertIs(bool(v), True)

    def test_stored_list_count_over_interval_where(self):
        v = _run(
            "library T using FHIR version '4.0.1'\n"
            "define L: { Interval[1, 5], Interval[10, 15] }\n"
            "define R: Count(L I where I contains 3)"
        )
        self.assertEqual(int(v), 1)

    def test_string_element_contains_still_string(self):
        """String elements over the same alias machinery keep string contains."""
        v = _run(
            "library T using FHIR version '4.0.1'\n"
            "define R: exists({ 'abc', 'bcd' } S where S contains 'ab')"
        )
        self.assertIs(bool(v), True)

    def test_scalar_element_membership_control(self):
        v = _run(
            "library T using FHIR version '4.0.1'\n"
            "define R: exists({ 1, 2 } S where S in {1, 2})"
        )
        self.assertIs(bool(v), True)


if __name__ == "__main__":
    unittest.main()
