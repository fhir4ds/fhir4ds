from ...engine.nodes import TypeInfo
from ...engine.errors import FHIRPathError

def type_fn(ctx, coll):
    return [TypeInfo.from_value(value).__dict__ for value in coll]


def is_fn(ctx, coll, type_info):
    model = ctx.get("model")
    if not coll:
        return []
    if len(coll) > 1:
        raise FHIRPathError("is() requires a singleton input collection")
    # is() uses type hierarchy (subtype matching)
    # Return a list containing the boolean result (FHIRPath convention)
    return [TypeInfo.from_value(coll[0]).is_(type_info, model=model)]


def as_fn(ctx, coll, type_info):
    model = ctx.get("model")
    if not coll:
        return []
    if len(coll) > 1:
        raise FHIRPathError("as() requires a singleton input collection")
    value_type = TypeInfo.from_value(coll[0])
    # FHIR R4 primitive conformance treats primitive casts as exact even though
    # complex/resource FHIR types follow the §6.3 "type or subclass" rule.
    if (
        value_type.namespace == TypeInfo.FHIR
        and type_info.namespace in (TypeInfo.FHIR, None)
        and (
            (value_type.name and value_type.name[0].islower())
            or (type_info.name and type_info.name[0].islower())
        )
    ):
        return coll if value_type.is_exact_type(type_info, model=model) else []
    return coll if value_type.is_(type_info, model=model) else []
