from ...engine.nodes import TypeInfo

def type_fn(ctx, coll):
    return [TypeInfo.from_value(value).__dict__ for value in coll]


def is_fn(ctx, coll, type_info):
    model = ctx.get("model")
    if not coll:
        return []
    if len(coll) > 1:
        raise ValueError(f"Expected singleton on left side of 'is', got {coll}")
    # is() uses type hierarchy (subtype matching)
    # Return a list containing the boolean result (FHIRPath convention)
    return [TypeInfo.from_value(coll[0]).is_(type_info, model=model)]


def as_fn(ctx, coll, type_info):
    model = ctx.get("model")
    if not coll:
        return []
    if len(coll) > 1:
        raise ValueError(f"Expected singleton on left side of 'as', got {coll}")
    # as() requires exact type match (no subtype matching)
    return coll if TypeInfo.from_value(coll[0]).is_exact_type(type_info, model=model) else []
