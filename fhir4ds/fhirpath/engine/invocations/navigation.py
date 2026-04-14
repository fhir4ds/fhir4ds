from collections import abc
from functools import reduce
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
            data = dict((i, data[i]) for i in range(0, len(data)))

        if isinstance(data, abc.Mapping):
            for prop in data.keys():
                value = data[prop]
                childPath = ""

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
                if prop.lower().endswith(childPath.lower()) and len(prop) > len(childPath):
                    # Check if the path is actually in the choice types
                    altPropName = res.path + "." + prop[:-len(childPath)]
                    actualTypes = model["choiceTypePaths"].get(altPropName, [])
                    if len(actualTypes) > 0:
                        # If it is, we can use it
                        fullPath = f"{res.propName}.{prop[:-len(childPath)]}"

                if isinstance(value, list):
                    mapped = [create_node(n, childPath, propName=f"{fullPath}[{i}]", index=i) for i, n in enumerate(value)]
                    acc = acc + mapped
                else:
                    acc.append(create_node(value, childPath, propName=fullPath))
        return acc

    return func


def children(ctx, coll):
    return reduce(create_reduce_children(ctx, True), coll, [])


def descendants(ctx, coll):
    from collections import deque
    result = []
    queue = deque(reduce(create_reduce_children(ctx, False), coll, []))
    while queue:
        item = queue.popleft()
        result.append(item)
        queue.extend(reduce(create_reduce_children(ctx, False), [item], []))
    return result
