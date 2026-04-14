"""
Library resolver for cross-library function resolution in CQL translation.

This module provides the LibraryResolver class for resolving functions,
expressions, and valuesets across included CQL libraries.

Library dependencies are handled by inlining functions with library name prefixing.
For example:
    FHIRHelpers.ToInterval(period) -> FHIRHelpers_ToInterval(period)
    QICoreCommon.ToInterval(period) -> QICoreCommon_ToInterval(period)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any

from ..parser.ast_nodes import (
    Library,
    IncludeDefinition,
    FunctionDefinition,
    Definition,
    Expression,
    ValueSetDefinition,
    CodeSystemDefinition,
    ParameterDefinition,
)


@dataclass
class ResolvedFunction:
    """
    Represents a resolved function from a library.

    Attributes:
        name: The original function name.
        prefixed_name: The prefixed name for SQL (e.g., "FHIRHelpers_ToInterval").
        library_alias: The library alias where the function is defined.
        parameters: List of parameter definitions.
        return_type: Optional return type specifier.
        expression: The function body expression.
        dependencies: List of other function names this function depends on.
    """

    name: str
    prefixed_name: str
    library_alias: str
    parameters: List[Any] = field(default_factory=list)
    return_type: Optional[Any] = None
    expression: Optional[Expression] = None
    dependencies: List[str] = field(default_factory=list)


@dataclass
class ResolvedExpressionDef:
    """
    Represents a resolved expression definition from a library.

    Attributes:
        name: The original expression name.
        prefixed_name: The prefixed name for SQL.
        library_alias: The library alias where the expression is defined.
        expression: The expression body.
        context: Optional context name (e.g., 'Patient').
    """

    name: str
    prefixed_name: str
    library_alias: str
    expression: Optional[Expression] = None
    context: Optional[str] = None


@dataclass
class LibraryInfo:
    """
    Information about a registered library.

    Attributes:
        library: The parsed Library AST node.
        alias: The alias used to reference this library.
        functions: Dictionary mapping function names to FunctionDefinition.
        expression_defs: Dictionary mapping expression names to Definition.
        valuesets: Dictionary mapping valueset names to URLs.
        codesystems: Dictionary mapping codesystem names to URLs.
        parameters: Dictionary mapping parameter names to ParameterDefinition.
        dependencies: List of library aliases this library depends on.
    """

    library: Library
    alias: str
    functions: Dict[str, FunctionDefinition] = field(default_factory=dict)
    expression_defs: Dict[str, Definition] = field(default_factory=dict)
    valuesets: Dict[str, str] = field(default_factory=dict)
    codesystems: Dict[str, str] = field(default_factory=dict)
    parameters: Dict[str, ParameterDefinition] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)


class LibraryResolver:
    """
    Resolves functions, expressions, and valuesets across included CQL libraries.

    This class handles cross-library resolution for CQL translation, supporting
    the macro-style inlining pattern where all functions are prefixed with their
    library name.

    Library dependency order (CMS165 example):
        1. FHIRHelpers.cql       (base - no dependencies)
        2. QICoreCommon.cql      (depends on FHIRHelpers)
        3. Status.cql            (depends on FHIRHelpers)
        4. CumulativeMedicationDuration.cql (depends on FHIRHelpers, QICoreCommon)
        5. AdultOutpatientEncounters.cql (depends on FHIRHelpers, QICoreCommon, Status)
        6. Hospice.cql           (depends on FHIRHelpers, QICoreCommon, Status)
        7. PalliativeCare.cql    (depends on FHIRHelpers, QICoreCommon, Status)
        8. AdvancedIllnessandFrailty.cql (depends on FHIRHelpers, QICoreCommon, Status, CumulativeMedicationDuration)
        9. SupplementalDataElements.cql (depends on FHIRHelpers)
        10. CMS165FHIRControllingHighBP.cql (depends on all above)

    Function handling:
        FHIRHelpers.ToInterval(period) -> Inline with prefix FHIRHelpers_ToInterval
        MyLib.Double(5) -> Inline: parameter substitution, prefixed

    Example usage:
        resolver = LibraryResolver()
        resolver.register_library(fhir_helpers_lib, "FHIRHelpers")
        resolver.register_library(qicore_lib, "QICoreCommon")

        # Resolve a function
        func = resolver.resolve_function("ToInterval", "FHIRHelpers")
        prefixed_name = func.prefixed_name  # "FHIRHelpers_ToInterval"

        # Get function dependencies for inlining order
        deps = resolver.get_function_dependencies("SomeFunction")
    """

    def __init__(self):
        """Initialize the library resolver."""
        # Libraries indexed by alias
        self._libraries: Dict[str, LibraryInfo] = {}

        # Cache for resolved functions (key: "alias:funcname")
        self._function_cache: Dict[str, ResolvedFunction] = {}

        # Cache for resolved expression definitions
        self._expression_cache: Dict[str, ResolvedExpressionDef] = {}

        # Track registration order for dependency resolution
        self._registration_order: List[str] = []

        # Current/main library alias
        self._main_library_alias: Optional[str] = None

    def register_library(self, library: Library, alias: str) -> None:
        """
        Register an included library for resolution.

        This method extracts all functions, expression definitions, valuesets,
        codesystems, and parameters from the library and indexes them for
        cross-library resolution.

        Args:
            library: The parsed Library AST node.
            alias: The local alias for the library (e.g., "FHIRHelpers").
        """
        # Create library info
        lib_info = LibraryInfo(library=library, alias=alias)

        # Extract includes to determine dependencies
        for include in library.includes:
            dep_alias = include.alias or include.path.rsplit(".", 1)[-1]
            lib_info.dependencies.append(dep_alias)

        # Extract functions and expression definitions from statements
        for statement in library.statements:
            if isinstance(statement, FunctionDefinition):
                lib_info.functions[statement.name] = statement
            elif isinstance(statement, Definition):
                lib_info.expression_defs[statement.name] = statement

        # Extract valuesets
        for valueset in library.valuesets:
            lib_info.valuesets[valueset.name] = valueset.id

        # Extract codesystems
        for codesystem in library.codesystems:
            lib_info.codesystems[codesystem.name] = codesystem.id

        # Extract parameters
        for param in library.parameters:
            lib_info.parameters[param.name] = param

        # Store the library
        self._libraries[alias] = lib_info
        self._registration_order.append(alias)

        # Clear caches since we added new library
        self._function_cache.clear()
        self._expression_cache.clear()

    def set_main_library(self, library: Library, alias: str) -> None:
        """
        Set the main/current library being translated.

        The main library's functions don't need prefixing when called from
        within the same library.

        Args:
            library: The main Library AST node.
            alias: The alias for the main library.
        """
        self._main_library_alias = alias
        self.register_library(library, alias)

    def resolve_function(
        self,
        func_name: str,
        library_alias: Optional[str] = None,
    ) -> Optional[ResolvedFunction]:
        """
        Resolve a function reference to its definition.

        If library_alias is provided, looks up the function in that specific
        library. Otherwise, searches all registered libraries.

        Args:
            func_name: The function name to resolve.
            library_alias: Optional library alias to search in.

        Returns:
            ResolvedFunction if found, None otherwise.
        """
        # Check cache first
        cache_key = f"{library_alias or '*'}:{func_name}"
        if cache_key in self._function_cache:
            return self._function_cache[cache_key]

        # If library alias specified, search only that library
        if library_alias:
            result = self._resolve_function_in_library(func_name, library_alias)
        else:
            # Search all libraries in registration order
            result = None
            for alias in self._registration_order:
                result = self._resolve_function_in_library(func_name, alias)
                if result:
                    break

        # Cache the result
        if result:
            self._function_cache[cache_key] = result

        return result

    def _resolve_function_in_library(
        self,
        func_name: str,
        library_alias: str,
    ) -> Optional[ResolvedFunction]:
        """Resolve a function within a specific library."""
        lib_info = self._libraries.get(library_alias)
        if not lib_info:
            return None

        func_def = lib_info.functions.get(func_name)
        if not func_def:
            return None

        # Create prefixed name
        prefixed_name = f"{library_alias}_{func_name}"

        # Analyze dependencies (functions called within this function)
        dependencies = self._extract_function_dependencies(func_def.expression)

        return ResolvedFunction(
            name=func_name,
            prefixed_name=prefixed_name,
            library_alias=library_alias,
            parameters=func_def.parameters,
            return_type=func_def.return_type,
            expression=func_def.expression,
            dependencies=dependencies,
        )

    def resolve_expression_def(
        self,
        name: str,
        library_alias: Optional[str] = None,
    ) -> Optional[ResolvedExpressionDef]:
        """
        Resolve an expression definition reference.

        Expression definitions are named expressions (define "Name": expression).

        Args:
            name: The expression definition name.
            library_alias: Optional library alias to search in.

        Returns:
            ResolvedExpressionDef if found, None otherwise.
        """
        # Check cache first
        cache_key = f"{library_alias or '*'}:{name}"
        if cache_key in self._expression_cache:
            return self._expression_cache[cache_key]

        # If library alias specified, search only that library
        if library_alias:
            result = self._resolve_expression_in_library(name, library_alias)
        else:
            # Search all libraries in registration order
            result = None
            for alias in self._registration_order:
                result = self._resolve_expression_in_library(name, alias)
                if result:
                    break

        # Cache the result
        if result:
            self._expression_cache[cache_key] = result

        return result

    def _resolve_expression_in_library(
        self,
        name: str,
        library_alias: str,
    ) -> Optional[ResolvedExpressionDef]:
        """Resolve an expression definition within a specific library."""
        lib_info = self._libraries.get(library_alias)
        if not lib_info:
            return None

        expr_def = lib_info.expression_defs.get(name)
        if not expr_def:
            return None

        # Create prefixed name
        prefixed_name = f"{library_alias}_{name}"

        return ResolvedExpressionDef(
            name=name,
            prefixed_name=prefixed_name,
            library_alias=library_alias,
            expression=expr_def.expression,
            context=expr_def.context,
        )

    def resolve_valueset(
        self,
        name: str,
        library_alias: Optional[str] = None,
    ) -> Optional[str]:
        """
        Resolve a valueset name to its URL.

        Args:
            name: The valueset name.
            library_alias: Optional library alias to search in.

        Returns:
            The valueset URL if found, None otherwise.
        """
        # If library alias specified, search only that library
        if library_alias:
            lib_info = self._libraries.get(library_alias)
            if lib_info:
                return lib_info.valuesets.get(name)
            return None

        # Search all libraries in registration order
        for alias in self._registration_order:
            lib_info = self._libraries.get(alias)
            if lib_info and name in lib_info.valuesets:
                return lib_info.valuesets[name]

        return None

    def resolve_codesystem(
        self,
        name: str,
        library_alias: Optional[str] = None,
    ) -> Optional[str]:
        """
        Resolve a codesystem name to its URL.

        Args:
            name: The codesystem name.
            library_alias: Optional library alias to search in.

        Returns:
            The codesystem URL if found, None otherwise.
        """
        if library_alias:
            lib_info = self._libraries.get(library_alias)
            if lib_info:
                return lib_info.codesystems.get(name)
            return None

        for alias in self._registration_order:
            lib_info = self._libraries.get(alias)
            if lib_info and name in lib_info.codesystems:
                return lib_info.codesystems[name]

        return None

    def get_function_dependencies(self, func_name: str, library_alias: Optional[str] = None) -> List[str]:
        """
        Get the list of function dependencies for inlining order.

        Returns all functions that need to be inlined before the specified
        function can be used, in topological order.

        Args:
            func_name: The function name.
            library_alias: Optional library alias.

        Returns:
            List of prefixed function names that this function depends on.
        """
        visited: Set[str] = set()
        result: List[str] = []

        def collect_deps(fn: str, alias: Optional[str]) -> None:
            # Resolve the function
            resolved = self.resolve_function(fn, alias)
            if not resolved:
                return

            # Create unique key
            key = resolved.prefixed_name
            if key in visited:
                return

            visited.add(key)

            # Recursively collect dependencies first
            for dep in resolved.dependencies:
                # Parse dependency - could be "Lib.Func" or just "Func"
                if "." in dep:
                    dep_alias, dep_name = dep.split(".", 1)
                    collect_deps(dep_name, dep_alias)
                else:
                    # Same library dependency
                    collect_deps(dep, alias)

            # Add this function to result
            result.append(key)

        collect_deps(func_name, library_alias)
        return result

    def get_all_functions(self, library_alias: Optional[str] = None) -> List[ResolvedFunction]:
        """
        Get all functions from registered libraries.

        Args:
            library_alias: Optional library alias to filter by.

        Returns:
            List of all resolved functions.
        """
        functions: List[ResolvedFunction] = []

        aliases = [library_alias] if library_alias else list(self._registration_order)

        for alias in aliases:
            lib_info = self._libraries.get(alias)
            if not lib_info:
                continue

            for func_name in lib_info.functions:
                resolved = self.resolve_function(func_name, alias)
                if resolved:
                    functions.append(resolved)

        return functions

    def get_inlining_order(self) -> List[str]:
        """
        Get the order in which library functions should be inlined.

        This returns function names in topological order based on library
        dependencies, ensuring that dependent functions are defined first.

        Returns:
            List of prefixed function names in inlining order.
        """
        # Build dependency graph between libraries
        visited_libs: Set[str] = set()
        order: List[str] = []

        def visit_library(alias: str) -> None:
            if alias in visited_libs:
                return
            visited_libs.add(alias)

            lib_info = self._libraries.get(alias)
            if not lib_info:
                return

            # Visit dependencies first
            for dep in lib_info.dependencies:
                visit_library(dep)

            # Add this library's functions in dependency order
            for func_name in lib_info.functions:
                deps = self.get_function_dependencies(func_name, alias)
                for dep in deps:
                    if dep not in order:
                        order.append(dep)

        # Visit all libraries
        for alias in self._registration_order:
            visit_library(alias)

        return order

    def get_prefixed_name(self, name: str, library_alias: str) -> str:
        """
        Generate a prefixed name for a function or expression.

        Args:
            name: The original name.
            library_alias: The library alias.

        Returns:
            The prefixed name (e.g., "FHIRHelpers_ToInterval").
        """
        return f"{library_alias}_{name}"

    def is_registered(self, alias: str) -> bool:
        """Check if a library is registered."""
        return alias in self._libraries

    def get_library_names(self) -> List[str]:
        """Get all registered library aliases."""
        return list(self._registration_order)

    def _extract_function_dependencies(self, expression: Optional[Expression]) -> List[str]:
        """
        Extract function dependencies from an expression.

        This recursively walks the expression tree to find all function calls,
        returning them as "LibraryAlias.FunctionName" strings.

        Args:
            expression: The expression to analyze.

        Returns:
            List of function references (e.g., ["FHIRHelpers.ToDateTime", "Length"]).
        """
        if expression is None:
            return []

        dependencies: List[str] = []

        # Import here to avoid circular imports
        from ..parser.ast_nodes import (
            FunctionRef,
            QualifiedIdentifier,
            Property,
            BinaryExpression,
            UnaryExpression,
            ConditionalExpression,
            CaseExpression,
            CaseItem,
            Query,
            ListExpression,
            TupleExpression,
            InstanceExpression,
            MethodInvocation,
            Interval,
        )

        if isinstance(expression, FunctionRef):
            # Direct function call
            dependencies.append(expression.name)
            # Also check arguments
            for arg in expression.arguments:
                dependencies.extend(self._extract_function_dependencies(arg))

        elif isinstance(expression, MethodInvocation):
            # Method invocation - extract method name and source
            dependencies.append(expression.method)
            dependencies.extend(self._extract_function_dependencies(expression.source))
            for arg in expression.arguments:
                dependencies.extend(self._extract_function_dependencies(arg))

        elif isinstance(expression, QualifiedIdentifier):
            # Could be Library.Function reference
            if len(expression.parts) >= 2:
                # Treat as library function reference
                dependencies.append(".".join(expression.parts))

        elif isinstance(expression, Property):
            # Check source expression
            if expression.source:
                dependencies.extend(self._extract_function_dependencies(expression.source))

        elif isinstance(expression, BinaryExpression):
            dependencies.extend(self._extract_function_dependencies(expression.left))
            dependencies.extend(self._extract_function_dependencies(expression.right))

        elif isinstance(expression, UnaryExpression):
            dependencies.extend(self._extract_function_dependencies(expression.operand))

        elif isinstance(expression, ConditionalExpression):
            dependencies.extend(self._extract_function_dependencies(expression.condition))
            dependencies.extend(self._extract_function_dependencies(expression.then_expr))
            dependencies.extend(self._extract_function_dependencies(expression.else_expr))

        elif isinstance(expression, CaseExpression):
            for item in expression.case_items:
                if isinstance(item, CaseItem):
                    dependencies.extend(self._extract_function_dependencies(item.when))
                    dependencies.extend(self._extract_function_dependencies(item.then))
            if expression.else_expr:
                dependencies.extend(self._extract_function_dependencies(expression.else_expr))

        elif isinstance(expression, Query):
            # Handle query sources
            if isinstance(expression.source, list):
                for source in expression.source:
                    dependencies.extend(self._extract_function_dependencies(source.expression))
            else:
                dependencies.extend(self._extract_function_dependencies(expression.source.expression))

            # Handle where, return, sort clauses
            if expression.where:
                dependencies.extend(self._extract_function_dependencies(expression.where.expression))
            if expression.return_clause:
                dependencies.extend(self._extract_function_dependencies(expression.return_clause.expression))
            if expression.sort:
                for item in expression.sort.by:
                    if item.expression:
                        dependencies.extend(self._extract_function_dependencies(item.expression))

            # Handle let clauses
            for let in expression.let_clauses:
                dependencies.extend(self._extract_function_dependencies(let.expression))

            # Handle with clauses
            for with_clause in expression.with_clauses:
                dependencies.extend(self._extract_function_dependencies(with_clause.expression))
                dependencies.extend(self._extract_function_dependencies(with_clause.such_that))

        elif isinstance(expression, ListExpression):
            for elem in expression.elements:
                dependencies.extend(self._extract_function_dependencies(elem))

        elif isinstance(expression, TupleExpression):
            for elem in expression.elements:
                # TupleElement has a value field that's an expression
                if hasattr(elem, 'value') and elem.value:
                    dependencies.extend(self._extract_function_dependencies(elem.value))

        elif isinstance(expression, InstanceExpression):
            for elem in expression.elements:
                if hasattr(elem, 'value') and elem.value:
                    dependencies.extend(self._extract_function_dependencies(elem.value))

        elif isinstance(expression, Interval):
            if expression.low:
                dependencies.extend(self._extract_function_dependencies(expression.low))
            if expression.high:
                dependencies.extend(self._extract_function_dependencies(expression.high))

        return dependencies

    def __repr__(self) -> str:
        """String representation."""
        libs = ", ".join(self._registration_order)
        return f"LibraryResolver(libraries=[{libs}])"


__all__ = [
    "LibraryResolver",
    "ResolvedFunction",
    "ResolvedExpressionDef",
    "LibraryInfo",
]
