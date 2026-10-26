"""Generic view-composition runner (manifest-driven).

Composes families of ViewDefinitions into a schema of DuckDB views,
driven entirely by a composition manifest — no family-specific logic
lives here. The OMOP mapping (``omop_runner``) is one consumer; future
view families (CQL 2.0 surfaces, US Core test views, CDM v5.4 variants)
compose through the same primitives.

Manifest schema (the OMOP ``manifest.json`` shape):

- ``views``: stem -> one-line description (the inventory; stems are
  file names under the manifest's directory minus ``.json``).
- ``unions``: target table -> ordered list of child view stems; the
  runner materializes each child then a table-level ``UNION ALL``.
- ``projections`` (optional): table -> projection rules the runner
  applies over the composed result:
  - ``hash_keys``: natural-key string columns projected to positive
    63-bit integer hashes (``hash(col) & 2^63-1``) — stable,
    referentially consistent ids.
  - ``defaults``: column -> literal default applied via COALESCE with a
    TRY_CAST to BIGINT (e.g. concept ids defaulting to 0 = no-map).
- ``view_schema`` (optional): schema for materialized views (default
  ``omop``).
- ``materialize`` (optional): extra single views to materialize as
  join targets WITHOUT a composed table (e.g. the flattened
  conceptmap). Entries map join-target view name -> VD stem.

Spec grounding: SQLView-notes — "each referenced result acts as a
virtual table for the referencing query"; "The executing engine may
materialise the view's result or inline it; either approach conforms
to this specification."
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from .parser import parse_view_definition
from .generator import SQLGenerator

_HASH_MASK = "9223372036854775807"


def load_manifest(manifest_path: Path) -> dict:
    """Load and structurally validate a composition manifest."""
    manifest = json.loads(Path(manifest_path).read_text())
    for key in ("views",):
        if key not in manifest:
            raise ValueError(f"Manifest missing required key '{key}'")
    if "unions" not in manifest:
        manifest["unions"] = {}
    if "projections" not in manifest:
        manifest["projections"] = {}
    return manifest


def generate_view_sql(vd_path: Path, source_table: str, view_schema: str = "omop") -> str:
    """Parse + generate one ViewDefinition against the staged table.

    ``view_schema`` aligns the generator's Join.view table resolution with
    the runner's materialization schema.
    """
    vd = parse_view_definition(json.loads(Path(vd_path).read_text()))
    gen = SQLGenerator(source_table=source_table)
    gen.view_schema = view_schema
    return gen.generate(vd)


def materialize_views(
    con,
    vd_dir: Path,
    stems: List[str],
    source_table: str,
    schema: str = "omop",
    table_name: Optional[str] = None,
) -> Dict[str, str]:
    """Materialize ViewDefinitions as views; return stem -> view name.

    Each stem's generated SQL becomes ``<schema>.<table_name or stem>``
    (stems normalized: '-'/'.json' -> '_'). Views are CREATE OR REPLACE.
    """
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    created: Dict[str, str] = {}
    for stem in stems:
        sql = generate_view_sql(vd_dir / f"{stem}.json", source_table, view_schema=schema)
        name = (table_name or stem).replace("-view", "").replace("-", "_").replace(".", "_")
        con.execute(f'CREATE OR REPLACE VIEW {schema}."{name}" AS\n{sql}')
        created[stem] = f'{schema}."{name}"'
    return created


def compose_union(
    con,
    child_tables: List[str],
    target: str,
    schema: str = "omop",
) -> str:
    """Create the table-level UNION ALL view over materialized children."""
    union_sql = "\nUNION ALL\n".join(f"SELECT * FROM {t}" for t in child_tables)
    con.execute(f'CREATE OR REPLACE VIEW {schema}."{target}" AS\n{union_sql}')
    return f'{schema}."{target}"'


def _result_columns(con, sql: str) -> List[str]:
    return [d[0] for d in con.execute(f"SELECT * FROM ({sql}) LIMIT 0").description]


def _projection_sql(
    select_sql: str,
    columns: List[str],
    hash_keys: Optional[List[str]] = None,
    defaults: Optional[Dict[str, int]] = None,
) -> str:
    """Pure projection wrapper (no connection needed)."""
    hash_keys = set(hash_keys or [])
    defaults = defaults or {}
    exprs = []
    for col in columns:
        if col in hash_keys:
            exprs.append(f"CAST(hash({col}) & {_HASH_MASK} AS BIGINT) AS {col}")
        elif col in defaults:
            exprs.append(
                f"CAST(COALESCE(TRY_CAST({col} AS BIGINT), {defaults[col]}) AS BIGINT) AS {col}"
            )
        else:
            exprs.append(col)
    return f"SELECT {', '.join(exprs)} FROM (\n{select_sql}\n)"


def apply_projections(
    con,
    select_sql: str,
    columns: List[str],
    hash_keys: Optional[List[str]] = None,
    defaults: Optional[Dict[str, int]] = None,
) -> str:
    """Return the projection-wrapped SQL over a composed select.

    ``hash_keys`` columns become ``CAST(hash(col) & MASK AS BIGINT)``;
    ``defaults`` columns become ``CAST(COALESCE(TRY_CAST(col AS BIGINT),
    default) AS BIGINT)``. Column order is preserved. ``con`` is accepted
    for API stability; the wrapping itself is pure.
    """
    return _projection_sql(select_sql, columns, hash_keys=hash_keys, defaults=defaults)


def infer_view_dependencies(vd_dir: Path, stems: List[str]) -> Dict[str, List[str]]:
    """Scan each VD's Join.view targets and map stem -> target view names.

    A view-target join references another ViewDefinition by its VD ``name``
    (not the file stem); the mapping needs the VD files themselves. Returns
    {stem: [target VD names]} for every stem that HAS view joins.
    """
    deps: Dict[str, List[str]] = {}
    for stem in stems:
        vd = parse_view_definition(json.loads((vd_dir / f"{stem}.json").read_text()))
        targets = [j.view for j in vd.joins if j.view]
        if targets:
            deps[stem] = targets
    return deps


def resolve_materialization_order(
    vd_dir: Path,
    stems: List[str],
) -> tuple:
    """Topologically order (join-target VDs first, then their consumers).

    Returns (ordered_stems, name_to_stem) where name_to_stem maps each VD's
    ``name`` to its file stem. Raises ValueError on dependency cycles or a
    view-target reference that no library VD provides (typed errors per the
    dependency-inference directive).
    """
    vd_names: Dict[str, str] = {}
    for stem in stems:
        vd = parse_view_definition(json.loads((vd_dir / f"{stem}.json").read_text()))
        vd_names[vd.name] = stem
    deps = infer_view_dependencies(vd_dir, stems)

    # Topological sort (Kahn); edges: target-stem -> consumer-stem.
    consumers: Dict[str, set] = {s: set() for s in stems}
    indegree: Dict[str, int] = {s: 0 for s in stems}
    for stem, targets in deps.items():
        for t in targets:
            if t not in vd_names:
                raise ValueError(
                    f"Join.view target {t!r} (referenced by {stem!r}) is not "
                    "provided by any ViewDefinition in the manifest library"
                )
            provider = vd_names[t]
            if provider not in consumers:
                continue
            if stem not in consumers[provider]:
                consumers[provider].add(stem)
                indegree[stem] += 1

    ready = sorted([s for s in stems if indegree[s] == 0])
    ordered: List[str] = []
    while ready:
        s = ready.pop(0)
        ordered.append(s)
        for c in sorted(consumers[s]):
            indegree[c] -= 1
            if indegree[c] == 0:
                ready.append(c)
                ready.sort()
    if len(ordered) != len(stems):
        stuck = sorted(s for s in stems if s not in ordered)
        raise ValueError(
            f"View dependency cycle detected among: {stuck}"
        )
    return ordered, vd_names


def _stem_table_name(stem: str) -> str:
    """Normalized table name for a single-view stem (person-view -> person)."""
    return stem.replace("-view", "").replace("-", "_").replace(".", "_")


def _union_child_name(table: str, stem: str) -> str:
    """Child view name under a union family (drug_exposure__medication_request)."""
    suffix = stem.replace("-view", "").replace("-", "_")
    family = table.replace("_", "-") + "-"
    if stem.startswith(family):
        suffix = stem[len(family):].replace("-view", "").replace("-", "_")
    return f"{table}__{suffix}"


def build_composition_plan(manifest_path: Path) -> dict:
    """Pure planner: ordered DDL steps for a composition manifest.

    Step shapes:
      {"type": "view", "role": "join_target"|"union_child"|"single"|"override",
       "name": <view name>, "table_sql": '<schema>."<name>"', "stem": <stem>,
       "projection": {hash_keys, defaults} | None}
      {"type": "union", "role": "union", "table": <table>,
       "table_sql": '<schema>."<table>"', "children": [child view names],
       "projection": {...} | None}

    Ordering: join targets (dependency order) -> manifest overrides ->
    per union (children then the union view) -> remaining single views.
    One stem maps to exactly one role.
    """
    manifest = load_manifest(manifest_path)
    vd_dir = Path(manifest_path).parent
    schema = manifest.get("view_schema", "omop")
    projections = manifest.get("projections", {})
    all_stems = list(manifest.get("views", {}).keys())
    ordered, vd_names = resolve_materialization_order(vd_dir, all_stems)
    name_by_stem = {stem: name for name, stem in vd_names.items()}

    deps = infer_view_dependencies(vd_dir, all_stems)
    joined_names = set()
    for targets in deps.values():
        joined_names.update(targets)
    union_stems = {s for stems in manifest.get("unions", {}).values() for s in stems}

    steps: List[dict] = []
    seen_stems = set()

    def _view_step(role, name, stem, projection=None):
        return {
            "type": "view",
            "role": role,
            "name": name,
            "table_sql": f'{schema}."{name}"',
            "stem": stem,
            "projection": projection,
        }

    # 1. Join-target VDs first (dependency order), under their VD name.
    for stem in ordered:
        if stem not in all_stems:
            continue
        vd_name = name_by_stem[stem]
        if vd_name in joined_names and stem not in union_stems:
            steps.append(_view_step("join_target", vd_name, stem))
            seen_stems.add(stem)

    # 2. Manifest overrides (eager materialization under a custom name).
    for view_name, stem in manifest.get("materialize", {}).items():
        steps.append(_view_step("override", view_name, stem))
        seen_stems.add(stem)

    # 3. Union families: child views, then the union + projections.
    for table, stems in manifest.get("unions", {}).items():
        children = []
        for stem in stems:
            child = _union_child_name(table, stem)
            steps.append(_view_step("union_child", child, stem))
            seen_stems.add(stem)
            children.append(child)
        steps.append({
            "type": "union",
            "role": "union",
            "table": table,
            "table_sql": f'{schema}."{table}"',
            "children": children,
            "projection": projections.get(table) or None,
        })

    # 4. Remaining single-table views (with projections when declared).
    for stem in ordered:
        if stem in union_stems or stem not in all_stems or stem in seen_stems:
            continue
        vd_name = name_by_stem[stem]
        if vd_name in joined_names:
            continue  # already materialized as a join target
        table = _stem_table_name(stem)
        steps.append(_view_step("single", table, stem, projections.get(table) or None))

    return {"schema": schema, "steps": steps}


def render_view_sqls(plan: dict, vd_dir: Path, source_table: str) -> List[dict]:
    """Generate SQL text for every 'view' step (dependency order, no execution).

    Returns [{"name", "table_sql", "stem", "sql"}] — the caller is expected
    to execute each as a plain CREATE OR REPLACE VIEW (introspection-ready),
    then call ``render_composition_ddl`` for the remaining composed steps.
    """
    schema = plan["schema"]
    out = []
    for step in plan["steps"]:
        if step["type"] != "view":
            continue
        sql = generate_view_sql(Path(vd_dir) / f'{step["stem"]}.json', source_table, view_schema=schema)
        out.append({
            "name": step["name"],
            "table_sql": step["table_sql"],
            "stem": step["stem"],
            "sql": sql,
        })
    return out


def render_composition_ddl(
    plan: dict,
    columns_by_view: Dict[str, List[str]],
    sql_by_view: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Pure: remaining DDL after plain view-step CREATEs have been executed.

    Emits, in order:
      - projected view steps (wrapping ``SELECT * FROM <view>`` with the
        manifest projection rules),
      - union steps (UNION ALL over the child views, then projections).
    Plain view steps without projections are assumed already created and
    are NOT re-emitted.
    """
    schema = plan["schema"]
    stmts: List[str] = []
    for step in plan["steps"]:
        if step["type"] == "view":
            proj = step.get("projection")
            if not proj:
                continue
            cols = columns_by_view.get(step["name"])
            if cols is None:
                raise ValueError(f"missing columns for view {step['name']!r}")
            # Wrap the ORIGINAL generated SQL: wrapping "SELECT * FROM
            # <same view>" would be a self-referential CREATE OR REPLACE.
            base_sql = (sql_by_view or {}).get(step["name"])
            if base_sql is None:
                raise ValueError(
                    f"missing base SQL for projected view {step['name']!r}"
                )
            wrapped = _projection_sql(
                base_sql,
                cols,
                hash_keys=proj.get("hash_keys"),
                defaults=proj.get("defaults"),
            )
            stmts.append(f'CREATE OR REPLACE VIEW {step["table_sql"]} AS\n{wrapped}')
            continue
        # union step
        children = [f'{schema}."{c}"' for c in step["children"]]
        first_cols = columns_by_view.get(step["children"][0])
        if first_cols is None:
            raise ValueError(f"missing columns for union child {step['children'][0]!r}")
        union_select = "\nUNION ALL\n".join(f"SELECT * FROM {t}" for t in children)
        proj = step.get("projection")
        if proj:
            union_select = _projection_sql(
                union_select,
                first_cols,
                hash_keys=proj.get("hash_keys"),
                defaults=proj.get("defaults"),
            )
        stmts.append(f'CREATE OR REPLACE VIEW {step["table_sql"]} AS\n{union_select}')
    return stmts


def run_composition(con, manifest_path: Path, source_table: str) -> Dict[str, str]:
    """Execute a full composition manifest; return table -> view name.

    Materialization ordering is INFERRED (dependency-inference directive):
    each VD's Join.view targets are resolved to their source VDs and
    materialized in topological order (join targets first; cycles and
    unknown targets are typed errors). The manifest's ``materialize`` map
    is an override/hint only (eager materialization under a custom name,
    e.g. a view nothing joins yet) — correctness never depends on it.

    Steps come from ``build_composition_plan`` (the same plan the
    text-only renderers use for browser-side derivation).
    """
    plan = build_composition_plan(manifest_path)
    vd_dir = Path(manifest_path).parent
    schema = plan["schema"]
    created: Dict[str, str] = {}
    join_targets: Dict[str, str] = {}

    con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    for step in plan["steps"]:
        if step["type"] == "view":
            sql = generate_view_sql(
                vd_dir / f'{step["stem"]}.json', source_table, view_schema=schema
            )
            proj = step.get("projection")
            if proj:
                cols = _result_columns(con, sql)
                sql = _projection_sql(
                    sql, cols,
                    hash_keys=proj.get("hash_keys"),
                    defaults=proj.get("defaults"),
                )
            con.execute(f'CREATE OR REPLACE VIEW {step["table_sql"]} AS\n{sql}')
            if step["role"] in ("join_target", "override"):
                join_targets[step["name"]] = step["table_sql"]
            elif step["role"] == "single":
                created[step["name"]] = step["table_sql"]
            continue

        # union step
        child_tables = [f'{schema}."{c}"' for c in step["children"]]
        first_cols = _result_columns(con, f"SELECT * FROM {child_tables[0]}")
        for t in child_tables[1:]:
            cols = _result_columns(con, f"SELECT * FROM {t}")
            if cols != first_cols:
                raise ValueError(
                    f"Union '{step['table']}' child column mismatch: {t} has {cols}, "
                    f"expected {first_cols}"
                )
        union_select = "\nUNION ALL\n".join(f"SELECT * FROM {t}" for t in child_tables)
        proj = step.get("projection")
        if proj:
            union_select = _projection_sql(
                union_select, first_cols,
                hash_keys=proj.get("hash_keys"),
                defaults=proj.get("defaults"),
            )
        con.execute(f'CREATE OR REPLACE VIEW {step["table_sql"]} AS\n{union_select}')
        created[step["table"]] = step["table_sql"]

    created["__join_targets__"] = join_targets  # reserved: not a table
    return created


class _RecordingExecutor:
    """DuckDB stand-in that records every statement instead of executing.

    ``_result_columns`` introspection still needs a real connection; the
    worker passes a Pyodide-side duckdb connection for that while DDL is
    captured for remote (DuckDB-WASM) replay.
    """

    def __init__(self, con):
        self._con = con
        self.statements: list = []

    def execute(self, sql, *args):
        self.statements.append(sql)
        return self._con.execute(sql, *args)


def composition_ddl(con, manifest_path: Path, source_table: str) -> list:
    """Run the composition while recording every DDL statement executed.

    Returns the statement list (CREATE SCHEMA / CREATE VIEW, in dependency
    order) suitable for replay on another connection — e.g. the Viewing
    Room worker replays them on DuckDB-WASM before running a SQLQuery
    Library over the composed views.
    """
    recorder = _RecordingExecutor(con)
    run_composition(recorder, manifest_path, source_table)
    return [s for s in recorder.statements if s.lstrip().upper().startswith("CREATE")]


__all__ = [
    "load_manifest", "generate_view_sql", "materialize_views",
    "compose_union", "apply_projections", "run_composition", "composition_ddl",
    "build_composition_plan", "render_view_sqls", "render_composition_ddl",
]
