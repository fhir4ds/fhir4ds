from ...engine.nodes import ResourceNode, TypeInfo
from ...engine.errors import FHIRPathError


def _is_any_type(type_info):
    return (
        isinstance(type_info, TypeInfo)
        and type_info.name == "Any"
        and type_info.namespace in (None, TypeInfo.System, TypeInfo.FHIR)
    )


def _matches_unqualified_choice_primitive(value, type_info):
    """Return true for valueInteger.as(Integer)-style choice assertions only."""
    if not isinstance(value, ResourceNode):
        return False
    if getattr(type_info, "explicit_namespace", False):
        return False
    if type_info.namespace != TypeInfo.System:
        return False
    if type_info.name not in TypeInfo.SYSTEM_TO_FHIR_TYPE:
        return False
    if type_info.name == "Any":
        return False
    if not value.path:
        return False

    fhir_name = TypeInfo.SYSTEM_TO_FHIR_TYPE.get(type_info.name)
    prop_name = getattr(value, "propName", None) or ""
    prop_segment = prop_name.rsplit(".", 1)[-1] if prop_name else ""
    if value.path == fhir_name:
        # Model-backed choice projection can carry the resolved primitive type
        # as the node path (e.g. path="integer", propName="Observation.value").
        # Ordinary primitive fields keep their element path, such as
        # Patient.active, and should not match unqualified System.Boolean.
        if prop_segment.endswith(type_info.name) and len(prop_segment) > len(type_info.name):
            prefix = prop_segment[: -len(type_info.name)]
            return bool(prefix) and prefix[0].islower()
        return bool(prop_name) and f"{prop_name}{type_info.name}" in TypeInfo.FHIR_PATH_TO_TYPE

    segment = value.path.rsplit(".", 1)[-1]
    suffix = type_info.name
    if not segment.endswith(suffix) or len(segment) <= len(suffix):
        return False
    prefix = segment[: -len(suffix)]
    return bool(prefix) and prefix[0].islower()


def type_fn(ctx, coll):
    return [TypeInfo.from_value(value).__dict__ for value in coll]


def is_fn(ctx, coll, type_info):
    model = ctx.get("model")
    if not coll:
        # FHIRPath §5.1 empty-collection propagation: any function whose
        # input is the empty collection returns the empty collection. Must
        # stay in lockstep with the C++ fn_isType in
        # extensions/fhirpath/src/fhirpath/evaluator.cpp — the parity
        # invariant is enforced by test_type_parity.py.
        return []
    if len(coll) > 1:
        raise FHIRPathError("is() requires a singleton input collection")
    if _is_any_type(type_info):
        return [True]
    if _matches_unqualified_choice_primitive(coll[0], type_info):
        return [True]
    # is() uses type hierarchy (subtype matching)
    # Return a list containing the boolean result (FHIRPath convention)
    return [TypeInfo.from_value(coll[0]).is_(type_info, model=model)]


def as_fn(ctx, coll, type_info):
    model = ctx.get("model")
    if not coll:
        return []
    if len(coll) > 1:
        raise FHIRPathError("as() requires a singleton input collection")
    if _is_any_type(type_info):
        return coll
    if _matches_unqualified_choice_primitive(coll[0], type_info):
        return coll
    value_type = TypeInfo.from_value(coll[0])
    # FP-15 HISTORIAN (2026-08-18): official R4 fixtures pin `as`/`ofType` as
    # EXACT-match for FHIR primitive specifiers while `is` uses the full
    # subtype rule: testFHIRPathAsFunction11 `Patient.gender.as(string)` is
    # EMPTY (missing <output>) although `gender is string` is TRUE
    # (testFHIRPathIsFunction group; code <: string per R4). Fixtures outrank
    # spec prose (GLOBAL_RULES), so primitive casts stay exact; complex and
    # resource FHIR types keep the §6.3 "type or subclass" rule.
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
