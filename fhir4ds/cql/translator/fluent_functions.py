"""
Fluent function translation for CQL to SQL.

This module provides the FluentFunctionTranslator class that handles
translation of CQL fluent function calls to SQL.

Key insight: ALL fluent functions are defined in CQL libraries
(e.g., QICoreCommon.cql, Status.cql), NOT built-in. They should be
inlined like regular CQL functions.

Translation process:
1. Condition.verified() -> Status_verified(Condition) (fluent syntax -> function call)
2. Inline Status_verified function body (just like regular functions)
3. Result: inlined SQL with parameter substitution

Naming convention:
- Pattern: {Library}_{ResourceType}_{functionName} for qualified calls
- Pattern: {ResourceType}_{functionName} for unqualified calls
- Example: Status.Condition.verified() -> Status_Condition_verified(conditions)
- Example: Condition.verified() -> Condition_verified(conditions) (searches included libraries)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from ..paths import get_resource_path

logger = logging.getLogger(__name__)

from ..translator.types import (
    SQLExpression,
    SQLFunctionCall,
    SQLIdentifier,
    SQLLiteral,
    SQLBinaryOp,
    SQLUnaryOp,
    SQLCase,
    SQLNull,
    SQLCast,
    SQLQualifiedIdentifier,
    SQLList,
    SQLLambda,
    SQLRaw,
    SQLSubquery,
    SQLSelect,
    SQLExists,
    SQLAlias,
)
from ..translator.function_inliner import FunctionInliner, TranslationError
from ..translator.fluent_function_loader import FluentFunctionLoader

if TYPE_CHECKING:
    from ..translator.context import SQLTranslationContext

# ---------------------------------------------------------------------------
# Gap 1: Status filter registry – maps fluent function names to the status
# codes they accept.  ``null_passes: True`` means a NULL value in the
# status field should pass the filter (implies / NULL-pass-through semantics).
# ---------------------------------------------------------------------------


@dataclass
class FunctionParameter:
    """
    Represents a parameter in a fluent function definition.

    Attributes:
        name: Parameter name.
        param_type: CQL type of the parameter.
        is_fluent_param: Whether this is the fluent receiver parameter.
    """

    name: str
    param_type: str = "Any"
    is_fluent_param: bool = False


@dataclass
class FunctionDefinition:
    """
    Represents a fluent function definition from a CQL library.

    Attributes:
        name: The function name (without library prefix).
        library: The library name where the function is defined.
        qualified_name: Fully qualified name (Library_FunctionName).
        parameters: List of function parameters.
        return_type: The return type of the function.
        body: The function body (AST node or SQL expression template).
        body_sql: Pre-translated SQL body template (if available).
        resource_type: The resource type this fluent function applies to.
    """

    name: str
    library: Optional[str] = None
    qualified_name: str = ""
    parameters: List[FunctionParameter] = field(default_factory=list)
    return_type: str = "Any"
    body: Any = None
    body_sql: Optional[str] = None
    resource_type: Optional[str] = None
    is_stub: bool = False  # True for registry-only placeholder entries (no body)

    def __post_init__(self):
        if not self.qualified_name:
            if self.library:
                self.qualified_name = f"{self.library}_{self.name}"
            else:
                self.qualified_name = self.name


@dataclass
class FluentFunctionRegistry:
    """
    Registry for fluent function definitions.

    Stores function definitions from included CQL libraries and provides
    lookup methods for resolving fluent function calls.
    """

    # Function storage: keyed by qualified name or simple name
    functions: Dict[str, FunctionDefinition] = field(default_factory=dict)

    # Index by resource type for faster lookup
    by_resource_type: Dict[str, List[str]] = field(default_factory=dict)

    # Index by library for qualified lookups
    by_library: Dict[str, List[str]] = field(default_factory=dict)

    def register(self, func: FunctionDefinition) -> None:
        """
        Register a fluent function definition.

        Args:
            func: The function definition to register.
        """
        # Store by qualified name
        self.functions[func.qualified_name] = func

        # Also store by simple name for unqualified lookups
        if func.name not in self.functions:
            self.functions[func.name] = func

        # Index by resource type
        if func.resource_type:
            if func.resource_type not in self.by_resource_type:
                self.by_resource_type[func.resource_type] = []
            if func.qualified_name not in self.by_resource_type[func.resource_type]:
                self.by_resource_type[func.resource_type].append(func.qualified_name)

        # Index by library
        if func.library:
            if func.library not in self.by_library:
                self.by_library[func.library] = []
            if func.qualified_name not in self.by_library[func.library]:
                self.by_library[func.library].append(func.qualified_name)

    def lookup_qualified(
        self,
        library: str,
        function_name: str,
        resource_type: Optional[str] = None,
    ) -> Optional[FunctionDefinition]:
        """
        Look up a function by qualified name (library prefix).

        Args:
            library: The library name/alias.
            function_name: The function name.
            resource_type: Optional resource type for disambiguation.

        Returns:
            The function definition, or None if not found.
        """
        # Try fully qualified name with resource type
        if resource_type:
            qualified = f"{library}_{resource_type}_{function_name}"
            if qualified in self.functions:
                return self.functions[qualified]

        # Try library + function name
        qualified = f"{library}_{function_name}"
        if qualified in self.functions:
            return self.functions[qualified]

        return None

    def lookup_unqualified(
        self,
        function_name: str,
        resource_type: Optional[str] = None,
        included_libraries: Optional[List[str]] = None,
    ) -> Optional[FunctionDefinition]:
        """
        Look up a function by unqualified name.

        Searches through included libraries to find the function.

        Args:
            function_name: The function name (without library prefix).
            resource_type: Optional resource type for disambiguation.
            included_libraries: List of included library names to search.

        Returns:
            The function definition, or None if not found.
        """
        # Try with resource type prefix first
        if resource_type:
            resource_qualified = f"{resource_type}_{function_name}"
            if resource_qualified in self.functions:
                return self.functions[resource_qualified]

        # Try simple name
        if function_name in self.functions:
            return self.functions[function_name]

        # Search included libraries in order
        if included_libraries:
            for lib in included_libraries:
                func = self.lookup_qualified(lib, function_name, resource_type)
                if func:
                    return func

        return None

    def get_functions_for_resource(
        self,
        resource_type: str,
    ) -> List[FunctionDefinition]:
        """
        Get all fluent functions applicable to a resource type.

        Args:
            resource_type: The FHIR resource type.

        Returns:
            List of function definitions for the resource type.
        """
        func_names = self.by_resource_type.get(resource_type, [])
        return [self.functions[name] for name in func_names if name in self.functions]


class FluentFunctionTranslator:
    """
    Translates CQL fluent function calls to SQL.

    Fluent functions are called with dot notation on a resource:
    - Condition.verified()
    - Observation.effective.latest()
    - Encounter.isEncounterPerformed()

    These are translated to regular function calls and then inlined:
    - Condition.verified() -> Status_verified(Condition) -> <inlined SQL>
    """

    def __init__(self, context: SQLTranslationContext, lightweight: bool = False):
        """
        Initialize the fluent function translator.

        Args:
            context: The translation context for symbol resolution.
            lightweight: If True, skip creating a FunctionInliner and loading
                        CQL libraries (used when expand-then-translate handles
                        CQL-defined functions via context.function_inliner).
        """
        self.context = context
        self.registry = FluentFunctionRegistry()

        if lightweight:
            # Use the shared inliner from context (already populated)
            self.inliner = context.function_inliner or FunctionInliner(context)
        else:
            # Legacy path: create own inliner and load libraries
            self.inliner = FunctionInliner(context)
            loader = FluentFunctionLoader()
            loader.load_default_libraries(self.inliner, context)

        self._initialize_common_functions()

    def _initialize_common_functions(self) -> None:
        """Pre-register well-known fluent functions from config so the registry
        is queryable without loading full CQL libraries."""
        stubs_path = get_resource_path("terminology", "fluent_function_stubs.json")
        if not stubs_path.exists():
            logger.debug("No fluent_function_stubs.json found; skipping stub registration")
            return
        with open(stubs_path) as f:
            data = json.load(f)
        for entry in data.get("stubs", []):
            self.registry.register(
                FunctionDefinition(
                    name=entry["name"],
                    library=entry["library"],
                    resource_type=entry["resource_type"],
                    is_stub=True,
                )
            )


    def translate_fluent_call(
        self,
        resource_expr: SQLExpression,
        function_name: str,
        args: List[SQLExpression],
        context: SQLTranslationContext,
        library_prefix: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> SQLExpression:
        """
        Translate a fluent function call to SQL.

        Converts fluent syntax (resource.function()) to regular function call
        (function(resource)) and inlines the function body.

        Args:
            resource_expr: The SQL expression for the resource (receiver).
            function_name: The name of the fluent function.
            args: Additional arguments to the function (excluding receiver).
            context: The translation context.
            library_prefix: Optional library prefix for qualified calls.
            resource_type: The FHIR resource type (if known).

        Returns:
            The SQL expression for the inlined function call.
        """
        # FHIRCommon ext(element, url) -> element.extension.where(url='URL')
        # Translates to fhirpath_text(resource, "extension.where(url='URL')")
        if function_name == "ext" and len(args) == 1:
            url_arg = args[0]
            url_val = getattr(url_arg, 'value', None) if hasattr(url_arg, 'value') else None
            if url_val and isinstance(url_val, str):
                fhirpath_expr = f"extension.where(url='{url_val}')"
                return SQLFunctionCall(
                    name="fhirpath_text",
                    args=[resource_expr, SQLLiteral(fhirpath_expr)],
                )

        # Direct AST builders bypass CQL inlining for functions with optimized
        # SQL generation (e.g., prevalenceInterval avoids broken type-check inlining)
        _AST_BUILDER_NAMES = {"prevalenceInterval", "latest", "hasPrincipalDiagnosisOf", "hasPrincipalProcedureOf"}
        if function_name in _AST_BUILDER_NAMES:
            try:
                return self._build_template_ast(
                    FunctionDefinition(name=function_name, body_sql="", resource_type=resource_type or ""),
                    resource_expr, args, context,
                )
            except NotImplementedError:
                pass  # Fall through to standard resolution

        # Resolve the function definition
        # Get resource_type from context if available (may not exist in all implementations)
        context_resource_type = getattr(context, 'resource_type', None)
        func_def = self.resolve_fluent_function(
            function_name,
            resource_type or context_resource_type,
            context,
            library_prefix,
        )

        if func_def is None or func_def.is_stub:
            # Stub entries are registry-only placeholders; fall through to CQL context lookup
            # Check for CQL-defined fluent function in context
            cql_func = context.get_function(function_name, resource_type=resource_type)

            # Also check included libraries if not found directly
            found_lib_alias = None
            if cql_func is None or not getattr(cql_func, 'is_fluent', False):
                for lib_alias in context.includes.keys():
                    lib_func = context.resolve_library_function(
                        lib_alias, function_name, resource_type=resource_type
                    )
                    if lib_func and getattr(lib_func, 'is_fluent', False):
                        cql_func = lib_func
                        found_lib_alias = lib_alias
                        break

            if cql_func and getattr(cql_func, 'is_fluent', False):
                # Check if this is a status filter function first — using the dedicated
                # AST builder preserves SQLUnion sources (the inliner loses them)
                if self._has_dynamic_status_filter(function_name, context):
                    return self._build_status_filter_ast(function_name, resource_expr, context)

                # Check if the resolved overload body uses unsupported CQL constructs
                # (e.g., 'collapse'). If so, fall back to the default overload.
                if resource_type and cql_func.expression and self._cql_body_has_unsupported_construct(cql_func.expression):
                    logger.debug(
                        "Overload for %s(%s) uses unsupported constructs, falling back",
                        function_name, resource_type,
                    )
                    fallback = context.get_function(function_name)
                    if fallback and fallback is not cql_func and not self._cql_body_has_unsupported_construct(getattr(fallback, 'expression', None)):
                        return self._inline_cql_function(
                            fallback, function_name, resource_expr, args, context
                        )
                    for lib_alias2 in context.includes.keys():
                        fallback = context.resolve_library_function(
                            lib_alias2, function_name
                        )
                        if fallback and getattr(fallback, 'is_fluent', False) and fallback is not cql_func:
                            if not self._cql_body_has_unsupported_construct(getattr(fallback, 'expression', None)):
                                return self._inline_cql_function(
                                    fallback, function_name, resource_expr, args, context, lib_alias2
                                )

                # Use FunctionInliner to handle CQL-defined fluent functions.
                # Use the SHARED inliner from context so the _inlining_stack is
                # preserved across recursive translate_fluent_call invocations.
                # Creating a fresh FunctionInliner() here would give it an empty
                # stack, defeating cycle detection and causing infinite recursion.
                from ..translator.function_inliner import FunctionInliner, FunctionDef
                inliner = context.function_inliner or FunctionInliner(context)

                # Register the CQL function with the inliner if it has an expression
                if cql_func.expression:
                    # Build parameters list
                    parameters = []
                    for param in (cql_func.parameters or []):
                        param_type = getattr(param, 'type', None)
                        if param_type:
                            try:
                                param_type = getattr(param_type, 'name', None) or repr(param_type)
                            except Exception as e:
                                logger.warning("Failed to get param type for %s: %s", param.name, e)
                                param_type = str(type(param_type).__name__)
                        parameters.append((param.name, param_type))

                    # Use a type-qualified name so that different overloads of the
                    # same function get distinct inliner keys.  Without this,
                    # references(List<Reference>, Resource) calling
                    # references(Reference, Resource) triggers false-positive cycle
                    # detection because both share the key "QICoreCommon.references".
                    type_sig = ",".join(str(pt) for _, pt in parameters if pt)
                    inliner_func_name = f"{cql_func.name}/{type_sig}" if type_sig else cql_func.name

                    # If this key is already in the shared inliner's stack it means
                    # we are inside this overload's body — the apparent recursive call
                    # is most likely a *different* overload (e.g. the scalar vs list
                    # overloads of QICoreCommon.references).  Collect all registered
                    # overloads of this function and try the first one NOT in the stack.
                    full_key = (
                        f"{found_lib_alias}.{inliner_func_name}"
                        if found_lib_alias else inliner_func_name
                    )
                    if full_key in inliner._inlining_stack:
                        # Look for an alternative overload from the library
                        alt_func = None
                        if found_lib_alias:
                            lib_info = context.includes.get(found_lib_alias)
                            if lib_info:
                                for ovl in lib_info.function_overloads.get(function_name, []):
                                    if ovl is cql_func or not getattr(ovl, 'expression', None):
                                        continue
                                    # Build candidate type sig for this overload
                                    ovl_params = []
                                    for p in (ovl.parameters or []):
                                        pt = getattr(p, 'type', None)
                                        if pt:
                                            try:
                                                pt = getattr(pt, 'name', None) or repr(pt)
                                            except Exception as e:
                                                logger.warning("Failed to get overload param type: %s", e)
                                                pt = type(pt).__name__
                                        ovl_params.append((p.name, pt))
                                    ovl_sig = ",".join(str(pt) for _, pt in ovl_params if pt)
                                    ovl_name = f"{ovl.name}/{ovl_sig}" if ovl_sig else ovl.name
                                    ovl_key = f"{found_lib_alias}.{ovl_name}"
                                    if ovl_key not in inliner._inlining_stack:
                                        alt_func = (ovl, ovl_params, ovl_name, found_lib_alias)
                                        break
                        if alt_func is None:
                            # Genuine cycle — raise so the caller falls through
                            raise NotImplementedError(
                                f"All overloads of {function_name} are in the inlining stack"
                            )
                        ovl, ovl_params, ovl_name, ovl_lib = alt_func
                        ovl_func_def = FunctionDef(
                            name=ovl_name,
                            library_name=ovl_lib,
                            parameters=ovl_params,
                            return_type=ovl.return_type,
                            body=ovl.expression,
                            fluent=True,
                        )
                        inliner.register_function(ovl_func_def)
                        return inliner.inline_function(
                            ovl_name,
                            [resource_expr] + args,
                            context,
                            library_name=ovl_lib,
                        )

                    func_def_for_inliner = FunctionDef(
                        name=inliner_func_name,
                        library_name=found_lib_alias,
                        parameters=parameters,
                        return_type=cql_func.return_type,
                        body=cql_func.expression,
                        fluent=True,
                    )
                    inliner.register_function(func_def_for_inliner)

                    # Inline the function with receiver as first argument, using the
                    # type-qualified name so the key matches what was registered.
                    return inliner.inline_function(
                        inliner_func_name,
                        [resource_expr] + args,
                        context,
                        library_name=found_lib_alias,
                    )
                else:
                    # No body — fall through to placeholder
                    pass

            # Function not found — raise so the caller can try the inliner fallback.
            # (Returning a placeholder here would silently block inliner.expand_function
            # in _lists.py, which is the correct path when Status.cql / QICoreCommon.cql
            # are loaded into context.function_inliner but not in context.includes.)
            raise NotImplementedError(
                f"No translation found for fluent function '{function_name}'"
            )

        # Inline the function body
        return self._inline_function_body(
            func_def,
            resource_expr,
            args,
            context,
        )

    @staticmethod
    def _inline_cql_function(
        cql_func: Any,
        function_name: str,
        resource_expr: SQLExpression,
        args: List[SQLExpression],
        context: SQLTranslationContext,
        lib_alias: Optional[str] = None,
    ) -> SQLExpression:
        """Inline a CQL-defined fluent function using the FunctionInliner."""
        from ..translator.function_inliner import FunctionInliner, FunctionDef
        inliner = FunctionInliner(context)
        if cql_func.expression:
            parameters = []
            for param in (cql_func.parameters or []):
                param_type = getattr(param, 'type', None)
                if param_type:
                    param_type = getattr(param_type, 'name', str(param_type))
                parameters.append((param.name, param_type))
            inliner.register_function(FunctionDef(
                name=cql_func.name,
                library_name=lib_alias or getattr(cql_func, 'library_alias', None),
                parameters=parameters,
                return_type=cql_func.return_type,
                body=cql_func.expression,
                fluent=True,
            ))
        return inliner.inline_function(
            function_name,
            [resource_expr] + args,
            context,
            library_name=lib_alias or getattr(cql_func, 'library_alias', None),
        )

    @staticmethod
    def _cql_body_has_unsupported_construct(node: Any) -> bool:
        """Check if a CQL AST body contains unsupported constructs like collapse."""
        if node is None:
            return False
        _UNSUPPORTED_FUNCTIONS = {'flatten'}
        ntype = getattr(node, 'type', type(node).__name__)
        if ntype == 'FunctionRef' and getattr(node, 'name', '') in _UNSUPPORTED_FUNCTIONS:
            return True
        for k in vars(node):
            if k.startswith('_') or k in ('locator', 'annotation', 'resultTypeSpecifier', 'resultTypeName'):
                continue
            val = getattr(node, k, None)
            if val is None or callable(val) or isinstance(val, (str, int, float, bool, type)):
                continue
            if isinstance(val, list):
                for item in val:
                    if hasattr(item, '__dict__') and not isinstance(item, type):
                        if FluentFunctionTranslator._cql_body_has_unsupported_construct(item):
                            return True
            elif hasattr(val, '__dict__') and not isinstance(val, type):
                if FluentFunctionTranslator._cql_body_has_unsupported_construct(val):
                    return True
        return False

    def resolve_fluent_function(
        self,
        function_name: str,
        resource_type: Optional[str],
        context: SQLTranslationContext,
        library_prefix: Optional[str] = None,
    ) -> Optional[FunctionDefinition]:
        """
        Resolve a fluent function to its definition.

        Args:
            function_name: The name of the function.
            resource_type: The FHIR resource type.
            context: The translation context.
            library_prefix: Optional library prefix for qualified calls.

        Returns:
            The function definition, or None if not found.
        """
        # Get included libraries from context
        included_libraries = list(context.includes.keys()) if context.includes else []

        if library_prefix:
            # Qualified lookup
            return self.registry.lookup_qualified(
                library_prefix,
                function_name,
                resource_type,
            )

        # Unqualified lookup - search included libraries
        return self.registry.lookup_unqualified(
            function_name,
            resource_type,
            included_libraries,
        )

    def _search_included_libraries(
        self,
        function_name: str,
        resource_type: str,
        context: SQLTranslationContext,
    ) -> Optional[FunctionDefinition]:
        """
        Search included libraries for a fluent function.

        Args:
            function_name: The name of the function.
            resource_type: The FHIR resource type.
            context: The translation context.

        Returns:
            The function definition, or None if not found.
        """
        included_libraries = list(context.includes.keys()) if context.includes else []
        return self.registry.lookup_unqualified(
            function_name,
            resource_type,
            included_libraries,
        )

    def _extract_cte_name(self, resource_expr: SQLExpression) -> Optional[str]:
        """
        Extract CTE name from a resource expression for column optimization.

        Args:
            resource_expr: The resource expression (identifier, subquery, etc.)

        Returns:
            CTE name if extractable, None otherwise
        """
        # Direct identifier: "Condition: Essential Hypertension"
        if isinstance(resource_expr, SQLIdentifier):
            name = resource_expr.name
            return name.strip('"') if name.startswith('"') else name

        # Qualified identifier: cte.column
        if isinstance(resource_expr, SQLQualifiedIdentifier):
            name = resource_expr.parts[0] if resource_expr.parts else None
            return name.strip('"') if name and name.startswith('"') else name

        # Subquery: (SELECT ... FROM cte)
        if isinstance(resource_expr, SQLSubquery):
            select = resource_expr.query
            if hasattr(select, 'from_clause') and isinstance(select.from_clause, SQLIdentifier):
                name = select.from_clause.name
                return name.strip('"') if name.startswith('"') else name

        return None

    @staticmethod
    def _ensure_resource_column(resource_expr: SQLExpression) -> SQLExpression:
        """
        Ensure resource_expr points to the JSON resource column for fhirpath calls.

        When resource_expr is a simple table alias (e.g., SQLIdentifier("Hypertension")),
        fhirpath functions need the .resource column, not the whole row (STRUCT).
        """
        if isinstance(resource_expr, SQLIdentifier) and not resource_expr.quoted:
            name = resource_expr.name
            if '.' not in name and '(' not in name:
                return SQLQualifiedIdentifier(parts=[name, "resource"])
        return resource_expr

    def _build_template_ast(
        self,
        func_def: FunctionDefinition,
        resource_expr: SQLExpression,
        args: List[SQLExpression],
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Build structured AST for fluent function templates.

        Returns AST instead of SQL string, enabling JOIN optimization
        and precomputed column usage.

        Args:
            func_def: The function definition
            resource_expr: The resource expression
            args: Additional arguments
            context: Translation context

        Returns:
            AST representation of the function call

        Raises:
            NotImplementedError: If AST builder not available for this function
        """
        # Dispatch based on function name
        # Check dynamically extracted status filters from library ASTs
        if self._has_dynamic_status_filter(func_def.name, context):
            return self._build_status_filter_ast(func_def.name, resource_expr, context)
        elif func_def.name == "prevalenceInterval":
            return self._build_prevalence_interval_ast(resource_expr, args, context)
        elif func_def.name == "latest":
            return self._build_latest_ast(resource_expr, args, context)
        elif func_def.name == "earliest":
            return self._build_earliest_ast(resource_expr, args, context)
        elif func_def.name == "hasPrincipalDiagnosisOf":
            return self._build_has_principal_diagnosis_of_ast(resource_expr, args, context)
        elif func_def.name == "hasPrincipalProcedureOf":
            return self._build_has_principal_procedure_of_ast(resource_expr, args, context)
        else:
            # No AST builder for this function - fall back to template
            raise NotImplementedError(f"No AST builder for function: {func_def.name}")

    def _ensure_dynamic_status_filters(self, context: SQLTranslationContext) -> None:
        """Lazily extract dynamic status filters from included library ASTs."""
        if not hasattr(self, '_dynamic_status_filters'):
            self._dynamic_status_filters: Dict[str, dict] = {}
            self._dynamic_extraction_done = False

        if not self._dynamic_extraction_done:
            self._dynamic_extraction_done = True
            try:
                from .status_filter_extractor import extract_all_status_filters
                for lib_info in context.includes.values():
                    if hasattr(lib_info, 'library_ast') and lib_info.library_ast is not None:
                        codes = dict(context.codes) if hasattr(context, 'codes') else None
                        extracted = extract_all_status_filters(lib_info.library_ast, codes)
                        self._dynamic_status_filters.update(extracted)
            except Exception as e:
                logger.warning("Failed to extract dynamic status filters: %s", e)

    def _has_dynamic_status_filter(self, function_name: str, context: SQLTranslationContext) -> bool:
        """Check if a dynamic status filter exists for the given function name."""
        self._ensure_dynamic_status_filters(context)
        return function_name in self._dynamic_status_filters

    def _resolve_status_filter(self, function_name: str, context: SQLTranslationContext) -> dict:
        """Resolve status filter config from dynamically extracted library ASTs."""
        self._ensure_dynamic_status_filters(context)
        if function_name in self._dynamic_status_filters:
            return self._dynamic_status_filters[function_name]
        raise KeyError(
            f"No status filter found for '{function_name}'. "
            "The status filter extractor could not read this function from the CQL AST. "
            "This is a bug in status_filter_extractor.py — fix the extractor."
        )

    def _build_status_filter_ast(
        self,
        function_name: str,
        resource_expr: SQLExpression,
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Build AST for status filter functions using dynamically extracted configs.

        Generates ``SELECT resource FROM {source} WHERE condition`` instead of
        ``list_filter`` lambdas so that no lambda expressions appear in the
        generated SQL.

        For entries with ``null_passes: True`` the WHERE clause becomes::

            (fhirpath_text(resource, field) IS NULL
             OR fhirpath_text(resource, field) IN ('v1', 'v2', ...))

        For standard entries::

            fhirpath_text(resource, field) IN ('v1', 'v2', ...)
        """
        config = self._resolve_status_filter(function_name, context)
        status_field = config["status_field"]
        allowed = config["allowed"]
        null_passes = config.get("null_passes", False)
        intent_field = config.get("intent_field")
        intent_allowed = config.get("intent_allowed")

        # Detect if resource_expr is a row-level alias (e.g., from a with clause)
        # vs. a table-level CTE reference. Row-level aliases are simple unquoted identifiers
        # or qualified identifiers — produce a scalar boolean instead of a subquery.
        is_row_level = (
            (isinstance(resource_expr, SQLIdentifier) and not resource_expr.quoted)
            or isinstance(resource_expr, SQLQualifiedIdentifier)
        )

        if is_row_level:
            # Scalar boolean: check properties on the current row
            if isinstance(resource_expr, SQLQualifiedIdentifier) and resource_expr.parts[-1] == "resource":
                res_col = resource_expr
            else:
                alias_name = resource_expr.name if isinstance(resource_expr, SQLIdentifier) else resource_expr.parts[0]
                res_col = SQLQualifiedIdentifier(parts=[alias_name, "resource"])

            fhirpath_call = SQLFunctionCall(
                name="fhirpath_text",
                args=[res_col, SQLLiteral(value=status_field)],
            )
            in_condition = SQLBinaryOp(
                operator="IN",
                left=fhirpath_call,
                right=SQLList(items=[SQLLiteral(v) for v in allowed]),
            )
            if null_passes:
                null_check = SQLUnaryOp(
                    operator="IS NULL",
                    operand=SQLFunctionCall(
                        name="fhirpath_text",
                        args=[res_col, SQLLiteral(value=status_field)],
                    ),
                    prefix=False,
                )
                result_condition = SQLBinaryOp(operator="OR", left=null_check, right=in_condition)
            else:
                result_condition = in_condition

            if intent_field and intent_allowed:
                intent_call = SQLFunctionCall(
                    name="fhirpath_text",
                    args=[res_col, SQLLiteral(value=intent_field)],
                )
                intent_cond = SQLBinaryOp(
                    operator="IN",
                    left=intent_call,
                    right=SQLList(items=[SQLLiteral(v) for v in intent_allowed]),
                )
                result_condition = SQLBinaryOp(operator="AND", left=result_condition, right=intent_cond)

            return result_condition

        fhirpath_call = SQLFunctionCall(
            name="fhirpath_text",
            args=[
                SQLIdentifier(name="resource"),
                SQLLiteral(value=status_field),
            ],
        )

        in_condition = SQLBinaryOp(
            operator="IN",
            left=fhirpath_call,
            right=SQLList(items=[SQLLiteral(v) for v in allowed]),
        )

        if null_passes:
            null_check = SQLUnaryOp(
                operator="IS NULL",
                operand=SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        SQLIdentifier(name="resource"),
                        SQLLiteral(value=status_field),
                    ],
                ),
                prefix=False,
            )
            where_condition = SQLBinaryOp(
                operator="OR",
                left=null_check,
                right=in_condition,
            )
        else:
            where_condition = in_condition

        # Add intent filter if configured (e.g., isInterventionOrder, isMedicationActive)
        if intent_field and intent_allowed:
            intent_call = SQLFunctionCall(
                name="fhirpath_text",
                args=[
                    SQLIdentifier(name="resource"),
                    SQLLiteral(value=intent_field),
                ],
            )
            intent_condition = SQLBinaryOp(
                operator="IN",
                left=intent_call,
                right=SQLList(items=[SQLLiteral(v) for v in intent_allowed]),
            )
            where_condition = SQLBinaryOp(
                operator="AND",
                left=where_condition,
                right=intent_condition,
            )

        select = SQLSelect(
            columns=[SQLIdentifier(name="patient_id"), SQLIdentifier(name="resource")],
            from_clause=resource_expr,
            where=where_condition,
        )

        return SQLSubquery(query=select)

    def _build_prevalence_interval_ast(
        self,
        resource_expr: SQLExpression,
        args: List[SQLExpression],
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Build AST for .prevalenceInterval() - extracts onset/abatement interval.

        This function is called on a SINGLE Condition resource (not a list),
        so resource_expr is the resource itself, not a list.

        Optimization: Use precomputed onset_date and abatement_date columns if available.
        But since this is called on a single resource (e.g., from a WHERE clause),
        we need to access it via the resource expression directly.

        Note: This optimization won't work until we can reference the CTE columns
        from the WHERE clause context. For now, fall back to FHIRPath.

        Args:
            resource_expr: The resource expression (single resource, not list)
            args: Additional arguments (none for prevalenceInterval)
            context: Translation context

        Returns:
            AST for prevalenceInterval() function
        """
        # FALLBACK: Use FHIRPath calls (match the existing template)
        # The optimization requires accessing CTE columns which isn't available in this context
        # Ensure we reference the .resource column when resource_expr is a table alias
        res = self._ensure_resource_column(resource_expr)
        # Build onset expression: COALESCE(onsetDateTime, onsetPeriod.start, recordedDate)
        # Use fhirpath_text to preserve datetime precision (time component matters for overlaps)
        onset_coalesce = SQLFunctionCall(
            name="COALESCE",
            args=[
                SQLFunctionCall(name="fhirpath_text", args=[res, SQLLiteral("onsetDateTime")]),
                SQLFunctionCall(name="fhirpath_text", args=[res, SQLLiteral("onsetPeriod.start")]),
                SQLFunctionCall(name="fhirpath_text", args=[res, SQLLiteral("recordedDate")]),
            ]
        )
        # When onset is NULL (e.g. Observations have no onset/recorded fields),
        # return SQL NULL so COALESCE falls through to the next alternative.
        return SQLCase(
            when_clauses=[
                (
                    SQLBinaryOp(
                        operator="IS NOT",
                        left=SQLFunctionCall(
                            name="fhirpath_text",
                            args=[res, SQLLiteral("abatementDateTime")]
                        ),
                        right=SQLNull()
                    ),
                    SQLFunctionCall(
                        name="intervalFromBounds",
                        args=[
                            onset_coalesce,
                            SQLFunctionCall(
                                name="fhirpath_text",
                                args=[res, SQLLiteral("abatementDateTime")]
                            ),
                            SQLLiteral(True),
                            SQLLiteral(True)
                        ]
                    )
                ),
                (
                    SQLBinaryOp(
                        operator="IS NOT",
                        left=onset_coalesce,
                        right=SQLNull()
                    ),
                    # CQL prevalenceInterval: active/recurrence/relapse → closed high
                    # (Interval[onset, null] = extends to infinity);
                    # inactive with no abatement → open high (Interval[onset, null)).
                    SQLCase(
                        when_clauses=[
                            (
                                SQLFunctionCall(
                                    name="fhirpath_bool",
                                    args=[
                                        res,
                                        SQLLiteral(
                                            "clinicalStatus.coding.where("
                                            "code='active' or code='recurrence' or code='relapse'"
                                            ").exists()"
                                        ),
                                    ],
                                ),
                                SQLFunctionCall(
                                    name="intervalFromBounds",
                                    args=[
                                        onset_coalesce,
                                        SQLNull(),
                                        SQLLiteral(True),
                                        SQLLiteral(True),
                                    ],
                                ),
                            )
                        ],
                        else_clause=SQLFunctionCall(
                            name="intervalFromBounds",
                            args=[
                                onset_coalesce,
                                SQLNull(),
                                SQLLiteral(True),
                                SQLLiteral(False),
                            ],
                        ),
                    )
                )
            ],
            else_clause=SQLNull()
        )

    def _build_latest_ast(
        self,
        resource_expr: SQLExpression,
        args: List[SQLExpression],
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Build AST for .latest() - returns most recent resource by property.

        Optimization: Use precomputed date columns if available.

        Args:
            resource_expr: The resource expression
            args: Additional arguments (property name if specified)
            context: Translation context

        Returns:
            AST for latest() function

        Generated SQL pattern:
            (SELECT resource FROM (
                SELECT resource, COALESCE(
                    fhirpath_date(resource, 'effectiveDateTime'),
                    fhirpath_date(resource, 'effectivePeriod.start')
                ) AS effective_date
                FROM {resource}
                ORDER BY effective_date DESC
                LIMIT 1
            ) AS sub)
        """
        # Extract property name from args (default to effectiveDateTime for Observation)
        # Note: The template uses COALESCE of effectiveDateTime and effectivePeriod.start
        property_name = "effectiveDateTime"
        if args:
            if isinstance(args[0], SQLLiteral):
                property_name = str(args[0].value).strip("'\"")

        cte_name = self._extract_cte_name(resource_expr)

        # If resource_expr is a scalar fhirpath_text call on a FHIR choice property
        # (e.g., effective[x]), latest() should resolve the choice to a date/time value
        # using COALESCE across DateTime and Period sub-properties.
        _CHOICE_DATE_PROPERTIES = {"effective", "onset", "abatement", "performed", "occurrence"}
        if isinstance(resource_expr, SQLFunctionCall) and resource_expr.name == "fhirpath_text":
            if len(resource_expr.args) >= 2 and isinstance(resource_expr.args[1], SQLLiteral):
                prop_name = str(resource_expr.args[1].value)
                if prop_name in _CHOICE_DATE_PROPERTIES:
                    res = resource_expr.args[0]  # The resource expression
                    return SQLFunctionCall(
                        name="COALESCE",
                        args=[
                            SQLFunctionCall(name="fhirpath_date", args=[res, SQLLiteral(f"{prop_name}DateTime")]),
                            SQLFunctionCall(name="intervalEnd", args=[
                                SQLFunctionCall(name="fhirpath_text", args=[res, SQLLiteral(f"{prop_name}Period")])
                            ]),
                        ],
                    )

        # If resource_expr is a scalar expression (function call, binary op,
        # inline subquery, or CASE), latest() is identity — return directly.
        # latest() only makes sense as a FROM-based subquery when applied to a collection
        # (i.e., an SQLIdentifier or SQLAlias referencing a CTE).
        if isinstance(resource_expr, (SQLFunctionCall, SQLBinaryOp, SQLSubquery, SQLCase)):
            return resource_expr
        if isinstance(resource_expr, SQLQualifiedIdentifier) and len(resource_expr.parts) >= 2:
            # e.g., BPExam.effective — this is a property access, not a table reference
            second_part = resource_expr.parts[-1]
            if second_part not in ("patient_id", "resource"):
                return resource_expr

        # Check for precomputed column
        date_expr: SQLExpression
        if cte_name and context.column_registry:
            # Try direct fhirpath lookup first
            col_name = context.column_registry.lookup(cte_name, property_name)
            # Also try the precomputed effective_date column (choice-type)
            if not col_name and context.column_registry.has_column(cte_name, "effective_date"):
                col_name = "effective_date"
            if col_name:
                # OPTIMIZATION: Use precomputed column directly
                date_expr = SQLQualifiedIdentifier(parts=["r", col_name])
            else:
                # Fall back to fhirpath_date calls
                date_expr = self._build_date_coalesce_expr(resource_expr, property_name)
        else:
            # Fall back to fhirpath_date calls
            date_expr = self._build_date_coalesce_expr(resource_expr, property_name)

        # Build the inner SELECT: SELECT r.resource, date_expr AS effective_date
        # FROM {resource} AS r ORDER BY effective_date DESC LIMIT 1
        # Unwrap any existing alias so we can re-alias as "r"
        from_base = resource_expr.expr if isinstance(resource_expr, SQLAlias) else resource_expr
        inner_select = SQLSelect(
            columns=[
                SQLQualifiedIdentifier(parts=["r", "resource"]),
                (date_expr, "effective_date"),
            ],
            from_clause=SQLAlias(expr=from_base, alias="r"),
            order_by=[(SQLIdentifier(name="effective_date"), "DESC")],
            limit=1,
        )

        # Build the outer SELECT: SELECT sub.resource FROM (inner) AS sub
        outer_select = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["sub", "resource"])],
            from_clause=SQLAlias(expr=SQLSubquery(query=inner_select), alias="sub"),
        )

        return SQLSubquery(query=outer_select)

    def _build_earliest_ast(
        self,
        resource_expr: SQLExpression,
        args: List[SQLExpression],
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Build AST for .earliest() - returns oldest resource by date property.

        Mirrors _build_latest_ast with ASC ordering instead of DESC.
        """
        property_name = "effectiveDateTime"
        if args:
            if isinstance(args[0], SQLLiteral):
                property_name = str(args[0].value).strip("'\"")

        cte_name = self._extract_cte_name(resource_expr)

        _CHOICE_DATE_PROPERTIES = {"effective", "onset", "abatement", "performed", "occurrence"}
        if isinstance(resource_expr, SQLFunctionCall) and resource_expr.name == "fhirpath_text":
            if len(resource_expr.args) >= 2 and isinstance(resource_expr.args[1], SQLLiteral):
                prop_name = str(resource_expr.args[1].value)
                if prop_name in _CHOICE_DATE_PROPERTIES:
                    res = resource_expr.args[0]
                    return SQLFunctionCall(
                        name="COALESCE",
                        args=[
                            SQLFunctionCall(name="fhirpath_date", args=[res, SQLLiteral(f"{prop_name}DateTime")]),
                            SQLFunctionCall(name="intervalStart", args=[
                                SQLFunctionCall(name="fhirpath_text", args=[res, SQLLiteral(f"{prop_name}Period")])
                            ]),
                        ],
                    )

        if isinstance(resource_expr, (SQLFunctionCall, SQLBinaryOp, SQLSubquery, SQLCase)):
            return resource_expr
        if isinstance(resource_expr, SQLQualifiedIdentifier) and len(resource_expr.parts) >= 2:
            second_part = resource_expr.parts[-1]
            if second_part not in ("patient_id", "resource"):
                return resource_expr

        date_expr: SQLExpression
        if cte_name and context.column_registry:
            col_name = context.column_registry.lookup(cte_name, property_name)
            if not col_name and context.column_registry.has_column(cte_name, "effective_date"):
                col_name = "effective_date"
            if col_name:
                date_expr = SQLQualifiedIdentifier(parts=["r", col_name])
            else:
                date_expr = self._build_date_coalesce_expr(resource_expr, property_name)
        else:
            date_expr = self._build_date_coalesce_expr(resource_expr, property_name)

        from_base = resource_expr.expr if isinstance(resource_expr, SQLAlias) else resource_expr
        inner_select = SQLSelect(
            columns=[
                SQLQualifiedIdentifier(parts=["r", "resource"]),
                (date_expr, "effective_date"),
            ],
            from_clause=SQLAlias(expr=from_base, alias="r"),
            order_by=[(SQLIdentifier(name="effective_date"), "ASC")],
            limit=1,
        )

        outer_select = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["sub", "resource"])],
            from_clause=SQLAlias(expr=SQLSubquery(query=inner_select), alias="sub"),
        )

        return SQLSubquery(query=outer_select)

    @staticmethod
    def _sql_concat(*parts: SQLExpression) -> SQLExpression:
        """Chain SQL expressions with || operator for string concatenation."""
        result = parts[0]
        for p in parts[1:]:
            result = SQLBinaryOp(operator="||", left=result, right=p)
        return result

    def _build_has_principal_diagnosis_of_ast(
        self,
        resource_expr: SQLExpression,
        args: List[SQLExpression],
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Build AST for hasPrincipalDiagnosisOf(encounter, valueSet).

        Uses the ``claim_principal_diagnosis`` UDF to extract the principal
        diagnosis entry from a Claim resource (handling the array-level
        item→diagnosis sequence matching that FHIRPath cannot express in a
        single scoped ``.where()``).  The returned diagnosis JSON is then
        checked against the valueset via ``in_valueset`` (direct code) or
        via a Condition reference sub-query.
        """
        if not args:
            return SQLLiteral(value=False)

        valueset_arg = args[0]
        vs_url = ""
        if isinstance(valueset_arg, SQLLiteral):
            vs_url = str(valueset_arg.value)
        elif isinstance(valueset_arg, SQLIdentifier):
            resolved = context.valuesets.get(valueset_arg.name)
            if resolved is None and hasattr(context, "includes"):
                for _lib in context.includes.values():
                    if hasattr(_lib, "valuesets") and valueset_arg.name in _lib.valuesets:
                        resolved = _lib.valuesets[valueset_arg.name]
                        break
            vs_url = resolved or ""
        else:
            raw = valueset_arg.to_sql()
            if raw.startswith("'") and raw.endswith("'"):
                vs_url = raw[1:-1].replace("''", "'")
            elif raw.startswith('"') and raw.endswith('"'):
                vs_url = raw[1:-1]

        # fhirpath_text(enc.resource, 'id')
        enc_id_expr = SQLFunctionCall(
            name="fhirpath_text",
            args=[resource_expr, SQLLiteral("id")],
        )

        # ── claim_principal_diagnosis(_c.resource, enc_id) ──────────────
        pdx_expr = SQLFunctionCall(
            name="claim_principal_diagnosis",
            args=[
                SQLQualifiedIdentifier(parts=["_c", "resource"]),
                enc_id_expr,
            ],
        )

        # ── Claim status & use ──────────────────────────────────────────
        claim_status_check = SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(
                operator="=",
                left=SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        SQLQualifiedIdentifier(parts=["_c", "resource"]),
                        SQLLiteral("status"),
                    ],
                ),
                right=SQLLiteral("active"),
            ),
            right=SQLBinaryOp(
                operator="=",
                left=SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        SQLQualifiedIdentifier(parts=["_c", "resource"]),
                        SQLLiteral("use"),
                    ],
                ),
                right=SQLLiteral("claim"),
            ),
        )

        # ── Patient match ───────────────────────────────────────────────
        patient_match = SQLBinaryOp(
            operator="=",
            left=SQLQualifiedIdentifier(parts=["_c", "patient_id"]),
            right=self._extract_patient_id(resource_expr),
        )

        # ── Principal diagnosis exists (UDF returns non-null) ───────────
        pdx_not_null = SQLUnaryOp(
            operator="IS NOT NULL",
            operand=pdx_expr,
            prefix=False,
        )

        # ── Direct code check ──────────────────────────────────────────
        # in_valueset(pdx, 'diagnosisCodeableConcept', vs)
        direct_code_check = SQLFunctionCall(
            name="in_valueset",
            args=[
                pdx_expr,
                SQLLiteral("diagnosisCodeableConcept"),
                SQLLiteral(vs_url),
            ],
        )

        # ── Condition reference check ──────────────────────────────────
        # fhirpath_text(pdx, 'diagnosisReference.reference') LIKE '%/' || cond.id
        cond_ref_match = SQLBinaryOp(
            operator="LIKE",
            left=SQLFunctionCall(
                name="fhirpath_text",
                args=[pdx_expr, SQLLiteral("diagnosisReference.reference")],
            ),
            right=self._sql_concat(
                SQLLiteral("%/"),
                SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        SQLQualifiedIdentifier(parts=["_cond", "resource"]),
                        SQLLiteral("id"),
                    ],
                ),
            ),
        )

        cond_ref_check = SQLExists(
            subquery=SQLSubquery(
                query=SQLSelect(
                    columns=[SQLLiteral("1")],
                    from_clause=SQLAlias(
                        expr=SQLRaw(
                            "(SELECT patient_ref AS patient_id, resource"
                            " FROM resources WHERE resourceType = 'Condition')"
                        ),
                        alias="_cond",
                    ),
                    where=SQLBinaryOp(
                        operator="AND",
                        left=SQLBinaryOp(
                            operator="AND",
                            left=SQLBinaryOp(
                                operator="=",
                                left=SQLQualifiedIdentifier(
                                    parts=["_cond", "patient_id"]
                                ),
                                right=self._extract_patient_id(resource_expr),
                            ),
                            right=SQLFunctionCall(
                                name="in_valueset",
                                args=[
                                    SQLQualifiedIdentifier(
                                        parts=["_cond", "resource"]
                                    ),
                                    SQLLiteral("code"),
                                    SQLLiteral(vs_url),
                                ],
                            ),
                        ),
                        right=cond_ref_match,
                    ),
                )
            )
        )

        # ── Combine: direct code OR condition reference ─────────────────
        diagnosis_check = SQLBinaryOp(
            operator="OR",
            left=direct_code_check,
            right=cond_ref_check,
        )

        # ── Full WHERE ──────────────────────────────────────────────────
        full_where = SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(
                operator="AND",
                left=SQLBinaryOp(
                    operator="AND",
                    left=patient_match,
                    right=claim_status_check,
                ),
                right=pdx_not_null,
            ),
            right=diagnosis_check,
        )

        return SQLExists(
            subquery=SQLSubquery(
                query=SQLSelect(
                    columns=[SQLLiteral("1")],
                    from_clause=SQLAlias(
                        expr=SQLRaw(
                            "(SELECT patient_ref AS patient_id, resource"
                            " FROM resources WHERE resourceType = 'Claim')"
                        ),
                        alias="_c",
                    ),
                    where=full_where,
                )
            )
        )

    def _extract_patient_id(self, resource_expr: SQLExpression) -> SQLExpression:
        """Extract patient_id from a resource expression (qualified identifier or alias)."""
        if isinstance(resource_expr, SQLQualifiedIdentifier):
            return SQLQualifiedIdentifier(parts=[resource_expr.parts[0], "patient_id"])
        return SQLQualifiedIdentifier(parts=["_enc", "patient_id"])

    def _build_has_principal_procedure_of_ast(
        self,
        resource_expr: SQLExpression,
        args: List[SQLExpression],
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """Build AST for hasPrincipalProcedureOf(encounter, valueSet).

        Parallel to ``_build_has_principal_diagnosis_of_ast`` but checks
        ``Claim.procedure`` via the ``claim_principal_procedure`` UDF.
        """
        if not args:
            return SQLLiteral(value=False)

        valueset_arg = args[0]
        vs_url = ""
        if isinstance(valueset_arg, SQLLiteral):
            vs_url = str(valueset_arg.value)
        elif isinstance(valueset_arg, SQLIdentifier):
            resolved = context.valuesets.get(valueset_arg.name)
            if resolved is None and hasattr(context, "includes"):
                for _lib in context.includes.values():
                    if hasattr(_lib, "valuesets") and valueset_arg.name in _lib.valuesets:
                        resolved = _lib.valuesets[valueset_arg.name]
                        break
            vs_url = resolved or ""
        else:
            raw = valueset_arg.to_sql()
            if raw.startswith("'") and raw.endswith("'"):
                vs_url = raw[1:-1].replace("''", "'")
            elif raw.startswith('"') and raw.endswith('"'):
                vs_url = raw[1:-1]

        enc_id_expr = SQLFunctionCall(
            name="fhirpath_text",
            args=[resource_expr, SQLLiteral("id")],
        )

        # claim_principal_procedure(_c.resource, enc_id)
        ppx_expr = SQLFunctionCall(
            name="claim_principal_procedure",
            args=[
                SQLQualifiedIdentifier(parts=["_c", "resource"]),
                enc_id_expr,
            ],
        )

        # Claim status & use
        claim_status_check = SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(
                operator="=",
                left=SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        SQLQualifiedIdentifier(parts=["_c", "resource"]),
                        SQLLiteral("status"),
                    ],
                ),
                right=SQLLiteral("active"),
            ),
            right=SQLBinaryOp(
                operator="=",
                left=SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        SQLQualifiedIdentifier(parts=["_c", "resource"]),
                        SQLLiteral("use"),
                    ],
                ),
                right=SQLLiteral("claim"),
            ),
        )

        patient_match = SQLBinaryOp(
            operator="=",
            left=SQLQualifiedIdentifier(parts=["_c", "patient_id"]),
            right=self._extract_patient_id(resource_expr),
        )

        ppx_not_null = SQLUnaryOp(
            operator="IS NOT NULL",
            operand=ppx_expr,
            prefix=False,
        )

        # Direct code: in_valueset(ppx, 'procedureCodeableConcept', vs)
        direct_code_check = SQLFunctionCall(
            name="in_valueset",
            args=[
                ppx_expr,
                SQLLiteral("procedureCodeableConcept"),
                SQLLiteral(vs_url),
            ],
        )

        # Condition^W Procedure reference check
        proc_ref_match = SQLBinaryOp(
            operator="LIKE",
            left=SQLFunctionCall(
                name="fhirpath_text",
                args=[ppx_expr, SQLLiteral("procedureReference.reference")],
            ),
            right=self._sql_concat(
                SQLLiteral("%/"),
                SQLFunctionCall(
                    name="fhirpath_text",
                    args=[
                        SQLQualifiedIdentifier(parts=["_pr", "resource"]),
                        SQLLiteral("id"),
                    ],
                ),
            ),
        )

        proc_ref_check = SQLExists(
            subquery=SQLSubquery(
                query=SQLSelect(
                    columns=[SQLLiteral("1")],
                    from_clause=SQLAlias(
                        expr=SQLRaw(
                            "(SELECT patient_ref AS patient_id, resource"
                            " FROM resources WHERE resourceType = 'Procedure')"
                        ),
                        alias="_pr",
                    ),
                    where=SQLBinaryOp(
                        operator="AND",
                        left=SQLBinaryOp(
                            operator="AND",
                            left=SQLBinaryOp(
                                operator="=",
                                left=SQLQualifiedIdentifier(
                                    parts=["_pr", "patient_id"]
                                ),
                                right=self._extract_patient_id(resource_expr),
                            ),
                            right=SQLFunctionCall(
                                name="in_valueset",
                                args=[
                                    SQLQualifiedIdentifier(
                                        parts=["_pr", "resource"]
                                    ),
                                    SQLLiteral("code"),
                                    SQLLiteral(vs_url),
                                ],
                            ),
                        ),
                        right=proc_ref_match,
                    ),
                )
            )
        )

        diagnosis_check = SQLBinaryOp(
            operator="OR",
            left=direct_code_check,
            right=proc_ref_check,
        )

        full_where = SQLBinaryOp(
            operator="AND",
            left=SQLBinaryOp(
                operator="AND",
                left=SQLBinaryOp(
                    operator="AND",
                    left=patient_match,
                    right=claim_status_check,
                ),
                right=ppx_not_null,
            ),
            right=diagnosis_check,
        )

        return SQLExists(
            subquery=SQLSubquery(
                query=SQLSelect(
                    columns=[SQLLiteral("1")],
                    from_clause=SQLAlias(
                        expr=SQLRaw(
                            "(SELECT patient_ref AS patient_id, resource"
                            " FROM resources WHERE resourceType = 'Claim')"
                        ),
                        alias="_c",
                    ),
                    where=full_where,
                )
            )
        )

    def _build_date_coalesce_expr(
        self,
        resource_expr: SQLExpression,
        property_name: str,
    ) -> SQLExpression:
        """
        Build a COALESCE expression for date properties.

        For effectiveDateTime: COALESCE(fhirpath_date(resource, 'effectiveDateTime'), fhirpath_date(resource, 'effectivePeriod.start'))
        For other properties: fhirpath_date(resource, property_name)

        Args:
            resource_expr: The resource expression
            property_name: The primary date property name

        Returns:
            AST for the date COALESCE expression
        """
        # Ensure we reference the resource column within the table alias
        # In the subquery context, resource_expr is the table, and we use r.resource
        res = SQLQualifiedIdentifier(parts=["r", "resource"])

        if property_name == "effectiveDateTime":
            # COALESCE of effectiveDateTime and effectivePeriod.start
            return SQLFunctionCall(
                name="COALESCE",
                args=[
                    SQLFunctionCall(
                        name="fhirpath_date",
                        args=[res, SQLLiteral(value="effectiveDateTime")],
                    ),
                    SQLFunctionCall(
                        name="fhirpath_date",
                        args=[res, SQLLiteral(value="effectivePeriod.start")],
                    ),
                ],
            )
        else:
            # Single property
            return SQLFunctionCall(
                name="fhirpath_date",
                args=[res, SQLLiteral(value=property_name)],
            )

    def _validate_template_substitution_safety(
        self,
        template: str,
        resource_sql: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that template substitution is safe before applying regex optimization.

        The regex patterns in _optimize_template_with_precomputed_columns operate on
        SQL strings generated by this translator. This validation catches edge cases
        that could produce malformed SQL.

        Args:
            template: The SQL template string (e.g., "SELECT ... FROM {resource}").
            resource_sql: The serialized resource SQL expression.

        Returns:
            Tuple of (is_safe: bool, error_message: str or None).
        """
        # Check for SQL comment injection
        if '--' in resource_sql:
            return False, "Resource SQL contains comment characters (--)"

        # Check for triple quotes that could break string literals
        if "'''" in template or '"""' in template:
            return False, "Template contains triple quotes which may break SQL strings"

        # Check for semicolons that could indicate statement injection
        if ';' in resource_sql:
            return False, "Resource SQL contains semicolon"

        return True, None

    def _inline_function_body(
        self,
        func_def: FunctionDefinition,
        resource_expr: SQLExpression,
        args: List[SQLExpression],
        context: SQLTranslationContext,
    ) -> SQLExpression:
        """
        Inline a function body with parameter substitution.

        Two paths:
        1. CQL-defined functions (func_def.body is not None): mandatory AST inlining
           via FunctionInliner — no fallback, no try/except.
        2. Hardcoded body_sql functions: string template substitution.
           These don't contain Retrieve nodes so DeferredTemplateSubstitution is safe.

        Args:
            func_def: The function definition.
            resource_expr: The SQL expression for the receiver resource.
            args: Additional arguments.
            context: The translation context.

        Returns:
            The inlined SQL expression.
        """
        library_name = func_def.library

        # CQL-defined functions (have CQL AST body): AST path is mandatory, no fallback
        if func_def.body is not None:
            return self.inliner.inline_function(
                func_def.name,
                [resource_expr] + args,
                context,
                library_name=library_name,
            )

        # Hardcoded body_sql functions (no CQL AST): string template path
        if func_def.body_sql:
            return self._substitute_template(
                func_def.body_sql,
                resource_expr,
                args,
                func_def,
            )

        raise TranslationError(
            f"Function {func_def.qualified_name} has neither body nor body_sql"
        )

    def _optimize_template_with_precomputed_columns(
        self,
        template: str,
        resource_expr: SQLExpression,
        func_def: FunctionDefinition,
        context: SQLTranslationContext,
    ) -> str:
        """
        Optimize a template by replacing FHIRPath calls with precomputed column references.

        When the resource comes from a CTE that has precomputed columns, we can replace
        fhirpath_text(r, 'property') with r.column_name for better performance.

        This method uses AST-based CTE detection and column lookup, but still operates
        on string templates (body_sql). The full AST-based refactor (parsing templates to
        AST, walking nodes, replacing SQLFunctionCall nodes) is deferred to Task C4, which
        will eliminate body_sql templates entirely.

        Args:
            template: The SQL template (may already have {resource} substituted).
            resource_expr: The resource expression (to detect CTE source).
            func_def: The function definition.
            context: The translation context.

        Returns:
            Optimized template with FHIRPath calls replaced where possible.
        """
        # Extract CTE name using AST metadata (not string inspection)
        cte_name = self._extract_cte_name(resource_expr)

        # If we found a CTE name, try to optimize FHIRPath calls
        if cte_name and context and context.column_registry:
            # Get available columns for this CTE
            available_columns = context.column_registry.get_columns(cte_name)

            if available_columns:
                # Build optimization map: fhirpath -> column_name
                # Use deterministic string replacement instead of regex
                for col_name, col_info in available_columns.items():
                    fhirpath = col_info.fhirpath
                    for func_name in ('fhirpath_text', 'fhirpath_date', 'fhirpath_bool'):
                        placeholder = f"{func_name}(r, '{fhirpath}')"
                        replacement = f"r.{col_name}"
                        template = template.replace(placeholder, replacement)

        return template

    def _substitute_template(
        self,
        template: str,
        resource_expr: SQLExpression,
        args: List[SQLExpression],
        func_def: FunctionDefinition,
    ) -> SQLExpression:
        """
        Substitute parameters into a SQL template.

        Args:
            template: The SQL template string.
            resource_expr: The resource expression (first parameter).
            args: Additional argument expressions.
            func_def: The function definition for parameter names.

        Returns:
            The SQL expression with substitutions applied.
        """
        from .types import SQLUnion
        from .placeholder import contains_placeholder

        # Handle SQLUnion specially - apply template to each operand and COALESCE results
        # This prevents invalid SQL like:
        # CASE WHEN fhirpath_text((SELECT ... UNION ALL ...), 'status') = 'completed'
        # THEN (SELECT ... UNION ALL ...) ELSE NULL END
        if isinstance(resource_expr, SQLUnion):
            coalesce_args = []
            for operand in resource_expr.operands:
                # Recursively call _substitute_template for each operand
                result = self._substitute_template(template, operand, args, func_def)
                coalesce_args.append(result)
            return SQLFunctionCall(name="COALESCE", args=coalesce_args)

        # Check if any expression contains a placeholder
        # If so, defer the template substitution until to_sql() is called (Phase 3)
        has_placeholder = contains_placeholder(resource_expr)
        if not has_placeholder:
            for arg in args:
                if contains_placeholder(arg):
                    has_placeholder = True
                    break

        if has_placeholder:
            # Return a deferred substitution that will resolve when to_sql() is called
            return DeferredTemplateSubstitution(
                template=template,
                resource_expr=resource_expr,
                args=args,
                func_def=func_def,
                substitutor=self,
            )

        # No placeholders - defer substitution to the rendering boundary (to_sql).
        # This eliminates mid-pipeline .to_sql() calls during AST construction.
        return DeferredTemplateSubstitution(
            template=template,
            resource_expr=resource_expr,
            args=args,
            func_def=func_def,
            substitutor=self,
        )

    def _wrap_list_filter_for_mixed_input(self, template: str, resource_sql: str, resource_expr: SQLExpression = None) -> SQLExpression:
        """
        Wrap a list_filter template to handle both scalar and list inputs.

        DuckDB's list_filter requires a LIST argument, but the input might be:
        - A list (from jsonConcat, list_filter, etc.) - use list_filter directly
        - A scalar (from a subquery returning single row) - use scalar pattern

        IMPORTANT: We CANNOT use CASE WHEN with list_filter in both branches because
        DuckDB type-checks both branches at parse time. When the input is a scalar
        subquery, list_filter fails even in the branch that won't execute.

        Solution: Detect at SQL generation time whether the input is a known list or
        scalar, and use completely different code paths:

        - For lists: list_filter({resource}, r -> ...)
        - For scalars: CASE WHEN {predicate} THEN [{resource}] ELSE [] END

        Args:
            template: The list_filter template.
            resource_sql: The resource SQL expression.
            resource_expr: The resource AST node (for list detection via AST introspection).

        Returns:
            SQLExpression that works for the detected input type.
        """
        # AST introspection replaces string-based detection
        from ..translator.ast_utils import ast_is_list_operation
        is_known_list = ast_is_list_operation(resource_expr) if resource_expr is not None else False

        # Extract the predicate from list_filter template using string parsing
        # Template format: list_filter({resource}, <lambda_var> -> <predicate>)
        template_stripped = template.strip()
        prefix = 'list_filter({resource},'
        lambda_var = None
        predicate = None
        scalar_predicate = "true"

        if template_stripped.startswith(prefix) and template_stripped.endswith(')'):
            inner = template_stripped[len(prefix):-1].strip()
            arrow_idx = inner.find('->')
            if arrow_idx >= 0:
                lambda_var = inner[:arrow_idx].strip()
                predicate = inner[arrow_idx + 2:].strip()
                scalar_predicate = self._replace_lambda_var(
                    predicate, lambda_var, resource_sql
                )

        if is_known_list:
            # Resource is definitely a list - build list_filter AST
            if lambda_var and predicate:
                predicate_ast = self._parse_predicate_to_ast(predicate, lambda_var)
                return SQLFunctionCall(
                    name="list_filter",
                    args=[resource_expr, SQLLambda(param=lambda_var, body=predicate_ast)],
                )
            else:
                # Fallback: template parsing failed, use raw substitution
                return RawSQLExpression(sql=template.replace("{resource}", resource_sql))
        else:
            # Resource is scalar - build CASE WHEN AST (no list_filter)
            scalar_pred_ast = self._parse_predicate_to_ast(scalar_predicate)
            return SQLCase(
                when_clauses=[(scalar_pred_ast, resource_expr if resource_expr is not None else RawSQLExpression(sql=resource_sql))],
                else_clause=SQLNull(),
            )

    @staticmethod
    def _replace_lambda_var(text: str, var_name: str, replacement: str) -> str:
        """Replace lambda variable in text, respecting word boundaries."""
        result = []
        i = 0
        var_len = len(var_name)
        while i < len(text):
            if text[i:i + var_len] == var_name:
                before_ok = (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == '_'))
                after_idx = i + var_len
                after_ok = (after_idx >= len(text) or not (text[after_idx].isalnum() or text[after_idx] == '_'))
                if before_ok and after_ok:
                    result.append(replacement)
                    i += var_len
                    continue
            result.append(text[i])
            i += 1
        return ''.join(result)

    def _wrap_boolean_for_list(self, template: str, resource_sql: str, resource_expr: SQLExpression = None) -> SQLExpression:
        """
        Wrap a boolean template for list expressions.

        Transforms:
            fhirpath_text({resource}, 'status') = 'finished'
        Into:
            array_length(list_filter({resource}, r -> fhirpath_text(r, 'status') = 'finished')) > 0

        For scalar expressions (CASE, COALESCE), uses the condition directly instead of list_filter.

        Args:
            template: The boolean template (e.g., "fhirpath_text({resource}, 'status') = 'finished'")
            resource_sql: The resource SQL expression (string, for final substitution).
            resource_expr: The resource AST node (for type detection). If None, falls back to string checks.

        Returns:
            SQLExpression for list processing.
        """
        if resource_expr is None:
            raise ValueError("resource_expr is required for boolean list wrapping")
        from ..translator.ast_utils import ast_has_node_type
        from ..translator.types import SQLCase, SQLFunctionCall, SQLSubquery
        
        # Check if resource is a scalar expression using AST
        is_scalar = (
            ast_has_node_type(resource_expr, SQLCase) or
            ast_has_node_type(resource_expr, SQLSubquery) or
            (isinstance(resource_expr, SQLFunctionCall) and
             resource_expr.name and resource_expr.name.upper() in ('COALESCE', 'NULLIF'))
        )

        if is_scalar:
            # For scalar expressions, use raw SQL since condition comes from template string
            condition = template.replace("{resource}", resource_sql)
            return RawSQLExpression(sql=f"({condition})")
        else:
            # For list expressions, build AST: array_length(list_filter(resource_expr, r -> condition)) > 0
            condition_with_r = template.replace("{resource}", "r")
            condition_ast = self._parse_predicate_to_ast(condition_with_r, "r")
            filter_call = SQLFunctionCall(
                name="list_filter",
                args=[resource_expr, SQLLambda(param="r", body=condition_ast)],
            )
            length_call = SQLFunctionCall(name="array_length", args=[filter_call])
            return SQLBinaryOp(operator=">", left=length_call, right=SQLLiteral(value=0))

    @staticmethod
    def _parse_predicate_to_ast(predicate: str, lambda_var: str = None) -> SQLExpression:
        """
        Parse a simple SQL predicate string into an AST node.

        Handles common patterns from fluent function templates:
        - func(var, 'path') = 'value'
        - func(var, 'path') IN ('v1', 'v2')
        - func(var, 'path') IS NOT NULL

        Falls back to RawSQLExpression for complex patterns that can't be parsed.
        """
        from ..translator.fluent_functions import RawSQLExpression

        stripped = predicate.strip()

        # Try to find comparison operator
        for op in (' IN ', ' = ', ' != ', ' <> ', ' IS NOT ', ' IS ', ' >= ', ' <= ', ' > ', ' < '):
            idx = stripped.find(op)
            if idx < 0:
                continue

            left_str = stripped[:idx].strip()
            right_str = stripped[idx + len(op):].strip()

            # Parse left side: typically fhirpath_func(var, 'path')
            left_node = FluentFunctionTranslator._parse_func_call_to_ast(left_str, lambda_var)

            # Parse right side: 'literal', ('v1', 'v2'), or keyword
            right_node = FluentFunctionTranslator._parse_value_to_ast(right_str)

            return SQLBinaryOp(operator=op.strip(), left=left_node, right=right_node)

        # Could not parse - fall back to RawSQLExpression
        return RawSQLExpression(sql=predicate)

    @staticmethod
    def _parse_func_call_to_ast(expr_str: str, lambda_var: str = None) -> SQLExpression:
        """Parse a function call string like fhirpath_text(r, 'status') into AST."""
        from ..translator.fluent_functions import RawSQLExpression
        stripped = expr_str.strip()

        # Check for function call pattern: name(...)
        paren_idx = stripped.find('(')
        if paren_idx > 0 and stripped.endswith(')'):
            func_name = stripped[:paren_idx].strip()
            inner = stripped[paren_idx + 1:-1].strip()

            # Split arguments (simple split - handles most cases)
            args = []
            depth = 0
            current = []
            for ch in inner:
                if ch == '(' :
                    depth += 1
                elif ch == ')':
                    depth -= 1
                if ch == ',' and depth == 0:
                    args.append(''.join(current).strip())
                    current = []
                else:
                    current.append(ch)
            if current:
                args.append(''.join(current).strip())

            ast_args = []
            for arg in args:
                arg = arg.strip()
                if arg == lambda_var:
                    ast_args.append(SQLIdentifier(name=arg))
                elif (arg.startswith("'") and arg.endswith("'")) or (arg.startswith('"') and arg.endswith('"')):
                    ast_args.append(SQLLiteral(value=arg[1:-1]))
                else:
                    ast_args.append(FluentFunctionTranslator._parse_func_call_to_ast(arg, lambda_var))

            return SQLFunctionCall(name=func_name, args=ast_args)

        # Simple identifier or lambda var
        if stripped == lambda_var:
            return SQLIdentifier(name=stripped)
        if stripped.startswith("'") and stripped.endswith("'"):
            return SQLLiteral(value=stripped[1:-1])

        return RawSQLExpression(sql=stripped)

    @staticmethod
    def _parse_value_to_ast(value_str: str) -> SQLExpression:
        """Parse a value expression: literal, tuple list, or keyword."""
        stripped = value_str.strip()

        if stripped.upper() == 'NULL':
            return SQLNull()
        if stripped.upper() in ('TRUE', 'FALSE'):
            return SQLLiteral(value=(stripped.upper() == 'TRUE'))
        if stripped.startswith("'") and stripped.endswith("'"):
            return SQLLiteral(value=stripped[1:-1])
        if stripped.startswith("(") and stripped.endswith(")"):
            # Tuple list: ('v1', 'v2', ...)
            inner = stripped[1:-1]
            items = []
            for item in inner.split(","):
                item = item.strip()
                if item.startswith("'") and item.endswith("'"):
                    items.append(SQLLiteral(value=item[1:-1]))
                else:
                    items.append(SQLLiteral(value=item))
            return SQLList(items=items)
        # Try numeric
        try:
            if '.' in stripped:
                return SQLLiteral(value=float(stripped))
            return SQLLiteral(value=int(stripped))
        except ValueError:
            pass
        from ..translator.fluent_functions import RawSQLExpression
        return RawSQLExpression(sql=stripped)

    def _wrap_for_table_source(self, resource_sql: str, resource_expr: SQLExpression = None) -> SQLExpression:
        """
        Wrap a resource SQL expression for use as a table source in FROM clause.

        When the resource is already an identifier or subquery, use it directly;
        otherwise wrap it via UNNEST so DuckDB sees a TABLE expression.

        Returns an AST node (SQLExpression) instead of a rendered string.
        """

        if resource_expr is None:
            raise ValueError("resource_expr is required for table source wrapping")

        from ..translator.types import (
            SQLIdentifier, SQLQualifiedIdentifier, SQLSubquery,
            SQLCase, SQLArray, SQLFunctionCall, SQLSelect, SQLAlias,
            SQLUnaryOp, SQLNull,
        )

        if isinstance(resource_expr, (SQLIdentifier, SQLQualifiedIdentifier, SQLSubquery)):
            return resource_expr

        # Build AST: (SELECT t.resource FROM UNNEST(CASE WHEN x IS NULL THEN [] ELSE [x] END) AS t(resource))
        case_expr = SQLCase(
            when_clauses=[
                (SQLUnaryOp(operator="IS NULL", operand=resource_expr, prefix=False), SQLArray(elements=[])),
            ],
            else_clause=SQLArray(elements=[resource_expr]),
        )
        unnest_call = SQLFunctionCall(name="UNNEST", args=[case_expr])
        select_node = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["t", "resource"])],
            from_clause=SQLAlias(expr=unnest_call, alias="t(resource)"),
        )
        return SQLSubquery(query=select_node)

    def register_function(
        self,
        name: str,
        library: Optional[str] = None,
        parameters: Optional[List[Tuple[str, str]]] = None,
        return_type: str = "Any",
        body_sql: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> None:
        """
        Register a new fluent function definition.

        Args:
            name: Function name.
            library: Library name where function is defined.
            parameters: List of (name, type) tuples for parameters.
            return_type: Return type of the function.
            body_sql: Pre-translated SQL body template.
            resource_type: Resource type this function applies to.
        """
        func_params = []
        if parameters:
            for i, (pname, ptype) in enumerate(parameters):
                func_params.append(FunctionParameter(
                    name=pname,
                    param_type=ptype,
                    is_fluent_param=(i == 0),  # First param is fluent receiver
                ))

        func_def = FunctionDefinition(
            name=name,
            library=library,
            parameters=func_params,
            return_type=return_type,
            body_sql=body_sql,
            resource_type=resource_type,
        )

        self.registry.register(func_def)

    def is_fluent_function(
        self,
        function_name: str,
        resource_type: Optional[str] = None,
        context: Optional[SQLTranslationContext] = None,
    ) -> bool:
        """
        Check if a function name refers to a fluent function.

        Args:
            function_name: The function name to check.
            resource_type: Optional resource type for context.
            context: Optional translation context.

        Returns:
            True if the function is a known fluent function.
        """
        # Check if it's in the registry
        if resource_type:
            resource_qualified = f"{resource_type}_{function_name}"
            if resource_qualified in self.registry.functions:
                return True

        if function_name in self.registry.functions:
            return True

        # Check for CQL-defined fluent functions in context
        if context:
            # Check context._functions for CQL-defined fluent functions
            cql_func = context.get_function(function_name)
            if cql_func and getattr(cql_func, 'is_fluent', False):
                return True

            # Check included libraries for fluent functions
            cql_func = context.resolve_library_function(library_alias='', function_name=function_name)
            if cql_func is None:
                # Try all included libraries
                for lib_alias in context.includes.keys():
                    cql_func = context.resolve_library_function(lib_alias, function_name)
                    if cql_func and getattr(cql_func, 'is_fluent', False):
                        return True

            # Get resource_type from context if available (may not exist in all implementations)
            context_resource_type = getattr(context, 'resource_type', None)
            func = self._search_included_libraries(
                function_name,
                resource_type or context_resource_type,
                context,
            )
            return func is not None

        return False


class DeferredTemplateSubstitution(SQLExpression):
    """
    A deferred template substitution that waits until to_sql() is called.

    This implements a 3-phase rendering system for CQL fluent functions:

    - **Phase 1 (Translation)**: The template and AST nodes are captured but NOT
      rendered. If the resource expression contains placeholders (from retrieve
      optimization), a marker string is returned instead.
    - **Phase 2 (Placeholder resolution)**: The CTE manager resolves placeholder
      markers to concrete CTE references.
    - **Phase 3 (SQL generation)**: ``to_sql()`` performs the actual template
      substitution, replacing ``{resource}`` and named parameters with rendered SQL.

    The template string uses ``{resource}`` for the fluent target and
    ``{param_name}`` for additional parameters.
    """

    # Template patterns that indicate the resource needs .resource qualification
    _FHIRPATH_RESOURCE_PATTERNS = frozenset({
        "fhirpath_text({resource}",
        "fhirpath_bool({resource}",
        "fhirpath_date({resource}",
    })

    def __init__(
        self,
        template: str,
        resource_expr: SQLExpression,
        args: List[SQLExpression],
        func_def: "FunctionDefinition",
        substitutor: "FluentFunctionTranslator",
    ):
        """
        Initialize with template and expressions.

        Args:
            template: The SQL template string.
            resource_expr: The resource expression (first parameter).
            args: Additional argument expressions.
            func_def: The function definition for parameter names.
            substitutor: The FluentFunctionTranslator to use for substitution.
        """
        self._template = template
        self._resource_expr = resource_expr
        self._args = args
        self._func_def = func_def
        self._substitutor = substitutor
        self._precedence = 10  # PRIMARY precedence

    @property
    def precedence(self) -> int:
        """Get precedence level for this expression."""
        return self._precedence

    def to_sql(self, parent_precedence: int = 0) -> str:
        """Perform the template substitution and return SQL (Phase 3)."""
        from .types import SQLUnion

        # Branch 1: SQLUnion → COALESCE over each operand
        if isinstance(self._resource_expr, SQLUnion):
            return self._apply_to_union()

        # Branch 2: Unresolved placeholders → emit marker for Phase 2
        if self._has_pending_placeholders():
            return self._emit_placeholder_marker()

        # Branch 3: Normal case → render template with substitutions
        return self._render_template()
    def _apply_to_union(self) -> str:
        """Apply template to each SQLUnion operand and COALESCE the results."""
        coalesce_args = []
        for operand in self._resource_expr.operands:
            coalesce_args.append(DeferredTemplateSubstitution(
                self._template, operand, self._args, self._func_def, self._substitutor
            ))
        coalesce_node = SQLFunctionCall(name="COALESCE", args=coalesce_args)
        return coalesce_node.to_sql()

    def _has_pending_placeholders(self) -> bool:
        """Check if the resource expression still contains unresolved placeholders."""
        from .placeholder import contains_placeholder
        return contains_placeholder(self._resource_expr)

    def _emit_placeholder_marker(self) -> str:
        """Emit a marker string for Phase 2 placeholder resolution."""
        from .placeholder import find_all_placeholders
        placeholders = find_all_placeholders(self._resource_expr)
        if placeholders:
            resource_key = placeholders[0].key
            return f"__DEFERRED_TEMPLATE__({self._template!r}, {resource_key!r}, {self._args!r})__"
        return self._resource_expr.to_sql()

    def _render_template(self) -> str:
        """Render the template with the resolved resource and parameter values."""
        from ..translator.ast_utils import is_simple_identifier, ast_is_function_call

        resource_sql = self._resource_expr.to_sql()

        # Qualify with .resource when template uses fhirpath_* and source is a CTE/alias
        if is_simple_identifier(self._resource_expr) and not ast_is_function_call(self._resource_expr):
            if any(pat in self._template for pat in self._FHIRPATH_RESOURCE_PATTERNS):
                resource_sql = f"{resource_sql}.resource"

        param_map = self._build_param_map(resource_sql)
        result = self._apply_optimizations_and_substitute(resource_sql)

        # Replace named parameters
        for param_name, param_value in param_map.items():
            result = result.replace(f"{{{param_name}}}", param_value)
        return result

    def _build_param_map(self, resource_sql: str) -> dict:
        """Build the parameter name → SQL string substitution map."""
        param_map = {}
        for param in self._func_def.parameters:
            if param.is_fluent_param:
                param_map[param.name] = resource_sql
                break
        if not param_map and self._func_def.parameters:
            param_map[self._func_def.parameters[0].name] = resource_sql
        for i, arg in enumerate(self._args):
            if i + 1 < len(self._func_def.parameters):
                param_name = self._func_def.parameters[i + 1].name
                param_map[param_name] = arg.to_sql()
        return param_map

    def _apply_optimizations_and_substitute(self, resource_sql: str) -> str:
        """Apply template optimizations and perform {resource} substitution."""
        result = self._template

        # Attempt precomputed-column optimization
        is_safe, error = self._substitutor._validate_template_substitution_safety(result, resource_sql)
        if is_safe:
            result = self._substitutor._optimize_template_with_precomputed_columns(
                result, self._resource_expr, self._func_def, self._substitutor.context
            )
        elif hasattr(self._substitutor.context, 'warnings') and self._substitutor.context.warnings:
            self._substitutor.context.warnings.add_performance(
                message=f"Template optimization skipped: {error}"
            )

        # FROM {resource}: wrap as table source (with correlated-ref guard)
        if "FROM {resource}" in result:
            return self._substitute_from_resource(result, resource_sql)

        # list_filter({resource}...): handle mixed list/scalar input
        if "list_filter({resource}" in self._template:
            return self._substitutor._wrap_list_filter_for_mixed_input(
                self._template, resource_sql, self._resource_expr
            ).to_sql()

        # Boolean template on list expression: wrap for list semantics
        from ..translator.ast_utils import ast_is_list_operation
        if (ast_is_list_operation(self._resource_expr)
                and self._func_def.return_type == "Boolean"
                and "fhirpath_text({resource}" in self._template
                and ("=" in self._template or " IN " in self._template)):
            return self._substitutor._wrap_boolean_for_list(
                self._template, resource_sql, self._resource_expr
            ).to_sql()

        # Default: simple string substitution
        return result.replace("{resource}", resource_sql)

    def _substitute_from_resource(self, result: str, resource_sql: str) -> str:
        """Handle the ``FROM {resource}`` pattern with correlated-ref guard."""
        from .ast_utils import ast_has_correlated_ref
        cte_name = self._substitutor._extract_cte_name(self._resource_expr)
        if cte_name and ast_has_correlated_ref(self._resource_expr, cte_name):
            if hasattr(self._substitutor.context, 'warnings') and self._substitutor.context.warnings:
                self._substitutor.context.warnings.add_performance(
                    message=f"Fluent function {self._func_def.name}() skipped for correlated ref"
                )
            return resource_sql
        resource_for_from = self._substitutor._wrap_for_table_source(resource_sql, self._resource_expr)
        result = result.replace("FROM {resource}", f"FROM {resource_for_from.to_sql()}")
        return result.replace("{resource}", resource_sql)


class RawSQLExpression(SQLExpression):
    """
    A raw SQL expression wrapper for pre-built SQL strings.

    Used when we have a complete SQL string that shouldn't be
    modified or escaped further.
    """

    def __init__(self, sql: str):
        """
        Initialize with raw SQL string.

        Args:
            sql: The raw SQL string.
        """
        self._sql = sql
        self._precedence = 10  # PRIMARY precedence

    @property
    def precedence(self) -> int:
        """Get precedence level for this expression."""
        return self._precedence

    def to_sql(self, parent_precedence: int = 0) -> str:
        """Return the raw SQL string."""
        return self._sql


__all__ = [
    "FluentFunctionTranslator",
    "FluentFunctionRegistry",
    "FunctionDefinition",
    "FunctionParameter",
    "RawSQLExpression",
    "DeferredTemplateSubstitution",
]
