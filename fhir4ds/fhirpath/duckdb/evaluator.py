"""
FHIRPath Evaluator

Wraps fhirpath-py to provide expression compilation and evaluation
against FHIR resources. Supports variables, let expressions, and
context variables.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from .collection import FHIRPathCollection, wrap_as_collection
from .context import EvaluationContext, create_context
from .errors import FHIRPathError, FHIRPathSyntaxError, FHIRPathEvaluationError
from .fhir_model import get_fhir_model

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger = logging.getLogger(__name__)


class FHIRPathEvaluator:
    """
    FHIRPath expression evaluator.

    Compiles and evaluates FHIRPath expressions against FHIR resources
    represented as Python dictionaries.

    The evaluator supports:
    - Basic path navigation (Patient.name.given)
    - Context variables (%context, %resource, %rootResource)
    - Let expressions (let $x = expr in body)
    - Variable references ($x, $this, $index, $total)
    - Environment variables (%`var`, %sct, %loinc, %ucum)

    Example:
        >>> evaluator = FHIRPathEvaluator()
        >>> evaluator.compile('Patient.name.given')
        >>> result = evaluator.evaluate({'resourceType': 'Patient', 'name': [{'given': ['John']}]})
        >>> print(result)
        ['John']

        # One-shot evaluation
        >>> result = evaluator.evaluate_expression(
        ...     {'id': '123', 'status': 'active'},
        ...     'status'
        ... )
        >>> print(result)
        ['active']

        # With variables
        >>> result = evaluator.evaluate_expression(
        ...     {'resourceType': 'Patient', 'name': [{'given': ['John']}]},
        ...     'name.given',
        ...     environment={'prefix': 'Mr.'}
        ... )
    """

    def __init__(self) -> None:
        """Initialize the evaluator."""
        self._compiled_expression: Any = None
        self._expression: str | None = None
        self._parser: Any = None
        self._visitor: Any = None
        self._fhirpath_module: Any = None
        self._initialize_parser()

    def _initialize_parser(self) -> None:
        """Initialize the fhirpath parser (optional)."""
        # Try vendored fhirpathpy first (sibling package at src/fhirpathpy)
        try:
            import fhirpathpy
            self._fhirpath_module = fhirpathpy
            return
        except ImportError:
            pass
        # Try fhirpath-py as another fallback
        try:
            import fhir4ds.fhirpath as _fhirpath
            self._fhirpath_module = _fhirpath
            return
        except ImportError:
            pass
        # No fhirpath module available, will use built-in evaluator
        self._fhirpath_module = None
        _logger.warning(
            "No FHIRPath parser available (fhirpathpy or fhir4ds.fhirpath). "
            "Falling back to limited built-in evaluator. Complex FHIRPath "
            "expressions (functions, where-clauses) will not work correctly."
        )

    def _requires_builtin_evaluator(self, expression: str) -> bool:
        """
        Check if expression requires the built-in evaluator.

        Some expressions like 'let' and arbitrary $variable references
        are not supported by fhirpathpy.

        Args:
            expression: The FHIRPath expression.

        Returns:
            True if built-in evaluator is required.
        """
        if not expression:
            return False

        expr_stripped = expression.strip()

        # Let expressions are not supported by fhirpathpy
        if expr_stripped.lower().startswith('let '):
            return True

        # All $variable references need built-in evaluator
        # fhirpathpy only supports $this, $index, $total inside iteration contexts
        # and throws KeyError when they're not set. Our implementation returns
        # empty collection for undefined variables, which matches FHIRPath spec.
        if expr_stripped.startswith('$'):
            return True

        return False

    # Pattern matching numeric literals directly followed by letters without a
    # dot separator. Valid: "123.convertsToInteger()", Invalid: "123abc".
    _INVALID_TOKEN_RE = re.compile(
        r'(?<![a-zA-Z_.])(\d+)([a-zA-Z_])'
    )

    # FHIRPath §3 — Reject structurally malformed path expressions that the
    # underlying parser may silently accept.
    _INVALID_EXPR_PATTERNS = re.compile(
        r'(?:'
        r'\.\s*$'        # trailing dot (e.g. "Patient.")
        r'|\.\.'         # consecutive dots (e.g. "Patient..name")
        r'|\(\s*$'       # unclosed paren at end
        r'|^\s*[+*/|&]'  # leading binary operator
        r')'
    )

    def compile(self, expression: str) -> None:
        """
        Compile a FHIRPath expression.

        Compiles the expression for efficient repeated evaluation.
        The compiled expression is cached in this evaluator instance.

        Args:
            expression: A FHIRPath expression string.

        Raises:
            FHIRPathSyntaxError: If the expression has invalid syntax.
        """
        if not expression or not isinstance(expression, str):
            raise FHIRPathSyntaxError("Expression must be a non-empty string")

        self._expression = expression

        # Validate: reject expressions where a numeric literal is directly followed
        # by alphabetic characters (e.g., "123abc"), which indicates garbage after
        # a valid prefix that many parsers silently accept.
        stripped = expression.strip()
        # Strip string literals before checking (they can contain anything)
        no_strings = re.sub(r"'[^']*'", '', stripped)
        m = self._INVALID_TOKEN_RE.search(no_strings)
        if m:
            pos = m.start()
            raise FHIRPathSyntaxError(
                f"Invalid FHIRPath expression: unexpected characters at position {pos} "
                f"in '{expression}'"
            )

        # Reject structurally malformed expressions (trailing dot, double dots, etc.)
        if self._INVALID_EXPR_PATTERNS.search(no_strings):
            raise FHIRPathSyntaxError(
                f"Invalid FHIRPath expression: '{expression}'"
            )

        self._expression = expression

        # Check if expression requires built-in evaluator
        # These expressions cannot be parsed by fhirpathpy
        if self._requires_builtin_evaluator(expression):
            # Store expression for built-in evaluation
            self._compiled_expression = expression
            return

        try:
            # Use fhirpath-py's compilation if available
            if self._fhirpath_module is not None:
                if hasattr(self._fhirpath_module, 'compile'):
                    self._compiled_expression = self._fhirpath_module.compile(expression)
                elif hasattr(self._fhirpath_module, 'FHIRPath'):
                    self._compiled_expression = self._fhirpath_module.FHIRPath(expression)
                else:
                    self._compiled_expression = expression
            else:
                # Fallback: store expression for later parsing
                self._compiled_expression = expression
        except (ValueError, TypeError, KeyError, AttributeError, NotImplementedError) as e:
            _logger.warning("Failed to compile FHIRPath expression '%s': %s", expression, e)
            raise FHIRPathSyntaxError(f"Failed to compile expression: {expression}") from e

    def evaluate(
        self,
        resource: dict[str, Any],
        context: EvaluationContext | None = None,
        environment: dict[str, Any] | None = None,
        root_resource: dict[str, Any] | None = None,
    ) -> list[Any]:
        """
        Evaluate the compiled expression against a FHIR resource.

        Args:
            resource: A FHIR resource as a Python dictionary.
            context: Optional evaluation context (created if not provided).
            environment: Optional environment variables for %`var` access.
            root_resource: Optional root resource for %rootResource in Bundles.

        Returns:
            A list containing the evaluation results.
            Returns an empty list if the path doesn't match.

        Raises:
            FHIRPathError: If no expression has been compiled.
            FHIRPathTypeError: If there's a type error during evaluation.
        """
        if self._compiled_expression is None:
            raise FHIRPathError("No expression compiled. Call compile() first.")

        # Create context if not provided
        if context is None:
            context = create_context(
                resource=resource,
                root_resource=root_resource,
                environment=environment or {},
            )

        try:
            # Check if expression requires built-in evaluator (let expressions, etc.)
            if self._requires_builtin_evaluator(self._expression or ""):
                result = self._evaluate_expression(resource, self._expression, context)
            elif self._fhirpath_module is not None and hasattr(self._fhirpath_module, 'evaluate'):
                # Build context for fhirpathpy with all variables
                fhirpath_context = self._build_fhirpath_context(resource, context)
                # Get the FHIR model for choice type resolution
                fhir_model = get_fhir_model()
                try:
                    result = self._fhirpath_module.evaluate(resource, self._expression, fhirpath_context, fhir_model)
                except ValueError as ve:
                    # fhirpathpy raises ValueError for undefined environment variables
                    # FHIRPath spec says undefined variables should return empty collection
                    if 'undefined environment variable' in str(ve):
                        result = []
                    else:
                        raise
            elif callable(self._compiled_expression):
                result = self._compiled_expression(resource)
            elif hasattr(self._compiled_expression, 'evaluate'):
                result = self._compiled_expression.evaluate(resource)
            else:
                # Use our built-in evaluator with full variable support
                result = self._evaluate_expression(resource, self._expression, context)

            # Normalize result to list (FHIRPath collection semantics)
            return self._normalize_result(result)

        except FHIRPathError:
            raise
        except NotImplementedError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as e:
            _logger.warning("FHIRPath evaluation error for '%s': %s", self._expression, e)
            raise FHIRPathError(f"Evaluation error: {e}") from e

    def _build_fhirpath_context(
        self,
        resource: dict[str, Any],
        context: EvaluationContext,
    ) -> dict[str, Any]:
        """
        Build the context dictionary for fhirpathpy.

        fhirpathpy expects variables in a context dict that gets stored
        in ctx['vars']. This includes:
        - 'context': the current resource (mapped to %context)
        - 'resource': the original resource (mapped to %resource)
        - 'rootResource': the root resource (mapped to %rootResource)
        - Any user-defined variables
        - Iteration variables ($this, $index, $total)

        Args:
            resource: The FHIR resource being evaluated.
            context: Our evaluation context.

        Returns:
            A dict suitable for passing to fhirpathpy's evaluate().
        """
        fhirpath_context: dict[str, Any] = {}

        # Context variables (%context, %resource, %rootResource)
        # fhirpathpy uses 'context' for %context by default
        if context.context_resource is not None:
            fhirpath_context['context'] = context.context_resource
        else:
            fhirpath_context['context'] = resource

        # %resource - the original input resource
        if context.resource is not None:
            fhirpath_context['resource'] = context.resource

        # %rootResource - the container root (for Bundles)
        if context.root_resource is not None:
            fhirpath_context['rootResource'] = context.root_resource

        # Default terminology contexts (%sct, %loinc, %ucum)
        # These are standard URLs defined by FHIRPath spec
        fhirpath_context['sct'] = 'http://snomed.info/sct'
        fhirpath_context['loinc'] = 'http://loinc.org'
        fhirpath_context['ucum'] = 'http://unitsofmeasure.org'

        # Environment variables (%sct, %loinc, %ucum, and custom %`var`)
        # Copy all environment variables to the context (overrides defaults)
        for name, value in context.environment.items():
            fhirpath_context[name] = value

        # User-defined variables from let expressions
        # These are accessed via $name in FHIRPath
        for name, value in context.variables.items():
            fhirpath_context[name] = value

        # Iteration variables
        # $this, $index, $total are set directly on ctx by fhirpathpy,
        # not in ctx['vars'], but we can try to pass them anyway
        # Note: fhirpathpy handles these internally during iteration

        return fhirpath_context

    def _evaluate_expression(
        self,
        resource: dict[str, Any],
        expression: str,
        context: EvaluationContext,
    ) -> Any:
        """
        Evaluate a FHIRPath expression with full variable support.

        Args:
            resource: The FHIR resource.
            expression: The FHIRPath expression.
            context: The evaluation context.

        Returns:
            The evaluation result.
        """
        expression = expression.strip()

        # Handle let expressions: let $name = expr in body
        let_match = self._parse_let_expression(expression)
        if let_match:
            return self._evaluate_let_expression(resource, let_match, context)

        # Handle variable references: $name
        if expression.startswith('$'):
            var_name = expression[1:]
            return context.get_variable(var_name)

        # Handle context variables: %context, %resource, %rootResource
        if expression.startswith('%'):
            return self._evaluate_context_variable(expression, context)

        # Handle path navigation
        return self._simple_evaluate(resource, expression, context)

    def _parse_let_expression(self, expression: str) -> dict[str, Any] | None:
        """
        Parse a let expression.

        Syntax: let $name = expression in body

        Args:
            expression: The expression to parse.

        Returns:
            A dict with 'name', 'value_expr', 'body_expr' or None if not a let expression.
        """
        # Pattern: let $name = expr in body
        # Need to handle nested expressions carefully
        expression = expression.strip()

        if not expression.lower().startswith('let '):
            return None

        # Find the variable name
        rest = expression[4:].strip()  # Skip 'let '
        if not rest.startswith('$'):
            return None

        # Find the $name
        name_match = re.match(r'\$(\w+)', rest)
        if not name_match:
            return None

        var_name = name_match.group(1)
        rest = rest[name_match.end():].strip()

        # Find the '='
        if not rest.startswith('='):
            return None

        rest = rest[1:].strip()  # Skip '='

        # Find 'in' - need to handle nested expressions
        # Simple approach: find the last 'in' that's not inside parentheses
        in_pos = self._find_in_keyword(rest)
        if in_pos is None:
            return None

        value_expr = rest[:in_pos].strip()
        body_expr = rest[in_pos + 2:].strip()  # Skip 'in'

        return {
            'name': var_name,
            'value_expr': value_expr,
            'body_expr': body_expr,
        }

    def _find_in_keyword(self, expression: str) -> int | None:
        """
        Find the 'in' keyword that separates value and body in a let expression.

        The 'in' must not be inside parentheses or string literals.

        Args:
            expression: The expression to search.

        Returns:
            The position of 'in' or None if not found.
        """
        paren_depth = 0
        in_string = False
        string_char = None
        i = 0

        while i < len(expression):
            char = expression[i]

            # Handle string literals
            if char in ('"', "'") and not in_string:
                in_string = True
                string_char = char
            elif char == string_char and in_string:
                in_string = False
                string_char = None

            # Handle parentheses
            elif char == '(' and not in_string:
                paren_depth += 1
            elif char == ')' and not in_string:
                paren_depth -= 1

            # Check for 'in' keyword (must be at depth 0, not in string)
            elif not in_string and paren_depth == 0:
                # Check if this is the 'in' keyword
                if (expression[i:i+2].lower() == 'in' and
                    (i == 0 or not expression[i-1].isalnum()) and
                    (i + 2 >= len(expression) or not expression[i+2].isalnum())):
                    return i

            i += 1

        return None

    def _evaluate_let_expression(
        self,
        resource: dict[str, Any],
        let_info: dict[str, Any],
        context: EvaluationContext,
    ) -> Any:
        """
        Evaluate a let expression.

        Args:
            resource: The FHIR resource.
            let_info: Parsed let expression info.
            context: The evaluation context.

        Returns:
            The result of evaluating the body expression.
        """
        var_name = let_info['name']
        value_expr = let_info['value_expr']
        body_expr = let_info['body_expr']

        # Evaluate the value expression in the current context
        value = self._evaluate_expression(resource, value_expr, context)

        # Create a child scope with the variable bound
        child_context = context.child_scope()
        child_context.set_variable(var_name, value)

        # Evaluate the body in the child scope
        return self._evaluate_expression(resource, body_expr, child_context)

    def _evaluate_context_variable(self, expression: str, context: EvaluationContext) -> Any:
        """
        Evaluate a context variable reference.

        Handles:
        - %context - current resource
        - %resource - original resource
        - %rootResource - root resource (Bundles)
        - %`name` - environment variable
        - %sct, %loinc, %ucum - terminology contexts

        Args:
            expression: The variable expression (starts with %).
            context: The evaluation context.

        Returns:
            The variable value.
        """
        rest = expression[1:]  # Skip '%'

        # Handle backtick syntax for environment variables: %`name`
        if rest.startswith('`') and rest.endswith('`'):
            var_name = rest[1:-1]
            return context.get_environment_variable(var_name)

        # Handle special context variables
        if rest == 'context':
            return context.get_context_variable('context')
        elif rest == 'resource':
            return context.get_context_variable('resource')
        elif rest == 'rootResource':
            return context.get_context_variable('rootResource')

        # Handle terminology contexts
        if rest in ('sct', 'loinc', 'ucum'):
            return context.get_environment_variable(rest)

        # Unknown context variable
        raise FHIRPathEvaluationError(f"Unknown context variable: %{rest}")

    def _simple_evaluate(
        self,
        resource: dict[str, Any],
        path: str,
        context: EvaluationContext,
    ) -> Any:
        """
        Simple path evaluation fallback.

        Handles basic dot-notation path navigation when fhirpath-py
        is not available or for simple cases. Also handles variable
        references within paths.

        Args:
            resource: The FHIR resource.
            path: A simple path like "Patient.name.given" or "id".
            context: The evaluation context.

        Returns:
            The value at the path, or None if not found.
        """
        # Strip resource type prefix if present
        if '.' in path:
            parts = path.split('.')
            # Check if first part matches resource type
            if parts[0] == resource.get('resourceType'):
                path = '.'.join(parts[1:])
            elif parts[0] in resource:
                # First part is actually a field name
                pass
            elif parts[0][0].isupper():
                # Looks like a resource type that doesn't match – return empty
                return []
            else:
                # First part is not a known field and not a resource type
                pass

        # Navigate the path
        current: Any = resource
        for part in path.split('.'):
            if current is None:
                return None

            # Check if this part is a variable reference
            if part.startswith('$'):
                var_name = part[1:]
                current = context.get_variable(var_name)
                continue

            # Check if this part is a context variable
            if part.startswith('%'):
                current = self._evaluate_context_variable(part, context)
                continue

            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                # Apply to each element and flatten
                results = []
                for item in current:
                    if isinstance(item, dict):
                        val = item.get(part)
                        if val is not None:
                            if isinstance(val, list):
                                results.extend(val)
                            else:
                                results.append(val)
                current = results if results else None
            else:
                return None

        return current

    def _normalize_result(self, result: Any) -> list[Any]:
        """
        Normalize evaluation result to a list (FHIRPath collection).

        FHIRPath always returns collections. This method ensures
        the result follows collection semantics.

        Args:
            result: The raw evaluation result.

        Returns:
            A list containing the result(s).
        """
        if result is None:
            return []
        if isinstance(result, list):
            return result
        return [result]

    def evaluate_expression(
        self,
        resource: dict[str, Any],
        expression: str,
        environment: dict[str, Any] | None = None,
        root_resource: dict[str, Any] | None = None,
        variables: dict[str, Any] | None = None,
    ) -> list[Any]:
        """
        Compile and evaluate an expression in one step.

        Convenience method for one-shot evaluation.

        Args:
            resource: A FHIR resource as a Python dictionary.
            expression: A FHIRPath expression string.
            environment: Optional environment variables.
            root_resource: Optional root resource for Bundles.
            variables: Optional pre-defined variables.

        Returns:
            A list containing the evaluation results.
        """
        self.compile(expression)

        # Create context with any pre-defined variables
        context = create_context(
            resource=resource,
            root_resource=root_resource,
            environment=environment or {},
        )

        # Add any pre-defined variables
        if variables:
            for name, value in variables.items():
                context.set_variable(name, value)

        return self.evaluate(resource, context=context)

    def evaluate_with_context(
        self,
        context: EvaluationContext,
        expression: str,
    ) -> list[Any]:
        """
        Evaluate an expression with a pre-built context.

        Args:
            context: The evaluation context.
            expression: A FHIRPath expression string.

        Returns:
            A list containing the evaluation results.
        """
        self.compile(expression)
        return self.evaluate(context.resource or {}, context=context)

    @property
    def expression(self) -> str | None:
        """Get the currently compiled expression."""
        return self._expression


def evaluate_fhirpath(
    resource: dict[str, Any],
    expression: str,
    environment: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
) -> list[Any]:
    """
    Convenience function for one-shot FHIRPath evaluation.

    Args:
        resource: A FHIR resource as a Python dictionary.
        expression: A FHIRPath expression string.
        environment: Optional environment variables.
        variables: Optional pre-defined variables.

    Returns:
        A list containing the evaluation results.
    """
    evaluator = FHIRPathEvaluator()
    return evaluator.evaluate_expression(
        resource,
        expression,
        environment=environment,
        variables=variables,
    )
