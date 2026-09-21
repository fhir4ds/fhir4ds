"""
Types module.

Canonical home of the CQL type reference (:class:`CQLTypeRef`) shared by
the CQL translator type map and the ``$cql`` facade serializer.
"""

from .typeref import ANY_TYPE, CQLTypeRef

__all__ = [
    "CQLTypeRef",
    "ANY_TYPE",
]
