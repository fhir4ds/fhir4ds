from collections import abc
from decimal import Decimal
from functools import reduce
import json
from ...engine import util as util
from ...engine import nodes as nodes

create_node = nodes.ResourceNode.create_node


def resolve(ctx, reference_collection):
    """
    Resolve a Reference to its target resource.

    For in-Bundle resolution:
    - Parse reference.reference (e.g., "Patient/123", "urn:uuid:...")
    - Search Bundle.entry for matching resource

    Args:
        ctx: Evaluation context with model and vars
        reference_collection: Collection of Reference objects

    Returns:
        Collection of resolved resources (or empty if not found)
    """
    if util.is_empty(reference_collection):
        return []

    results = []
    for ref in reference_collection:
        # Get the data from ResourceNode if needed
        ref_data = util.get_data(ref)

        if not isinstance(ref_data, dict):
            continue

        reference_str = ref_data.get('reference')
        if not reference_str:
            continue

        # Try to resolve from context (Bundle)
        resolved = _resolve_reference(ctx, reference_str)
        if resolved:
            results.append(resolved)

    return results


def _resolve_reference(ctx, reference_str):
    """Resolve a reference string to a resource."""
    # Get the root resource from dataRoot
    data_root = ctx.get('dataRoot', [])
    root_resource = data_root[0] if data_root else None

    if not root_resource:
        return None

    # Get the actual data if it's a ResourceNode
    root_data = util.get_data(root_resource)

    # Handle contained resource references (#id)
    if reference_str.startswith('#'):
        contained_id = reference_str[1:]  # Remove '#' prefix
        # Search the current resource's contained array
        if isinstance(root_data, dict):
            contained = root_data.get('contained', [])
            for resource in contained:
                resource_data = util.get_data(resource)
                if isinstance(resource_data, dict) and resource_data.get('id') == contained_id:
                    return resource
        return None

    # Handle Bundle.entry resolution
    if isinstance(root_data, dict) and root_data.get('resourceType') == 'Bundle':
        entries = root_data.get('entry', [])

        for entry in entries:
            resource = entry.get('resource')
            if not resource:
                continue

            # Get actual data if resource is a ResourceNode
            resource_data = util.get_data(resource)

            # Match by reference type
            if reference_str.startswith('urn:uuid:'):
                # UUID reference - match full.id or just the uuid part
                uuid_part = reference_str[9:]  # Remove "urn:uuid:" prefix
                if resource_data.get('id') == uuid_part:
                    return resource
            elif '/' in reference_str:
                # Resource type reference: "Patient/123" or "http://server/Patient/123"
                parts = reference_str.split('/')
                if len(parts) >= 2:
                    # Handle absolute URLs by taking last two parts
                    res_type = parts[-2]
                    res_id = parts[-1]
                    if resource_data.get('resourceType') == res_type and resource_data.get('id') == res_id:
                        return resource
            else:
                # Simple id reference (less common)
                if resource_data.get('id') == reference_str:
                    return resource

    return None


def create_reduce_children(ctx, exclude_primitive_extensions):
    model = ctx["model"]

    def func(acc, res):
        data = util.get_data(res)
        res = create_node(res)

        if isinstance(data, list):
            mapping = getattr(res, "_data", None)
            if isinstance(mapping, abc.Mapping):
                data = mapping
            else:
                # An array JSON item's children are its elements (native
                # fn_children parity). Only reachable with nested-array JSON,
                # which valid FHIR never produces.
                for n in data:
                    acc.append(create_node(n))
                return acc

        if not isinstance(data, abc.Mapping) and isinstance(getattr(res, "_data", None), abc.Mapping):
            data = res._data

        if isinstance(data, abc.Mapping):
            for prop in data.keys():
                value = data[prop]
                childPath = ""

                if prop == "resourceType":
                    continue

                # extensions shouldn't filter through here, yet they should for descendants?
                # unless this item is the node that is being processed (primitive extension)
                # though if you filter it, descendants will not work too
                if prop.startswith("_") and exclude_primitive_extensions:
                    continue

                if res.path is not None:
                    childPath = res.path + "." + prop

                fullPath = f"{res.propName}.{prop}" if res.propName else childPath # The full path to the node (weill evenutally be) e.g. Patient.name[0].given
                fullPath = fullPath.replace("_", "")

                if prop == "extension":
                    childPath = "Extension"

                if (
                    isinstance(model, dict)
                    and "pathsDefinedElsewhere" in model
                    and childPath in model["pathsDefinedElsewhere"]
                ):
                    childPath = model["pathsDefinedElsewhere"][childPath]

                childPath = (
                    model["path2Type"].get(childPath, childPath)
                    if isinstance(model, dict) and "path2Type" in model
                    else childPath
                )

                # If the prop tolower ends with the type tolower
                if res.path is not None and prop.lower().endswith(childPath.lower()) and len(prop) > len(childPath):
                    # Check if the path is actually in the choice types
                    altPropName = res.path + "." + prop[:-len(childPath)]
                    actualTypes = model["choiceTypePaths"].get(altPropName, [])
                    if len(actualTypes) > 0:
                        # If it is, we can use it. Fall back to the element
                        # path (not res.propName, which is None at the
                        # resource root) so the truncated propName stays a
                        # resolvable FHIR path — ofType()/is() choice-primitive
                        # matching re-appends the type suffix and looks the
                        # full path up in FHIR_PATH_TO_TYPE (FP-12 QA-001:
                        # `children().ofType(Integer)` on multipleBirthInteger
                        # must match, exactly like direct navigation).
                        stripped = prop[:-len(childPath)]
                        fullPath = (
                            f"{res.propName}.{stripped}" if res.propName
                            else f"{res.path}.{stripped}" if res.path is not None
                            else stripped
                        )

                shadow_value = data.get(f"_{prop}") if isinstance(prop, str) else None

                if isinstance(value, list):
                    shadow_items = shadow_value if isinstance(shadow_value, list) else []
                    mapped = [
                        create_node(
                            n,
                            childPath,
                            _data=shadow_items[i] if i < len(shadow_items) else None,
                            propName=f"{fullPath}[{i}]",
                            index=i,
                        )
                        for i, n in enumerate(value)
                    ]
                    acc = acc + mapped
                else:
                    acc.append(create_node(value, childPath, _data=shadow_value, propName=fullPath))
        return acc

    return func


def children(ctx, coll):
    return reduce(create_reduce_children(ctx, True), coll, [])


def descendants(ctx, coll):
    from collections import deque

    result = []
    seen = set()
    # FHIRPath §5.8.2 defines descendants() as shorthand for repeat(children()),
    # so it must use the same child projection as children().
    queue = deque(coll)
    while queue:
        item = queue.popleft()
        new_children = []
        pending = set()
        for child in reduce(create_reduce_children(ctx, True), [item], []):
            key = _descendant_repeat_key(child)
            if key not in seen and key not in pending:
                new_children.append(child)
                pending.add(key)
        result.extend(new_children)
        seen.update(pending)
        queue.extend(new_children)
    return result


def _descendant_repeat_key(item):
    data = util.get_data(item)
    if data is None:
        return ("null", None)
    if isinstance(data, bool):
        return ("boolean", data)
    if isinstance(data, (int, float, Decimal)) and not isinstance(data, bool):
        return ("number", str(Decimal(str(data)).normalize()))
    if isinstance(data, (dict, list)):
        # FP-12 EXPLORER (2026-06-29): The standard `json.dumps` and
        # `orjson.dumps` both serialize nested structures recursively
        # (orjson has an internal depth cap around ~500; json.dumps
        # consumes one Python stack frame per nesting level). For deeply
        # nested resources (>= ~200 deep), each call to
        # `_descendant_repeat_key` for an item at depth N pushes past
        # Python's default 1000-frame recursion limit. The native C++
        # `descendants()` uses an iterative work-queue with a 50000-
        # descendant safety cap, so the Python fallback must mirror that
        # capacity.
        #
        # Iteratively serialize the structure with explicit stack to avoid
        # all Python recursion. Mirrors the canonical form used by the
        # prior `json.dumps(data, sort_keys=True, separators=(",", ":"),
        # default=str)` for backward compatibility on shallow structures.
        return ("json", _iterative_canonical_json(data))
    return (type(data).__name__, str(data))


def _iterative_canonical_json(data):
    """Iteratively serialize to canonical JSON without Python-level recursion.

    Produces output identical to
        json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    but uses an explicit stack so deeply nested data does not blow Python's
    recursion limit. Mirrors orjson's output for shallow inputs and remains
    correct for arbitrary depth.
    """
    # `out` is a flat list of fragment strings, indexed by slot.
    # Slot 0 is reserved for the top-level result.
    # For each container (dict/list), we allocate child slots for each value
    # plus an assembly task that runs after all children complete.
    out = ["__PLACEHOLDER__"]
    # Frame: a dict with keys indicating the kind of work.
    #   {"kind": "value", "obj": <obj>, "slot": <int>}
    #   {"kind": "assemble_dict", "keys": [...], "child_slots": [...], "slot": <int>}
    #   {"kind": "assemble_list", "child_slots": [...], "slot": <int>}
    stack = [{"kind": "value", "obj": data, "slot": 0}]

    while stack:
        frame = stack.pop()
        kind = frame["kind"]

        if kind == "assemble_dict":
            keys = frame["keys"]
            child_slots = frame["child_slots"]
            slot = frame["slot"]
            parts = []
            for i, k in enumerate(keys):
                parts.append(json.dumps(k) + ":" + out[child_slots[i]])
            out[slot] = "{" + ",".join(parts) + "}"
            continue

        if kind == "assemble_list":
            child_slots = frame["child_slots"]
            slot = frame["slot"]
            parts = [out[cs] for cs in child_slots]
            out[slot] = "[" + ",".join(parts) + "]"
            continue

        # kind == "value"
        obj = frame["obj"]
        slot = frame["slot"]

        if obj is None:
            out[slot] = "null"
        elif obj is True:
            out[slot] = "true"
        elif obj is False:
            out[slot] = "false"
        elif isinstance(obj, str):
            out[slot] = json.dumps(obj)
        elif isinstance(obj, bool):  # defensive; True/False handled above
            out[slot] = "true" if obj else "false"
        elif isinstance(obj, Decimal):
            out[slot] = json.dumps(str(obj))
        elif isinstance(obj, (int, float)):
            out[slot] = json.dumps(obj)
        elif isinstance(obj, dict):
            keys = sorted(obj.keys(), key=lambda k: str(k))
            child_slots = []
            for _ in keys:
                child_slots.append(len(out))
                out.append("__PLACEHOLDER__")
            # Push assembly task first (LIFO: runs last).
            stack.append({
                "kind": "assemble_dict",
                "keys": keys,
                "child_slots": child_slots,
                "slot": slot,
            })
            # Push children in reverse so they run in key order.
            for i in range(len(keys) - 1, -1, -1):
                stack.append({
                    "kind": "value",
                    "obj": obj[keys[i]],
                    "slot": child_slots[i],
                })
        elif isinstance(obj, list):
            child_slots = []
            for _ in obj:
                child_slots.append(len(out))
                out.append("__PLACEHOLDER__")
            stack.append({
                "kind": "assemble_list",
                "child_slots": child_slots,
                "slot": slot,
            })
            for i in range(len(obj) - 1, -1, -1):
                stack.append({
                    "kind": "value",
                    "obj": obj[i],
                    "slot": child_slots[i],
                })
        else:
            # Fallback — match default=str
            out[slot] = json.dumps(str(obj))

    return out[0]


def get_resource_key(ctx, coll):
    """Return {resourceType}/{id} for the current resource.

    Per SQL-on-FHIR v2, getResourceKey() returns the canonical key for the
    root resource being processed. The input collection is the resource itself.
    """
    if util.is_empty(coll):
        return []
    results = []
    for item in coll:
        data = util.get_data(item)
        if isinstance(data, dict):
            rt = data.get('resourceType', '')
            rid = data.get('id', '')
            if rt and rid:
                results.append(f"{rt}/{rid}")
    return results


def get_reference_key(ctx, coll, type_arg=None):
    """Resolve a Reference element to {resourceType}/{id}.

    Per SQL-on-FHIR v2, getReferenceKey() extracts the reference string from
    a FHIR Reference element. If a type argument is provided, returns empty
    when the reference doesn't match that type.

    Args:
        ctx: Evaluation context.
        coll: Collection of Reference elements.
        type_arg: Optional TypeInfo to filter by (e.g., Patient).
    """
    if util.is_empty(coll):
        return []
    results = []
    for item in coll:
        data = util.get_data(item)
        if isinstance(data, dict):
            ref = data.get('reference', '')
            if not ref:
                continue
            if type_arg is not None:
                type_name = type_arg.name if hasattr(type_arg, 'name') else str(type_arg)
                if not ref.startswith(type_name + '/'):
                    continue
            results.append(ref)
    return results
