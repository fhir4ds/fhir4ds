"""
FHIRPath Evaluation Context

Implements the evaluation context for FHIRPath expressions, including:
- Context variables (%context, %resource, %rootResource)
- User-defined variables (let expressions)
- Iteration variables ($this, $index, $total)
- Environment variables (%`var`, %sct, %loinc, %ucum)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass
class EvaluationContext:
    """
    FHIRPath evaluation context.

    Maintains the state needed during expression evaluation, including:
    - The current resource being evaluated
    - Variable bindings from let expressions
    - Iteration context ($this, $index, $total)
    - Environment variable values

    Context Variables:
        %context: The current resource being evaluated (changes with focus)
        %resource: The original input resource (does not change)
        %rootResource: The container root resource (for Bundles)

    User Variables (let expressions):
        $name: Variable defined by `let $name = expr in ...`

    Iteration Variables:
        $this: Current element in iteration (where, select, etc.)
        $index: Current index in iteration (0-based)
        $total: Total count of elements in iteration

    Environment Variables:
        %`var`: Access to environment variables via backtick syntax
        %sct: SNOMED CT context
        %loinc: LOINC context
        %ucum: UCUM context

    Example:
        >>> ctx = EvaluationContext(resource=patient_dict)
        >>> ctx.get_context_variable('context')  # Returns patient_dict
        >>> ctx.set_variable('x', [1, 2, 3])
        >>> ctx.get_variable('x')  # Returns [1, 2, 3]
    """

    # The original input resource (immutable)
    resource: dict[str, Any] | None = None

    # The current resource being evaluated (changes with focus)
    context_resource: dict[str, Any] | None = None

    # The root container resource (for Bundles)
    root_resource: dict[str, Any] | None = None

    # User-defined variables from let expressions
    variables: dict[str, Any] = field(default_factory=dict)

    # Environment variables (external context)
    environment: dict[str, Any] = field(default_factory=dict)

    # Iteration context
    iteration_this: Any = None
    iteration_index: int | None = None
    iteration_total: int | None = None

    # Parent context for scoped lookups
    parent: EvaluationContext | None = None

    def __post_init__(self) -> None:
        """Initialize derived fields."""
        # If context_resource not set, use resource
        if self.context_resource is None and self.resource is not None:
            self.context_resource = self.resource

    def get_context_variable(self, name: str) -> Any:
        """
        Get a context variable (%context, %resource, %rootResource).

        Args:
            name: The variable name (without % prefix).

        Returns:
            The variable value, or empty list if not found.

        Raises:
            KeyError: For unknown context variables.
        """
        if name == 'context':
            return self.context_resource if self.context_resource is not None else []
        elif name == 'resource':
            return self.resource if self.resource is not None else []
        elif name == 'rootResource':
            return self.root_resource if self.root_resource is not None else []
        else:
            raise KeyError(f"Unknown context variable: {name}")

    def get_variable(self, name: str) -> Any:
        """
        Get a user-defined variable ($name).

        Looks up the variable in current scope and parent scopes.

        Args:
            name: The variable name (without $ prefix).

        Returns:
            The variable value, or empty list if not found.
        """
        # Check iteration variables first
        if name == 'this':
            if self.iteration_this is not None:
                return self.iteration_this
            return []  # $this undefined outside iteration
        elif name == 'index':
            if self.iteration_index is not None:
                return self.iteration_index
            return []  # $index undefined outside iteration
        elif name == 'total':
            if self.iteration_total is not None:
                return self.iteration_total
            return []  # $total undefined outside iteration

        # Check user-defined variables
        if name in self.variables:
            return self.variables[name]

        # Check parent scope
        if self.parent is not None:
            return self.parent.get_variable(name)

        # Variable not found
        return []

    def set_variable(self, name: str, value: Any) -> None:
        """
        Set a user-defined variable.

        Args:
            name: The variable name (without $ prefix).
            value: The variable value.
        """
        self.variables[name] = value

    def get_environment_variable(self, name: str) -> Any:
        """
        Get an environment variable (%`name`).

        Args:
            name: The environment variable name.

        Returns:
            The variable value, or empty list if not found.
        """
        # Special FHIR terminology contexts - return standard URLs by default
        if name == 'sct':
            return self.environment.get('sct', 'http://snomed.info/sct')
        elif name == 'loinc':
            return self.environment.get('loinc', 'http://loinc.org')
        elif name == 'ucum':
            return self.environment.get('ucum', 'http://unitsofmeasure.org')

        # User-defined environment variables
        if name in self.environment:
            return self.environment[name]

        # Check parent scope
        if self.parent is not None:
            return self.parent.get_environment_variable(name)

        return []

    def set_environment_variable(self, name: str, value: Any) -> None:
        """
        Set an environment variable.

        Args:
            name: The variable name.
            value: The variable value.
        """
        self.environment[name] = value

    def child_scope(self) -> EvaluationContext:
        """
        Create a child scope for let expressions.

        Returns:
            A new context with this context as parent.
        """
        return EvaluationContext(
            resource=self.resource,
            context_resource=self.context_resource,
            root_resource=self.root_resource,
            variables={},  # New scope has empty variables
            environment=self.environment.copy(),
            iteration_this=self.iteration_this,
            iteration_index=self.iteration_index,
            iteration_total=self.iteration_total,
            parent=self,
        )

    def with_iteration(self, this_value: Any, index: int, total: int) -> EvaluationContext:
        """
        Create a context for iteration.

        Args:
            this_value: The current element ($this).
            index: The current index ($index).
            total: The total count ($total).

        Returns:
            A new context with iteration values set.
        """
        return EvaluationContext(
            resource=self.resource,
            context_resource=self.context_resource,
            root_resource=self.root_resource,
            variables=self.variables.copy(),
            environment=self.environment.copy(),
            iteration_this=this_value,
            iteration_index=index,
            iteration_total=total,
            parent=self.parent,
        )

    def with_focus(self, focus_resource: dict[str, Any] | None) -> EvaluationContext:
        """
        Create a context with a new focus resource.

        The %context variable changes to the new focus, but %resource
        and %rootResource remain the same.

        Args:
            focus_resource: The new focus resource.

        Returns:
            A new context with updated focus.
        """
        return EvaluationContext(
            resource=self.resource,
            context_resource=focus_resource,
            root_resource=self.root_resource,
            variables=self.variables.copy(),
            environment=self.environment.copy(),
            iteration_this=self.iteration_this,
            iteration_index=self.iteration_index,
            iteration_total=self.iteration_total,
            parent=self.parent,
        )

    def has_variable(self, name: str) -> bool:
        """
        Check if a variable exists.

        Args:
            name: The variable name (without $ prefix).

        Returns:
            True if the variable is defined.
        """
        # Check iteration variables
        if name in ('this', 'index', 'total'):
            return True

        # Check user-defined variables
        if name in self.variables:
            return True

        # Check parent scope
        if self.parent is not None:
            return self.parent.has_variable(name)

        return False

    def has_environment_variable(self, name: str) -> bool:
        """
        Check if an environment variable exists.

        Args:
            name: The environment variable name.

        Returns:
            True if the variable is defined.
        """
        if name in ('sct', 'loinc', 'ucum'):
            return True

        if name in self.environment:
            return True

        if self.parent is not None:
            return self.parent.has_environment_variable(name)

        return False


def create_context(
    resource: dict[str, Any],
    root_resource: dict[str, Any] | None = None,
    environment: dict[str, Any] | None = None,
) -> EvaluationContext:
    """
    Create an evaluation context for a resource.

    Args:
        resource: The FHIR resource to evaluate against.
        root_resource: The container root (for Bundles).
        environment: Environment variable values.

    Returns:
        An initialized evaluation context.
    """
    return EvaluationContext(
        resource=resource,
        context_resource=resource,
        root_resource=root_resource or resource,
        environment=environment or {},
    )
