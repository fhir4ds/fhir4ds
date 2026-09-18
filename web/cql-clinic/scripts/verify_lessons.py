#!/usr/bin/env python3
"""Verify cql-clinic lessons: translate + execute each solution against its
fixtures using the same code path as the browser (native extension +
removeListExtractFhirpathWrappers postprocess), then write expected.json.

Usage: PYTHONPATH=/mnt/d/fhir4ds python3 scripts/verify_lessons.py
"""

import json
import sys
from pathlib import Path

import duckdb

LESSONS_DIR = Path(__file__).resolve().parent.parent / "src" / "lessons"


def remove_list_extract(sql: str) -> str:
    """Faithful port of pyodide.worker.ts removeListExtractFhirpathWrappers:
    rewrite list_extract(<expr containing fhirpath>, N) -> <expr>. Handles
    nesting (outer wrapper first) and skips string literals."""

    needle = "list_extract("
    result = sql
    changed = True
    while changed:
        changed = False
        out = ""
        pos = 0
        while pos < len(result):
            idx = result.find(needle, pos)
            if idx == -1:
                out += result[pos:]
                break
            depth = 0
            last_top_comma = -1
            i = idx + len(needle) - 1  # points at opening '('
            in_str = False
            q_char = ""
            while i < len(result):
                c = result[i]
                if in_str:
                    if c == q_char and result[i - 1] != "\\":
                        in_str = False
                elif c in ("'", '"'):
                    in_str = True
                    q_char = c
                elif c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        break
                elif c == "," and depth == 1:
                    last_top_comma = i
                i += 1
            if depth != 0 or last_top_comma == -1:
                out += result[pos : idx + 1]
                pos = idx + 1
                continue
            inner_expr = result[idx + len(needle) : last_top_comma].strip()
            # Only strip the LEGACY broken form list_extract(fhirpath_text(...), N).
            # list_extract(fhirpath(...), N) is CORRECT with the C++ UDF (JSON[]).
            if "fhirpath_text" in inner_expr.lower() and "fhirpath(" not in inner_expr.lower():
                out += result[pos:idx] + inner_expr
                result = out + result[i + 1 :]
                changed = True
                out = ""
                pos = 0
                continue
            out += result[pos : i + 1]
            pos = i + 1
        if not changed:
            result = out
    return result


def extract_patient_ref(res: dict) -> str | None:
    if res.get("resourceType") == "Patient":
        return res.get("id")
    for key in ("subject", "patient", "beneficiary"):
        ref = res.get(key)
        if isinstance(ref, dict) and isinstance(ref.get("reference"), str):
            seg = ref["reference"].split("/")[-1]
            return seg
    return None


def setup_connection(fixtures: list[dict]) -> duckdb.DuckDBPyConnection:
    from fhir4ds import register

    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    flags = register(con)
    if not flags.get("cql_cpp", False):
        print(f"  WARNING: cql_cpp=False (flags={flags}) — browser uses native ext", file=sys.stderr)
    con.execute(
        "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
    )
    for res in fixtures:
        con.execute(
            "INSERT INTO resources VALUES (?, ?, ?, ?)",
            [res["id"], res["resourceType"], json.dumps(res), extract_patient_ref(res)],
        )
    return con


def translate(cql: str) -> str:
    from fhir4ds.cql import parse_cql
    from fhir4ds.cql.translator import CQLToSQLTranslator

    library = parse_cql(cql)
    sql = CQLToSQLTranslator().translate_library_to_population_sql(library)
    return remove_list_extract(sql)


def normalize(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    # DuckDB structs / maps
    if hasattr(value, "items"):
        return {k: normalize(v) for k, v in value.items()}
    return str(value)


def verify_lesson(dir_path: Path) -> bool:
    meta = json.loads((dir_path / "lesson.json").read_text())
    fixtures = json.loads((dir_path / "fixtures.json").read_text())
    print(f"== {meta['id']}: {meta['title']}")

    # 1. Template should fail to parse (TODOs are intentional holes) OR translate
    #    incompletely — templates are not graded, just note behavior.
    template = (dir_path / "template.cql").read_text()
    from fhir4ds.cql import parse_cql
    from fhir4ds.cql.translator import CQLToSQLTranslator

    try:
        parse_cql(template)
        print("  note: template parses (comment-style TODOs); solution-only grading is unaffected")
    except Exception as exc:  # noqa: BLE001
        print(f"  template parse fails as expected: {type(exc).__name__}")

    # 2. Translate + execute the solution.
    solution = (dir_path / "solution.cql").read_text()
    sql = translate(solution)
    (dir_path / "generated.sql").write_text(sql)

    con = setup_connection(fixtures)
    try:
        result = con.execute(sql)
        cols = [d[0] for d in result.description]
        rows = {}
        for row in result.fetchall():
            # First column is patient_id
            pid = str(row[0])
            rows[pid] = [normalize(v) for v in row[1:]]
        expected = {"columns": cols[1:], "rows": rows}
        (dir_path / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
        print(f"  OK: {len(cols) - 1} defines, {len(rows)} patients -> expected.json")
        for pid, vals in rows.items():
            print(f"    {pid}: {vals}")
        return True
    finally:
        con.close()


def main() -> int:
    from fhir4ds.cql import parse_cql  # noqa: F401  (import check)

    failures = []
    for dir_path in sorted(LESSONS_DIR.iterdir()):
        if not (dir_path / "solution.cql").exists():
            continue
        try:
            ok = verify_lesson(dir_path)
            if not ok:
                failures.append(dir_path.name)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
            failures.append(dir_path.name)
    if failures:
        print(f"\nFAILED lessons: {failures}", file=sys.stderr)
        return 1
    print("\nAll lessons verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
