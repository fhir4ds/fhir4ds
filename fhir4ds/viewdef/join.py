"""
JOIN generation for SQL-on-FHIR v2 ViewDefinitions.

Generates SQL JOIN clauses from ViewDefinition join specifications.
"""

import logging
from typing import List, Dict
from .parser import Join
from .utils import pluralize_resource

_logger = logging.getLogger(__name__)


# Valid join types per SQL-on-FHIR spec
VALID_JOIN_TYPES = frozenset(['inner', 'left', 'right', 'full'])


def resource_to_table_name(resource: str) -> str:
    """Convert a FHIR resource type to its table name.

    FHIR resource types (e.g., 'Patient', 'Observation') are stored
    in tables with lowercase plural names (e.g., 'patients', 'observations').

    Args:
        resource: FHIR resource type name (e.g., 'Patient', 'Observation')

    Returns:
        Lowercase plural table name
    """
    return pluralize_resource(resource)


def generate_on_condition(
    on_clauses: List[Dict[str, str]],
    left_alias: str,
    right_alias: str
) -> str:
    """Generate the ON condition for a JOIN.

    Creates SQL expressions that compare FHIRPath values between two resources.
    Each pair of paths in the on_clauses list forms an equality condition.

    Args:
        on_clauses: List of {path: "..."} dicts containing FHIRPath expressions.
                    Typically pairs of paths - one for left side, one for right.
        left_alias: SQL alias for the left/base table (e.g., 't')
        right_alias: SQL alias for the right/joined table (e.g., 'patient')

    Returns:
        SQL ON condition string

    Example:
        >>> on_clauses = [
        ...     {"path": "subject.reference"},
        ...     {"path": "'Patient/' + id"}
        ... ]
        >>> generate_on_condition(on_clauses, 't', 'patient')
        "fhirpath_text(t.resource, 'subject.reference') =\\n    fhirpath_text(patient.resource, \\'Patient/' + id\\')"
    """
    if not on_clauses:
        raise ValueError("JOIN requires at least one ON clause")

    # Extract paths from on_clauses
    paths = [clause.get('path', '') for clause in on_clauses]

    # If we have pairs of paths, create equality conditions
    if len(paths) >= 2:
        # Take pairs: first path is left side, second is right side
        left_path = paths[0].replace("'", "''")
        right_path = paths[1].replace("'", "''")

        # Generate FHIRPath expressions for both sides
        left_expr = f"fhirpath_text({left_alias}.resource, '{left_path}')"
        right_expr = f"fhirpath_text({right_alias}.resource, '{right_path}')"

        return f"{left_expr} =\n    {right_expr}"

    # Single path: just generate the expression
    if len(paths) == 1:
        escaped_path = paths[0].replace("'", "''")
        return f"fhirpath_text({left_alias}.resource, '{escaped_path}')"

    return "TRUE"  # Unreachable after validation above, but required by the spec
    # for degenerate cases where paths list is somehow non-empty but all empty strings


def generate_join(join: Join, base_alias: str) -> str:
    """Generate a SQL JOIN clause from a Join definition.

    Creates a JOIN statement that links the base resource to another
    FHIR resource based on FHIRPath expressions.

    Args:
        join: Join dataclass with name, resource, on, and type fields
        base_alias: SQL alias for the base/left table (e.g., 't')

    Returns:
        Complete JOIN clause string

    Raises:
        ValueError: If join type is invalid

    Example:
        >>> from fhir4ds.viewdef.parser import Join
        >>> join = Join(
        ...     name="patient",
        ...     resource="Patient",
        ...     on=[
        ...         {"path": "subject.reference"},
        ...         {"path": "'Patient/' + id"}
        ...     ],
        ...     type="inner"
        ... )
        >>> generate_join(join, 't')
        "JOIN patients patient ON\\n    fhirpath_text(t.resource, 'subject.reference') =\\n    fhirpath_text(patient.resource, \\'Patient/' + id\\')"
    """
    # Validate join type
    join_type_raw = join.type
    if hasattr(join_type_raw, 'value'):
        join_type = join_type_raw.value
    else:
        join_type = join_type_raw.lower() if join_type_raw else 'inner'
    if join_type not in VALID_JOIN_TYPES:
        raise ValueError(
            f"Invalid join type '{join.type}'. "
            f"Must be one of: {', '.join(sorted(VALID_JOIN_TYPES))}"
        )

    # Get table name from resource type
    table_name = resource_to_table_name(join.resource)

    # Generate ON condition
    on_condition = generate_on_condition(join.on, base_alias, join.name)

    # Build the JOIN clause
    # SQL join type keywords
    join_keyword = {
        'inner': 'JOIN',
        'left': 'LEFT JOIN',
        'right': 'RIGHT JOIN',
        'full': 'FULL JOIN'
    }[join_type]

    return f"{join_keyword} {table_name} {join.name} ON\n    {on_condition}"


class JoinGenerator:
    """Manages generation of multiple JOIN clauses.

    This class handles the generation of one or more JOIN statements
    for a ViewDefinition, managing aliases and tracking joined tables.

    Attributes:
        base_alias: The SQL alias for the base/primary table
        joins: List of generated JOIN clauses
        aliases: Set of all table aliases in use
    """

    def __init__(self, base_alias: str = 't'):
        """Initialize the JoinGenerator.

        Args:
            base_alias: SQL alias for the base/primary table (default: 't')
        """
        self.base_alias = base_alias
        self._joins: List[str] = []
        self._aliases: set = {base_alias}

    @property
    def joins(self) -> List[str]:
        """Get the list of generated JOIN clauses."""
        return self._joins.copy()

    @property
    def aliases(self) -> set:
        """Get the set of all table aliases in use."""
        return self._aliases.copy()

    def add_join(self, join: Join) -> str:
        """Add a JOIN clause from a Join definition.

        Args:
            join: Join dataclass defining the join

        Returns:
            The generated JOIN clause string

        Raises:
            ValueError: If join name conflicts with existing alias
        """
        # Check for alias conflicts
        if join.name in self._aliases:
            raise ValueError(
                f"Join alias '{join.name}' conflicts with existing alias. "
                f"Current aliases: {', '.join(sorted(self._aliases))}"
            )

        # Generate the JOIN clause
        join_clause = generate_join(join, self.base_alias)

        # Track the new alias
        self._aliases.add(join.name)
        self._joins.append(join_clause)

        return join_clause

    def add_joins(self, joins: List[Join]) -> List[str]:
        """Add multiple JOIN clauses.

        Args:
            joins: List of Join definitions

        Returns:
            List of generated JOIN clause strings
        """
        result = []
        for join in joins:
            result.append(self.add_join(join))
        return result

    def generate_all(self) -> str:
        """Generate all JOIN clauses as a single string.

        Returns:
            All JOIN clauses joined with newlines, or empty string if no joins
        """
        if not self._joins:
            return ""
        return '\n'.join(self._joins)

    def clear(self) -> None:
        """Clear all generated joins, keeping only the base alias."""
        self._joins.clear()
        self._aliases = {self.base_alias}

    def has_joins(self) -> bool:
        """Check if any joins have been added.

        Returns:
            True if at least one join has been added
        """
        return len(self._joins) > 0
