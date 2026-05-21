"""
SQL-on-FHIR v2 type definitions.

NOTE: The canonical dataclass definitions used at runtime are in parser.py.
These types provide enum-based validation (ColumnType, JoinType) and are
used for type checking and public API exports. For new code, prefer
importing from parser.py for dataclasses and from types.py for enums.
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import date
from decimal import Decimal
import re
import math
import base64
import binascii
from typing import Any, Dict, List, Optional

from .metadata import (
    KNOWN_FHIR_RESOURCE_TYPES,
    PUBLICATION_STATUS_CODES,
    SHAREABLE_VIEWDEFINITION_PROFILE,
    TABULAR_VIEWDEFINITION_PROFILE,
    VIEWDEFINITION_RESOURCE_TYPE,
)


SQL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
CONSTANT_NAME_RE = SQL_NAME_RE
FHIR_STRUCTURE_DEFINITION_PREFIX = "http://hl7.org/fhir/StructureDefinition/"


def validate_sql_name(value: Any, field_name: str) -> str:
    """Validate a SQL-on-FHIR sql-name field and return it."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    if not SQL_NAME_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} {value!r} violates sql-name invariant "
            "^[A-Za-z][A-Za-z0-9_]*$"
        )
    return value


def validate_required_string(value: Any, field_name: str) -> str:
    """Validate a required non-empty string field and return it."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def validate_optional_markdown(value: Any, field_name: str) -> Optional[str]:
    """Validate an optional markdown/string metadata field and return it."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a markdown string")
    return value


def validate_optional_boolean(value: Any, field_name: str) -> bool:
    """Validate an optional boolean field that has already been defaulted."""
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a JSON boolean")
    return value


def validate_optional_fhirpath_string(value: Any, field_name: str) -> Optional[str]:
    """Validate an optional FHIRPath string field and return it."""
    if value is None:
        return None
    return validate_required_string(value, field_name)


def validate_optional_uri_string(value: Any, field_name: str) -> Optional[str]:
    """Validate an optional URI string field and return it."""
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty URI string")
    if not _URI_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a valid URI string")
    return value


def validate_repeat_paths(value: Any, field_name: str) -> Optional[List[str]]:
    """Validate a repeating string FHIRPath field used by Select.repeat."""
    if value is None:
        raise ValueError(f"{field_name} must be an array of non-empty strings")
    if isinstance(value, str):
        raise ValueError(f"{field_name} must be an array of non-empty strings")
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array of non-empty strings")
    for item in value:
        validate_required_string(item, field_name)
    return list(value)


def validate_where_conditions(value: Any, field_name: str) -> List[Dict[str, Any]]:
    """Validate and normalize SQL-on-FHIR where condition objects.

    A where condition is either the public convenience string form or an object
    with a non-empty string ``path`` predicate.
    """
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, dict):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        raise ValueError(
            f"{field_name} must be a string, object, or array of strings/objects"
        )

    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        item_name = f"{field_name}[{index}]"
        if isinstance(item, str):
            normalized.append({
                "path": validate_required_string(item, f"{item_name}.path")
            })
            continue
        if isinstance(item, dict):
            if "path" not in item:
                raise ValueError(f"{item_name} must include a 'path' field")
            path = validate_required_string(item.get("path"), f"{item_name}.path")
            condition = dict(item)
            condition["path"] = path
            if "description" in condition:
                if condition["description"] is None:
                    raise ValueError(f"{item_name}.description must be a markdown string")
                condition["description"] = validate_optional_markdown(
                    condition["description"],
                    f"{item_name}.description",
                )
            normalized.append(condition)
            continue
        raise ValueError(
            f"{item_name} must be a string or object, got {type(item).__name__}"
        )
    return normalized


def validate_column_fields(
    path: Any,
    name: Any,
    description: Any = None,
) -> tuple[str, str, Optional[str]]:
    """Validate ViewDefinition.select.column primitive fields."""
    return (
        validate_required_string(path, "Column.path"),
        validate_sql_name(name, "Column.name"),
        validate_optional_markdown(description, "Column.description"),
    )

CONSTANT_VALUE_FIELD_TYPES = {
    "valueBase64Binary": "base64Binary",
    "valueBoolean": "boolean",
    "valueCanonical": "canonical",
    "valueCode": "code",
    "valueDate": "date",
    "valueDateTime": "dateTime",
    "valueDecimal": "decimal",
    "valueId": "id",
    "valueInstant": "instant",
    "valueInteger": "integer",
    "valueInteger64": "integer64",
    "valueOid": "oid",
    "valueString": "string",
    "valuePositiveInt": "positiveInt",
    "valueTime": "time",
    "valueUnsignedInt": "unsignedInt",
    "valueUri": "uri",
    "valueUrl": "url",
    "valueUuid": "uuid",
}


_BASE64_RE = re.compile(r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$")
_CODE_RE = re.compile(r"^[^\s]+(?: [^\s]+)*$")
_ID_RE = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")
_OID_RE = re.compile(r"^urn:oid:[0-2](?:\.(?:0|[1-9][0-9]*))+$")
_UUID_RE = re.compile(r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_URI_RE = re.compile(r"^\S*$")
_TIME_RE = re.compile(r"^(?P<hour>[01][0-9]|2[0-3]):(?P<minute>[0-5][0-9]):(?P<second>[0-5][0-9]|60)(?:\.[0-9]{1,9})?$")
_DATE_PART_RE = re.compile(r"^(?P<year>[1-9][0-9]{3})(?:-(?P<month>0[1-9]|1[0-2])(?:-(?P<day>0[1-9]|[12][0-9]|3[01]))?)?$")
_DATETIME_RE = re.compile(
    r"^(?P<date>[1-9][0-9]{3}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12][0-9]|3[01]))?)?)"
    r"(?:T(?P<time>(?:[01][0-9]|2[0-3]):[0-5][0-9]:(?:[0-5][0-9]|60)(?:\.[0-9]{1,9})?)"
    r"(?P<tz>Z|[+-](?:(?:0[0-9]|1[0-3]):[0-5][0-9]|14:00)))?$"
)


def _validate_partial_date(value: str, field_name: str) -> None:
    match = _DATE_PART_RE.fullmatch(value)
    if not match:
        raise ValueError(f"{field_name} must be a valid FHIR date")
    month = match.group("month")
    day = match.group("day")
    if month and day:
        try:
            date(int(match.group("year")), int(month), int(day))
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a valid calendar date") from exc


def _validate_primitive_value(field_name: str, value: Any, value_type: str) -> None:
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{field_name} must be a JSON boolean")
        return

    if value_type in {"integer", "positiveInt", "unsignedInt"}:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{field_name} must be a JSON integer")
        min_value, max_value = {
            "integer": (-2147483648, 2147483647),
            "positiveInt": (1, 2147483647),
            "unsignedInt": (0, 2147483647),
        }[value_type]
        if not min_value <= value <= max_value:
            raise ValueError(f"{field_name} must be in range {min_value}..{max_value}")
        return

    if value_type == "integer64":
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a JSON string containing a 64-bit integer")
        text = value
        if not re.fullmatch(r"0|[-+]?[1-9][0-9]*", text):
            raise ValueError(f"{field_name} must be a valid FHIR integer64")
        parsed = int(text)
        if not -9223372036854775808 <= parsed <= 9223372036854775807:
            raise ValueError(f"{field_name} must be in range -9223372036854775808..9223372036854775807")
        return

    if value_type == "decimal":
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError(f"{field_name} must be a JSON number")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{field_name} must be finite")
        return

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a JSON string")

    if value_type == "base64Binary":
        if not _BASE64_RE.fullmatch(value):
            raise ValueError(f"{field_name} must be valid base64Binary")
        try:
            base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"{field_name} must be valid base64Binary") from exc
    elif value_type == "canonical":
        if not _URI_RE.fullmatch(value):
            raise ValueError(f"{field_name} must be a valid canonical URI string")
    elif value_type == "code":
        if not _CODE_RE.fullmatch(value):
            raise ValueError(f"{field_name} must be a valid FHIR code")
    elif value_type == "date":
        _validate_partial_date(value, field_name)
    elif value_type == "dateTime":
        match = _DATETIME_RE.fullmatch(value)
        if not match:
            raise ValueError(f"{field_name} must be a valid FHIR dateTime")
        _validate_partial_date(match.group("date"), field_name)
    elif value_type == "id":
        if not _ID_RE.fullmatch(value):
            raise ValueError(f"{field_name} must be a valid FHIR id")
    elif value_type == "instant":
        match = _DATETIME_RE.fullmatch(value)
        if not match or not match.group("time") or not match.group("tz"):
            raise ValueError(f"{field_name} must be a valid FHIR instant with timezone")
        _validate_partial_date(match.group("date"), field_name)
    elif value_type == "oid":
        if not _OID_RE.fullmatch(value):
            raise ValueError(f"{field_name} must be a valid FHIR oid")
    elif value_type == "string":
        if value == "" or len(value) > 1024 * 1024:
            raise ValueError(f"{field_name} must be a non-empty FHIR string of at most 1048576 characters")
    elif value_type == "time":
        if not _TIME_RE.fullmatch(value):
            raise ValueError(f"{field_name} must be a valid FHIR time")
    elif value_type in {"uri", "url"}:
        if not _URI_RE.fullmatch(value):
            raise ValueError(f"{field_name} must be a valid FHIR {value_type}")
    elif value_type == "uuid":
        if not _UUID_RE.fullmatch(value):
            raise ValueError(f"{field_name} must be a valid FHIR uuid")


def _extract_constant_value(data: Dict[str, Any]) -> tuple[Any, str]:
    value_fields = [key for key in data if key.startswith("value") and key != "value_type"]
    if not value_fields:
        raise ValueError(
            "Constant has no value. A constant must include exactly one typed "
            "value[x] property (e.g., valueString, valueInteger)."
        )

    unsupported = [key for key in value_fields if key not in CONSTANT_VALUE_FIELD_TYPES]
    if unsupported:
        supported = ", ".join(CONSTANT_VALUE_FIELD_TYPES)
        raise ValueError(
            f"Unsupported constant value[x] field(s): {', '.join(unsupported)}. "
            f"Supported fields are: {supported}."
        )

    if len(value_fields) != 1:
        raise ValueError(
            f"Constant must include exactly one value[x] field, got {len(value_fields)}: "
            f"{', '.join(value_fields)}."
        )

    field_name = value_fields[0]
    value = data[field_name]
    if value is None:
        raise ValueError(f"Constant {field_name} must not be null")
    value_type = CONSTANT_VALUE_FIELD_TYPES[field_name]
    _validate_primitive_value(field_name, value, value_type)
    return value, value_type


class ColumnType(Enum):
    """Supported column types in SQL-on-FHIR v2.

    Includes FHIR primitive types that map to SQL STRING (id, uri, url, etc.)
    per the SQL-on-FHIR v2 specification.
    """

    STRING = "string"
    INTEGER = "integer"
    INTEGER64 = "integer64"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "dateTime"
    TIME = "time"
    CODE = "code"
    CODING = "Coding"
    CODEABLE_CONCEPT = "CodeableConcept"
    # FHIR string-like types (all map to SQL VARCHAR/STRING)
    ID = "id"
    URI = "uri"
    URL = "url"
    CANONICAL = "canonical"
    OID = "oid"
    UUID = "uuid"
    MARKDOWN = "markdown"
    BASE64BINARY = "base64Binary"
    INSTANT = "instant"
    # FHIR numeric types
    POSITIVE_INT = "positiveInt"
    UNSIGNED_INT = "unsignedInt"
    # Common non-primitive FHIR datatypes supported by the JSON UDF path.
    QUANTITY = "Quantity"

    @classmethod
    def normalize_name(cls, type_str: Optional[str]) -> Optional[str]:
        """Normalize relative/full FHIR StructureDefinition URIs to type names."""
        if type_str is None:
            return None
        validate_optional_uri_string(type_str, "Column.type")
        if type_str.startswith(FHIR_STRUCTURE_DEFINITION_PREFIX):
            normalized = type_str[len(FHIR_STRUCTURE_DEFINITION_PREFIX):]
            if "#" in normalized:
                _, fragment = normalized.split("#", 1)
                if fragment:
                    return fragment
            return normalized
        return type_str

    @classmethod
    def from_string(cls, type_str: Optional[str]) -> "ColumnType | str | None":
        """Convert supported type strings/URIs to ColumnType, preserving unknown URIs."""
        normalized = cls.normalize_name(type_str)
        if normalized is None:
            return None
        try:
            return cls(normalized)
        except ValueError:
            return normalized


class JoinType(Enum):
    """Supported join types in SQL-on-FHIR v2."""

    INNER = "inner"
    LEFT = "left"
    RIGHT = "right"
    FULL = "full"

    @classmethod
    def from_string(cls, type_str: str) -> "JoinType":
        """Convert string to JoinType.

        Raises ValueError for unrecognised join types. Valid values are:
        'inner', 'left', 'right', 'full'.
        """
        try:
            return cls(type_str.lower())
        except ValueError:
            valid = ", ".join(f"'{m.value}'" for m in cls)
            raise ValueError(
                f"Unknown join type '{type_str}'. Valid values are: {valid}."
            ) from None


@dataclass
class ColumnTag:
    """Additional metadata attached to a ViewDefinition column."""

    name: str
    value: str

    def __post_init__(self) -> None:
        validate_required_string(self.name, "Column.tag.name")
        validate_required_string(self.value, "Column.tag.value")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ColumnTag":
        if not isinstance(data, dict):
            raise ValueError(f"Column.tag item must be a JSON object, got {type(data).__name__}")
        return cls(
            name=validate_required_string(data.get("name"), "Column.tag.name"),
            value=validate_required_string(data.get("value"), "Column.tag.value"),
        )

    def to_dict(self) -> Dict[str, str]:
        return {"name": self.name, "value": self.value}


@dataclass
class Column:
    """Represents a column in a ViewDefinition.

    Attributes:
        path: FHIRPath expression to extract the column value.
        name: Name of the column in the output SQL.
        type: Optional FHIR StructureDefinition URI/type hint for the column.
        collection: Whether this column contains multiple values.
        description: Optional human-readable description.
    """

    path: str
    name: str
    type: ColumnType | str | None = None
    collection: bool = False
    description: Optional[str] = None
    tag: List[ColumnTag] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Convert string type/tag dictionaries to structured values if needed."""
        if isinstance(self.type, str):
            self.type = ColumnType.from_string(self.type)
        elif self.type is not None and not isinstance(self.type, ColumnType):
            raise ValueError("Column.type must be a URI string")

        if self.tag is None or not isinstance(self.tag, list):
            raise ValueError("Column.tag must be an array of tag objects")
        converted_tags: List[ColumnTag] = []
        for item in self.tag:
            if isinstance(item, ColumnTag):
                converted_tags.append(item)
            elif isinstance(item, dict):
                converted_tags.append(ColumnTag.from_dict(item))
            else:
                raise ValueError(
                    f"Column.tag item must be a JSON object, got {type(item).__name__}"
                )
        self.tag = converted_tags

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "path": self.path,
            "name": self.name,
        }
        if self.type is not None:
            data["type"] = self.type.value if isinstance(self.type, ColumnType) else self.type
        if self.collection:
            data["collection"] = self.collection
        if self.description is not None:
            data["description"] = self.description
        if self.tag:
            data["tag"] = [tag.to_dict() for tag in self.tag]
        return data


@dataclass
class Select:
    """Represents a select structure in a ViewDefinition.

    A select can contain columns, nested selects, forEach iteration,
    unionAll for combining results, where filters, and repeat traversal.

    Attributes:
        column: List of column definitions.
        select: List of nested select structures.
        forEach: FHIRPath expression for iteration (INNER JOIN behavior).
        forEachOrNull: FHIRPath expression for iteration (LEFT JOIN behavior).
        unionAll: List of select structures to union.
        where: List of filter conditions.
        repeat: List of FHIRPath expressions for recursive traversal
            (SQL-on-FHIR v2 §Select.repeat).
    """

    column: List[Column] = field(default_factory=list)
    select: List["Select"] = field(default_factory=list)
    forEach: Optional[str] = None
    forEachOrNull: Optional[str] = None
    unionAll: List["Select"] = field(default_factory=list)
    where: List[Dict[str, str]] = field(default_factory=list)
    repeat: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if self.column:
            data["column"] = [column.to_dict() for column in self.column]
        if self.select:
            data["select"] = [select.to_dict() for select in self.select]
        if self.forEach is not None:
            data["forEach"] = self.forEach
        if self.forEachOrNull is not None:
            data["forEachOrNull"] = self.forEachOrNull
        if self.unionAll:
            data["unionAll"] = [select.to_dict() for select in self.unionAll]
        if self.where:
            data["where"] = [dict(condition) for condition in self.where]
        if self.repeat is not None:
            data["repeat"] = list(self.repeat)
        return data


@dataclass
class Constant:
    """Represents a constant definition in a ViewDefinition.

    Constants can be simple values (strings, codes) or complex
    FHIR types (Coding, CodeableConcept).

    Attributes:
        name: Name of the constant for reference.
        value: The constant value (string, code, Coding, CodeableConcept, etc.).
        value_type: The type of the constant value.
    """

    name: str
    value: Any
    value_type: Optional[str] = None

    # Convenience properties for type-specific access (matching spec naming)
    @property
    def valueString(self) -> Optional[str]:
        """Get value as string if this is a string constant."""
        return self.value if self.value_type == "string" else None

    @property
    def valueCode(self) -> Optional[str]:
        """Get value as code if this is a code constant."""
        return self.value if self.value_type == "code" else None

    @property
    def valueInteger(self) -> Optional[int]:
        """Get value as integer if this is an integer constant."""
        return self.value if self.value_type == "integer" else None

    @property
    def valueDecimal(self) -> Optional[float]:
        """Get value as decimal if this is a decimal constant."""
        return self.value if self.value_type == "decimal" else None

    @property
    def valueBoolean(self) -> Optional[bool]:
        """Get value as boolean if this is a boolean constant."""
        return self.value if self.value_type == "boolean" else None

    @property
    def valueCanonical(self) -> Optional[str]:
        """Get value as canonical if this is a canonical constant."""
        return self.value if self.value_type == "canonical" else None

    @property
    def valueDate(self) -> Optional[str]:
        """Get value as date if this is a date constant."""
        return self.value if self.value_type == "date" else None

    @property
    def valueDateTime(self) -> Optional[str]:
        """Get value as dateTime if this is a dateTime constant."""
        return self.value if self.value_type == "dateTime" else None

    @property
    def valueTime(self) -> Optional[str]:
        """Get value as time if this is a time constant."""
        return self.value if self.value_type == "time" else None

    @property
    def valueInstant(self) -> Optional[str]:
        """Get value as instant if this is an instant constant."""
        return self.value if self.value_type == "instant" else None

    @property
    def valueInteger64(self) -> Optional[str]:
        """Get value as integer64 if this is an integer64 constant."""
        return self.value if self.value_type == "integer64" else None

    @property
    def valueUri(self) -> Optional[str]:
        """Get value as uri if this is a uri constant."""
        return self.value if self.value_type == "uri" else None

    @property
    def valueUrl(self) -> Optional[str]:
        """Get value as url if this is a url constant."""
        return self.value if self.value_type == "url" else None

    @property
    def valueUuid(self) -> Optional[str]:
        """Get value as uuid if this is a uuid constant."""
        return self.value if self.value_type == "uuid" else None

    @property
    def valueOid(self) -> Optional[str]:
        """Get value as oid if this is an oid constant."""
        return self.value if self.value_type == "oid" else None

    @property
    def valueBase64Binary(self) -> Optional[str]:
        """Get value as base64Binary if this is a base64Binary constant."""
        return self.value if self.value_type == "base64Binary" else None

    @property
    def valueId(self) -> Optional[str]:
        """Get value as id if this is an id constant."""
        return self.value if self.value_type == "id" else None

    @property
    def valuePositiveInt(self) -> Optional[int]:
        """Get value as positiveInt if this is a positiveInt constant."""
        return self.value if self.value_type == "positiveInt" else None

    @property
    def valueUnsignedInt(self) -> Optional[int]:
        """Get value as unsignedInt if this is an unsignedInt constant."""
        return self.value if self.value_type == "unsignedInt" else None

    @property
    def valueCoding(self) -> Optional[Dict[str, Any]]:
        """Get value as Coding if this is a Coding constant."""
        return self.value if self.value_type == "Coding" else None

    @property
    def valueCodeableConcept(self) -> Optional[Dict[str, Any]]:
        """Get value as CodeableConcept if this is a CodeableConcept constant."""
        return self.value if self.value_type == "CodeableConcept" else None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Constant":
        """Create a Constant from a dictionary representation.

        Handles the various value* fields in the SQL-on-FHIR spec:
        - FHIR primitive choices such as valueString, valueCode,
          valueCanonical, and valueInteger64.
        """
        name = data.get("name", "")
        if not name:
            raise ValueError(f"Constant missing required 'name' field: {data}")
        validate_sql_name(name, "Constant.name")

        value, value_type = _extract_constant_value(data)
        return cls(name=name, value=value, value_type=value_type)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"name": self.name}
        for field_name, value_type in CONSTANT_VALUE_FIELD_TYPES.items():
            if value_type == self.value_type:
                data[field_name] = self.value
                return data
        if self.value_type:
            raise ValueError(f"Unsupported Constant.value_type {self.value_type!r}")
        raise ValueError("Constant.value_type is required for JSON serialization")


@dataclass
class Join:
    """Represents a join definition in a ViewDefinition.

    Joins allow linking resources based on FHIRPath expressions.

    Attributes:
        name: Name for the joined resource (used as table alias).
        resource: The FHIR resource type to join.
        on: List of FHIRPath expressions for join conditions.
        type: The type of join (inner, left, right, full).
    """

    name: str
    resource: str
    on: List[Dict[str, str]] = field(default_factory=list)
    type: JoinType = JoinType.INNER

    def __post_init__(self) -> None:
        """Validate public join construction and convert string type values."""
        validate_sql_name(self.name, "Join.name")
        if not isinstance(self.resource, str) or not self.resource:
            raise ValueError("Join.resource must be a non-empty FHIR ResourceType string")
        if self.resource not in KNOWN_FHIR_RESOURCE_TYPES:
            raise ValueError(
                f"Join.resource {self.resource!r} is not in the required ResourceType binding"
            )
        if isinstance(self.type, str):
            self.type = JoinType.from_string(self.type)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "resource": self.resource,
            "on": [dict(condition) for condition in self.on],
            "type": self.type.value if isinstance(self.type, JoinType) else self.type,
        }


@dataclass
class ViewDefinition:
    """Complete SQL-on-FHIR v2 ViewDefinition.

    This is the root structure that defines how to transform
    a FHIR resource into a SQL view.

    Attributes:
        resource: The FHIR resource type.
        profile: FHIR profile canonical URLs the view was intended for.
        fhirVersion: FHIR version codes the view was intended for.
        select: List of select structures defining the columns.
        name: Optional name for the view.
        description: Optional human-readable description.
        constants: List of constant definitions.
        joins: List of join definitions.
        where: List of filter conditions applied to the root.
    """

    resource: str
    select: List[Select] = field(default_factory=list)
    resourceType: Optional[str] = None
    id: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
    url: Optional[str] = None
    version: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    profile: List[str] = field(default_factory=list)
    fhirVersion: List[str] = field(default_factory=list)
    constants: List[Constant] = field(default_factory=list)
    joins: List[Join] = field(default_factory=list)
    where: List[Dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ViewDefinition":
        """Create a ViewDefinition from a dictionary representation.

        This is a convenience method for parsing JSON ViewDefinitions.
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"ViewDefinition.from_dict expects a dictionary, got {type(data).__name__}"
            )
        try:
            from .parser import parse_view_definition

            return parse_view_definition(data)
        except Exception as exc:
            raise ValueError(str(exc)) from exc

    def declared_profile_urls(self) -> set[str]:
        profiles: set[str] = set()
        if isinstance(self.meta, dict):
            raw_profiles = self.meta.get("profile", [])
            if isinstance(raw_profiles, list):
                profiles.update(
                    item.split("|", 1)[0]
                    for item in raw_profiles
                    if isinstance(item, str) and item
                )
        return profiles

    def has_profile(self, profile_url: str) -> bool:
        return profile_url in self.declared_profile_urls()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize using SQL-on-FHIR logical-model JSON field names."""
        data: Dict[str, Any] = {}
        if self.resourceType is not None:
            data["resourceType"] = self.resourceType
        if self.id is not None:
            data["id"] = self.id
        if self.meta is not None:
            data["meta"] = dict(self.meta)
        if self.url is not None:
            data["url"] = self.url
        if self.version is not None:
            data["version"] = self.version
        if self.name is not None:
            data["name"] = self.name
        if self.status is not None:
            data["status"] = self.status
        if self.title is not None:
            data["title"] = self.title
        if self.description is not None:
            data["description"] = self.description
        data["resource"] = self.resource
        if self.profile:
            data["profile"] = list(self.profile)
        if self.fhirVersion:
            data["fhirVersion"] = list(self.fhirVersion)
        if self.constants:
            data["constant"] = [constant.to_dict() for constant in self.constants]
        data["select"] = [select.to_dict() for select in self.select]
        if self.joins:
            data["joins"] = [join.to_dict() for join in self.joins]
        if self.where:
            data["where"] = [dict(condition) for condition in self.where]
        return data


TABULAR_PRIMITIVE_TYPE_NAMES = frozenset({
    "base64Binary",
    "boolean",
    "canonical",
    "code",
    "dateTime",
    "decimal",
    "id",
    "instant",
    "integer",
    "integer64",
    "markdown",
    "oid",
    "positiveInt",
    "string",
    "time",
    "unsignedInt",
    "url",
    "uuid",
})


def _column_type_to_string(type_value: ColumnType | str | None) -> str | None:
    if isinstance(type_value, ColumnType):
        return type_value.value
    return type_value


def _iter_select_columns(selects: List[Select]):
    for select in selects:
        for column in select.column:
            yield column
        yield from _iter_select_columns(select.select)
        yield from _iter_select_columns(select.unionAll)


def validate_root_metadata_fields(
    *,
    resourceType: Any = None,
    id: Any = None,
    meta: Any = None,
    url: Any = None,
    version: Any = None,
    status: Any = None,
    title: Any = None,
    description: Any = None,
) -> tuple[
    Optional[str],
    Optional[str],
    Optional[Dict[str, Any]],
    Optional[str],
    Optional[str],
    Optional[str],
    Optional[str],
    Optional[str],
]:
    if resourceType is not None:
        resourceType = validate_optional_uri_string(resourceType, "ViewDefinition.resourceType")
        if resourceType != VIEWDEFINITION_RESOURCE_TYPE:
            raise ValueError(
                "ViewDefinition.resourceType must be "
                f"{VIEWDEFINITION_RESOURCE_TYPE!r} when present"
            )
    if id is not None:
        _validate_primitive_value("ViewDefinition.id", id, "id")
    if meta is not None:
        if not isinstance(meta, dict):
            raise ValueError("ViewDefinition.meta must be a JSON object")
        if "profile" in meta:
            raw_profile = meta["profile"]
            if raw_profile is None or not isinstance(raw_profile, list):
                raise ValueError("ViewDefinition.meta.profile must be an array of canonical strings")
            if not all(isinstance(item, str) and item for item in raw_profile):
                raise ValueError("ViewDefinition.meta.profile must contain only non-empty canonical strings")
        meta = dict(meta)
    if url is not None:
        url = validate_optional_uri_string(url, "ViewDefinition.url")
    if version is not None:
        version = validate_required_string(version, "ViewDefinition.version")
    if status is not None:
        status = validate_required_string(status, "ViewDefinition.status")
        if status not in PUBLICATION_STATUS_CODES:
            raise ValueError("ViewDefinition.status must be a PublicationStatus code")
    if title is not None:
        title = validate_required_string(title, "ViewDefinition.title")
    description = validate_optional_markdown(description, "ViewDefinition.description")
    return resourceType, id, meta, url, version, status, title, description


def validate_supported_view_profiles(view_definition: ViewDefinition) -> None:
    """Validate profile constraints supported by this implementation."""
    if view_definition.has_profile(SHAREABLE_VIEWDEFINITION_PROFILE):
        if not view_definition.url:
            raise ValueError("ShareableViewDefinition requires ViewDefinition.url")
        if not view_definition.name:
            raise ValueError("ShareableViewDefinition requires ViewDefinition.name")
        if not view_definition.fhirVersion:
            raise ValueError("ShareableViewDefinition requires ViewDefinition.fhirVersion")
        for column in _iter_select_columns(view_definition.select):
            if _column_type_to_string(column.type) is None:
                raise ValueError(
                    f"ShareableViewDefinition requires Column.type for column {column.name!r}"
                )

    if view_definition.has_profile(TABULAR_VIEWDEFINITION_PROFILE):
        for column in _iter_select_columns(view_definition.select):
            if column.collection:
                raise ValueError(
                    f"TabularViewDefinition forbids collection columns; "
                    f"column {column.name!r} has collection=true"
                )
            column_type = _column_type_to_string(column.type)
            if column_type not in TABULAR_PRIMITIVE_TYPE_NAMES:
                raise ValueError(
                    f"TabularViewDefinition column {column.name!r} must declare "
                    "one of the profile's primitive column types"
                )
