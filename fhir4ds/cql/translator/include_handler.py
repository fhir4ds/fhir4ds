"""
Include/Library handling mixin for the CQL-to-SQL translator.

Extracts methods responsible for processing CQL include statements,
translating included library definitions, and managing prefixed names.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set, TYPE_CHECKING

_logger = logging.getLogger(__name__)

from ..errors import TranslationError
from ..parser.ast_nodes import (
    Definition,
    FunctionDefinition,
    Library,
)
from ..translator.ast_utils import collect_cte_references

if TYPE_CHECKING:
    from ..translator.context import SQLTranslationContext
    from ..translator.types import SQLExpression


class IncludeHandlerMixin:
    """Mixin providing include/library handling for CQLToSQLTranslator."""

    @staticmethod
    def _short_library_name(path: str) -> str:
        """Return the last path segment for dotted library identifiers."""
        return path.rsplit(".", 1)[-1]

    def _load_required_library(self, path: str, alias: str) -> Library:
        """Load an included library or raise a clear TranslationError."""
        loader = self._library_loader
        if loader is None:
            raise TranslationError(
                message=f"Cannot load included library '{path}' without a library loader",
            )

        candidates = [path]
        short_name = self._short_library_name(path)
        if short_name != path:
            candidates.append(short_name)

        errors: list[str] = []
        for candidate in candidates:
            try:
                library = loader(candidate)
            except Exception as exc:
                errors.append(f"{candidate}: {exc}")
                continue
            if library is not None:
                return library

        if errors:
            raise TranslationError(
                message=(
                    f"Failed to load included library '{path}'"
                    f" (alias '{alias}'). Loader errors: {'; '.join(errors)}"
                ),
            )

        raise TranslationError(
            message=f"Included library '{path}' (alias '{alias}') could not be loaded",
        )

    def _build_included_definition_cte(
        self, name: str, expr: SQLExpression
    ) -> SQLExpression:
        """
        Build a CTE for an included library definition.

        These definitions come from included libraries and are referenced with
        prefixed names like "LibraryAlias.DefinitionName". They include patient_id
        so they can be joined with the main population query.

        This method uses metadata-based routing instead of string inspection.

        Args:
            name: The prefixed definition name (e.g., "AdultOutpatientEncounters.Qualifying Encounters").
            expr: The translated SQL expression.

        Returns:
            SQLExpression AST for the CTE body (without the CTE name and AS).
        """
        from ..translator.context import RowShape
        from ..translator.types import SQLSelect, SQLAlias, SQLIdentifier, SQLQualifiedIdentifier, SQLSubquery

        # Look up metadata for this definition
        meta = self._context.definition_meta.get(name)

        if meta is not None:
            # Use metadata-based wrapping (each section handles unwrapping itself)
            wrapped_ast = self._wrap_definition_cte(name, expr, meta)
            # Validate: check for unresolved aliases (single-letter identifiers in
            # FROM-less contexts indicate a failed query source translation)
            if self._has_unresolved_refs(wrapped_ast):
                return self._fallback_cte_sql(name, meta)
            return wrapped_ast

        # Unwrap SQLSubquery for the fallback path — CTE bodies need bare SQLSelect.
        if isinstance(expr, SQLSubquery) and isinstance(expr.query, SQLSelect):
            expr = expr.query

        # Fallback for definitions without metadata: check if it's a SQLSelect
        if isinstance(expr, SQLSelect):
            # Check if it already has patient_id using AST helpers
            if self._select_has_patient_id(expr):
                return expr
            # Wrap with patient_id from _patients
            wrapped = SQLSelect(
                columns=[
                    SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                ],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name="_patients"),
                    alias="_pt",
                ),
                where=SQLSubquery(query=expr) if not isinstance(expr, SQLSelect) else None,
            )
            return wrapped

        # For non-SELECT expressions, wrap with patient_id
        return SQLSelect(
            columns=[
                SQLQualifiedIdentifier(parts=["_pt", "patient_id"]),
                SQLAlias(expr=SQLSubquery(query=expr) if isinstance(expr, SQLSelect) else expr, alias="value"),
            ],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name="_patients"),
                alias="_pt",
            ),
        )

    def _process_includes(
        self, library: Library, context: SQLTranslationContext
    ) -> None:
        """
        Handle include statements.

        If a library_loader is provided, this will also load and translate
        the included library's definitions, storing them with prefixed names
        like "LibraryAlias.DefinitionName".

        P1.2: External Library CTE Generation
        This method now also runs the three-phase optimization pipeline on included
        libraries and collects their retrieve CTEs so they can be emitted in the
        final SQL output.

        Args:
            library: The parsed CQL library.
            context: The translation context.
        """
        import copy as _copy  # noqa: PLC0415

        for inc in library.includes:
            alias = inc.alias or inc.path.rsplit(".", 1)[-1]
            lib_info = context.add_include(alias=alias, path=inc.path, version=inc.version)

            if self._library_loader is None:
                continue

            # Check the shared cache first — avoid re-translating the same library
            # when it appears multiple times in the dependency graph (diamond pattern).
            # Cache key includes all parameter bindings (not just measurement period) so
            # that any CQL parameter changes are reflected in the cached output.
            def _binding_to_hashable(v):
                if isinstance(v, (list, tuple)):
                    return tuple(str(x) if x is not None else "" for x in v)
                return str(v) if v is not None else ""

            bindings_key = tuple(sorted(
                (k, _binding_to_hashable(v))
                for k, v in context._parameter_bindings.items()
            ))
            cache_key = (inc.path, inc.version or "", bindings_key)
            if cache_key in self._library_cache:
                cached = self._library_cache[cache_key]
                lib_info.library_ast = cached["library_ast"]
                self._apply_included_library_results(
                    cached["translator"],
                    # Deep-copy resolved ASTs because _prefix_intra_library_refs
                    # mutates them in place; the cache must hold pristine originals.
                    _copy.deepcopy(cached["resolved_asts"]),
                    cached["phase2_ctes"],
                    alias,
                    lib_info,
                )
                continue

            # Cache miss — load and fully translate the library.
            # For namespaced paths (e.g. hl7.fhir.uv.cql.FHIRHelpers), also try
            # the last segment as the library name.
            included_library = self._load_required_library(inc.path, alias)

            # Store the parsed AST on the library info for downstream analysis.
            lib_info.library_ast = included_library

            # Create a new translator instance, sharing the library cache so that
            # transitive dependencies are also de-duplicated.
            from ..translator.translator import CQLToSQLTranslator
            included_translator = CQLToSQLTranslator(
                connection=self._connection,
                use_fhirpath_udfs=self._use_fhirpath_udfs,
                library_loader=self._library_loader,
                _library_cache=self._library_cache,
            )

            try:
                # Set up context from included library declarations
                included_translator._setup_context(included_library)

                # Process parameters
                included_translator._process_parameters(included_library, included_translator._context)

                # Propagate ALL parameter bindings from parent to included library.
                # This ensures any CQL parameter (not just "Measurement Period") is available.
                for _name, _binding in context._parameter_bindings.items():
                    included_translator._context.set_parameter_binding(_name, _binding)

                # Process includes recursively (for nested includes)
                included_translator._process_includes(included_library, included_translator._context)

                # First pass: collect function definitions
                for statement in included_library.statements:
                    if isinstance(statement, FunctionDefinition):
                        included_translator._register_function(statement)

                # Initialize function inliner for included translator
                included_translator._init_shared_function_inliner()

                # Pre-register all definition names for forward reference resolution
                included_translator._context._definition_names = {
                    stmt.name for stmt in included_library.statements if isinstance(stmt, Definition)
                }

                # Pre-register all definition ASTs for forward-reference shape inference.
                for stmt in included_library.statements:
                    if isinstance(stmt, Definition) and not isinstance(stmt, FunctionDefinition):
                        included_translator._context.expression_definitions[stmt.name] = getattr(stmt, 'expression', stmt)

                # P1.2: Run three-phase optimization pipeline on included library
                # This populates phase2_result.ctes with retrieve CTEs
                from .retrieve_optimizer import run_optimization_phases
                included_resolved_asts, included_phase1, included_phase2, included_stats = run_optimization_phases(
                    included_library, included_translator._context, included_translator
                )

                # Snapshot phase2 CTE data before any mutation.
                phase2_ctes: Dict[str, Any] = {
                    cte_name: (cte_ast, included_phase2.column_registry._columns.get(cte_name, {}))
                    for cte_name, cte_ast in included_phase2.ctes.items()
                }

                # Store in cache BEFORE applying results (resolved_asts are pristine here;
                # _prefix_intra_library_refs below will mutate them for the current caller).
                self._library_cache[cache_key] = {
                    "library_ast": included_library,
                    "translator": included_translator,
                    "resolved_asts": _copy.deepcopy(included_resolved_asts),
                    "phase2_ctes": phase2_ctes,
                }

                # Apply translated results to this translator's context.
                self._apply_included_library_results(
                    included_translator,
                    included_resolved_asts,
                    phase2_ctes,
                    alias,
                    lib_info,
                )

            except TranslationError:
                raise
            except Exception as e:
                raise TranslationError(
                    message=f"Failed to translate included library '{alias}': {e}",
                ) from e

    def _apply_included_library_results(
        self,
        included_translator: "CQLToSQLTranslator",
        included_resolved_asts: Dict[str, Any],
        phase2_ctes: Dict[str, Any],
        alias: str,
        lib_info: Any,
    ) -> None:
        """Apply the translation results of an included library to this translator's context.

        Called both for cache hits (with deep-copied resolved_asts) and cache misses.
        ``phase2_ctes`` is a dict mapping CTE name → (cte_ast, col_info).

        NOTE: ``included_resolved_asts`` is modified in place by
        ``_prefix_intra_library_refs``; callers must pass a deep copy when reading
        from the cache so the cached originals remain pristine.
        """
        import copy as _copy

        # Copy codes, codesystems, and valuesets from included library to main context
        for code_name, code_info in included_translator._context.codes.items():
            self._context.codes[code_name] = code_info
        for cs_name, cs_url in included_translator._context.codesystems.items():
            self._context.codesystems[cs_name] = cs_url
        for vs_name, vs_url in included_translator._context.valuesets.items():
            self._context.valuesets[vs_name] = vs_url

        # Store retrieve CTEs from included library
        for cte_name, (cte_ast, col_info) in phase2_ctes.items():
            # When audit_mode is enabled in the parent but not the included
            # translator, included retrieve CTEs lack _audit_item.  Patch it
            # in so that definition-level evidence propagation can reach them.
            from .types import SQLSelect as _SQLSelect
            if (self._context.audit_mode
                    and isinstance(cte_ast, _SQLSelect)
                    and not self._cte_has_audit_item(cte_ast)):
                cte_ast = self._add_audit_item_to_retrieve(cte_ast, cte_name)
                if not hasattr(self._context, '_audit_retrieve_cte_names'):
                    self._context._audit_retrieve_cte_names = set()
                self._context._audit_retrieve_cte_names.add(cte_name)
            self._included_retrieve_ctes[cte_name] = (cte_ast, col_info)
            if col_info:
                self._context.column_registry.register_cte(cte_name, col_info)

        # Build rename map: bare def names → prefixed names
        _def_names_in_lib = set(included_resolved_asts.keys())

        # Store definitions with prefixed names
        for def_name, sql_expr in included_resolved_asts.items():
            prefixed_name = f"{alias}.{def_name}"
            # Rewrite intra-library CTE refs to use prefixed names
            sql_expr = self._prefix_intra_library_refs(sql_expr, alias, _def_names_in_lib)
            self._included_definitions[prefixed_name] = sql_expr
            self._context.register_included_definition(prefixed_name)

            # Copy DefinitionMeta so _build_included_definition_cte uses proper
            # metadata-based wrapping instead of the fallback path.
            included_meta = included_translator._context.definition_meta.get(def_name)
            if included_meta is not None:
                # Shallow-copy the meta object so mutations to tracked_refs don't
                # corrupt the cached translator's context when re-used from the cache.
                included_meta = _copy.copy(included_meta)
                if included_meta.tracked_refs:
                    new_refs = {}
                    for key, ref in included_meta.tracked_refs.items():
                        if ref.cte_name in _def_names_in_lib:
                            new_ref = _copy.copy(ref)
                            new_ref.cte_name = f"{alias}.{ref.cte_name}"
                            new_key = (f"{alias}.{key[0]}", key[1]) if isinstance(key, tuple) and len(key) >= 1 else key
                            new_refs[new_key] = new_ref
                        else:
                            new_refs[key] = ref
                    included_meta.tracked_refs = new_refs
                self._context.definition_meta[prefixed_name] = included_meta

            # Also store function definitions with the prefix in the library info
            func = included_translator._context.get_function(def_name)
            if func:
                from ..translator.translator import FunctionInfo
                prefixed_func = FunctionInfo(
                    name=def_name,
                    parameters=func.parameters,
                    return_type=func.return_type,
                    expression=func.expression,
                    is_fluent=func.is_fluent,
                    library_alias=alias,
                )
                lib_info.functions[def_name] = prefixed_func
                if def_name not in lib_info.function_overloads:
                    lib_info.function_overloads[def_name] = []
                lib_info.function_overloads[def_name].append(prefixed_func)

        # Store definitions in library info for cross-reference resolution
        for def_name in included_resolved_asts.keys():
            lib_info.definitions[def_name] = included_resolved_asts[def_name]

        # Copy fluent functions from included library to lib_info
        for func_name, func_info in included_translator._context._functions.items():
            if func_name not in lib_info.functions:
                lib_info.functions[func_name] = func_info
        # Copy ALL overloads for overloaded fluent functions
        for func_name, overloads in included_translator._context._function_overloads.items():
            if func_name not in lib_info.function_overloads:
                lib_info.function_overloads[func_name] = []
            for ol in overloads:
                if ol not in lib_info.function_overloads[func_name]:
                    lib_info.function_overloads[func_name].append(ol)

    def _sort_included_definitions(
        self, included_defs: Dict[str, "SQLExpression"]
    ) -> List[str]:
        """Topologically sort included library definitions by inter-CTE dependencies.

        Scans each definition's SQL representation for references to other included
        definition CTE names, then returns names in dependency order.
        """
        names = list(included_defs.keys())
        name_set = set(names)

        # Build dependency graph by walking AST and checking for CTE references
        deps: Dict[str, Set[str]] = {n: set() for n in names}
        for name, expr in included_defs.items():
            try:
                # Collect all CTE references from the expression AST
                cte_refs = collect_cte_references(expr)
                # Add dependencies for each CTE reference found
                for cte_ref in cte_refs:
                    if cte_ref in name_set and cte_ref != name:
                        deps[name].add(cte_ref)
            except Exception as e:
                raise TranslationError(
                    message=f"Failed to collect CTE references for included definition '{name}': {e}",
                ) from e

        # Kahn's algorithm
        in_degree = {n: 0 for n in names}
        for n, d in deps.items():
            for dep in d:
                if dep in in_degree:
                    in_degree[n] += 1

        dependents: Dict[str, List[str]] = {n: [] for n in names}
        for n, d in deps.items():
            for dep in d:
                if dep in dependents:
                    dependents[dep].append(n)

        queue = sorted([n for n, deg in in_degree.items() if deg == 0])
        result = []
        while queue:
            current = queue.pop(0)
            result.append(current)
            for dependent in sorted(dependents[current]):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # Fallback: append any remaining (cycle) in original order
        if len(result) != len(names):
            remaining = [n for n in names if n not in set(result)]
            result.extend(remaining)

        return result

    # ------------------------------------------------------------------
    # Audit helpers: inject _audit_item into included retrieve CTEs
    # ------------------------------------------------------------------

    @staticmethod
    def _cte_has_audit_item(cte_ast: "SQLExpression") -> bool:
        """Check whether a retrieve CTE already carries an ``_audit_item`` column."""
        from .types import SQLSelect, SQLAlias, SQLIdentifier, SQLQualifiedIdentifier
        if not isinstance(cte_ast, SQLSelect):
            return False
        for col in (cte_ast.columns or []):
            if isinstance(col, SQLAlias) and col.alias == "_audit_item":
                return True
            c = col.expr if isinstance(col, SQLAlias) else col
            if isinstance(c, SQLIdentifier) and c.name == "_audit_item":
                return True
            if isinstance(c, SQLQualifiedIdentifier) and c.parts[-1] == "_audit_item":
                return True
        return False

    @staticmethod
    def _add_audit_item_to_retrieve(cte_ast: "SQLExpression", cte_name: str) -> "SQLExpression":
        """Add ``_audit_item`` column to an included retrieve CTE.

        Mimics the logic in ``cte_builder.build_retrieve_cte`` but works on an
        already-built SQLSelect.  The evidence item is a struct_pack with the
        resource type + id as target and an ``exists`` operator.
        """
        from .types import (
            SQLSelect, SQLAlias, SQLQualifiedIdentifier, SQLFunctionCall,
            SQLLiteral, SQLBinaryOp, SQLCast, SQLNull, SQLEvidenceItem,
        )

        # Derive a human-friendly threshold label from CTE name
        threshold_label = f'[{cte_name}]'
        audit_item = SQLEvidenceItem(
            target=SQLBinaryOp(
                operator="||",
                left=SQLBinaryOp(
                    operator="||",
                    left=SQLQualifiedIdentifier(parts=["r", "resourceType"]),
                    right=SQLLiteral("/"),
                ),
                right=SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        SQLQualifiedIdentifier(parts=["r", "resource"]),
                        SQLLiteral("id"),
                    ],
                ),
            ),
            attribute=SQLCast(expression=SQLNull(), target_type="VARCHAR"),
            value=SQLCast(expression=SQLNull(), target_type="VARCHAR"),
            operator_str="exists",
            threshold=SQLLiteral(threshold_label),
        )
        new_columns = list(cte_ast.columns or []) + [
            SQLAlias(expr=audit_item, alias="_audit_item")
        ]
        return SQLSelect(
            columns=new_columns,
            from_clause=cte_ast.from_clause,
            where=cte_ast.where,
            joins=cte_ast.joins,
            group_by=cte_ast.group_by,
            having=cte_ast.having,
            order_by=cte_ast.order_by,
            limit=cte_ast.limit,
            distinct=cte_ast.distinct,
        )

    def _prefix_intra_library_refs(
        self, node: "SQLExpression", alias: str, def_names: set
    ) -> "SQLExpression":
        """Recursively rewrite bare CTE references to use library-prefixed names.

        When an included library definition references a sibling definition by bare name
        (e.g. 'Has Criteria Indicating Frailty'), this rewrites it to the prefixed form
        (e.g. 'AIFrailLTCF.Has Criteria Indicating Frailty') so the CTE reference matches
        the actual CTE name in the final SQL.
        """
        from .types import (
            SQLIdentifier, SQLSelect, SQLSubquery, SQLExists, SQLBinaryOp,
            SQLUnaryOp, SQLCase, SQLAlias, SQLCast, SQLFunctionCall,
            SQLUnion, SQLJoin, SQLInterval, SQLArray, SQLList, SQLNamedArg,
        )
        if node is None:
            return None

        if isinstance(node, SQLIdentifier):
            if node.quoted and node.name in def_names:
                return SQLIdentifier(name=f"{alias}.{node.name}", quoted=True)
            return node

        if isinstance(node, SQLSelect):
            node.from_clause = self._prefix_intra_library_refs(node.from_clause, alias, def_names)
            node.columns = [self._prefix_intra_library_refs(c, alias, def_names) for c in node.columns]
            if node.where:
                node.where = self._prefix_intra_library_refs(node.where, alias, def_names)
            if node.joins:
                node.joins = [self._prefix_intra_library_refs(j, alias, def_names) for j in node.joins]
            if node.group_by:
                node.group_by = [self._prefix_intra_library_refs(g, alias, def_names) for g in node.group_by]
            if node.having:
                node.having = self._prefix_intra_library_refs(node.having, alias, def_names)
            if node.order_by:
                node.order_by = [self._prefix_intra_library_refs(o, alias, def_names) for o in node.order_by]
            return node

        if isinstance(node, SQLSubquery):
            node.query = self._prefix_intra_library_refs(node.query, alias, def_names)
            return node

        if isinstance(node, SQLExists):
            node.subquery = self._prefix_intra_library_refs(node.subquery, alias, def_names)
            return node

        if isinstance(node, SQLBinaryOp):
            node.left = self._prefix_intra_library_refs(node.left, alias, def_names)
            node.right = self._prefix_intra_library_refs(node.right, alias, def_names)
            return node

        if isinstance(node, SQLUnaryOp):
            node.operand = self._prefix_intra_library_refs(node.operand, alias, def_names)
            return node

        if isinstance(node, SQLCase):
            if node.operand:
                node.operand = self._prefix_intra_library_refs(node.operand, alias, def_names)
            node.when_clauses = [
                (self._prefix_intra_library_refs(w, alias, def_names),
                 self._prefix_intra_library_refs(t, alias, def_names))
                for w, t in node.when_clauses
            ]
            if node.else_clause:
                node.else_clause = self._prefix_intra_library_refs(node.else_clause, alias, def_names)
            return node

        if isinstance(node, SQLAlias):
            node.expr = self._prefix_intra_library_refs(node.expr, alias, def_names)
            return node

        if isinstance(node, SQLCast):
            node.expression = self._prefix_intra_library_refs(node.expression, alias, def_names)
            return node

        if isinstance(node, SQLFunctionCall):
            node.args = [self._prefix_intra_library_refs(a, alias, def_names) for a in node.args]
            return node

        if isinstance(node, SQLUnion):
            node.operands = [self._prefix_intra_library_refs(q, alias, def_names) for q in node.operands]
            return node

        if isinstance(node, SQLJoin):
            node.table = self._prefix_intra_library_refs(node.table, alias, def_names)
            if node.on_condition:
                node.on_condition = self._prefix_intra_library_refs(node.on_condition, alias, def_names)
            return node

        if isinstance(node, SQLInterval):
            if node.low:
                node.low = self._prefix_intra_library_refs(node.low, alias, def_names)
            if node.high:
                node.high = self._prefix_intra_library_refs(node.high, alias, def_names)
            return node

        if isinstance(node, SQLArray):
            node.elements = [self._prefix_intra_library_refs(e, alias, def_names) for e in node.elements]
            return node

        if isinstance(node, SQLList):
            node.items = [self._prefix_intra_library_refs(e, alias, def_names) for e in node.items]
            return node

        if isinstance(node, SQLNamedArg):
            node.value = self._prefix_intra_library_refs(node.value, alias, def_names)
            return node

        return node

    def _register_included_functions_in_inliner(self, inliner) -> None:
        """Register functions from all included libraries (including transitive) in the inliner."""
        if self._library_loader is None:
            return
        visited = set()

        def _scan_library(library_ast, alias_prefix):
            """Recursively scan a library AST and register its functions."""
            if library_ast is None:
                return
            lib_id = id(library_ast)
            if lib_id in visited:
                return
            visited.add(lib_id)

            # Register function definitions from this library
            func_count = 0
            for stmt in library_ast.statements:
                if isinstance(stmt, FunctionDefinition):
                    inliner.register_function_from_ast(stmt, library_name=alias_prefix)
                    func_count += 1

            # Recursively process includes
            for inc in library_ast.includes:
                inc_alias = inc.alias or inc.path.rsplit(".", 1)[-1]
                inc_lib = self._load_required_library(inc.path, inc_alias)
                _scan_library(inc_lib, inc_alias)

        # Start from first-level includes
        for alias, lib_info in self._context.includes.items():
            lib_ast = getattr(lib_info, 'library_ast', None)
            if lib_ast:
                _scan_library(lib_ast, alias)
            elif self._library_loader:
                # Try loading via library_loader
                lib_path = lib_info.path if hasattr(lib_info, 'path') else alias
                lib_ast = self._load_required_library(lib_path, alias)
                _scan_library(lib_ast, alias)
