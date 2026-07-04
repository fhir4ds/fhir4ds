"""Phase 3 (medterm4ds) — pre-expanded subsumption closure table.

This module populates the ``terminology_closure`` DuckDB table used by the
CQL->SQL translator to make the three subsumption operators correct:

1. ``Descendents(Code)`` — returns all codes subsumed by the seed.
2. ``Code X ~ Code Y`` — subsumption-aware equivalence (symmetric).
3. ``Code X is Code Y`` — directional subsumption (right subsumes left).

When the closure table is loaded and the caller has set
``SQLTranslationContext.closure_table_loaded = True`` (typically via
:func:`set_closure_loaded`), the translator emits SQL that consults the
table. When the flag is False (the default), the translator emits the
byte-identical SQL the conformance baseline expects — preserving
INV-1 (zero regression).

The closure table is per-connection (Decision b in the FDD) and namespaced
by ``closure_set`` so multiple libraries share rows without conflict:

    CREATE TABLE IF NOT EXISTS terminology_closure (
        ancestor_system   VARCHAR NOT NULL,
        ancestor_code     VARCHAR NOT NULL,
        descendant_system VARCHAR NOT NULL,
        descendant_code   VARCHAR NOT NULL,
        closure_set       VARCHAR NOT NULL,
        PRIMARY KEY (ancestor_system, ancestor_code,
                     descendant_system, descendant_code)
    );

Public API:
    * :func:`build_closure_table` — scan a library, expand seeds via an
      endpoint, load rows. Idempotent.
    * :func:`clear_closure_table` — drop everything (caller-driven reset).
    * :func:`set_closure_loaded` — set the flag on a translator/context.
    * :class:`ClosureReport` — outcome dataclass (counts + per-seed errors).

Zero-dependency contract:
    The TerminologyEndpoint protocol is imported only under
    ``typing.TYPE_CHECKING`` so importing this module does not pull httpx,
    medterm4ds, or any adapter — only stdlib + fhir4ds internal modules.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable, List, Optional, Tuple

from ..duckdb.udf.system_resolver import SystemResolver
from ..translator.code_resolver import resolve_code_ref_for_library

if TYPE_CHECKING:
    import duckdb

    from ..parser.ast_nodes import Library
    from ..translator.context import SQLTranslationContext
    from ..translator.translator import CQLToSQLTranslator
    from .endpoint import TerminologyEndpoint


# Schema (kept in sync with the FDD §3a).
_CLOSURE_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS terminology_closure ("
    "ancestor_system   VARCHAR NOT NULL, "
    "ancestor_code     VARCHAR NOT NULL, "
    "descendant_system VARCHAR NOT NULL, "
    "descendant_code   VARCHAR NOT NULL, "
    "closure_set       VARCHAR NOT NULL, "
    "PRIMARY KEY (ancestor_system, ancestor_code, "
    "descendant_system, descendant_code)"
    ")"
)


@dataclass
class ClosureReport:
    """Outcome of a single :func:`build_closure_table` invocation.

    Attributes:
        seeds_scanned: total number of distinct seed codes detected in the
            library AST.
        seeds_expanded: number of seeds for which the endpoint returned at
            least one row (reflexive rows don't count — only real expansions).
        rows_loaded: total rows inserted (including reflexive rows).
        errors: list of ``(seed_label, error_message)`` tuples for seeds
            that failed and were skipped under the ``"warn"`` or ``"skip"``
            error policies.
    """

    seeds_scanned: int = 0
    seeds_expanded: int = 0
    rows_loaded: int = 0
    errors: List[Tuple[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AST scanner
# ---------------------------------------------------------------------------


def _iter_expression_nodes(root: Any) -> Iterable[Any]:
    """Yield every node in the CQL AST under ``root`` (depth-first).

    The AST is heterogeneous (dataclasses with arbitrary attributes), so we
    walk via ``__dataclass_fields__`` when available and via ``__dict__``
    otherwise. We do NOT recurse into strings, ints, None, etc.
    """
    if root is None:
        return
    if isinstance(root, (str, int, float, bool)):
        return
    yield root
    children: List[Any] = []
    fields = getattr(root, "__dataclass_fields__", None)
    if fields is not None:
        for fname in fields:
            try:
                value = getattr(root, fname)
            except AttributeError:
                continue
            children.append(value)
    elif isinstance(root, dict):
        children.extend(root.values())
    elif isinstance(root, (list, tuple, set)):
        children.extend(root)
    else:
        # Fall back to __dict__ for slotted / regular objects.
        try:
            children.extend(vars(root).values())
        except TypeError:
            pass

    for child in children:
        if isinstance(child, (list, tuple, set)):
            for grand in child:
                yield from _iter_expression_nodes(grand)
        else:
            yield from _iter_expression_nodes(child)


def _scan_for_subsumption_seeds(library: "Library") -> List[Any]:
    """Walk the library and return AST nodes that are subsumption operands.

    Returns a de-duplicated list of operand nodes — each entry is suitable
    for :func:`resolve_code_ref_for_library`. The seeds are extracted from:

    * ``FunctionRef(name="Descendents", args=[code_expr])`` (case-insensitive).
    * ``BinaryExpression(operator="~"|"!~", left, right)`` where both sides
      look like code references.
    * ``BinaryExpression(operator="is"|"is not", left, right)`` when neither
      side is a :class:`NamedTypeSpecifier` (the type-check form must stay
      routed to the translator's existing type-check branch).
    """
    # Local import to avoid import cycles at module load.
    from ..parser.ast_nodes import BinaryExpression, FunctionRef, NamedTypeSpecifier

    seeds: List[Any] = []
    seen_ids: set = set()

    def _add(node: Any) -> None:
        # De-duplicate by identity (AST nodes are not hashable in general but
        # ``id()`` always works).
        nid = id(node)
        if nid in seen_ids:
            return
        seen_ids.add(nid)
        seeds.append(node)

    # Walk every Definition and FunctionDefinition expression in the library.
    roots = []
    for stmt in getattr(library, "statements", []) or []:
        expr = getattr(stmt, "expression", None)
        if expr is not None:
            roots.append(expr)
    # Also walk code/concept definitions and parameter defaults — a seed may
    # be a Code referenced via a `define X: Code 'y' from S` form.
    for code_def in getattr(library, "codes", []) or []:
        roots.append(code_def)
    for param_def in getattr(library, "parameters", []) or []:
        default = getattr(param_def, "default", None)
        if default is not None:
            roots.append(default)

    for root in roots:
        for node in _iter_expression_nodes(root):
            if isinstance(node, FunctionRef):
                # ``Descendents`` (and case variants) per CQL §20.4. Also
                # accept the snake-cased ``descendents`` form because some
                # call sites use that spelling.
                name = (node.name or "").split(".")[-1].lower()
                if name == "descendents":
                    for arg in node.arguments:
                        _add(arg)
                continue
            if isinstance(node, BinaryExpression):
                op = (node.operator or "").strip().lower()
                if op in ("~", "!~"):
                    _add(node.left)
                    _add(node.right)
                    continue
                if op in ("is", "is not"):
                    # Only treat as code-vs-code when neither side is a
                    # NamedTypeSpecifier (the type-check form). If either
                    # side IS a NamedTypeSpecifier, this is
                    # ``Order is MedicationRequest`` and must NOT seed a
                    # closure expansion.
                    if not isinstance(node.left, NamedTypeSpecifier) and not isinstance(
                        node.right, NamedTypeSpecifier
                    ):
                        _add(node.left)
                        _add(node.right)
                continue
    return seeds


# ---------------------------------------------------------------------------
# Endpoint expansion
# ---------------------------------------------------------------------------

_SNOMED_PREFIX = "http://snomed.info/sct"


def _is_snomed(system: str) -> bool:
    return (system or "").startswith(_SNOMED_PREFIX)


def _expand_seed(
    endpoint: "TerminologyEndpoint",
    system: str,
    code: str,
) -> List[Any]:
    """Expand a single seed code via the endpoint.

    SNOMED uses the ``?fhir_vs=isa/{code}`` URL form (Phase 1 fast-path).
    All other code systems go through ``expand_intensional`` with a
    ``concept is-a <code>`` filter.
    """
    normalized_system = SystemResolver.normalize(system) or system
    if _is_snomed(normalized_system):
        url = f"{_SNOMED_PREFIX}?fhir_vs=isa/{code}"
        return list(endpoint.expand(url))

    value_set = {
        "resourceType": "ValueSet",
        "compose": {
            "include": [
                {
                    "system": normalized_system,
                    "filter": [
                        {"property": "concept", "op": "is-a", "value": code}
                    ],
                }
            ]
        },
    }
    return list(endpoint.expand_intensional(value_set))


# ---------------------------------------------------------------------------
# Row load
# ---------------------------------------------------------------------------


def _closure_set_key(system: str, code: str) -> str:
    return f"{system}|{code}"


def _ensure_table(con: "duckdb.DuckDBPyConnection") -> None:
    con.execute(_CLOSURE_TABLE_DDL)


def _insert_seed_rows(
    con: "duckdb.DuckDBPyConnection",
    ancestor_system: str,
    ancestor_code: str,
    descendants: List[Any],
    closure_set: str,
) -> int:
    """Bulk-insert the (ancestor, descendant) rows for a seed.

    Reflexive row is always inserted so ``X is Y`` returns True when
    ``X == Y`` even if the endpoint omitted the seed from its own expansion.

    Returns the number of rows actually inserted (post-dedup against the
    primary key — INSERT OR IGNORE silently skips duplicates).
    """
    normalized_anc_sys = SystemResolver.normalize(ancestor_system) or ancestor_system
    rows = [(normalized_anc_sys, ancestor_code, normalized_anc_sys, ancestor_code, closure_set)]
    seen = {(normalized_anc_sys, ancestor_code, normalized_anc_sys, ancestor_code)}
    for ref in descendants:
        desc_sys = SystemResolver.normalize(ref.system) or ref.system
        desc_code = ref.code
        key = (normalized_anc_sys, ancestor_code, desc_sys, desc_code)
        if key in seen:
            continue
        seen.add(key)
        rows.append((normalized_anc_sys, ancestor_code, desc_sys, desc_code, closure_set))

    before = con.execute("SELECT COUNT(*) FROM terminology_closure").fetchone()[0]
    con.executemany(
        "INSERT OR IGNORE INTO terminology_closure "
        "(ancestor_system, ancestor_code, descendant_system, descendant_code, closure_set) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    after = con.execute("SELECT COUNT(*) FROM terminology_closure").fetchone()[0]
    return after - before


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_closure_table(
    library: "Library",
    endpoint: "TerminologyEndpoint",
    con: "duckdb.DuckDBPyConnection",
    *,
    on_expand_error: str = "warn",
    closure_set: Optional[str] = None,
) -> ClosureReport:
    """Scan ``library`` for subsumption operands and load closures into DuckDB.

    Args:
        library: parsed CQL :class:`Library` AST.
        endpoint: terminology service implementing the
            :class:`~fhir4ds.cql.terminology.endpoint.TerminologyEndpoint`
            protocol.
        con: open DuckDB connection. A ``terminology_closure`` table is
            created if absent. Multiple calls on the same connection are
            idempotent (``INSERT OR IGNORE`` + closure_set dedup).
        on_expand_error: per-seed error policy. ``"warn"`` (default) emits a
            ``UserWarning`` and continues to the next seed; ``"skip"`` is
            silent; ``"raise"`` re-raises (useful in tests).
        closure_set: optional override for the ``closure_set`` column.
            Defaults to a per-seed ``"{system}|{code}"`` so multiple
            libraries on the same connection share rows cleanly.

    Returns:
        :class:`ClosureReport` with seed/row counts and per-seed errors.
    """
    if on_expand_error not in ("warn", "skip", "raise"):
        raise ValueError(
            f"on_expand_error must be 'warn', 'skip', or 'raise'; got {on_expand_error!r}"
        )

    _ensure_table(con)

    # Scan AST for seed operands, then resolve each to (system, code).
    seed_nodes = _scan_for_subsumption_seeds(library)
    resolved: List[Tuple[str, str]] = []
    seen_keys: set = set()
    for node in seed_nodes:
        info = resolve_code_ref_for_library(node, library)
        if not info:
            # Dynamic / unresolved node — skip silently (the translator's
            # instance-level _resolve_code_ref will pick it up at translation
            # time if it can; otherwise literal-match fallback applies).
            continue
        if info.get("is_concept") or isinstance(info.get("codes"), list):
            entries = info.get("codes") or []
        elif info.get("code"):
            entries = [info]
        else:
            entries = []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("code"):
                continue
            sys_url = entry.get("codesystem") or entry.get("system") or ""
            if not sys_url:
                continue
            normalized = SystemResolver.normalize(sys_url) or sys_url
            key = (normalized, entry["code"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            resolved.append(key)

    report = ClosureReport(seeds_scanned=len(resolved))

    for system, code in resolved:
        cset = closure_set or _closure_set_key(system, code)
        try:
            descendants = _expand_seed(endpoint, system, code)
        except Exception as exc:  # noqa: BLE001 — per-seed fault tolerance
            label = f"{system}|{code}"
            report.errors.append((label, f"{type(exc).__name__}: {exc}"))
            if on_expand_error == "raise":
                raise
            if on_expand_error == "warn":
                warnings.warn(
                    f"Closure expansion failed for seed {label}: {exc}",
                    UserWarning,
                    stacklevel=2,
                )
            continue

        if descendants:
            report.seeds_expanded += 1
        report.rows_loaded += _insert_seed_rows(
            con, system, code, descendants, cset
        )

    return report


def clear_closure_table(con: "duckdb.DuckDBPyConnection") -> None:
    """Drop all rows from ``terminology_closure`` (and the table itself).

    Intentionally aggressive — this is the documented production reset.
    Callers that only want to clear a single ``closure_set`` should DELETE
    WHERE closure_set = ? directly against the table.
    """
    con.execute("DROP TABLE IF EXISTS terminology_closure")


def set_closure_loaded(
    target: Any, loaded: bool = True
) -> None:
    """Set ``closure_table_loaded`` on a translator or context.

    Args:
        target: a :class:`CQLToSQLTranslator` or a
            :class:`SQLTranslationContext`. Translator instances are detected
            via their ``context`` attribute (a property returning the
            context); context instances are detected via the
            ``set_closure_table_loaded`` method.
        loaded: True when the table is populated; False to revert to
            literal-match fallback.
    """
    ctx: Any = None
    # Translator path: has a ``context`` attribute that itself has the setter.
    inner_ctx = getattr(target, "context", None)
    if inner_ctx is not None and hasattr(inner_ctx, "set_closure_table_loaded"):
        ctx = inner_ctx
    elif hasattr(target, "set_closure_table_loaded"):
        ctx = target
    if ctx is None:
        raise TypeError(
            "set_closure_loaded requires a CQLToSQLTranslator or "
            "SQLTranslationContext; got "
            f"{type(target).__name__}"
        )
    ctx.set_closure_table_loaded(bool(loaded))
