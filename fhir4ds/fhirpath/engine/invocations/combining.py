from ...engine.invocations import existence as existence
from ...engine.invocations import equality as equality_invocations

"""
This file holds code to hande the FHIRPath Combining functions
"""


def union_op(ctx, coll1, coll2):
    return existence.distinct_fn(ctx, coll1 + coll2)


def combine_fn(ctx, coll1, coll2, preserve_order=False):
    if preserve_order == []:
        return []
    return coll1 + coll2


def exclude_fn(ctx, coll1, coll2):
    return [
        element
        for element in coll1
        if not any(equality_invocations.equality(ctx, [element], [other]) is True for other in coll2)
    ]
