def intersect_fn(ctx, list_1, list_2):
    """FHIRPath §5.3.8 — intersect using FHIRPath equality semantics."""
    from ...engine.invocations import equality as equality_invocations

    result = []
    for item in list_1:
        if any(equality_invocations.equality(ctx, [item], [existing]) is True for existing in result):
            continue
        if any(equality_invocations.equality(ctx, [item], [other]) is True for other in list_2):
            result.append(item)
    return result
