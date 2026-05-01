"""
SQL-on-FHIR v2 type definitions.

NOTE: The canonical dataclass definitions used at runtime are in parser.py.
These types provide enum-based validation (ColumnType, JoinType) and are
used for type checking and public API exports. For new code, prefer
importing from parser.py for dataclasses and from types.py for enums.
"""

import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class ColumnType(Enum):
    """Supported column types in SQL-on-FHIR v2.

    Includes FHIR primitive types that map to SQL STRING (id, uri, url, etc.)
    per the SQL-on-FHIR v2 specification.
    """

    STRING = "string"
    INTEGER = "integer"
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

    @classmethod
    def from_string(cls, type_str: Optional[str]) -> "ColumnType":
        """Convert string to ColumnType, defaults to STRING if None."""
        if type_str is None:
            return cls.STRING
        try:
            return cls(type_str)
        except ValueError:
            warnings.warn(f"Unknown column type '{type_str}', defaulting to STRING", stacklevel=2)
            return cls.STRING


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
class Column:
    """Represents a column in a ViewDefinition.

    Attributes:
        path: FHIRPath expression to extract the column value.
        name: Name of the column in the output SQL.
        type: Optional type hint for the column (string, integer, etc.).
        collection: Whether this column contains multiple values.
        description: Optional human-readable description.
    """

    path: str
    name: str
    type: Optional[ColumnType] = None
    collection: bool = False
    description: Optional[str] = None

    def __post_init__(self) -> None:
        """Convert string type to ColumnType enum if needed."""
        if isinstance(self.type, str):
            self.type = ColumnType.from_string(self.type)


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
        - valueString
        - valueCode
        - valueCoding
        - valueCodeableConcept
        """
        name = data.get("name", "")
        value_type = None
        value = None

        # Check for various value types in order of specificity.
        # Must stay in sync with parser.py:_parse_constant().
        value_fields = [
            ("valueCodeableConcept", "CodeableConcept"),
            ("valueCoding", "Coding"),
            ("valueCode", "code"),
            ("valueString", "string"),
            ("valueInteger", "integer"),
            ("valueDecimal", "decimal"),
            ("valueBoolean", "boolean"),
            ("valueDate", "date"),
            ("valueDateTime", "dateTime"),
            ("valueTime", "time"),
            ("valueInstant", "instant"),
            ("valueUri", "uri"),
            ("valueUrl", "url"),
            ("valueUuid", "uuid"),
            ("valueOid", "oid"),
            ("valueBase64Binary", "base64Binary"),
            ("valueId", "id"),
            ("valuePositiveInt", "positiveInt"),
            ("valueUnsignedInt", "unsignedInt"),
        ]

        for field_name, vtype in value_fields:
            if field_name in data:
                value = data[field_name]
                value_type = vtype
                break

        return cls(name=name, value=value, value_type=value_type)


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
        """Convert string type to JoinType enum if needed."""
        if isinstance(self.type, str):
            self.type = JoinType.from_string(self.type)


@dataclass
class ViewDefinition:
    """Complete SQL-on-FHIR v2 ViewDefinition.

    This is the root structure that defines how to transform
    a FHIR resource into a SQL view.

    Attributes:
        resource: The FHIR resource type (string), or a list of types
            for multi-resource union ViewDefinitions.
        select: List of select structures defining the columns.
        name: Optional name for the view.
        description: Optional human-readable description.
        constants: List of constant definitions.
        joins: List of join definitions.
        where: List of filter conditions applied to the root.
    """

    resource: Union[str, List[str]]
    select: List[Select] = field(default_factory=list)
    name: Optional[str] = None
    description: Optional[str] = None
    constants: List[Constant] = field(default_factory=list)
    joins: List[Join] = field(default_factory=list)
    where: List[Dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ViewDefinition":
        """Create a ViewDefinition from a dictionary representation.

        This is a convenience method for parsing JSON ViewDefinitions.
        """
        resource = data.get("resource", "")
        name = data.get("name")
        description = data.get("description")

        # Parse constants
        constants = [
            Constant.from_dict(c) if isinstance(c, dict) else c
            for c in data.get("constants", [])
        ]

        # Parse joins
        joins = [
            Join(**j) if isinstance(j, dict) else j
            for j in data.get("joins", [])
        ]

        # Parse selects recursively
        def parse_select(s: Dict[str, Any]) -> Select:
            columns = [
                Column(**c) if isinstance(c, dict) else c
                for c in s.get("column", [])
            ]
            nested = [parse_select(ns) for ns in s.get("select", [])]
            union_all = [parse_select(u) for u in s.get("unionAll", [])]

            return Select(
                column=columns,
                select=nested,
                forEach=s.get("forEach"),
                forEachOrNull=s.get("forEachOrNull"),
                unionAll=union_all,
                where=s.get("where", []),
            )

        selects = [parse_select(s) for s in data.get("select", [])]
        where = data.get("where", [])

        return cls(
            resource=resource,
            select=selects,
            name=name,
            description=description,
            constants=constants,
            joins=joins,
            where=where,
        )
