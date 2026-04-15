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

import re
import logging
from typing import List, Optional, Set, Tuple

from .utils import pluralize_resource

_logger = logging.getLogger(__name__)

# Regex for safe SQL identifiers — alphanumeric and underscores only
_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _quote_identifier(name: str) -> str:
    """Quote a SQL identifier, rejecting names that could enable injection."""
    if not name or not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Invalid SQL identifier: {name!r}. "
            "Column names must start with a letter or underscore and contain "
            "only alphanumeric characters and underscores."
        )
    return f'"{name}"'

from .types import Column, ColumnType, Select, ViewDefinition
from .errors import ValidationError

from .unnest import generate_foreach_unnest, generate_foreachornull_unnest
from .constants import ConstantResolver


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
        "decimal": "fhirpath_number",
        "boolean": "fhirpath_bool",
        "date": "fhirpath_text",
        "dateTime": "fhirpath_text",
        "time": "fhirpath_text",
        "code": "fhirpath_text",
        "Coding": "fhirpath_json",
        "CodeableConcept": "fhirpath_json",
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
    _TYPE_CAST = {
        "date": "DATE",
        "dateTime": "TIMESTAMP",
        "instant": "TIMESTAMP",
        "integer": "INTEGER",
        "positiveInt": "INTEGER",
        "unsignedInt": "INTEGER",
    }

    def __init__(self, dialect: str = "duckdb", *, strict_collection: bool = False,
                 source_table: str | None = None):
        """Initialize SQL generator.

        Args:
            dialect: SQL dialect (currently only 'duckdb' supported)
            strict_collection: If True, raise ValidationError when
                collection=false columns use multi-value paths (spec-strict).
                If False, log a warning and proceed (default).
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

    def _get_udf_for_type(self, column_type) -> str:
        """Get the appropriate UDF function name for a column type.

        Args:
            column_type: ColumnType enum or string type hint

        Returns:
            UDF function name to use
        """
        if column_type is None:
            return "fhirpath_text"
        type_str = column_type.value if isinstance(column_type, ColumnType) else str(column_type)
        if type_str in self.TYPE_TO_UDF:
            return self.TYPE_TO_UDF[type_str]
        _logger.warning("Unknown column type '%s', defaulting to fhirpath_text", type_str)
        return "fhirpath_text"

    def _get_sql_cast(self, column_type) -> str | None:
        """Return the SQL type to TRY_CAST the UDF result to, or None."""
        if column_type is None:
            return None
        type_str = column_type.value if isinstance(column_type, ColumnType) else str(column_type)
        return self._TYPE_CAST.get(type_str)

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
        if not resource or not self._VALID_RESOURCE_TYPE_RE.match(resource):
            raise ValidationError(
                f"Invalid FHIR resource type: {resource!r}. "
                "Resource types must be PascalCase alphanumeric (e.g., 'Patient', 'Observation')."
            )
        if self._source_table is not None:
            self._current_resource_type = resource
            return self._source_table
        return pluralize_resource(resource)

    def _resolve_path(self, path: str) -> str:
        """Resolve constant references in a FHIRPath expression."""
        if self._constant_resolver is not None:
            return self._constant_resolver.resolve_in_path(path)
        return path

    def generate_column_expr(self, column: Column, resource_var: str = "resource") -> str:
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
        # Resolve constants in path (%name_use -> 'official')
        resolved_path = self._resolve_path(column.path)

        # %rowIndex: 0-based row counter within the enclosing forEach context
        if resolved_path == "%rowIndex":
            quoted_name = _quote_identifier(column.name)
            if resource_var == f"{self.table_alias}.resource":
                # Top level (no forEach) — each resource is one row, index is 0
                return f"0 as {quoted_name}"
            # Inside forEach/forEachOrNull — use the ordinality column
            return f"COALESCE({resource_var}__row_index, 0) as {quoted_name}"

        # When path is $this, the resource_var itself is the value.
        # This happens inside forEach where the unnested element IS the value
        # (e.g., forEach: "name.given" produces primitive strings).
        if resolved_path == "$this":
            udf_func = self._get_udf_for_type(column.type)
            quoted_name = _quote_identifier(column.name)
            return (
                f"COALESCE({udf_func}({resource_var}, '$this'), "
                f"CAST({resource_var} AS VARCHAR)) as {quoted_name}"
            )

        # For collection columns, use fhirpath() to return JSON array
        if column.collection:
            escaped_path = resolved_path.replace("'", "''")
            quoted_name = _quote_identifier(column.name)
            return f"fhirpath({resource_var}, '{escaped_path}') as {quoted_name}"

        udf_func = self._get_udf_for_type(column.type)
        sql_cast = self._get_sql_cast(column.type)

        # Escape single quotes in path for SQL string literal
        escaped_path = resolved_path.replace("'", "''")
        quoted_name = _quote_identifier(column.name)

        udf_call = f"{udf_func}({resource_var}, '{escaped_path}')"
        if sql_cast:
            return f"TRY_CAST({udf_call} AS {sql_cast}) as {quoted_name}"
        return f"{udf_call} as {quoted_name}"

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

    # Pattern to match %ConstantName in FHIRPath expressions
    _CONSTANT_PATTERN = re.compile(r'%([a-zA-Z_][a-zA-Z0-9_]*)')

    # Built-in variables recognised by the SQL-on-FHIR v2 spec that do NOT
    # need to appear in the ViewDefinition's ``constants`` section.
    _BUILTIN_VARIABLES = {"rowIndex"}

    def _extract_constant_references(self, path: str) -> Set[str]:
        """Extract all constant references (%name) from a FHIRPath expression.

        Args:
            path: A FHIRPath expression that may contain constant references

        Returns:
            Set of constant names referenced in the path
        """
        return set(self._CONSTANT_PATTERN.findall(path))

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
            if isinstance(where, dict):
                for key, value in where.items():
                    if isinstance(value, str):
                        paths.append(value)

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

                # where clauses
                for where in select.where:
                    if isinstance(where, dict):
                        for key, value in where.items():
                            if isinstance(value, str):
                                paths.append(value)

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
        # Build set of defined constant names
        defined_constants = {const.name for const in view_definition.constants}

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

    # Known FHIR R4 array element names (max cardinality = *).
    # Derived from StructureDefinition snapshots in fhir4ds/cql/resources/fhir/r4/.
    # Excludes ambiguous names that are predominantly scalar (code, type, location,
    # class, performerType, statusReason) to avoid false positives in heuristic checks.
    _FHIR_ARRAY_ELEMENTS = {
        'about', 'account', 'address', 'appliesTo', 'appointment', 'assessment',
        'authorizingPrescription', 'basedOn', 'batch', 'bodySite',
        'category', 'classHistory', 'communication', 'complication',
        'complicationDetail', 'component', 'conclusionCode', 'contact', 'contained',
        'contract', 'costToBeneficiary',
        'definition', 'derivedFrom', 'destination', 'detail', 'detectedIssue', 'device',
        'diagnosis', 'dietPreference', 'dosageInstruction',
        'education', 'entry', 'episodeOfCare', 'eventHistory', 'evidence', 'exception',
        'extension',
        'focalDevice', 'focus', 'followUp',
        'generalPractitioner', 'given',
        'hasMember',
        'identifier', 'imagingStudy', 'ingredient', 'input', 'instantiates',
        'instantiatesCanonical', 'instantiatesUri', 'insurance', 'interpretation',
        'line', 'link',
        'manifestation', 'media', 'medium', 'modifierExtension',
        'name', 'note',
        'orderDetail', 'output',
        'parameter', 'partOf', 'participant', 'payload', 'payor', 'performer',
        'photo', 'prefix', 'presentedForm', 'priorRequest',
        'programEligibility', 'protocolApplied',
        'reaction', 'reason', 'reasonCode', 'reasonReference', 'receiver', 'recipient',
        'referenceRange', 'relationship', 'relevantHistory', 'replaces', 'report',
        'responsibleParty', 'result', 'resultsInterpreter',
        'sender', 'source', 'specialArrangement', 'specialCourtesy', 'specimen', 'stage',
        'statusHistory', 'subpotentReason', 'suffix', 'supportingInfo',
        'supportingInformation',
        'targetDisease', 'telecom',
        'usedCode', 'usedReference',
    }

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

        Per SQL-on-FHIR spec, when collection is false the engine returns
        only the first value. Uses heuristics to detect paths that traverse
        FHIR array elements without singleton accessors.

        In strict mode (strict_collection=True), raises ValidationError.
        In permissive mode (default), logs a warning and proceeds.

        When columns are inside a forEach/forEachOrNull context, validation
        is skipped because paths are relative to unnested elements.

        Args:
            view_definition: The ViewDefinition to validate
        """
        def validate_select_columns(selects: List[Select], in_foreach: bool = False) -> None:
            for select in selects:
                current_in_foreach = in_foreach or bool(select.forEach) or bool(select.forEachOrNull)

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
        """Validate that column names are unique within a single select scope.

        Per SQL-on-FHIR v2 spec, column names in a ViewDefinition's output
        must be unique within each select scope. Names within unionAll branches
        are expected to match (they contribute to the same UNION ALL output).
        Sibling selects with unionAll at the top level may share names across
        their branches as they produce independent column groups.

        This validates within each individual select's direct columns plus
        nested selects (non-unionAll) for duplicates.

        Args:
            view_definition: The ViewDefinition to validate

        Raises:
            ValidationError: If duplicate column names are found within a single select
        """
        def validate_select(sel: Select, path: str = "select") -> None:
            """Check for duplicates within a single select's own columns."""
            names: List[str] = [col.name for col in sel.column]
            seen: Set[str] = set()
            duplicates: Set[str] = set()
            for name in names:
                if name in seen:
                    duplicates.add(name)
                seen.add(name)
            if duplicates:
                raise ValidationError(
                    f"Duplicate column names in {path}: {sorted(duplicates)}. "
                    f"Column names must be unique per the SQL-on-FHIR v2 specification.",
                    details={"duplicate_names": sorted(duplicates), "path": path}
                )
            # Recurse into nested selects
            for i, nested in enumerate(sel.select):
                validate_select(nested, f"{path}.select[{i}]")
            # Recurse into unionAll branches
            for i, branch in enumerate(sel.unionAll):
                validate_select(branch, f"{path}.unionAll[{i}]")

        for i, sel in enumerate(view_definition.select):
            validate_select(sel, f"select[{i}]")

    def _validate_foreach_mutual_exclusion(self, selects: List[Select]) -> None:
        """Validate that no select uses both forEach and forEachOrNull.

        Per SQL-on-FHIR v2 spec, these are mutually exclusive.
        """
        def _check(sels: List[Select], path: str = "select") -> None:
            for i, sel in enumerate(sels):
                if sel.forEach and sel.forEachOrNull:
                    raise ValidationError(
                        f"{path}[{i}]: Both forEach and forEachOrNull specified "
                        "(they are mutually exclusive per the SQL-on-FHIR v2 specification)"
                    )
                if sel.select:
                    _check(sel.select, f"{path}[{i}].select")
                if sel.unionAll:
                    _check(sel.unionAll, f"{path}[{i}].unionAll")
        _check(selects)

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
    ) -> Tuple[List[str], List[str], List[str]]:
        """Recursively process a list of Select structures.

        Traverses nested selects, tracking the resource variable in scope for
        each forEach/forEachOrNull context and collecting WHERE conditions.
        unionAll branches are NOT processed here — they are handled in generate().

        Args:
            selects: List of Select structures to process
            resource_var: Current resource variable expression

        Returns:
            Tuple of (column_exprs, join_clauses, where_conditions)
        """
        column_exprs: List[str] = []
        join_clauses: List[str] = []
        where_conditions: List[str] = []

        for select in selects:
            current_var = resource_var

            # Establish a new forEach context (CROSS JOIN LATERAL)
            if select.forEach:
                resolved_foreach = self._resolve_path(select.forEach)
                alias = self._next_alias(resolved_foreach)
                join_clauses.append(
                    generate_foreach_unnest(resolved_foreach, current_var, alias)
                )
                current_var = alias
            elif select.forEachOrNull:
                resolved_foreach = self._resolve_path(select.forEachOrNull)
                alias = self._next_alias(resolved_foreach)
                join_clauses.append(
                    generate_foreachornull_unnest(resolved_foreach, current_var, alias)
                )
                current_var = alias

            # Generate column expressions using the current (possibly forEach) context
            for col in select.column:
                column_exprs.append(self.generate_column_expr(col, current_var))

            # WHERE conditions use the current context variable
            for w in select.where:
                path = w.get("path", "") if isinstance(w, dict) else ""
                if path:
                    resolved = self._resolve_path(path)
                    escaped = resolved.replace("'", "''")
                    where_conditions.append(
                        f"fhirpath_bool({current_var}, '{escaped}') = true"
                    )

            # Recurse into nested selects passing the current forEach context down
            if select.select:
                sub_cols, sub_joins, sub_where = self._process_selects(
                    select.select, current_var
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
            selects, base_resource_var
        )

        if not column_exprs:
            return "SELECT NULL WHERE FALSE"

        for w in root_where:
            path = w.get("path", "") if isinstance(w, dict) else ""
            if path:
                resolved = self._resolve_path(path)
                escaped = resolved.replace("'", "''")
                where_conditions.append(
                    f"fhirpath_bool({base_resource_var}, '{escaped}') = true"
                )

        columns_sql = ",\n    ".join(column_exprs)
        from_sql = f"FROM {table_name} {self.table_alias}"

        # When using a shared source_table, filter by resourceType
        if self._source_table is not None and hasattr(self, '_current_resource_type'):
            where_conditions.insert(
                0, f"{self.table_alias}.\"resourceType\" = '{self._current_resource_type}'"
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
            or union_select.column or union_select.select
            or union_select.where
        )

        branch_sqls = []

        for branch in union_select.unionAll:
            if has_parent_context:
                # Wrap the branch inside the parent's forEach context so that
                # the branch's paths resolve relative to the unnested element.
                wrapper = Select(
                    forEach=union_select.forEach,
                    forEachOrNull=union_select.forEachOrNull,
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

    def _generate_single_resource(self, view_definition: ViewDefinition) -> str:
        """Generate SQL for a single-resource ViewDefinition (internal)."""
        base_resource_var = f"{self.table_alias}.resource"
        table_name = self._get_table_name(view_definition.resource)
        root_where = list(view_definition.where)

        union_selects: List[Select] = []
        sibling_selects: List[Select] = []
        for s in view_definition.select:
            if s.unionAll:
                union_selects.append(s)
            else:
                sibling_selects.append(s)

        if union_selects:
            union_queries = [
                self._build_union_all_query(
                    union_select,
                    sibling_selects,
                    table_name,
                    base_resource_var,
                    root_where,
                )
                for union_select in union_selects
            ]
            return "\nUNION ALL\n".join(union_queries)

        return self._build_single_query(
            view_definition.select, table_name, base_resource_var, root_where
        )

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
        self._validate_constants(view_definition)
        self._validate_collection_columns(view_definition)
        self._validate_unique_column_names(view_definition)
        self._validate_foreach_mutual_exclusion(view_definition.select)
        self._alias_counter = 0
        self._constant_resolver = ConstantResolver.from_view_definition(view_definition)

        # Handle resource-as-list (multi-resource union)
        resource = view_definition.resource
        if isinstance(resource, list):
            return self._generate_multi_resource_union(view_definition)

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
