"""
ViewDefinition parser for SQL-on-FHIR v2.

Parses JSON ViewDefinitions into Python dataclasses for SQL generation.
"""

from typing import List, Dict, Any, Union
import json

from .types import (
    _extract_constant_value,
    Column,
    ColumnTag,
    Select,
    Constant,
    Join,
    JoinType,
    ViewDefinition,
    validate_canonical_array,
    validate_column_fields,
    validate_constant_fields,
    validate_fhir_version_array,
    validate_optional_boolean,
    validate_optional_fhirpath_string,
    validate_optional_uri_string,
    validate_repeat_paths,
    validate_resource_type,
    validate_root_metadata_fields,
    validate_sql_name,
    validate_supported_view_profiles,
    validate_where_conditions,
)
from .errors import ParseError
from .metadata import KNOWN_FHIR_RESOURCE_TYPES


def _parse_optional_sql_name(data: Dict[str, Any], field_name: str) -> str | None:
    """Parse an optional SQL-on-FHIR sql-name field."""
    if field_name not in data:
        return None
    value = data[field_name]
    try:
        return validate_sql_name(value, f"ViewDefinition.{field_name}")
    except ValueError as exc:
        raise ParseError(str(exc)) from exc


def _parse_optional_root_metadata(data: Dict[str, Any], field_name: str) -> Any:
    """Return optional root metadata while rejecting present JSON null."""
    if field_name not in data:
        return None
    value = data[field_name]
    if value is None:
        raise ParseError(f"ViewDefinition.{field_name} must not be null when present")
    return value


def _parse_string_array(data: Dict[str, Any], field_name: str) -> List[str]:
    """Parse an optional 0..* string field from a ViewDefinition object."""
    if field_name not in data:
        return []
    raw = data[field_name]
    if raw is None:
        raise ParseError(
            f"ViewDefinition '{field_name}' must be an array of strings, got null"
        )
    if not isinstance(raw, list):
        raise ParseError(
            f"ViewDefinition '{field_name}' must be an array of strings, "
            f"got {type(raw).__name__}"
        )
    if not all(isinstance(item, str) and item for item in raw):
        raise ParseError(f"ViewDefinition '{field_name}' must contain only non-empty strings")
    return list(raw)


def _parse_optional_fhirpath_string(
    data: Dict[str, Any],
    field_name: str,
    label: str,
) -> str | None:
    """Parse an optional 0..1 FHIRPath string from official JSON input."""
    if field_name not in data:
        return None
    if data[field_name] is None:
        raise ParseError(f"{label} must be a non-empty string")
    try:
        return validate_optional_fhirpath_string(data[field_name], label)
    except ValueError as exc:
        raise ParseError(str(exc)) from exc


def _parse_canonical_array(data: Dict[str, Any], field_name: str) -> List[str]:
    """Parse an optional 0..* canonical field from a ViewDefinition object."""
    if field_name not in data:
        return []
    try:
        return validate_canonical_array(
            data[field_name],
            f"ViewDefinition.{field_name}",
        )
    except ValueError as exc:
        raise ParseError(str(exc)) from exc


def _validate_fhir_versions(values: List[str]) -> None:
    try:
        validate_fhir_version_array(values, "ViewDefinition.fhirVersion")
    except ValueError as exc:
        raise ParseError(str(exc)) from exc


def _parse_column(col_data: Dict[str, Any]) -> Column:
    """Parse a column definition from JSON dict.

    Args:
        col_data: Dictionary with column properties

    Returns:
        Column dataclass instance
    """
    if not isinstance(col_data, dict):
        raise ParseError(
            f"Column definition must be a JSON object, got "
            f"{type(col_data).__name__}: {col_data!r}"
        )

    if "tags" in col_data:
        raise ParseError(
            "Unsupported field 'tags'. SQL-on-FHIR ViewDefinition uses "
            "the singular 'tag' array for column metadata."
        )
    raw_tag = col_data.get("tag", [])
    if raw_tag is None or not isinstance(raw_tag, list):
        raise ParseError(
            f"Column 'tag' must be an array of JSON objects, got {type(raw_tag).__name__}"
        )
    tags = []
    for idx, tag_item in enumerate(raw_tag):
        try:
            tags.append(ColumnTag.from_dict(tag_item))
        except ValueError as exc:
            raise ParseError(f"Invalid column tag at index {idx}: {exc}") from exc

    try:
        if "description" in col_data and col_data["description"] is None:
            raise ValueError("Column.description must be a markdown string")
        path, name, description = validate_column_fields(
            col_data.get('path'),
            col_data.get('name'),
            col_data.get('description'),
        )
        collection = validate_optional_boolean(
            col_data["collection"] if "collection" in col_data else False,
            "Column.collection",
        )
        if "type" in col_data:
            if col_data["type"] is None:
                raise ValueError("Column.type must be a non-empty URI string")
            column_type = validate_optional_uri_string(col_data["type"], "Column.type")
        else:
            column_type = None
    except ValueError as exc:
        raise ParseError(f"Invalid column definition: {exc}") from exc

    return Column(
        path=path,
        name=name,
        type=column_type,
        collection=collection,
        description=description,
        tag=tags,
    )


def _parse_where(where_data: Union[List[Any], Dict[str, Any], str]) -> List[Dict[str, str]]:
    """Parse where conditions from JSON.

    Accepts both spec-compliant dict format ({"path": "expr"}) and
    convenience string format ("expr") which is wrapped automatically.

    Args:
        where_data: Where condition object, string, or list of either form

    Returns:
        List of condition dictionaries with 'path' keys

    Raises:
        ParseError: If a where condition has an unsupported type
    """
    try:
        return validate_where_conditions(where_data, "Where")
    except ValueError as exc:
        raise ParseError(str(exc)) from exc


def _parse_select(select_data: Dict[str, Any]) -> Select:
    """Parse a select structure from JSON dict.

    Args:
        select_data: Dictionary with select properties

    Returns:
        Select dataclass instance
    """
    if not isinstance(select_data, dict):
        raise ParseError(
            f"Select definition must be a JSON object, got "
            f"{type(select_data).__name__}: {select_data!r}"
        )

    def _parse_object_array(
        field_name: str,
        *,
        require_non_empty: bool = False,
    ) -> List[Dict[str, Any]]:
        if field_name not in select_data:
            return []
        raw = select_data[field_name]
        if not isinstance(raw, list):
            raise ParseError(
                f"Select '{field_name}' must be an array of JSON objects, "
                f"got {type(raw).__name__}"
            )
        if require_non_empty and not raw:
            raise ParseError(
                f"Select '{field_name}' must contain at least one JSON object when present"
            )
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                raise ParseError(
                    f"Select '{field_name}' item {idx} must be a JSON object, "
                    f"got {type(item).__name__}: {item!r}"
                )
        return raw

    # Parse columns
    columns = []
    for col in _parse_object_array('column'):
        columns.append(_parse_column(col))

    # Parse nested selects
    nested_selects = []
    for sel in _parse_object_array('select'):
        nested_selects.append(_parse_select(sel))

    # Parse unionAll
    union_all = []
    for u in _parse_object_array('unionAll', require_non_empty=True):
        union_all.append(_parse_select(u))

    # Parse where conditions
    where = _parse_where(select_data.get('where', []))

    try:
        for_each = _parse_optional_fhirpath_string(
            select_data,
            'forEach',
            "Select.forEach",
        )
        for_each_or_null = _parse_optional_fhirpath_string(
            select_data,
            'forEachOrNull',
            "Select.forEachOrNull",
        )
        repeat = (
            validate_repeat_paths(select_data['repeat'], "Select.repeat")
            if 'repeat' in select_data
            else None
        )
    except ValueError as exc:
        raise ParseError(str(exc)) from exc

    active_iterators = []
    if for_each:
        active_iterators.append("forEach")
    if for_each_or_null:
        active_iterators.append("forEachOrNull")
    if repeat:
        active_iterators.append("repeat")
    if len(active_iterators) > 1:
        raise ParseError(
            "Select can only have at most one of forEach, forEachOrNull, or repeat; "
            f"got {', '.join(active_iterators)}"
        )

    return Select(
        column=columns,
        select=nested_selects,
        forEach=for_each,
        forEachOrNull=for_each_or_null,
        unionAll=union_all,
        where=where,
        repeat=repeat,
    )


def _parse_constant(const_data: Dict[str, Any]) -> Constant:
    """Parse a constant definition from JSON dict.

    Handles various constant value types per SQL-on-FHIR v2 spec:
    - valueString, valueCode, valueInteger, valueInteger64, valueBoolean, valueDecimal
    - valueDate, valueDateTime, valueTime, valueInstant
    - valueUri, valueUrl, valueUuid, valueOid, valueCanonical, valueBase64Binary, valueId
    - valuePositiveInt, valueUnsignedInt

    Args:
        const_data: Dictionary with constant properties

    Returns:
        Constant dataclass instance with value and value_type set
    """
    name = const_data.get('name', '')
    if not name:
        raise ParseError(f"Constant missing required 'name' field: {const_data}")

    try:
        validate_sql_name(name, "Constant.name")
    except ValueError as exc:
        raise ParseError(str(exc)) from exc

    try:
        value, value_type = _extract_constant_value(const_data)
    except ValueError as exc:
        raise ParseError(f"Constant '{name}' invalid value[x]: {exc}") from exc

    return Constant(name=name, value=value, value_type=value_type)


def _parse_join(join_data: Dict[str, Any]) -> Join:
    """Parse a join definition from JSON dict.

    Args:
        join_data: Dictionary with join properties

    Returns:
        Join dataclass instance
    """
    if not isinstance(join_data, dict):
        raise ParseError(
            f"Join definition must be a JSON object, got "
            f"{type(join_data).__name__}: {join_data!r}"
        )

    name = join_data.get('name', '')
    resource = join_data.get('resource', '')

    if not name:
        raise ParseError(f"Join missing required 'name' field: {join_data}")
    if not resource:
        raise ParseError(f"Join missing required 'resource' field: {join_data}")
    try:
        validate_sql_name(name, "Join.name")
    except ValueError as exc:
        raise ParseError(str(exc)) from exc
    if not isinstance(resource, str):
        raise ParseError(
            f"Join.resource must be a FHIR ResourceType string, got {type(resource).__name__}"
        )
    if resource not in KNOWN_FHIR_RESOURCE_TYPES:
        raise ParseError(
            f"Join.resource {resource!r} is not in the required ResourceType binding"
        )

    # Parse on conditions
    raw_on = join_data.get('on', [])
    if not isinstance(raw_on, list):
        raise ParseError(
            f"Join 'on' must be an array of JSON objects, got {type(raw_on).__name__}"
        )
    on_conditions = []
    for on_item in raw_on:
        if isinstance(on_item, dict):
            on_conditions.append(dict(on_item))
        else:
            raise ParseError(
                f"Join 'on' items must be dicts, got {type(on_item).__name__}: {on_item}"
            )
    try:
        return Join(
            name=name,
            resource=resource,
            on=on_conditions,
            type=join_data.get('type', 'inner')
        )
    except ValueError as exc:
        raise ParseError(str(exc)) from exc


def parse_view_definition(json_str_or_dict) -> ViewDefinition:
    """Parse a JSON string or dict into a ViewDefinition dataclass.

    Args:
        json_str_or_dict: JSON string or dict containing a ViewDefinition

    Returns:
        ViewDefinition dataclass instance

    Raises:
        ParseError: If JSON is invalid or required fields are missing
        TypeError: If the input type is not supported
    """
    if isinstance(json_str_or_dict, dict):
        data = json_str_or_dict
    elif isinstance(json_str_or_dict, str):
        if json_str_or_dict.lstrip().startswith("<"):
            raise ParseError(
                "XML ViewDefinition parsing is not supported. Provide the "
                "SQL-on-FHIR JSON representation instead."
            )
        try:
            data = json.loads(json_str_or_dict)
        except json.JSONDecodeError as e:
            raise ParseError(f"Invalid JSON: {e}")
    else:
        raise TypeError(
            f"Expected str or dict, got {type(json_str_or_dict).__name__}"
        )

    if not isinstance(data, dict):
        raise ParseError("ViewDefinition must be a JSON object")

    try:
        (
            resource_type,
            view_id,
            meta,
            url,
            version,
            status,
            title,
            description,
        ) = validate_root_metadata_fields(
            resourceType=_parse_optional_root_metadata(data, "resourceType"),
            id=_parse_optional_root_metadata(data, "id"),
            meta=_parse_optional_root_metadata(data, "meta"),
            url=_parse_optional_root_metadata(data, "url"),
            version=_parse_optional_root_metadata(data, "version"),
            status=_parse_optional_root_metadata(data, "status"),
            title=_parse_optional_root_metadata(data, "title"),
            description=_parse_optional_root_metadata(data, "description"),
        )
    except ValueError as exc:
        raise ParseError(str(exc)) from exc

    # Parse required fields
    resource = data.get('resource', '')
    if not resource:
        raise ParseError("ViewDefinition missing required 'resource' field")

    # ViewDefinition.resource is 1..1 code, bound to FHIR ResourceType.
    try:
        resource = validate_resource_type(resource, "ViewDefinition.resource")
    except ValueError as exc:
        raise ParseError(str(exc)) from exc

    profile = _parse_canonical_array(data, "profile")
    fhir_version = _parse_string_array(data, "fhirVersion")
    _validate_fhir_versions(fhir_version)

    # Parse select structures
    selects = []
    if 'select' not in data:
        raise ParseError("ViewDefinition missing required 'select' field")
    select_data = data['select']
    if not isinstance(select_data, list):
        raise ParseError(
            f"ViewDefinition 'select' must be an array of JSON objects, "
            f"got {type(select_data).__name__}"
        )
    if not select_data:
        raise ParseError("ViewDefinition 'select' array must not be empty")

    for idx, sel in enumerate(select_data):
        if not isinstance(sel, dict):
            raise ParseError(
                f"ViewDefinition 'select' item {idx} must be a JSON object, "
                f"got {type(sel).__name__}: {sel!r}"
            )
        selects.append(_parse_select(sel))

    # SQL-on-FHIR v2 ValidateColumns algorithm: a duplicate column name in the
    # effective output schema is a hard "Column Already Defined" error. The
    # effective schema counts each select's direct columns, its nested selects'
    # effective schemas, and only the first unionAll branch's effective schema
    # (subsequent branches must match the first by name/order/type, so they do
    # not contribute additional names). The parser already enforces the
    # analogous hard rejection for duplicate Constant.name; enforce the same
    # boundary here so parse_view_definition() does not return a spec-invalid
    # ViewDefinition. This mirrors SQLGenerator._collect_select_output_schema.
    def _effective_output_names(select: "Select") -> List[str]:
        names: List[str] = [col.name for col in select.column]
        for nested in select.select:
            names.extend(_effective_output_names(nested))
        if select.unionAll:
            names.extend(_effective_output_names(select.unionAll[0]))
        return names

    seen_column_names: set[str] = set()
    duplicate_column_names: set[str] = set()
    for sel in selects:
        for name in _effective_output_names(sel):
            if name in seen_column_names:
                duplicate_column_names.add(name)
            seen_column_names.add(name)
    if duplicate_column_names:
        raise ParseError(
            f"Duplicate column names across select tree: "
            f"{sorted(duplicate_column_names)}. Column names must be unique "
            f"per the SQL-on-FHIR v2 specification."
        )

    # Parse constants. SQL-on-FHIR uses the singular JSON field `constant`.
    constants = []
    if 'constants' in data:
        raise ParseError(
            "Unsupported field 'constants'. SQL-on-FHIR ViewDefinition uses "
            "the singular 'constant' array."
        )
    if 'constant' in data:
        const_raw = data['constant']
    else:
        const_raw = []
    if isinstance(const_raw, list):
        constant_names = set()
        for const in const_raw:
            if isinstance(const, dict):
                parsed_constant = _parse_constant(const)
                if parsed_constant.name in constant_names:
                    raise ParseError(
                        f"Duplicate constant name: {parsed_constant.name}"
                    )
                constant_names.add(parsed_constant.name)
                constants.append(parsed_constant)
            else:
                raise ParseError(
                    f"Each constant must be a JSON object, got {type(const).__name__}: {const!r}"
                )
    elif const_raw is None:
        raise ParseError("'constant' must be a JSON array, got null")
    elif const_raw:
        raise ParseError(
            f"'constant' must be a JSON array, got {type(const_raw).__name__}"
        )

    # Parse joins
    joins = []
    raw_joins = data.get('joins', [])
    if raw_joins is None or not isinstance(raw_joins, list):
        raise ParseError(
            f"ViewDefinition 'joins' must be an array of JSON objects, "
            f"got {type(raw_joins).__name__}"
        )
    for j in raw_joins:
        joins.append(_parse_join(j))

    # Parse top-level where conditions
    where = _parse_where(data.get('where', []))

    name = _parse_optional_sql_name(data, "name")

    # §G-3 CanonicalResource/DomainResource roundtrip: preserve unknown
    # top-level keys verbatim in extra_fields. No validation, no coercion.
    # The known-keys set covers everything the dataclass models explicitly.
    _KNOWN_TOP_LEVEL_KEYS = frozenset({
        "resourceType", "resource", "id", "meta", "url", "version", "name",
        "status", "title", "description", "profile", "fhirVersion",
        "constant", "select", "where", "joins",
    })
    extensions_bag: dict = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if key not in _KNOWN_TOP_LEVEL_KEYS:
                extensions_bag[key] = value

    view_definition = ViewDefinition(
        resource=resource,
        select=selects,
        resourceType=resource_type,
        id=view_id,
        meta=meta,
        url=url,
        version=version,
        name=name,
        status=status,
        title=title,
        description=description,
        profile=profile,
        fhirVersion=fhir_version,
        constants=constants,
        joins=joins,
        where=where,
        extra_fields=extensions_bag,
    )
    try:
        validate_supported_view_profiles(view_definition)
    except ValueError as exc:
        raise ParseError(str(exc)) from exc
    return view_definition


def validate_view_definition(vd: ViewDefinition) -> List[str]:
    """Validate a ViewDefinition per SQL-on-FHIR spec (permissive mode).

    This function returns warnings rather than raising exceptions,
    allowing for permissive parsing where minor issues are flagged
    but don't prevent processing.

    Args:
        vd: ViewDefinition to validate

    Returns:
        List of warning messages (empty if valid)
    """
    warnings = []

    def _warn_from_validator(func, *args, **kwargs) -> None:
        try:
            func(*args, **kwargs)
        except ValueError as exc:
            warnings.append(str(exc))

    _warn_from_validator(
        validate_root_metadata_fields,
        resourceType=vd.resourceType,
        id=vd.id,
        meta=vd.meta,
        url=vd.url,
        version=vd.version,
        status=vd.status,
        title=vd.title,
        description=vd.description,
    )

    if vd.name is not None:
        _warn_from_validator(validate_sql_name, vd.name, "ViewDefinition.name")
        # SQL-on-FHIR v2 cnl-0 warning invariant on ViewDefinition.name:
        # when present, must match ^[A-Z]([A-Za-z0-9_]){1,254}$ (leading
        # capital, 2-255 chars total). Warning severity per spec — do not
        # promote to error. The sql-name error invariant above stays.
        if vd.name and (
            not vd.name[0].isupper() or len(vd.name) > 255 or len(vd.name) < 2
        ):
            warnings.append(
                f"ViewDefinition.name {vd.name!r} violates cnl-0: must start "
                f"with a capital letter and be 2-255 characters total"
            )

    if vd.profile or not isinstance(vd.profile, list):
        _warn_from_validator(validate_canonical_array, vd.profile, "ViewDefinition.profile")

    if vd.fhirVersion or not isinstance(vd.fhirVersion, list):
        _warn_from_validator(
            validate_fhir_version_array,
            vd.fhirVersion,
            "ViewDefinition.fhirVersion",
        )

    # Check required fields
    if not vd.resource:
        warnings.append("Missing required field: resource")
    else:
        _warn_from_validator(validate_resource_type, vd.resource, "ViewDefinition.resource")

    if not vd.select:
        warnings.append("Missing required field: select")
    elif not isinstance(vd.select, list):
        warnings.append("ViewDefinition.select must be an array of Select objects")
        return warnings

    # Check column name uniqueness at top level
    all_names = collect_column_names(vd.select)
    seen = set()
    duplicates = set()
    for name in all_names:
        if name in seen:
            duplicates.add(name)
        seen.add(name)

    if duplicates:
        warnings.append(f"Duplicate column names: {sorted(duplicates)}")

    # Validate nested structures
    warnings.extend(_validate_selects(vd.select, "select"))
    if _select_tree_is_profile_checkable(vd.select):
        _warn_from_validator(validate_supported_view_profiles, vd)

    # Validate constants
    const_names = set()
    for const in vd.constants:
        if not isinstance(const, Constant):
            warnings.append("ViewDefinition.constant items must be Constant objects")
            continue
        if const.name in const_names:
            warnings.append(f"Duplicate constant name: {const.name}")
        const_names.add(const.name)

        _warn_from_validator(
            validate_constant_fields,
            const.name,
            const.value,
            const.value_type,
        )

    # Validate joins
    join_names = set()
    for join in vd.joins:
        if not isinstance(join, Join):
            warnings.append("ViewDefinition.joins items must be Join objects")
            continue
        if join.name in join_names:
            warnings.append(f"Duplicate join name: {join.name}")
        join_names.add(join.name)

        if not join.on:
            warnings.append(f"Join '{join.name}' has no 'on' conditions")

        if join.type not in (JoinType.INNER, JoinType.LEFT, JoinType.RIGHT, JoinType.FULL):
            warnings.append(f"Join '{join.name}' has invalid type: {join.type}")

    return warnings


def _select_tree_is_profile_checkable(selects: List[Select]) -> bool:
    """Return True when select/column objects are safe for profile validation."""
    if not isinstance(selects, list):
        return False
    for sel in selects:
        if not isinstance(sel, Select):
            return False
        if not isinstance(sel.column, list):
            return False
        if any(not isinstance(col, Column) for col in sel.column):
            return False
        if not _select_tree_is_profile_checkable(sel.select):
            return False
        if not _select_tree_is_profile_checkable(sel.unionAll):
            return False
    return True


def _validate_selects(selects: List[Select], path: str) -> List[str]:
    """Recursively validate select structures.

    Args:
        selects: List of Select structures to validate
        path: Current path for error messages

    Returns:
        List of warning messages
    """
    warnings = []

    for i, sel in enumerate(selects):
        current_path = f"{path}[{i}]"
        if not isinstance(sel, Select):
            warnings.append(f"{current_path}: Must be a Select object")
            continue

        try:
            validate_optional_fhirpath_string(
                sel.forEach,
                f"{current_path}.forEach",
            )
        except ValueError as exc:
            warnings.append(str(exc))
        try:
            validate_optional_fhirpath_string(
                sel.forEachOrNull,
                f"{current_path}.forEachOrNull",
            )
        except ValueError as exc:
            warnings.append(str(exc))
        if sel.repeat is not None:
            try:
                validate_repeat_paths(sel.repeat, f"{current_path}.repeat")
            except ValueError as exc:
                warnings.append(str(exc))

        # Check iterator mutual exclusion per SQL-on-FHIR sql-expressions constraint.
        active_iterators = []
        if sel.forEach:
            active_iterators.append("forEach")
        if sel.forEachOrNull:
            active_iterators.append("forEachOrNull")
        if sel.repeat:
            active_iterators.append("repeat")
        if len(active_iterators) > 1:
            warnings.append(
                f"{current_path}: Select can only have at most one of "
                f"forEach, forEachOrNull, or repeat; got {', '.join(active_iterators)}"
            )

        # Check for empty select (no columns, no nested selects, no unionAll)
        if (not sel.column and not sel.select and not sel.unionAll and
            not sel.forEach and not sel.forEachOrNull):
            warnings.append(f"{current_path}: Empty select structure")

        # Validate columns
        for j, col in enumerate(sel.column):
            col_path = f"{current_path}.column[{j}]"
            if not isinstance(col, Column):
                warnings.append(f"{col_path}: Must be a Column object")
                continue
            if not col.path:
                warnings.append(f"{col_path}: Missing 'path'")
            if not col.name:
                warnings.append(f"{col_path}: Missing 'name'")
            try:
                validate_column_fields(col.path, col.name, col.description)
            except ValueError as exc:
                warnings.append(str(exc))

            # SQL-on-FHIR v2 §G-4: column.tag.name namespace recommendation.
            # Spec language is "Namespace recommended (e.g. `ansi/type`)",
            # not "shall". Warning severity only — do not promote to error.
            for tag in (col.tag or []):
                if isinstance(tag, ColumnTag) and tag.name and "/" not in tag.name:
                    warnings.append(
                        f"{col_path}.tag: name {tag.name!r} lacks a namespace "
                        f"prefix; spec recommends namespaced tag names like "
                        f"'ansi/type'"
                    )

        # Recursively validate nested selects
        if sel.select:
            warnings.extend(_validate_selects(sel.select, f"{current_path}.select"))

        # Recursively validate unionAll
        if sel.unionAll:
            warnings.extend(_validate_selects(sel.unionAll, f"{current_path}.unionAll"))

    return warnings


def collect_column_names(select: List[Select]) -> List[str]:
    """Collect all column names from a list of Select structures.

    Recursively traverses the select structure to find all column names,
    including those in nested selects and unionAll branches.

    Args:
        select: List of Select structures to process

    Returns:
        List of all column names found (may include duplicates)
    """
    names = []

    for sel in select:
        # Add column names from this select
        for col in sel.column:
            names.append(col.name)

        # Recursively collect from nested selects
        names.extend(collect_column_names(sel.select))

        # Recursively collect from unionAll branches
        names.extend(collect_column_names(sel.unionAll))

    return names


# Convenience function to load from file
def load_view_definition(file_path: str) -> ViewDefinition:
    """Load a ViewDefinition from a JSON file.

    Args:
        file_path: Path to JSON file containing a ViewDefinition

    Returns:
        ViewDefinition dataclass instance

    Raises:
        FileNotFoundError: If file doesn't exist
        ParseError: If JSON is invalid or required fields are missing
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return parse_view_definition(f.read())
