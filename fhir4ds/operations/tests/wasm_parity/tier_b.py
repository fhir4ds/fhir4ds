"""Tier B: the thin real-browser audit (FEATURE_WASM_PARITY_TEST_INFRA.md §4.6).

Step 0 proves the *contract* and Tier A proves corpus parity, both on desktop DuckDB against
the simulated browser surface. Tier B boots the real engine — duckdb-wasm plus the SHIPPED
wasm bundles and the reference macros — and checks what only the real engine can show:

* B1  the real catalog: macro bodies equal the simulation, and the exact list of x86-bundle
      functions the shipped wasm bundles lack (the staleness list);
* B2  version pins: engine version == manifest ABI == npm package;
* B3  curated case families: value and type equal desktop;
* B4  the Arrow transport under the apps' ``castBigIntToDouble`` flag vs the text path;
* B5  opt-in (``FHIR4DS_WASM_FULL_CORPUS=1``): the whole CQL corpus on the real engine.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from . import surfaces
from .evaluators import (
    BOTH_FAIL,
    BROWSER_ONLY_PASS,
    ENGINE_DIFF,
    GREEN,
    PARITY_GAP,
    CaseOutcome,
    SuiteResult,
    suspects_for,
)
from .real_engine import RealConnection, plain
from .shipped_bundles import load_manifest

SUITE = "real"
FULL_CORPUS_ENV = "FHIR4DS_WASM_FULL_CORPUS"
STALE_KIND = "STALE_WASM_FUNCTION"

# ----------------------------------------------------------------------------------------------
# B1 / B2 facts
# ----------------------------------------------------------------------------------------------


def staleness(real: Any, sim: Any) -> tuple[frozenset[str], frozenset[str]]:
    """``(x86_only, wasm_only)``: names one bundle set has and the other lacks.

    ``x86_only`` is the exact staleness list: a function the desktop bundles provide that the
    shipped wasm bundles do not is a Catalog Error in every browser app.
    """
    x86_extension = surfaces.extension_names(sim)
    real_names = real.names()
    return x86_extension - real_names, real_names - frozenset(surfaces.catalog(sim))


def macro_parity(real: Any, sim: Any) -> dict[str, list[str]]:
    """Compare the real macro catalog with the simulation's."""
    real_defs = real.macro_definitions()
    sim_defs = surfaces.macro_definitions(sim)
    return {
        "real_only": sorted(set(real_defs) - set(sim_defs)),
        "sim_only": sorted(set(sim_defs) - set(real_defs)),
        "body_diff": sorted(
            name for name in set(real_defs) & set(sim_defs) if real_defs[name] != sim_defs[name]
        ),
    }


def versions(real: Any, node_modules: Any) -> dict[str, str]:
    """Engine version, manifest ABI, manifest package pin, installed npm package."""
    manifest = load_manifest()
    package = json.loads(
        (node_modules / "@duckdb" / "duckdb-wasm" / "package.json").read_text()
    )["version"]
    return {
        "engine": real.version,
        "manifest_abi": manifest["duckdb_abi"],
        "manifest_package": manifest["duckdb_wasm_version"],
        "installed_package": package,
    }


# ----------------------------------------------------------------------------------------------
# B3 curated families
# ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    family: str
    name: str
    expression: str


PATIENT = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p1",
        "gender": "male",
        "birthDate": "1980-01-02",
        "active": True,
        "name": [{"family": "Chalmers", "given": ["John", "James"]}],
        "multipleBirthInteger": 2,
    }
)

def _udf(udf: str, path: str) -> str:
    """``<udf>('<PATIENT>', '<path>')`` as SQL text (embedded quotes doubled)."""
    return f"{udf}('{PATIENT}', '{path.replace(chr(39), chr(39) * 2)}')"


_FAMILIES: dict[str, list[tuple[str, str]]] = {
    "list": [
        ("distinct", '"Distinct"([1, 2, 2, 3])'),
        ("contains", '"Contains"([1, 2, 3], 2)'),
        ("index-of", "CQLIndexOf([1, 2, 3], 2)"),
        ("skip", '"Skip"([1, 2, 3], 1)'),
        ("take", '"Take"([1, 2, 3], 2)'),
        ("tail", '"Tail"([1, 2, 3])'),
        ("length", '"Length"([1, 2, 3])'),
        ("element-equal", '"CQLListElementEqual"(1, 1)'),
        ("native-intersect", "list_intersect([1, 2, 3], [2, 3, 4])"),
        ("native-union", "list_union([1, 2], [2, 3])"),
        ("native-except", "list_except([1, 2, 3], [2])"),
        ("native-distinct", "list_distinct([1, 2, 2])"),
        ("native-transform", "list_transform([1, 2, 3], x -> x + 1)"),
        ("native-filter", "list_filter([1, 2, 3], x -> x % 2 = 1)"),
        ("native-reduce", "list_reduce([1, 2, 3], (a, b) -> a + b)"),
        ("native-slice", "list_slice([1, 2, 3, 4], 2, 3)"),
        ("native-sum", "list_sum([1, 2, 3])"),
    ],
    "interval": [
        ("from-bounds-int", "intervalFromBounds('1', '5', true, true)"),
        ("from-bounds-date", "intervalFromBounds('2024-01-01', '2024-01-31', true, true)"),
        ("contains", "intervalContains(intervalFromBounds('1', '5', true, true), '3')"),
        ("overlaps", "intervalOverlaps(intervalFromBounds('1', '5', true, true), intervalFromBounds('4', '8', true, true))"),
        ("meets", "intervalMeets(intervalFromBounds('1', '5', true, true), intervalFromBounds('6', '8', true, true))"),
        ("includes", "intervalIncludes(intervalFromBounds('1', '8', true, true), intervalFromBounds('2', '3', true, true))"),
        ("start", "intervalStart(intervalFromBounds('2024-01-01', '2024-01-31', true, true))"),
        ("end", "intervalEnd(intervalFromBounds('2024-01-01', '2024-01-31', true, true))"),
        ("width", "intervalWidth(intervalFromBounds('1', '5', true, true))"),
        ("intersect", "intervalIntersect(intervalFromBounds('1', '5', true, true), intervalFromBounds('4', '8', true, true))"),
        ("except", "intervalExcept(intervalFromBounds('1', '5', true, true), intervalFromBounds('2', '3', true, true))"),
        ("union", "intervalUnion(intervalFromBounds('1', '5', true, true), intervalFromBounds('4', '8', true, true))"),
        (
            "collapse",
            "collapse_intervals('[{\"low\":\"2024-01-01\",\"high\":\"2024-01-10\",\"lowClosed\":true,"
            "\"highClosed\":true},{\"low\":\"2024-01-05\",\"high\":\"2024-01-20\",\"lowClosed\":true,"
            "\"highClosed\":true}]')",
        ),
        ("native-interval", "(DATE '2024-01-31' + INTERVAL 1 MONTH)::VARCHAR"),
        ("native-datediff", "datediff('day', DATE '2024-01-01', DATE '2024-02-01')"),
        ("native-trunc", "date_trunc('month', TIMESTAMP '2024-03-15 10:00:00')"),
    ],
    "string": [
        ("position-of", '"PositionOf"(\'a\', \'banana\')'),
        ("last-position-of", '"LastPositionOf"(\'a\', \'banana\')'),
        ("substring", '"Substring"(\'hello\', 1, 3)'),
        ("substring-len", '"SubstringLen"(\'hello\', 1, 3)'),
        ("starts-with", '"StartsWith"(\'hello\', \'he\')'),
        ("ends-with", '"EndsWith"(\'hello\', \'lo\')'),
        ("matches", '"Matches"(\'abc\', \'^a\')'),
        ("replace-matches", '"ReplaceMatches"(\'abc\', \'b\', \'X\')'),
        ("split-on-matches", '"SplitOnMatches"(\'a1b2\', \'[0-9]\')'),
        ("upper", '"Upper"(\'aé\')'),
        ("lower", '"Lower"(\'AÉ\')'),
        ("trim", '"Trim"(\'  a  \')'),
        ("replace", '"Replace"(\'abc\', \'b\', \'X\')'),
        ("split", '"Split"(\'a,b\', \',\')'),
        ("length", '"Length"(\'héllo\')'),
        ("indexer", '"Indexer"(\'abc\', 1)'),
        ("combine", '"Combine"([\'a\', \'b\'])'),
        ("combine-sep", '"CombineSep"([\'a\', \'b\'], \'-\')'),
        ("concat", '"Concat"(\'a\', \'b\')'),
        ("left", '"Left"(\'abc\', 2)'),
        ("native-regexp", "regexp_replace(\'abc123\', \'[0-9]+\', \'#\')"),
        ("native-split", "string_split(\'a,b,c\', \',\')"),
        ("native-position", "strpos(\'banana\', \'na\')"),
    ],
    "logical": [
        ("and-null", '"And"(TRUE, NULL)'),
        ("or-null", '"Or"(NULL, TRUE)'),
        ("not-null", '"Not"(NULL)'),
        ("implies", '"Implies"(FALSE, NULL)'),
        ("xor", '"Xor"(TRUE, TRUE)'),
        ("is-null", '"IsNull"(NULL)'),
        ("is-not-null", '"IsNotNull"(1)'),
        ("is-true-null", '"IsTrue"(NULL)'),
        ("is-false", '"IsFalse"(FALSE)'),
        ("if-null", '"IfNull"(NULL, 2)'),
        ("coalesce", '"Coalesce"(NULL, 1)'),
        ("all-true", '"AllTrue"([true, false])'),
        ("any-true", '"AnyTrue"([true, false])'),
        ("all-false", '"AllFalse"([true, false])'),
        ("any-false", '"AnyFalse"([true, false])'),
        ("native-3vl", "(NULL AND TRUE) OR NOT (FALSE)"),
    ],
    "fhirpath_udf": [
        ("list-nav", _udf("fhirpath", "name.given")),
        ("text", _udf("fhirpath_text", "name.family")),
        ("number", _udf("fhirpath_number", "multipleBirthInteger")),
        ("bool", _udf("fhirpath_bool", "gender = 'male'")),
        ("json", _udf("fhirpath_json", "name")),
        ("date", _udf("fhirpath_date", "birthDate")),
        ("is-valid", "fhirpath_is_valid('gender')"),
        ("count", _udf("fhirpath_text", "name.given.count()")),
        ("where", _udf("fhirpath_text", "name.where(family = 'Chalmers').family")),
    ],
    "audit_structs": [
        ("leaf", "audit_leaf(1)::VARCHAR"),
        ("and", "audit_and(audit_leaf(TRUE), audit_leaf(FALSE))::VARCHAR"),
        ("or", "audit_or(audit_leaf(NULL), audit_leaf(TRUE))::VARCHAR"),
        ("or-all", "audit_or_all(audit_leaf(FALSE), audit_leaf(NULL))::VARCHAR"),
        ("not", "audit_not(audit_leaf(TRUE))::VARCHAR"),
        ("breadcrumb", "audit_breadcrumb(audit_leaf(1), 'Def')::VARCHAR"),
        ("patient-property", "audit_patient_property(5, 'p1', 'value', 5)::VARCHAR"),
        ("comparison", "audit_comparison(TRUE, '>=', 5, 3, 'value', 'o1')::VARCHAR"),
    ],
}

_VIEWDEF = {
    "resource": "Patient",
    "select": [
        {"column": [{"name": "id", "path": "id"}, {"name": "gender", "path": "gender"}]},
        {
            "forEach": "name",
            "column": [{"name": "family", "path": "family"}, {"name": "given", "path": "given.first()"}],
        },
    ],
}
_VIEW_ROWS = [
    {"resourceType": "Patient", "id": "p1", "gender": "male", "name": [{"family": "A", "given": ["Joel"]}]},
    {"resourceType": "Patient", "id": "p2", "gender": "female", "name": [{"family": "B"}]},
    {
        "resourceType": "Patient",
        "id": "p3",
        "name": [{"family": "C", "given": ["X", "Y"]}, {"family": "D", "given": ["Z"]}],
    },
]
_VIEW_COLUMNS = ("id", "gender", "family", "given")


def viewdefinition_statements() -> list[str]:
    """CREATE TABLE, the INSERTs and the final SELECT (last) for one generated ViewDefinition."""
    from fhir4ds.viewdef import SQLGenerator, parse_view_definition

    sql = SQLGenerator(strict_collection=True, source_table="patients").generate(
        parse_view_definition(json.dumps(_VIEWDEF))
    )
    quoted = ", ".join(f"{column}::VARCHAR AS {column}" for column in _VIEW_COLUMNS)
    order = ", ".join(_VIEW_COLUMNS)
    return [
        "CREATE OR REPLACE TABLE patients (id VARCHAR, resourceType VARCHAR, resource JSON, "
        "patient_ref VARCHAR)",
        *[f"INSERT INTO patients VALUES ('{row['id']}', 'Patient', '{json.dumps(row)}', '{row['id']}')" for row in _VIEW_ROWS],
        f"SELECT {quoted} FROM ({sql}) AS _view ORDER BY {order}",
    ]


def curated_cases(contract: Any) -> tuple[list[Case], dict[str, list[str]]]:
    """``(cases, skipped_by_family)``.

    Only expressions whose every name the browser contract provides are evaluated: a missing
    name is Tier A's finding (T5), already registered. What is left isolates names that exist
    in the browser but behave differently.
    """
    from fhir4ds.operations.tests import wasm_surface_harness

    available = contract.browser_names - set(contract.stale_wasm_functions)
    cases: list[Case] = []
    skipped: dict[str, list[str]] = {}
    candidates = [
        *(
            Case("conversion", f"case{i}", case.expression)
            for i, case in enumerate(
                [
                    *wasm_surface_harness.CLASS_A_CASES,
                    *wasm_surface_harness.CLASS_B_CASES,
                    *wasm_surface_harness.CLASS_B_BOUNDARY_CASES,
                    *wasm_surface_harness.CLASS_B_SCALAR_CASES,
                ]
            )
        ),
        *(
            Case(family, name, expression)
            for family, rows in _FAMILIES.items()
            for name, expression in rows
        ),
    ]
    for case in candidates:
        missing = surfaces.emitted_names(case.expression) - available
        if missing:
            skipped.setdefault(case.family, []).append(f"{case.name}: {sorted(missing)}")
        else:
            cases.append(case)
    return cases, skipped


def _first_line(exc: BaseException, limit: int = 300) -> str:
    return " ".join(str(exc).split("\n")[0].split())[:limit]


def _typed_desktop(con: Any, expressions: list[str]) -> list[tuple[str | None, str | None, str | None]]:
    out = []
    for expr in expressions:
        try:
            row = con.execute(
                f"SELECT ({expr})::VARCHAR AS value, typeof(({expr})) AS type"
            ).fetchone()
            out.append((row[0], row[1], None))
        except Exception as exc:  # noqa: BLE001 - an execution error is the finding
            out.append((None, None, _first_line(exc)))
    return out


def _outcome(case: Case, sql: str, run_d: tuple, run_b: tuple, contract: Any) -> CaseOutcome:
    text_d, type_d, error_d = run_d
    text_b, type_b, error_b = run_b
    case_id = f"{SUITE}::{case.family}::{case.name}"
    if error_d is not None and error_b is not None:
        outcome, detail = BOTH_FAIL, f"both error: desktop={error_d!r} browser={error_b!r}"
    elif error_d is not None:
        outcome, detail = BROWSER_ONLY_PASS, error_d
    elif error_b is not None:
        outcome, detail = PARITY_GAP, error_b
    elif text_d == text_b and type_d == type_b:
        outcome, detail = GREEN, ""
    else:
        outcome = ENGINE_DIFF
        if text_d == text_b:
            detail = f"type: desktop={type_d} browser={type_b}"
        else:
            detail = f"value: desktop={str(text_d)[:120]!r} browser={str(text_b)[:120]!r}"
    suspects, missing = suspects_for(sql, contract)
    return CaseOutcome(case_id, outcome, "ok", "ok", detail, suspects, missing)


def run(desktop: Any, real: Any, contract: Any, *, families: list[str] | None = None) -> SuiteResult:
    """B3: evaluate the curated families on desktop and on the real engine."""
    started = perf_counter()
    cases, _ = curated_cases(contract)
    if families:
        cases = [case for case in cases if case.family in families]
    expressions = [case.expression for case in cases]
    desktop_runs = _typed_desktop(desktop, expressions)
    real_runs = real.typed(expressions)
    outcomes = [
        _outcome(case, case.expression, run_d, run_b, contract)
        for case, run_d, run_b in zip(cases, desktop_runs, real_runs, strict=True)
    ]
    if not families or "viewdef" in families:
        outcomes.append(_viewdef_outcome(desktop, real, contract))
    return SuiteResult(SUITE, tuple(outcomes), 0, perf_counter() - started, "real")


def _viewdef_outcome(desktop: Any, real: Any, contract: Any) -> CaseOutcome:
    """One generated ViewDefinition SQL, run end to end on both engines (CREATE, INSERT, SELECT)."""
    statements = viewdefinition_statements()
    try:
        for statement in statements[:-1]:
            desktop.execute(statement)
        rows_d = sorted(tuple(map(str, row)) for row in desktop.execute(statements[-1]).fetchall())
        run_d = (json.dumps(rows_d), "rows", None)
    except Exception as exc:  # noqa: BLE001 - an execution error is the finding
        run_d = (None, None, _first_line(exc))
    results = real.run([("stmt", statement) for statement in statements])
    final = results[-1]
    if final["ok"]:
        rows_b = sorted(
            tuple(str(plain(value)) for value in row.values()) for row in final["rows"]
        )
        run_b = (json.dumps(rows_b), "rows", None)
    else:
        failed = next((r["error"] for r in results if not r["ok"]), final.get("error"))
        run_b = (None, None, failed)
    return _outcome(
        Case("viewdef", "patient_names", " ".join(statements)),
        " ".join(statements),
        run_d,
        run_b,
        contract,
    )


# ----------------------------------------------------------------------------------------------
# B4 Arrow transport
# ----------------------------------------------------------------------------------------------

# (label, sql, expected Arrow value as the harness tags it)
TRANSPORT_PROBES: tuple[tuple[str, str, list], ...] = (
    ("int32", "2147483647", ["number", 2147483647]),
    ("bigint-2^53", "9007199254740992::BIGINT", ["number", 9007199254740992]),
    ("bigint-2^53+1", "9007199254740993::BIGINT", ["number", 9007199254740992]),
    ("ubigint-max", "18446744073709551615::UBIGINT", ["number", 18446744073709552000]),
    ("double", "0.1::DOUBLE", ["number", 0.1]),
    ("varchar", "'1.5'", ["string", "1.5"]),
    ("boolean", "TRUE", ["boolean", True]),
    ("date", "DATE '2024-01-31'", ["number", 1706659200000]),
    (
        "decimal-unscaled",
        "1.50::DECIMAL(4,2)",
        ["object", {"0": ["number", 150], "1": ["number", 0], "2": ["number", 0], "3": ["number", 0]}],
    ),
    (
        "hugeint-limbs",
        "170141183460469231731687303715884105727::HUGEINT",
        [
            "object",
            {
                "0": ["number", 4294967295],
                "1": ["number", 4294967295],
                "2": ["number", 4294967295],
                "3": ["number", 2147483647],
            },
        ],
    ),
)
# The envelope the pins above describe, for the report:
TRANSPORT_ENVELOPE = (
    "Exact through Arrow: INTEGER, BIGINT/UBIGINT up to 2^53, DOUBLE, VARCHAR, BOOLEAN. "
    "Lossy: BIGINT/UBIGINT beyond 2^53 round silently; HUGEINT and DECIMAL arrive as the "
    "UNSCALED 128-bit value (four 32-bit limbs) with the scale dropped; DATE/TIMESTAMP arrive "
    "as milliseconds. Move values as ::VARCHAR (+ typeof) or rescale explicitly."
)


def transport(desktop: Any, real: Any) -> list[dict[str, Any]]:
    """One record per probe: the text path (desktop and browser) and the Arrow path."""
    sqls = [sql for _, sql, _ in TRANSPORT_PROBES]
    text_d = _typed_desktop(desktop, sqls)
    text_b = real.typed(sqls)
    raw = real.raw(sqls)
    return [
        {
            "label": label,
            "sql": sql,
            "expected_arrow": expected,
            "desktop_text": text_d[i][0],
            "desktop_type": text_d[i][1],
            "desktop_error": text_d[i][2],
            "browser_text": text_b[i][0],
            "browser_type": text_b[i][1],
            "browser_error": text_b[i][2],
            "arrow": json.loads(raw[i][0]) if raw[i][0] is not None else None,
            "arrow_type": raw[i][1],
            "arrow_error": raw[i][2],
        }
        for i, (label, sql, expected) in enumerate(TRANSPORT_PROBES)
    ]


# ----------------------------------------------------------------------------------------------
# B5 opt-in whole corpus
# ----------------------------------------------------------------------------------------------


def full_corpus(desktop: Any, real: Any, contract: Any) -> SuiteResult:
    """The CQL corpus with the browser side evaluated on the real engine (batched)."""
    from .evaluators import cql

    return dataclasses.replace(cql.run(desktop, RealConnection(real), contract), surface="real")
