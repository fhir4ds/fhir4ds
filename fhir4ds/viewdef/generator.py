"""
SQL Generator for SQL-on-FHIR v2 ViewDefinitions.

Generates DuckDB SQL queries from ViewDefinition objects using the fhirpath() UDF family.

Type mapping (FHIRPath type -> DuckDB UDF):
    - string -> fhirpath_text()
    - integer -> fhirpath_number()
    - decimal -> fhirpath_number()
    - boolean -> fhirpath_bool()
    - date -> fhirpath_text()
    - dateTime -> fhirpath_text()
    - time -> fhirpath_text()
    - code -> fhirpath_text()
    - Coding -> fhirpath_json()
    - CodeableConcept -> fhirpath_json()
"""

import json
import re
import copy
import logging
from pathlib import Path
from typing import List, Optional, Set, Tuple

from .utils import pluralize_resource

_logger = logging.getLogger(__name__)

# Regex for safe SQL identifiers — alphanumeric and underscores only
_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
_SIMPLE_FHIRPATH_NAV_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*$"
)
_CONTEXT_SWITCHING_BUILTINS = {"context", "resource", "rootResource"}


def _quote_identifier(name: str) -> str:
    """Quote a SQL identifier, rejecting names that could enable injection."""
    if not isinstance(name, str) or not name or not _SAFE_IDENTIFIER_RE.match(name):
        raise ValidationError(
            f"Invalid SQL identifier: {name!r}. "
            "SQL identifiers must start with a letter or underscore and contain "
            "only alphanumeric characters and underscores."
        )
    return f'"{name}"'


def _quote_column_identifier(name: str) -> str:
    """Quote a ViewDefinition output column name using SQL-on-FHIR sql-name."""
    if not isinstance(name, str) or not SQL_NAME_RE.fullmatch(name):
        raise ValidationError(
            f"Invalid SQL identifier: {name!r}. "
            "ViewDefinition column names must satisfy SQL-on-FHIR sql-name "
            "^[A-Za-z][A-Za-z0-9_]*$."
        )
    return f'"{name}"'


def _quote_table_reference(name: str) -> str:
    """Quote a table reference, allowing schema-qualified identifiers."""
    if not isinstance(name, str) or not name:
        raise ValidationError("Invalid SQL table reference: table name must be a non-empty string.")

    parts = name.split(".")
    if any(part == "" for part in parts):
        raise ValidationError(f"Invalid SQL table reference: {name!r}.")
    return ".".join(_quote_identifier(part) for part in parts)


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"

from .types import (
    Column,
    ColumnType,
    ColumnTag,
    Constant,
    Select,
    ViewDefinition,
    SQL_NAME_RE,
    validate_optional_boolean,
    validate_optional_markdown,
    validate_optional_fhirpath_string,
    validate_optional_uri_string,
    validate_repeat_paths,
    validate_required_string,
    validate_root_metadata_fields,
    validate_sql_name,
    validate_supported_view_profiles,
    validate_where_conditions,
)
from .errors import ValidationError
from .metadata import FHIR_VERSION_CODES, KNOWN_FHIR_RESOURCE_TYPES

from .unnest import generate_foreach_unnest, generate_foreachornull_unnest, generate_repeat_unnest
from .constants import ConstantResolver, extract_constant_references, iter_constant_references
from fhir4ds.fhirpath.parser import parse as parse_fhirpath


def _load_fhir_array_elements() -> set:
    """Load FHIR array element names from metadata config."""
    config_path = Path(__file__).parent / "resources" / "fhir_array_elements.json"
    with open(config_path) as f:
        data = json.load(f)
    return set(data.get("elements", []))


class SQLGenerator:
    """Generate DuckDB SQL from ViewDefinition.

    This class converts SQL-on-FHIR v2 ViewDefinitions into executable
    DuckDB SQL queries using the fhirpath() UDF family.

    Supported features:
    - Basic column generation with type-specific UDFs
    - forEach (CROSS JOIN LATERAL) and forEachOrNull (LEFT JOIN LATERAL)
    - where clauses (fhirpath_bool filtering)
    - unionAll (UNION ALL across branches)
    - Constant references (%name) in FHIRPath expressions
    """

    # Map column types to their UDF functions per spec
    TYPE_TO_UDF = {
        "string": "fhirpath_text",
        "integer": "fhirpath_number",
        "integer64": "fhirpath_text",
        "decimal": "fhirpath_number",
        "boolean": "fhirpath_bool",
        "date": "fhirpath_text",
        "dateTime": "fhirpath_text",
        "time": "fhirpath_text",
        "code": "fhirpath_text",
        "Coding": "fhirpath_json",
        "CodeableConcept": "fhirpath_json",
        "Quantity": "fhirpath_json",
        # FHIR string-like types
        "id": "fhirpath_text",
        "uri": "fhirpath_text",
        "url": "fhirpath_text",
        "canonical": "fhirpath_text",
        "oid": "fhirpath_text",
        "uuid": "fhirpath_text",
        "markdown": "fhirpath_text",
        "base64Binary": "fhirpath_text",
        "instant": "fhirpath_text",
        # FHIR numeric types
        "positiveInt": "fhirpath_number",
        "unsignedInt": "fhirpath_number",
    }

    # Post-UDF SQL type casts for proper SQL typing
    # Note: date/dateTime/instant are kept as VARCHAR (from fhirpath_text)
    # to preserve timezone offsets and precision that TIMESTAMP/DATE would lose.
    _TYPE_CAST = {
        "integer": "INTEGER",
        "positiveInt": "INTEGER",
        "unsignedInt": "INTEGER",
        "integer64": "BIGINT",
    }

    _COLLECTION_ELEMENT_CAST = {
        "boolean": "BOOLEAN",
        "decimal": "DOUBLE",
        "integer": "INTEGER",
        "integer64": "BIGINT",
        "positiveInt": "INTEGER",
        "unsignedInt": "INTEGER",
    }

    _COMPLEX_TYPE_NAMES = {
        "Address", "Age", "Annotation", "Attachment", "BackboneElement",
        "CodeableConcept", "CodeableReference", "Coding", "ContactDetail",
        "ContactPoint", "Contributor", "Count", "DataRequirement", "Distance",
        "Dosage", "Duration", "Element", "Expression", "Extension",
        "HumanName", "Identifier", "Meta", "Money", "MoneyQuantity",
        "Narrative", "ParameterDefinition", "Period", "Quantity", "Range",
        "Ratio", "RatioRange", "Reference", "RelatedArtifact", "SampledData",
        "Signature", "Timing", "TriggerDefinition", "UsageContext",
    }

    _PRIMITIVE_TYPE_NAMES = {
        "base64Binary", "boolean", "canonical", "code", "date", "dateTime",
        "decimal", "id", "instant", "integer", "integer64", "markdown", "oid",
        "positiveInt", "string", "time", "unsignedInt", "uri", "url", "uuid",
    }

    _STRING_COMPATIBLE_TYPE_NAMES = {
        "base64Binary", "canonical", "code", "id", "markdown", "oid", "string",
        "uri", "url", "uuid",
    }

    _INTEGER_COMPATIBLE_TYPE_NAMES = {"integer", "integer64", "positiveInt", "unsignedInt"}
    _DECIMAL_COMPATIBLE_TYPE_NAMES = _INTEGER_COMPATIBLE_TYPE_NAMES | {"decimal"}

    def _is_element_id_type(self, type_str: str | None) -> bool:
        """Return True for FHIR element ID notation such as Observation.referenceRange."""
        return bool(type_str and "." in type_str)

    def _is_complex_declared_type(self, type_str: str | None) -> bool:
        """Return True when a column declaration expects a non-primitive JSON value."""
        return bool(
            type_str
            and (type_str in self._COMPLEX_TYPE_NAMES or self._is_element_id_type(type_str))
        )

    def _json_complex_condition(self, resource_var: str) -> str:
        """SQL predicate for values physically represented as JSON objects/arrays."""
        json_type_expr = f"json_type(TRY_CAST(CAST({resource_var} AS VARCHAR) AS JSON))"
        return f"COALESCE({json_type_expr} IN ('OBJECT', 'ARRAY'), false)"

    def __init__(self, dialect: str = "duckdb", *, strict_collection: bool = False,
                 source_table: str | None = None):
        """Initialize SQL generator.

        Args:
            dialect: SQL dialect (currently only 'duckdb' supported)
            strict_collection: If True, raise ValidationError when
                collection=false columns use likely multi-value paths. If
                False, log a warning and rely on runtime SQL guards (default).
            source_table: Override the source table name. When set, this table
                is used directly (with a ``resource_type = 'X'`` filter) instead
                of the default pluralized per-type table (e.g., ``patients``).
                Use ``"resources"`` to match the FHIRDataLoader default schema.
        """
        if dialect != "duckdb":
            raise ValueError(f"Unsupported dialect: {dialect}. Only 'duckdb' is supported.")
        self.dialect = dialect
        self._source_table = source_table
        self.strict_collection = strict_collection
        self.table_alias = "t"  # Base table alias
        self._alias_counter = 0
        self._constant_resolver = None

    def _get_type_name(self, column_type) -> str | None:
        """Return the normalized FHIR type name for a column type declaration."""
        if column_type is None:
            return None
        if isinstance(column_type, ColumnType):
            return column_type.value
        if isinstance(column_type, str):
            try:
                normalized = ColumnType.from_string(column_type)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            if isinstance(normalized, ColumnType):
                return normalized.value
            return normalized
        raise ValidationError("Column.type must be a URI string")

    def _get_udf_for_type(self, column_type) -> str:
        """Get the appropriate UDF function name for a column type.

        Args:
            column_type: ColumnType enum or string type hint

        Returns:
            UDF function name to use
        """
        type_str = self._get_type_name(column_type)
        if type_str is None:
            return "fhirpath_text"
        if type_str in self.TYPE_TO_UDF:
            return self.TYPE_TO_UDF[type_str]
        if type_str in self._COMPLEX_TYPE_NAMES or self._is_element_id_type(type_str):
            return "fhirpath_json"
        supported = sorted(set(self.TYPE_TO_UDF) | self._COMPLEX_TYPE_NAMES)
        raise ValidationError(
            f"Unsupported ViewDefinition column type {type_str!r}. "
            "Supported core FHIR types are: "
            f"{', '.join(supported)}."
        )

    def _get_sql_cast(self, column_type) -> str | None:
        """Return the SQL type to TRY_CAST the UDF result to, or None."""
        type_str = self._get_type_name(column_type)
        if type_str is None:
            return None
        return self._TYPE_CAST.get(type_str)

    def _get_collection_element_cast(self, column_type) -> str | None:
        """Return the SQL type used to cast primitive collection elements."""
        type_str = self._get_type_name(column_type)
        if type_str is None:
            return None
        return self._COLLECTION_ELEMENT_CAST.get(type_str)

    def _allowed_actual_type_names(self, declared_type: str) -> set[str]:
        """Return runtime FHIRPath type().name values compatible with a declaration."""
        if declared_type == "string":
            return set(self._STRING_COMPATIBLE_TYPE_NAMES)
        if declared_type == "integer":
            return set(self._INTEGER_COMPATIBLE_TYPE_NAMES)
        if declared_type == "decimal":
            return set(self._DECIMAL_COMPATIBLE_TYPE_NAMES)
        if declared_type in self._STRING_COMPATIBLE_TYPE_NAMES:
            # Python fallback cannot always distinguish FHIR string subtypes such
            # as id from plain string, so accept the physical string shape too.
            return {declared_type, "string"}
        return {declared_type}

    def _sql_string_list(self, values: set[str]) -> str:
        quoted_values = []
        for value in sorted(values):
            quoted_values.append(_sql_string_literal(value))
        return ", ".join(quoted_values)

    def _fhirpath_expression_sql(
        self,
        resolved_path: str,
        row_index_expr: str = "0",
    ) -> str:
        """Return the SQL expression used as the FHIRPath argument.

        SQL-on-FHIR exposes ``%rowIndex`` as a FHIRPath environment variable.
        The DuckDB UDF surface takes only a resource and expression string, so
        replace lexical ``%rowIndex`` references with the current row-index SQL
        value before handing the expression to the UDF.
        """
        parts: list[str] = []
        last = 0
        replaced = False

        for start, end, name in iter_constant_references(resolved_path):
            if name != "rowIndex":
                continue
            if start > last:
                parts.append(_sql_string_literal(resolved_path[last:start]))
            parts.append(f"CAST(({row_index_expr}) AS VARCHAR)")
            last = end
            replaced = True

        if not replaced:
            return _sql_string_literal(resolved_path)

        if last < len(resolved_path):
            parts.append(_sql_string_literal(resolved_path[last:]))
        if not parts:
            return f"CAST(({row_index_expr}) AS VARCHAR)"
        return "(" + " || ".join(parts) + ")"

    def _expression_uses_current_focus(self, resolved_path: str) -> bool:
        """Return True when a FHIRPath expression refers to the current focus."""
        try:
            ast = parse_fhirpath(resolved_path, strict_mode=True)
        except Exception:
            return True

        def _external_name(node: dict) -> str | None:
            for child in node.get("children", []):
                if isinstance(child, dict) and child.get("type") == "Identifier":
                    return child.get("text")
                if isinstance(child, dict):
                    nested = _external_name(child)
                    if nested is not None:
                        return nested
            return None

        def _walk(node) -> bool:
            if isinstance(node, list):
                return any(_walk(child) for child in node)
            if not isinstance(node, dict):
                return False

            node_type = node.get("type")
            children = node.get("children", [])
            if node_type == "ExternalConstant":
                return _external_name(node) == "context"
            if node_type == "ThisInvocation":
                return True
            if node_type == "InvocationTerm" and children:
                first = children[0]
                if isinstance(first, dict) and first.get("type") == "MemberInvocation":
                    return True
            return any(_walk(child) for child in children)

        return _walk(ast)

    def _path_supports_runtime_type_guard(self, resolved_path: str) -> bool:
        """Return True when ``type().name`` is reliable for this expression.

        Literal expressions, functions, operators, and unrolled element aliases
        can be valid SQL-on-FHIR column paths without retaining enough FHIR
        element metadata for a runtime type probe. Restrict type probes to
        simple root-resource navigation paths and let cardinality checks cover
        the broader expression surface.
        """
        return bool(_SIMPLE_FHIRPATH_NAV_RE.fullmatch(resolved_path))

    def _runtime_guard_condition(
        self,
        resource_var: str,
        resolved_path: str,
        column: Column,
        *,
        include_type_checks: bool = True,
        row_index_expr: str = "0",
    ) -> str | None:
        """Build SQL condition that detects runtime type/cardinality errors."""
        path_expr = self._fhirpath_expression_sql(resolved_path, row_index_expr)
        values_expr = f"fhirpath({resource_var}, {path_expr})"
        value_count = f"array_length({values_expr})"

        conditions: list[str] = []
        if not column.collection:
            conditions.append(f"{value_count} > 1")

        if include_type_checks and self._path_supports_runtime_type_guard(resolved_path):
            type_path = f"({resolved_path}).type().name"
            type_path_expr = self._fhirpath_expression_sql(type_path, row_index_expr)
            type_names = f"fhirpath({resource_var}, {type_path_expr})"
            declared_type = self._get_type_name(column.type)
            if self._is_element_id_type(declared_type):
                # Element-ID declarations identify a specific FHIR element
                # shape (e.g. Observation.referenceRange). Runtime
                # type().name values are datatype-oriented and can differ
                # between native and fallback paths, so cardinality remains the
                # portable execution guard.
                pass
            elif declared_type is None:
                allowed = self._sql_string_list(self._PRIMITIVE_TYPE_NAMES)
                conditions.append(
                    f"array_length(list_filter({type_names}, _t -> NOT (_t IN ({allowed})))) > 0"
                )
            else:
                allowed_names = self._allowed_actual_type_names(declared_type)
                allowed = self._sql_string_list(allowed_names)
                conditions.append(
                    f"array_length(list_filter({type_names}, _t -> NOT (_t IN ({allowed})))) > 0"
                )

        return " OR ".join(f"({condition})" for condition in conditions) if conditions else None

    def _runtime_error_message(self, column: Column) -> str:
        declared_type = self._get_type_name(column.type)
        if declared_type is None:
            type_fragment = "type unset; non-primitive outputs require column.type"
        else:
            type_fragment = f"declared type {declared_type}"
        cardinality = "collection=true" if column.collection else "collection=false"
        message = (
            f"ViewDefinition column {column.name!r} path {column.path!r} violates "
            f"{cardinality} / {type_fragment}"
        )
        return message.replace("'", "''")

    # Regex for validating FHIR resource type names (PascalCase alphanumeric)
    _VALID_RESOURCE_TYPE_RE = re.compile(r'^[A-Z][a-zA-Z0-9]*$')

    def _get_table_name(self, resource: str) -> str:
        """Convert resource type to table name.

        When ``source_table`` was provided at construction, returns that table
        and stores the resource type for a WHERE filter.  Otherwise returns the
        pluralized, lowercase form (e.g., "patients").

        Args:
            resource: FHIR resource type (e.g., "Patient", "Observation")

        Returns:
            Table name

        Raises:
            ValidationError: If resource type contains invalid characters
        """
        if not isinstance(resource, str) or not resource or not self._VALID_RESOURCE_TYPE_RE.match(resource):
            raise ValidationError(
                f"Invalid FHIR resource type: {resource!r}. "
                "Resource types must be PascalCase alphanumeric (e.g., 'Patient', 'Observation')."
            )
        if resource not in KNOWN_FHIR_RESOURCE_TYPES:
            raise ValidationError(
                f"Invalid FHIR resource type: {resource!r}. "
                "Resource must be a code from the FHIR ResourceType binding."
            )
        if self._source_table is not None:
            self._current_resource_type = resource
            return _quote_table_reference(self._source_table)
        return pluralize_resource(resource)

    def _resolve_path(self, path: str) -> str:
        """Resolve constant references in a FHIRPath expression."""
        if self._constant_resolver is not None:
            return self._constant_resolver.resolve_in_path(path)
        return path

    def _resolve_environment_path_context(
        self,
        resolved_path: str,
        current_resource_var: str,
        root_resource_var: Optional[str],
    ) -> Tuple[str, str]:
        """Resolve leading built-in variables to the SQL value they target.

        ViewDefinition iteration changes the current focus for ordinary
        FHIRPath paths, but FHIRPath's resource variables still refer to the
        containing/root resource for that focus.  The public DuckDB FHIRPath
        UDFs accept one JSON input value, so simple built-in-variable paths are
        routed to the appropriate SQL input before evaluation.
        """
        root_var = root_resource_var or current_resource_var
        variable_targets = {
            "%context": current_resource_var,
            "%resource": root_var,
            "%rootResource": root_var,
        }
        referenced_builtins = {
            name for _, _, name in iter_constant_references(resolved_path)
            if name in _CONTEXT_SWITCHING_BUILTINS
        }

        for variable, target_var in variable_targets.items():
            if resolved_path == variable:
                return "$this", target_var

            prefix = f"{variable}."
            if resolved_path.startswith(prefix):
                tail = resolved_path[len(prefix):]
                mixed_context_refs = {
                    name for _, _, name in iter_constant_references(tail)
                    if name in _CONTEXT_SWITCHING_BUILTINS
                }
                # Do not silently run mixed-context expressions against the wrong
                # JSON input. The public DuckDB UDF accepts a single context value.
                if mixed_context_refs and current_resource_var != root_var:
                    refs = ", ".join(f"%{name}" for name in sorted(mixed_context_refs))
                    raise ValidationError(
                        "FHIRPath expression mixes built-in ViewDefinition contexts "
                        f"inside an iterator ({variable} with {refs}); this cannot be "
                        "lowered to the single-input DuckDB FHIRPath UDF surface"
                    )
                return tail, target_var

        root_refs = referenced_builtins & {"resource", "rootResource"}
        if root_refs and current_resource_var != root_var:
            if self._expression_uses_current_focus(resolved_path):
                refs = ", ".join(f"%{name}" for name in sorted(root_refs))
                raise ValidationError(
                    "FHIRPath expression mixes built-in ViewDefinition contexts "
                    f"inside an iterator ({refs} with the current focus); this cannot be "
                    "lowered to the single-input DuckDB FHIRPath UDF surface"
                )
            return resolved_path, root_var

        return resolved_path, current_resource_var

    def _validate_column_shape(self, column: Column) -> None:
        """Validate a Column object before generating SQL from it."""
        try:
            validate_required_string(column.path, "Column.path")
            validate_optional_markdown(column.description, "Column.description")
            validate_optional_boolean(column.collection, "Column.collection")
            if column.type is not None and not isinstance(column.type, ColumnType):
                validate_optional_uri_string(column.type, "Column.type")
            if column.tag is None or not isinstance(column.tag, list):
                raise ValueError("Column.tag must be an array of tag objects")
            for tag in column.tag:
                if not isinstance(tag, ColumnTag):
                    raise ValueError("Column.tag items must be ColumnTag objects")
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def _validate_select_shape(self, selects: List[Select], path: str = "select") -> None:
        """Validate direct Select/Column dataclass input shape."""
        if not isinstance(selects, list):
            raise ValidationError(f"{path} must be an array of Select objects")

        for i, select in enumerate(selects):
            current_path = f"{path}[{i}]"
            if not isinstance(select, Select):
                raise ValidationError(f"{current_path} must be a Select object")
            if not isinstance(select.column, list):
                raise ValidationError(f"{current_path}.column must be an array of Column objects")
            if not isinstance(select.select, list):
                raise ValidationError(f"{current_path}.select must be an array of Select objects")
            if not isinstance(select.unionAll, list):
                raise ValidationError(f"{current_path}.unionAll must be an array of Select objects")

            try:
                validate_optional_fhirpath_string(
                    select.forEach,
                    f"{current_path}.forEach",
                )
                validate_optional_fhirpath_string(
                    select.forEachOrNull,
                    f"{current_path}.forEachOrNull",
                )
                if select.repeat is not None:
                    validate_repeat_paths(select.repeat, f"{current_path}.repeat")
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc

            for column in select.column:
                if not isinstance(column, Column):
                    raise ValidationError(f"{current_path}.column items must be Column objects")
                self._validate_column_shape(column)
            if select.select:
                self._validate_select_shape(select.select, f"{current_path}.select")
            if select.unionAll:
                self._validate_select_shape(select.unionAll, f"{current_path}.unionAll")

    def generate_column_expr(
        self,
        column: Column,
        resource_var: str = "resource",
        *,
        runtime_type_guard: bool = True,
        root_resource_var: Optional[str] = None,
        row_index_expr: str = "0",
    ) -> str:
        """Generate SQL expression for a single column.

        Args:
            column: Column definition with path, name, and optional type
            resource_var: Variable/alias holding the resource JSON

        Returns:
            SQL expression string (e.g., "fhirpath_text(resource, 'id') as patient_id")

        Example:
            >>> col = Column(path="id", name="patient_id")
            >>> gen.generate_column_expr(col, "t.resource")
            "fhirpath_text(t.resource, 'id') as patient_id"
        """
        self._validate_column_shape(column)

        # Resolve constants in path (%name_use -> 'official')
        resolved_path = self._resolve_path(column.path)

        # %rowIndex: 0-based row counter within the enclosing forEach context
        if resolved_path == "%rowIndex":
            quoted_name = _quote_column_identifier(column.name)
            return f"{row_index_expr} as {quoted_name}"

        resolved_path, eval_resource_var = self._resolve_environment_path_context(
            resolved_path,
            resource_var,
            root_resource_var,
        )

        # When path is $this, the resource_var itself is the value.
        # This happens inside forEach where the unnested element IS the value
        # (e.g., forEach: "name.given" produces primitive strings).
        if resolved_path == "$this":
            udf_func = self._get_udf_for_type(column.type)
            quoted_name = _quote_column_identifier(column.name)
            complex_value = self._json_complex_condition(eval_resource_var)
            declared_type = self._get_type_name(column.type)
            if self._is_complex_declared_type(declared_type):
                guard = f"({eval_resource_var} IS NOT NULL AND NOT ({complex_value}))"
            else:
                guard = complex_value

            expr = (
                f"COALESCE({udf_func}({eval_resource_var}, '$this'), "
                f"CAST({eval_resource_var} AS VARCHAR))"
            )
            if guard:
                message = self._runtime_error_message(column)
                expr = f"CASE WHEN {guard} THEN error('{message}') ELSE {expr} END"
            return f"{expr} as {quoted_name}"

        # For collection columns, use fhirpath() to return JSON array
        if column.collection:
            quoted_name = _quote_column_identifier(column.name)
            path_expr = self._fhirpath_expression_sql(resolved_path, row_index_expr)
            expr = f"fhirpath({eval_resource_var}, {path_expr})"
            sql_cast = self._get_collection_element_cast(column.type)
            if sql_cast:
                expr = f"list_transform({expr}, _v -> TRY_CAST(_v AS {sql_cast}))"
            guard = self._runtime_guard_condition(
                eval_resource_var,
                resolved_path,
                column,
                include_type_checks=runtime_type_guard,
                row_index_expr=row_index_expr,
            )
            if guard:
                message = self._runtime_error_message(column)
                expr = f"CASE WHEN {guard} THEN error('{message}') ELSE {expr} END"
            return f"{expr} as {quoted_name}"

        udf_func = self._get_udf_for_type(column.type)
        sql_cast = self._get_sql_cast(column.type)

        path_expr = self._fhirpath_expression_sql(resolved_path, row_index_expr)
        quoted_name = _quote_column_identifier(column.name)

        udf_call = f"{udf_func}({eval_resource_var}, {path_expr})"
        expr = udf_call
        if sql_cast:
            expr = f"TRY_CAST({udf_call} AS {sql_cast})"
        guard = self._runtime_guard_condition(
            eval_resource_var,
            resolved_path,
            column,
            include_type_checks=runtime_type_guard,
            row_index_expr=row_index_expr,
        )
        if guard:
            message = self._runtime_error_message(column)
            expr = f"CASE WHEN {guard} THEN error('{message}') ELSE {expr} END"
        return f"{expr} as {quoted_name}"

    def generate_columns(self, columns: List[Column], resource_var: str = "resource") -> str:
        """Generate comma-separated column expressions.

        Args:
            columns: List of column definitions
            resource_var: Variable/alias holding the resource JSON

        Returns:
            SQL column expressions, newline-separated with indentation

        Example:
            >>> cols = [Column(path="id", name="id"), Column(path="gender", name="gender")]
            >>> gen.generate_columns(cols, "t.resource")
            "fhirpath_text(t.resource, 'id') as id,\\n    fhirpath_text(t.resource, 'gender') as gender"
        """
        if not columns:
            return ""

        column_exprs = [
            self.generate_column_expr(col, resource_var)
            for col in columns
        ]
        return ",\n    ".join(column_exprs)

    def _collect_columns(self, selects: List[Select]) -> List[Column]:
        """Recursively collect all columns from select structures.

        Traverses nested select structures to find all column definitions.
        Sibling selects at the same level are all processed.

        Args:
            selects: List of Select structures to process

        Returns:
            List of all Column objects found
        """
        all_columns: List[Column] = []

        for select in selects:
            # Add direct columns from this select
            all_columns.extend(select.column)

            # Recursively collect from nested selects
            if select.select:
                all_columns.extend(self._collect_columns(select.select))

            # Recursively collect from unionAll branches
            if select.unionAll:
                all_columns.extend(self._collect_columns(select.unionAll))

        return all_columns

    # Built-in variables recognised by the SQL-on-FHIR v2 spec that do NOT
    # need to appear in the ViewDefinition's ``constants`` section.
    # Imported from the canonical definition in constants.py.
    from .constants import FHIRPATH_BUILTIN_VARIABLES as _BUILTIN_VARIABLES

    def _extract_constant_references(self, path: str) -> Set[str]:
        """Extract all constant references (%name) from a FHIRPath expression.

        Args:
            path: A FHIRPath expression that may contain constant references

        Returns:
            Set of constant names referenced in the path
        """
        return extract_constant_references(path)

    def _collect_all_paths(self, view_definition: ViewDefinition) -> List[str]:
        """Collect all FHIRPath expressions from a ViewDefinition.

        Gathers paths from:
        - Column definitions
        - forEach/forEachOrNull expressions
        - where clauses
        - Join conditions

        Args:
            view_definition: The ViewDefinition to extract paths from

        Returns:
            List of all FHIRPath expressions found
        """
        paths: List[str] = []

        # Collect from root-level where clauses
        for where in view_definition.where:
            if isinstance(where, dict) and isinstance(where.get("path"), str):
                paths.append(where["path"])

        # Recursively collect from selects
        def collect_from_selects(selects: List[Select]) -> None:
            for select in selects:
                # Column paths
                for column in select.column:
                    paths.append(column.path)

                # forEach and forEachOrNull
                if select.forEach:
                    paths.append(select.forEach)
                if select.forEachOrNull:
                    paths.append(select.forEachOrNull)

                # repeat paths
                if select.repeat:
                    paths.extend(select.repeat)

                # where clauses
                for where in select.where:
                    if isinstance(where, dict) and isinstance(where.get("path"), str):
                        paths.append(where["path"])

                # Nested selects
                if select.select:
                    collect_from_selects(select.select)

                # unionAll branches
                if select.unionAll:
                    collect_from_selects(select.unionAll)

        collect_from_selects(view_definition.select)

        # Collect from joins
        for join in view_definition.joins:
            for on_clause in join.on:
                if isinstance(on_clause, dict):
                    for key, value in on_clause.items():
                        if isinstance(value, str):
                            paths.append(value)

        return paths

    def _validate_constants(self, view_definition: ViewDefinition) -> None:
        """Validate that all constant references are defined.

        Checks all FHIRPath expressions in the ViewDefinition for constant
        references (%name) and verifies they are defined in vd.constants.

        Args:
            view_definition: The ViewDefinition to validate

        Raises:
            ValidationError: If any undefined constant is referenced
        """
        defined_constants: Set[str] = set()
        for const in view_definition.constants:
            if not isinstance(const, Constant):
                raise ValidationError("ViewDefinition.constant items must be Constant objects")
            try:
                validate_sql_name(const.name, "Constant.name")
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            if const.value is None:
                raise ValidationError(
                    f"Constant {const.name!r} has no value. A constant must include "
                    "a typed value[x] property."
                )
            defined_constants.add(const.name)

        # Collect all paths and extract constant references
        all_paths = self._collect_all_paths(view_definition)

        undefined_refs: Set[str] = set()
        for path in all_paths:
            refs = self._extract_constant_references(path)
            # Find any references not in defined constants or built-ins
            undefined = refs - defined_constants - self._BUILTIN_VARIABLES
            undefined_refs.update(undefined)

        if undefined_refs:
            # Raise ValidationError with details about undefined constants
            undefined_list = sorted(undefined_refs)
            raise ValidationError(
                f"Undefined constant(s) referenced: {', '.join(undefined_list)}",
                details={"undefined_constants": undefined_list}
            )

    def _validate_fhirpath_syntax(self, view_definition: ViewDefinition) -> None:
        """Validate that ViewDefinition FHIRPath expressions parse."""
        for path in self._collect_all_paths(view_definition):
            if not path:
                continue
            try:
                parse_fhirpath(path, strict_mode=True)
            except Exception as exc:
                raise ValidationError(
                    f"Invalid FHIRPath expression: {path!r}",
                    details={"path": path, "error": str(exc)},
                ) from exc

    def _validate_where_shapes(self, view_definition: ViewDefinition) -> None:
        """Validate and normalize root/select where predicates."""
        def _normalize(where, path: str) -> List[dict]:
            try:
                return validate_where_conditions(where, path)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc

        view_definition.where = _normalize(view_definition.where, "ViewDefinition.where")

        def _check_selects(selects: List[Select], path: str) -> None:
            for i, select in enumerate(selects):
                current_path = f"{path}[{i}]"
                select.where = _normalize(select.where, f"{current_path}.where")
                if select.select:
                    _check_selects(select.select, f"{current_path}.select")
                if select.unionAll:
                    _check_selects(select.unionAll, f"{current_path}.unionAll")

        _check_selects(view_definition.select, "ViewDefinition.select")

    # Known FHIR R4 array element names (max cardinality = *).
    # Loaded from resources/fhir_array_elements.json at module init.
    # Excludes ambiguous names that are predominantly scalar (code, type, location,
    # class, performerType, statusReason) to avoid false positives in heuristic checks.
    _FHIR_ARRAY_ELEMENTS = _load_fhir_array_elements()

    # Patterns that indicate singleton access (not returning multiple values)
    _SINGLETON_PATTERNS = [
        r'\.first\(\)',        # .first() - returns first element
        r'\[\d+\]',            # [0], [1] - numeric index access
        r'\[%[a-zA-Z_]',       # [%const] - constant-based index access
        r'\.single\(\)',       # .single() - returns single element
        r'\.last\(\)',         # .last() - returns last element
        r'\.where\(',          # .where() - filters to specific element
        r'\.ofType\(',         # .ofType() - filters by type
    ]

    # Patterns that indicate scalar result (even from array traversal)
    _SCALAR_RESULT_PATTERNS = [
        r'\.exists\(\)',       # .exists() - returns boolean
        r'\.empty\(\)',        # .empty() - returns boolean
        r'\.count\(\)',        # .count() - returns integer
        r'\.size\(\)',         # .size() - returns integer
        r'\.join\(',           # .join() - returns single string
        r'\.sum\(\)',          # .sum() - returns single number
        r'\.all\(',            # .all() - returns boolean
        r'\.any\(',            # .any() - returns boolean
        r'\.allTrue\(\)',      # .allTrue() - returns boolean
        r'\.allFalse\(\)',     # .allFalse() - returns boolean
        r'\.anyTrue\(\)',      # .anyTrue() - returns boolean
        r'\.anyFalse\(\)',     # .anyFalse() - returns boolean
    ]

    def _path_likely_returns_collection(self, path: str) -> bool:
        """Check if a FHIRPath expression likely returns multiple values.

        Uses heuristics to detect paths that traverse array elements
        without using singleton accessors like .first() or [n].

        Args:
            path: FHIRPath expression to check

        Returns:
            True if the path likely returns multiple values
        """
        # Check if path uses any singleton accessor pattern
        for pattern in self._SINGLETON_PATTERNS:
            if re.search(pattern, path):
                return False

        # Check if path ends with a scalar result function
        for pattern in self._SCALAR_RESULT_PATTERNS:
            if re.search(pattern, path):
                return False

        # Split path into segments
        segments = path.split('.')

        # Check if any segment matches a known array element
        for segment in segments:
            # Remove any function calls or qualifiers from the segment
            base_name = segment.split('(')[0].split('[')[0].strip()
            if base_name in self._FHIR_ARRAY_ELEMENTS:
                return True

        return False

    def _validate_collection_columns(self, view_definition: ViewDefinition) -> None:
        """Validate collection=false columns against multi-value paths.

        Per SQL-on-FHIR spec, collection=false columns cannot produce multiple
        values. This preflight uses heuristics to detect paths that traverse
        FHIR array elements without singleton accessors; runtime SQL guards
        enforce the rule for values that cannot be proven statically.

        In strict mode (strict_collection=True), raises ValidationError.
        In permissive mode (default), logs a warning and relies on runtime
        SQL guards.

        When columns are inside a forEach/forEachOrNull context, validation
        is skipped because paths are relative to unnested elements.

        Args:
            view_definition: The ViewDefinition to validate
        """
        def validate_select_columns(selects: List[Select], in_foreach: bool = False) -> None:
            for select in selects:
                current_in_foreach = in_foreach or bool(select.forEach) or bool(select.forEachOrNull) or bool(select.repeat)

                if not current_in_foreach:
                    for column in select.column:
                        if column.collection:
                            continue

                        if self._path_likely_returns_collection(column.path):
                            if self.strict_collection:
                                raise ValidationError(
                                    f"Column '{column.name}' has collection=false but path "
                                    f"'{column.path}' likely returns multiple values. "
                                    f"Either set collection=true or use a singleton accessor "
                                    f"(e.g., .first(), [0], .where())",
                                    details={
                                        "column_name": column.name,
                                        "path": column.path,
                                        "hint": "Set collection=true or use .first(), [n], or .where()"
                                    }
                                )
                            else:
                                _logger.warning(
                                    "Column '%s' has collection=false but path '%s' may "
                                    "return multiple values; only the first will be used. "
                                    "Set collection=true to return all values.",
                                    column.name, column.path,
                                )

                if select.select:
                    validate_select_columns(select.select, current_in_foreach)

                if select.unionAll:
                    validate_select_columns(select.unionAll, current_in_foreach)

        validate_select_columns(view_definition.select)

    def _validate_unique_column_names(self, view_definition: ViewDefinition) -> None:
        """Validate that column names are unique across the entire select tree.

        Per SQL-on-FHIR v2 spec, column names in a ViewDefinition's output
        must be unique across all selects — including siblings and parent-child
        relationships. Names within unionAll branches are expected to match
        (they contribute to the same UNION ALL output) and are not checked
        against siblings.

        Args:
            view_definition: The ViewDefinition to validate

        Raises:
            ValidationError: If duplicate column names are found
        """
        all_names: List[Tuple[str, str]] = []
        for i, sel in enumerate(view_definition.select):
            for j, (name, _, _) in enumerate(self._collect_select_output_schema(sel)):
                all_names.append((name, f"select[{i}].output[{j}]"))

        seen: dict[str, str] = {}
        duplicates: dict[str, List[str]] = {}
        for name, path in all_names:
            if name in seen:
                if name not in duplicates:
                    duplicates[name] = [seen[name]]
                duplicates[name].append(path)
            else:
                seen[name] = path

        if duplicates:
            dup_names = sorted(duplicates.keys())
            raise ValidationError(
                f"Duplicate column names across select tree: {dup_names}. "
                f"Column names must be unique per the SQL-on-FHIR v2 specification.",
                details={"duplicate_names": dup_names, "locations": duplicates}
            )

    def _validate_foreach_mutual_exclusion(self, selects: List[Select]) -> None:
        """Validate that no select uses both forEach and forEachOrNull.

        Per SQL-on-FHIR v2 spec, forEach, forEachOrNull, and repeat are
        mutually exclusive iteration mechanisms at the same select level.
        """
        def _check(sels: List[Select], path: str = "select") -> None:
            for i, sel in enumerate(sels):
                if sel.forEach and sel.forEachOrNull:
                    raise ValidationError(
                        f"{path}[{i}]: Both forEach and forEachOrNull specified "
                        "(they are mutually exclusive per the SQL-on-FHIR v2 specification)"
                    )
                if sel.repeat and sel.forEach:
                    raise ValidationError(
                        f"{path}[{i}]: Both repeat and forEach specified "
                        "(they are mutually exclusive per the SQL-on-FHIR v2 specification)"
                    )
                if sel.repeat and sel.forEachOrNull:
                    raise ValidationError(
                        f"{path}[{i}]: Both repeat and forEachOrNull specified "
                        "(they are mutually exclusive per the SQL-on-FHIR v2 specification)"
                    )
                if sel.select:
                    _check(sel.select, f"{path}[{i}].select")
                if sel.unionAll:
                    _check(sel.unionAll, f"{path}[{i}].unionAll")
        _check(selects)

    def _collect_branch_column_names(self, select: 'Select') -> List[str]:
        """Collect column names produced by a unionAll branch (non-recursive into unionAll).

        For branches that contain their own unionAll, take the columns from
        the first nested unionAll branch (they must all match per the spec).
        """
        return [name for name, _, _ in self._collect_branch_column_schema(select)]

    def _collect_select_non_union_schema(
        self,
        select: 'Select',
    ) -> List[Tuple[str, Optional[str], bool]]:
        """Collect columns produced outside a select's direct unionAll."""
        schema: List[Tuple[str, Optional[str], bool]] = []
        for col in select.column:
            schema.append((col.name, self._get_type_name(col.type), bool(col.collection)))
        for nested in select.select:
            schema.extend(self._collect_select_output_schema(nested))
        return schema

    def _collect_select_output_schema(
        self,
        select: 'Select',
    ) -> List[Tuple[str, Optional[str], bool]]:
        """Collect the effective output schema for a select rowset."""
        schema = self._collect_select_non_union_schema(select)
        if select.unionAll:
            schema.extend(self._collect_select_output_schema(select.unionAll[0]))
        return schema

    def _collect_branch_column_schema(
        self,
        select: 'Select',
    ) -> List[Tuple[str, Optional[str], bool]]:
        """Collect the branch output schema as name/type/collection triples."""
        return self._collect_select_output_schema(select)

    def _collect_non_union_column_names(self, selects: List['Select']) -> List[str]:
        """Collect names projected outside unionAll branch alternatives."""
        names: List[str] = []
        for select in selects:
            names.extend(name for name, _, _ in self._collect_select_non_union_schema(select))
        return names

    def _validate_union_branch_schema_names(
        self,
        branch_names: List[str],
        context_names: Set[str],
        path: str,
    ) -> None:
        """Validate a unionAll branch schema against its parent/sibling context."""
        seen: Set[str] = set()
        duplicate_branch_names: Set[str] = set()
        for name in branch_names:
            if name in seen:
                duplicate_branch_names.add(name)
            seen.add(name)

        context_collisions = set(branch_names) & context_names
        duplicates = sorted(duplicate_branch_names | context_collisions)
        if duplicates:
            raise ValidationError(
                f"{path}: Duplicate column names in unionAll output schema: "
                f"{duplicates}. Column names must be unique per the "
                f"SQL-on-FHIR v2 specification.",
                details={
                    "duplicate_names": duplicates,
                    "context_collisions": sorted(context_collisions),
                    "branch_duplicates": sorted(duplicate_branch_names),
                },
            )

    def _validate_union_all_columns(
        self,
        selects: List['Select'],
        path: str = "select",
        inherited_context: Optional[Set[str]] = None,
    ) -> None:
        """Validate that unionAll branches have identical column names in the same order.

        Per SQL-on-FHIR v2 spec, all branches of a unionAll must produce the
        same columns in the same order. The branch schema is also combined with
        sibling and parent columns that are projected into the same output row,
        so those names must not collide.
        """
        inherited_context = inherited_context or set()
        select_schemas = [self._collect_select_output_schema(sel) for sel in selects]
        select_name_sets = [
            {name for name, _, _ in schema}
            for schema in select_schemas
        ]

        for i, sel in enumerate(selects):
            sibling_context: Set[str] = set()
            for j, names in enumerate(select_name_sets):
                if j != i:
                    sibling_context.update(names)
            direct_context = {
                name for name, _, _ in self._collect_select_non_union_schema(sel)
            }
            branch_context = inherited_context | sibling_context | direct_context

            if sel.unionAll:
                reference_schema = self._collect_branch_column_schema(sel.unionAll[0])
                reference_names = [name for name, _, _ in reference_schema]
                for j, branch in enumerate(sel.unionAll):
                    branch_schema = self._collect_branch_column_schema(branch)
                    branch_names = [name for name, _, _ in branch_schema]
                    if j > 0 and branch_names != reference_names:
                        raise ValidationError(
                            f"{path}[{i}].unionAll: Branch {j} column names "
                            f"{branch_names} do not match branch 0 column names "
                            f"{reference_names}. All unionAll branches must produce "
                            f"identical columns in the same order."
                        )
                    if j > 0 and branch_schema != reference_schema:
                        raise ValidationError(
                            f"{path}[{i}].unionAll: Branch {j} column schema "
                            f"{branch_schema} does not match branch 0 column schema "
                            f"{reference_schema}. All unionAll branches must produce "
                            f"identical column names, FHIR types, and collection flags "
                            f"in the same order."
                        )
                    self._validate_union_branch_schema_names(
                        branch_names,
                        branch_context,
                        f"{path}[{i}].unionAll[{j}]",
                    )
                    self._validate_union_all_columns(
                        [branch],
                        f"{path}[{i}].unionAll[{j}]",
                        branch_context,
                    )
            if sel.select:
                child_context = inherited_context | sibling_context | {
                    col.name for col in sel.column
                }
                if sel.unionAll:
                    child_context.update(
                        name for name, _, _ in self._collect_branch_column_schema(sel.unionAll[0])
                    )
                self._validate_union_all_columns(
                    sel.select,
                    f"{path}[{i}].select",
                    child_context,
                )

    def _validate_where_paths(self, view_definition: 'ViewDefinition') -> None:
        """Validate that where clause paths can evaluate to boolean.

        Per SQL-on-FHIR v2 spec, where paths must resolve to boolean values.
        Compound property paths (e.g., name.family) without boolean operators
        are clearly non-boolean and should be rejected. Single-segment paths
        (e.g., active) may refer to boolean elements and are allowed through.
        """
        boolean_indicators = {'=', '!=', '<', '>', '<=', '>=', 'and', 'or', 'not',
                              'contains', 'in', 'exists', 'empty', 'is', 'as',
                              'matches', 'startsWith', 'endsWith', 'hasValue',
                              'true', 'false', '~', '!~'}

        def _is_clearly_non_boolean(path: str) -> bool:
            """Return True if the path clearly cannot resolve to boolean."""
            tokens = set(path.split())
            # Has boolean indicators or function calls → could be boolean
            if tokens & boolean_indicators or '(' in path:
                return False
            # Compound property path (contains dots) → likely non-boolean
            # e.g., "name.family" is a string path
            if '.' in path:
                return True
            # Single segment (e.g., "active") → might be a boolean element
            return False

        def _check_where(selects: List['Select'], path: str = "select") -> None:
            for i, sel in enumerate(selects):
                if sel.where:
                    for w in sel.where:
                        wp = w.get("path", "") if isinstance(w, dict) else ""
                        if wp and _is_clearly_non_boolean(wp):
                            raise ValidationError(
                                f"{path}[{i}].where: Path '{wp}' does not appear "
                                f"to resolve to a boolean value"
                            )
                if sel.select:
                    _check_where(sel.select, f"{path}[{i}].select")
                if sel.unionAll:
                    _check_where(sel.unionAll, f"{path}[{i}].unionAll")

        # Check root-level where
        if hasattr(view_definition, 'where') and view_definition.where:
            for w in view_definition.where:
                wp = w.get("path", "") if isinstance(w, dict) else ""
                if wp and _is_clearly_non_boolean(wp):
                    raise ValidationError(
                        f"Root where: Path '{wp}' does not appear "
                        f"to resolve to a boolean value"
                    )

        _check_where(view_definition.select)

    def _where_condition_sql(
        self,
        resource_var: str,
        path_expr: str,
    ) -> str:
        """Return SQL that only accepts a singleton FHIRPath Boolean true."""
        return f"fhirpath_json({resource_var}, {path_expr}) = '[true]'"

    def _next_alias(self, path: str) -> str:
        """Generate a unique SQL alias for a forEach/forEachOrNull unnested element."""
        base = path.replace("/", ".").split(".")[-1] if path else "elem"
        base = "".join(c if c.isalnum() or c == "_" else "_" for c in base)
        alias = f"{base}_elem_{self._alias_counter}"
        self._alias_counter += 1
        return alias

    def _process_selects(
        self,
        selects: List[Select],
        resource_var: str,
        null_preserve_var: Optional[str] = None,
        runtime_type_guard: bool = True,
        root_resource_var: Optional[str] = None,
        row_index_expr: str = "0",
    ) -> Tuple[List[str], List[str], List[str]]:
        """Recursively process a list of Select structures.

        Traverses nested selects, tracking the resource variable in scope for
        each forEach/forEachOrNull context and collecting WHERE conditions.
        unionAll branches are NOT processed here — they are handled in generate().

        Args:
            selects: List of Select structures to process
            resource_var: Current resource variable expression
            null_preserve_var: If set, all WHERE conditions are wrapped with
                ``({var} IS NULL OR ...)`` to preserve NULL rows from an
                enclosing forEachOrNull context.

        Returns:
            Tuple of (column_exprs, join_clauses, where_conditions)
        """
        column_exprs: List[str] = []
        join_clauses: List[str] = []
        where_conditions: List[str] = []
        root_resource_var = root_resource_var or resource_var

        for select in selects:
            current_var = resource_var
            in_foreach_or_null = False
            current_runtime_type_guard = runtime_type_guard
            current_row_index_expr = row_index_expr

            # Establish a repeat context (CROSS JOIN LATERAL with recursive UDF)
            if select.repeat:
                resolved_paths = []
                for p in select.repeat:
                    resolved_path = self._resolve_path(p)
                    resolved_paths.append(resolved_path)
                alias = self._next_alias("repeat")
                join_clauses.append(
                    generate_repeat_unnest(resolved_paths, current_var, alias)
                )
                current_var = alias
                current_runtime_type_guard = False
                current_row_index_expr = f"COALESCE({alias}__row_index, 0)"

            # Establish a new forEach context (CROSS JOIN LATERAL)
            if select.forEach:
                resolved_foreach = self._resolve_path(select.forEach)
                resolved_foreach, foreach_var = self._resolve_environment_path_context(
                    resolved_foreach,
                    current_var,
                    root_resource_var,
                )
                alias = self._next_alias(resolved_foreach)
                foreach_path_expr = self._fhirpath_expression_sql(
                    resolved_foreach,
                    current_row_index_expr,
                )
                join_clauses.append(
                    generate_foreach_unnest(
                        resolved_foreach,
                        foreach_var,
                        alias,
                        foreach_path_expr,
                    )
                )
                current_var = alias
                current_runtime_type_guard = False
                current_row_index_expr = f"COALESCE({alias}__row_index, 0)"
            elif select.forEachOrNull:
                resolved_foreach = self._resolve_path(select.forEachOrNull)
                resolved_foreach, foreach_var = self._resolve_environment_path_context(
                    resolved_foreach,
                    current_var,
                    root_resource_var,
                )
                alias = self._next_alias(resolved_foreach)
                foreach_path_expr = self._fhirpath_expression_sql(
                    resolved_foreach,
                    current_row_index_expr,
                )
                join_clauses.append(
                    generate_foreachornull_unnest(
                        resolved_foreach,
                        foreach_var,
                        alias,
                        foreach_path_expr,
                    )
                )
                current_var = alias
                in_foreach_or_null = True
                current_runtime_type_guard = False
                current_row_index_expr = f"COALESCE({alias}__row_index, 0)"

            # Generate column expressions using the current (possibly forEach) context
            for col in select.column:
                column_exprs.append(
                    self.generate_column_expr(
                        col,
                        current_var,
                        runtime_type_guard=current_runtime_type_guard,
                        root_resource_var=root_resource_var,
                        row_index_expr=current_row_index_expr,
                    )
                )

            # WHERE conditions use the current context variable.
            # For forEachOrNull contexts, NULL rows (absent path) must be
            # preserved — wrap the condition so NULLs pass through.
            for w in select.where:
                path = w.get("path", "") if isinstance(w, dict) else ""
                if path:
                    resolved = self._resolve_path(path)
                    resolved, where_var = self._resolve_environment_path_context(
                        resolved,
                        current_var,
                        root_resource_var,
                    )
                    path_expr = self._fhirpath_expression_sql(
                        resolved,
                        current_row_index_expr,
                    )
                    cond = self._where_condition_sql(where_var, path_expr)
                    if in_foreach_or_null:
                        cond = f"({current_var} IS NULL OR {cond})"
                    elif null_preserve_var:
                        # Nested inside an enclosing forEachOrNull — preserve
                        # NULL rows by guarding against the null variable.
                        cond = f"({null_preserve_var} IS NULL OR {cond})"
                    where_conditions.append(cond)

            # Recurse into nested selects passing the current forEach context down
            if select.select:
                # Propagate the null-preservation variable: if we're inside
                # a forEachOrNull, nested WHERE conditions must also be
                # wrapped to preserve NULL rows.
                nested_null_var = null_preserve_var
                if in_foreach_or_null:
                    nested_null_var = current_var
                sub_cols, sub_joins, sub_where = self._process_selects(
                    select.select,
                    current_var,
                    nested_null_var,
                    current_runtime_type_guard,
                    root_resource_var,
                    current_row_index_expr,
                )
                column_exprs.extend(sub_cols)
                join_clauses.extend(sub_joins)
                where_conditions.extend(sub_where)

        return column_exprs, join_clauses, where_conditions

    def _has_union_all(self, selects: List[Select]) -> bool:
        """Check if any select in the list contains a unionAll."""
        return any(s.unionAll for s in selects)

    def _build_single_query(
        self,
        selects: List[Select],
        table_name: str,
        base_resource_var: str,
        root_where: List[dict],
    ) -> str:
        """Build a single SELECT query from a list of non-unionAll selects."""
        column_exprs, join_clauses, where_conditions = self._process_selects(
            selects,
            base_resource_var,
            root_resource_var=base_resource_var,
        )

        if not column_exprs:
            return "SELECT NULL WHERE FALSE"

        for w in root_where:
            path = w.get("path", "") if isinstance(w, dict) else ""
            if path:
                resolved = self._resolve_path(path)
                resolved, where_var = self._resolve_environment_path_context(
                    resolved,
                    base_resource_var,
                    base_resource_var,
                )
                path_expr = self._fhirpath_expression_sql(resolved, "0")
                where_conditions.append(self._where_condition_sql(where_var, path_expr))

        columns_sql = ",\n    ".join(column_exprs)
        from_sql = f"FROM {table_name} {self.table_alias}"

        # When using a shared source_table, filter by resourceType
        if self._source_table is not None and hasattr(self, '_current_resource_type'):
            where_conditions.insert(
                0,
                f"json_extract_string({self.table_alias}.resource, '$.resourceType') = "
                f"'{self._current_resource_type}'"
            )

        parts = [f"SELECT\n    {columns_sql}", from_sql]
        parts.extend(join_clauses)
        if where_conditions:
            parts.append("WHERE " + "\n  AND ".join(where_conditions))

        return "\n".join(parts)

    def _build_union_all_query(
        self,
        union_select: Select,
        sibling_selects: List[Select],
        table_name: str,
        base_resource_var: str,
        root_where: List[dict],
    ) -> str:
        """Build a UNION ALL query from a select containing unionAll branches.

        Each unionAll branch becomes a separate SELECT joined by UNION ALL.
        Sibling selects (columns at the same level) are included in each branch.

        If the union_select itself has forEach/forEachOrNull, that unnest context
        wraps each branch so branch paths resolve relative to the unnested element.
        """
        has_parent_context = bool(
            union_select.forEach or union_select.forEachOrNull
            or union_select.repeat
            or union_select.column or union_select.select
            or union_select.where
        )

        branch_sqls = []

        for branch in union_select.unionAll:
            if has_parent_context:
                # Wrap the branch inside the parent's forEach/repeat context so that
                # the branch's paths resolve relative to the unnested element.
                wrapper = Select(
                    forEach=union_select.forEach,
                    forEachOrNull=union_select.forEachOrNull,
                    repeat=union_select.repeat,
                    column=list(union_select.column),
                    select=list(union_select.select or []) + [branch],
                    where=list(union_select.where or []),
                )
                branch_selects = list(sibling_selects) + [wrapper]
            else:
                branch_selects = list(sibling_selects) + [branch]

            # Check for nested unionAll (recursive)
            if branch.unionAll:
                nested_siblings = list(sibling_selects)
                if has_parent_context:
                    # Push parent context as a sibling for nested union
                    parent_ctx = Select(
                        forEach=union_select.forEach,
                        forEachOrNull=union_select.forEachOrNull,
                        repeat=union_select.repeat,
                        column=list(union_select.column),
                        select=list(union_select.select or []),
                        where=list(union_select.where or []),
                    )
                    nested_siblings.append(parent_ctx)
                branch_sql = self._build_union_all_query(
                    branch, nested_siblings,
                    table_name, base_resource_var, root_where
                )
            else:
                branch_sql = self._build_single_query(
                    branch_selects, table_name, base_resource_var, root_where
                )
            branch_sqls.append(branch_sql)

        return "\nUNION ALL\n".join(branch_sqls)

    def _generate_multi_resource_union(self, view_definition: ViewDefinition) -> str:
        """Generate UNION ALL query across multiple resource types.

        When resource is a list (e.g., ["Patient", "Practitioner"]),
        generates a separate query for each type and combines with UNION ALL.

        Args:
            view_definition: ViewDefinition with list resource field

        Returns:
            UNION ALL SQL combining queries for each resource type
        """
        from dataclasses import replace
        queries = []
        for res_type in view_definition.resource:
            single_vd = replace(view_definition, resource=res_type)
            self._alias_counter = 0
            queries.append(self._generate_single_resource(single_vd))
        return "\nUNION ALL\n".join(queries)

    def _hoist_nested_unions(self, selects: List[Select]) -> List[Select]:
        """Hoist nested unionAll to the parent level.

        When a select has a nested select containing unionAll, the UNION ALL
        branches cannot be handled by ``_process_selects`` (which returns a
        flat tuple of cols/joins/wheres). This transformation lifts nested
        unionAll up by replicating the parent context for each branch, so
        ``_generate_single_resource`` can handle them at the top level via
        ``_build_union_all_query``.

        SQL-on-FHIR v2 models both ``select.select`` and ``select.unionAll`` as
        recursive references to ``ViewDefinition.select``. Nested unions inherit
        any parent context, including the default ``$this`` context when no
        forEach/forEachOrNull/repeat is present.
        """
        result: List[Select] = []
        for s in selects:
            # Recursively hoist in sub-selects first
            if s.select:
                s = copy.copy(s)
                s.select = self._hoist_nested_unions(list(s.select))
            # Recursively hoist inside unionAll branches too
            if s.unionAll:
                s = copy.copy(s)
                s.unionAll = self._hoist_nested_unions(list(s.unionAll))

            # Check if this select has a nested select child that contains
            # unionAll. The parent context may be an explicit iterator or the
            # implicit default $this context.
            if s.select:
                nested_unions = [sub for sub in s.select if sub.unionAll]
                if nested_unions:
                    nested_regular = [sub for sub in s.select if not sub.unionAll]
                    # For each nested unionAll, hoist its branches
                    for nu in nested_unions:
                        branches = []
                        for branch in nu.unionAll:
                            # Replicate parent context for each branch
                            hoisted = Select(
                                forEach=s.forEach,
                                forEachOrNull=s.forEachOrNull,
                                repeat=s.repeat,
                                column=list(s.column),
                                select=list(nested_regular) + [branch],
                                where=list(s.where),
                            )
                            branches.append(hoisted)
                        # Replace the original select with a unionAll wrapper
                        result.append(Select(unionAll=branches))
                    continue

            result.append(s)
        return result

    def _copy_select_for_union_expansion(
        self,
        select: Select,
        *,
        nested_selects: Optional[List[Select]] = None,
        union_all: Optional[List[Select]] = None,
    ) -> Select:
        copied = copy.copy(select)
        copied.column = list(select.column)
        copied.select = list(select.select if nested_selects is None else nested_selects)
        copied.unionAll = list(select.unionAll if union_all is None else union_all)
        copied.where = list(select.where)
        copied.repeat = list(select.repeat) if select.repeat is not None else None
        return copied

    def _expand_select_unions(self, select: Select) -> List[List[Select]]:
        """Expand unionAll nodes into branch alternatives that compose as selects."""
        if select.unionAll:
            has_parent_context = bool(
                select.forEach or select.forEachOrNull or select.repeat
                or select.column or select.select or select.where
            )
            alternatives: List[List[Select]] = []
            for branch in select.unionAll:
                if has_parent_context:
                    wrapper = Select(
                        forEach=select.forEach,
                        forEachOrNull=select.forEachOrNull,
                        repeat=list(select.repeat) if select.repeat is not None else None,
                        column=list(select.column),
                        select=list(select.select) + [branch],
                        where=list(select.where),
                    )
                    alternatives.extend(self._expand_select_unions(wrapper))
                else:
                    alternatives.extend(self._expand_select_unions(branch))
            return alternatives or [[]]

        if not select.select:
            return [[self._copy_select_for_union_expansion(select, union_all=[])]]

        alternatives = []
        for nested_selects in self._expand_select_list_unions(list(select.select)):
            alternatives.append([
                self._copy_select_for_union_expansion(
                    select,
                    nested_selects=nested_selects,
                    union_all=[],
                )
            ])
        return alternatives

    def _expand_select_list_unions(self, selects: List[Select]) -> List[List[Select]]:
        """Return SELECT alternatives after applying unionAll/select composition."""
        alternatives: List[List[Select]] = [[]]
        for select in selects:
            select_alternatives = self._expand_select_unions(select)
            next_alternatives: List[List[Select]] = []
            for prefix in alternatives:
                for select_alternative in select_alternatives:
                    next_alternatives.append(prefix + select_alternative)
            alternatives = next_alternatives
        return alternatives or [[]]

    def _generate_single_resource(self, view_definition: ViewDefinition) -> str:
        """Generate SQL for a single-resource ViewDefinition (internal)."""
        base_resource_var = f"{self.table_alias}.resource"
        table_name = self._get_table_name(view_definition.resource)
        root_where = list(view_definition.where)

        expanded_selects = self._expand_select_list_unions(list(view_definition.select))
        queries = [
            self._build_single_query(selects, table_name, base_resource_var, root_where)
            for selects in expanded_selects
        ]
        return "\nUNION ALL\n".join(queries)

    def generate(self, view_definition: ViewDefinition) -> str:
        """Generate complete SQL query from a ViewDefinition.

        Handles basic columns, forEach/forEachOrNull (LATERAL JOINs),
        where clauses, and unionAll (UNION ALL).

        Args:
            view_definition: The ViewDefinition to convert to SQL

        Returns:
            Complete SQL query string

        Raises:
            ValidationError: If undefined constants are referenced

        Example:
            >>> vd = parse_view_definition('''
            ... {
            ...     "resource": "Patient",
            ...     "select": [{
            ...         "column": [
            ...             {"path": "id", "name": "patient_id"},
            ...             {"path": "gender", "name": "gender"}
            ...         ]
            ...     }]
            ... }
            ... ''')
            >>> sql = SQLGenerator().generate(vd)
            >>> print(sql)
            SELECT
                fhirpath_text(t.resource, 'id') as patient_id,
                fhirpath_text(t.resource, 'gender') as gender
            FROM patients t
        """
        if view_definition.name is not None:
            try:
                validate_sql_name(view_definition.name, "ViewDefinition.name")
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
        try:
            validate_root_metadata_fields(
                resourceType=view_definition.resourceType,
                id=view_definition.id,
                meta=view_definition.meta,
                url=view_definition.url,
                version=view_definition.version,
                status=view_definition.status,
                title=view_definition.title,
                description=view_definition.description,
            )
            validate_supported_view_profiles(view_definition)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        if not isinstance(view_definition.fhirVersion, list):
            raise ValidationError("ViewDefinition.fhirVersion must be an array of FHIRVersion codes")
        for version in view_definition.fhirVersion:
            if not isinstance(version, str) or version not in FHIR_VERSION_CODES:
                raise ValidationError(
                    f"ViewDefinition.fhirVersion value {version!r} is not in the "
                    "required FHIRVersion binding"
                )

        self._validate_select_shape(view_definition.select)
        self._validate_where_shapes(view_definition)
        self._validate_fhirpath_syntax(view_definition)
        self._validate_constants(view_definition)
        self._validate_collection_columns(view_definition)
        self._validate_unique_column_names(view_definition)
        self._validate_foreach_mutual_exclusion(view_definition.select)
        self._validate_union_all_columns(view_definition.select)
        self._validate_where_paths(view_definition)
        self._alias_counter = 0
        self._constant_resolver = ConstantResolver.from_view_definition(view_definition)

        resource = view_definition.resource
        if not isinstance(resource, str):
            raise ValidationError(
                "ViewDefinition.resource must be a single FHIR ResourceType string"
            )

        return self._generate_single_resource(view_definition)

    def generate_from_json(self, json_str: str) -> str:
        """Generate SQL directly from a JSON ViewDefinition string.

        Convenience method that parses JSON and generates SQL.

        Args:
            json_str: JSON string containing a ViewDefinition

        Returns:
            Complete SQL query string
        """
        from .parser import parse_view_definition
        vd = parse_view_definition(json_str)
        return self.generate(vd)
