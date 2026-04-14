"""
FHIRPath Collection Semantics

Implements the collection semantics defined in the FHIRPath specification,
including empty collection propagation and singleton unwrapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, TypeVar

if TYPE_CHECKING:
    from collections.abc import Sequence

T = TypeVar('T')


class EmptyCollectionSentinel:
    """
    Sentinel value representing an empty collection in propagation.

    Used internally to track when an operation should return {}
    due to empty collection propagation rules.
    """

    _instance = None

    def __new__(cls) -> EmptyCollectionSentinel:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "EMPTY"

    def __bool__(self) -> bool:
        return False


EMPTY = EmptyCollectionSentinel()


@dataclass
class FHIRPathCollection:
    """
    A FHIRPath collection with full semantic operations.

    FHIRPath collections have specific behaviors:
    - Empty collections {} propagate through operations
    - Singletons [x] can be automatically unwrapped
    - Operations are applied to each element

    Attributes:
        values: The values in the collection.
    """

    values: list[Any]

    def __init__(self, values: Any = None) -> None:
        """
        Initialize a collection.

        Args:
            values: Single value, list of values, or None for empty.
        """
        if values is None:
            self.values = []
        elif isinstance(values, list):
            self.values = values
        elif isinstance(values, FHIRPathCollection):
            self.values = values.values[:]
        else:
            self.values = [values]

    # Properties

    @property
    def is_empty(self) -> bool:
        """Check if collection is empty ({})."""
        return len(self.values) == 0

    @property
    def is_singleton(self) -> bool:
        """Check if collection has exactly one element ([x])."""
        return len(self.values) == 1

    @property
    def singleton_value(self) -> Any:
        """
        Get the singleton value, unwrapping if needed.

        Returns:
            The single value if singleton.

        Raises:
            ValueError: If collection is not a singleton.
        """
        if self.is_empty:
            raise ValueError("Cannot unwrap empty collection")
        if len(self.values) > 1:
            raise ValueError(f"Cannot unwrap collection with {len(self.values)} elements")
        return self.values[0]

    # Magic methods

    def __len__(self) -> int:
        """Return collection size."""
        return len(self.values)

    def __iter__(self):
        """Iterate over values."""
        return iter(self.values)

    def __getitem__(self, index: int | slice) -> Any:
        """Get item by index."""
        return self.values[index]

    def __bool__(self) -> bool:
        """Collection is truthy if non-empty."""
        return not self.is_empty

    def __repr__(self) -> str:
        """String representation."""
        if self.is_empty:
            return "FHIRPathCollection({})"
        return f"FHIRPathCollection({self.values})"

    def __eq__(self, other: object) -> bool:
        """Equality with propagation semantics."""
        if isinstance(other, FHIRPathCollection):
            return self.values == other.values
        if isinstance(other, EmptyCollectionSentinel):
            return self.is_empty
        if isinstance(other, list):
            return self.values == other
        if self.is_singleton:
            return self.singleton_value == other
        return False

    # Collection operations

    def contains(self, value: Any) -> bool:
        """
        Check if collection contains a value.

        Args:
            value: The value to check.

        Returns:
            True if value is in collection.
        """
        return value in self.values

    def first(self) -> Any:
        """
        Get first element.

        Returns:
            First element or None if empty.
        """
        return self.values[0] if self.values else None

    def last(self) -> Any:
        """
        Get last element.

        Returns:
            Last element or None if empty.
        """
        return self.values[-1] if self.values else None

    def tail(self) -> FHIRPathCollection:
        """
        Get all elements except the first.

        Returns:
            New collection without first element.
        """
        return FHIRPathCollection(self.values[1:])

    def take(self, n: int) -> FHIRPathCollection:
        """
        Take first n elements.

        Args:
            n: Number of elements to take.

        Returns:
            New collection with at most n elements.
        """
        return FHIRPathCollection(self.values[:n])

    def skip(self, n: int) -> FHIRPathCollection:
        """
        Skip first n elements.

        Args:
            n: Number of elements to skip.

        Returns:
            New collection without first n elements.
        """
        return FHIRPathCollection(self.values[n:])

    def where(self, predicate: Callable[[Any], bool]) -> FHIRPathCollection:
        """
        Filter collection by predicate.

        Args:
            predicate: Function returning True for items to keep.

        Returns:
            New filtered collection.
        """
        return FHIRPathCollection([v for v in self.values if predicate(v)])

    def select(self, func: Callable[[Any], Any]) -> FHIRPathCollection:
        """
        Map function over collection.

        Args:
            func: Function to apply to each element.

        Returns:
            New collection with transformed values.
        """
        results = []
        for v in self.values:
            result = func(v)
            if isinstance(result, FHIRPathCollection):
                results.extend(result.values)
            elif isinstance(result, list):
                results.extend(result)
            elif result is not None:
                results.append(result)
        return FHIRPathCollection(results)

    def flatten(self) -> FHIRPathCollection:
        """
        Flatten nested collections.

        Returns:
            Flattened collection.
        """
        results = []
        for v in self.values:
            if isinstance(v, FHIRPathCollection):
                results.extend(v.values)
            elif isinstance(v, list):
                results.extend(v)
            else:
                results.append(v)
        return FHIRPathCollection(results)

    def distinct(self) -> FHIRPathCollection:
        """
        Get unique values.

        Returns:
            Collection with duplicates removed.
        """
        seen = []
        result = []
        for v in self.values:
            # Use repr for comparison to handle unhashable types
            v_repr = repr(v)
            if v_repr not in seen:
                seen.append(v_repr)
                result.append(v)
        return FHIRPathCollection(result)

    def count(self) -> int:
        """
        Count elements.

        Returns:
            Number of elements in collection.
        """
        return len(self.values)

    def union(self, other: FHIRPathCollection) -> FHIRPathCollection:
        """
        Union with another collection.

        Args:
            other: Another collection.

        Returns:
            Combined collection with duplicates removed.
        """
        combined = FHIRPathCollection(self.values + other.values)
        return combined.distinct()

    def intersect(self, other: FHIRPathCollection) -> FHIRPathCollection:
        """
        Intersection with another collection.

        Args:
            other: Another collection.

        Returns:
            Collection with common elements.
        """
        other_reprs = {repr(v) for v in other.values}
        result = [v for v in self.values if repr(v) in other_reprs]
        return FHIRPathCollection(result).distinct()

    def exclude(self, other: FHIRPathCollection) -> FHIRPathCollection:
        """
        Exclude elements from other collection.

        Args:
            other: Collection of elements to exclude.

        Returns:
            Collection without elements from other.
        """
        other_reprs = {repr(v) for v in other.values}
        result = [v for v in self.values if repr(v) not in other_reprs]
        return FHIRPathCollection(result)

    # Conversion methods

    def to_list(self) -> list[Any]:
        """
        Convert to Python list.

        Returns:
            List of values.
        """
        return self.values[:]

    def to_py(self) -> Any:
        """
        Convert to Python value.

        Returns:
            Single value for singletons, list otherwise, None if empty.
        """
        if self.is_empty:
            return None
        if self.is_singleton:
            return self.values[0]
        return self.values[:]


def propagate_empty(func: Callable[..., T]) -> Callable[..., T | EmptyCollectionSentinel]:
    """
    Decorator to propagate empty collections.

    If any argument is an empty collection, returns EMPTY instead
    of calling the function.

    Args:
        func: Function to wrap.

    Returns:
        Wrapped function with empty propagation.
    """
    def wrapper(*args, **kwargs) -> T | EmptyCollectionSentinel:
        for arg in args:
            if isinstance(arg, FHIRPathCollection) and arg.is_empty:
                return EMPTY
        return func(*args, **kwargs)
    return wrapper


def singleton_or_collection(values: list[Any]) -> Any:
    """
    Return singleton value or collection based on FHIRPath semantics.

    Args:
        values: List of values.

    Returns:
        Single value if list has one element, list otherwise.
    """
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return values


def wrap_as_collection(value: Any) -> FHIRPathCollection:
    """
    Wrap a value as a FHIRPath collection.

    Args:
        value: Any value.

    Returns:
        A FHIRPathCollection wrapping the value.
    """
    if isinstance(value, FHIRPathCollection):
        return value
    if isinstance(value, list):
        return FHIRPathCollection(value)
    if value is None:
        return FHIRPathCollection([])
    return FHIRPathCollection([value])
