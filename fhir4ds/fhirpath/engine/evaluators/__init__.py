from collections import abc
from decimal import Decimal
from functools import reduce

import re
import json
from ... import engine as engine
from ...engine import util as util
from ...engine import nodes as nodes
from ..errors import FHIRPathError


def boolean_literal(ctx, parentData, node):
    if node["text"] == "true":
        return [True]
    return [False]


def number_literal(ctx, parentData, node):
    text = node["text"]

    # Check if the number has a decimal point - if so, it's a Decimal
    # Otherwise, it's an Integer
    if '.' in text:
        return [Decimal(text)]
    else:
        return [int(text)]


def identifier(ctx, parentData, node):
    return [re.sub(r"(^\"|\"$)", "", node["text"])]


def invocation_term(ctx, parentData, node):
    return engine.do_eval(ctx, parentData, node["children"][0])


_UNORDERED_FNS = frozenset({"children", "descendants"})
_ORDERED_FNS = frozenset({"first", "last", "skip", "take", "tail"})


def _get_fn_name(node):
    """Extract function name from an AST node if it's a function invocation."""
    if node.get("type") == "FunctionInvocation":
        functn = node.get("children", [{}])[0]
        if functn.get("type") == "Functn":
            ident = functn.get("children", [{}])[0]
            return ident.get("text", "")
    return ""


def _get_last_fn_name(node):
    """Get the last function name in an invocation chain."""
    if node.get("type") == "FunctionInvocation":
        return _get_fn_name(node)
    if node.get("type") == "InvocationExpression":
        children = node.get("children", [])
        if children:
            return _get_last_fn_name(children[-1])
    return ""


def _extract_as_target_type(node):
    """Extract the target type from (expr as Type) patterns for static checking."""
    # Look for ParenthesizedTerm containing a TypeExpression with 'as'
    if node.get("type") == "TermExpression":
        children = node.get("children", [])
        if children and children[0].get("type") == "ParenthesizedTerm":
            return _extract_as_target_type(children[0])
    if node.get("type") == "ParenthesizedTerm":
        children = node.get("children", [])
        if children and children[0].get("type") == "TypeExpression":
            texpr = children[0]
            terms = texpr.get("terminalNodeText", [])
            if "as" in terms:
                # Get the type specifier (last child)
                type_children = texpr.get("children", [])
                if len(type_children) >= 2:
                    type_node = type_children[-1]
                    return type_node.get("text", "")
    return None


def invocation_expression(ctx, parentData, node):
    if ctx.get("strict_mode"):
        children = node.get("children", [])
        if len(children) == 2:
            # Check ordered function on unordered collection
            curr_fn = _get_fn_name(children[1])
            if curr_fn in _ORDERED_FNS:
                prev_fn = _get_last_fn_name(children[0])
                if prev_fn in _UNORDERED_FNS:
                    raise TypeError(
                        f"Ordered function '{curr_fn}()' cannot be used on "
                        f"unordered collection from '{prev_fn}()'"
                    )

            # Check (expr as Type).property — validate property exists on Type
            as_type = _extract_as_target_type(children[0])
            if as_type:
                member = children[1]
                if member.get("type") == "MemberInvocation":
                    prop = member.get("children", [{}])[0].get("text", "")
                    if prop:
                        model = ctx.get("model")
                        if isinstance(model, dict):
                            valid = _get_valid_props(model, as_type)
                            if valid and prop not in valid:
                                raise TypeError(
                                    f"'{prop}' is not a valid property of '{as_type}'"
                                )

    return list(
        reduce(
            lambda accumulator, children: engine.do_eval(ctx, accumulator, children),
            node["children"],
            parentData,
        )
    )


def param_list(ctx, parentData, node):
    # we do not eval param list because sometimes it should be passed as
    # lambda/macro (for example in case of where(...)
    return node


def union_expression(ctx, parentData, node):
    return engine.infix_invoke(ctx, "|", parentData, node["children"])


def index_invocation(ctx, parentData, node):
    return util.arraify(ctx["$index"])


def this_invocation(ctx, parentData, node):
    return util.arraify(ctx["$this"])


def total_invocation(ctx, parentData, node):
    return util.arraify(ctx["$total"])


def op_expression(ctx, parentData, node):
    op = node["terminalNodeText"][0]
    return engine.infix_invoke(ctx, op, parentData, node["children"])


def alias_op_expression(mapFn):
    def func(ctx, parentData, node):
        op = node["terminalNodeText"][0]

        if not op in mapFn:
            raise FHIRPathError("Do not know how to alias " + op + " by " + json.dumps(mapFn))

        alias = mapFn[op]
        return engine.infix_invoke(ctx, alias, parentData, node["children"])

    return func


def term_expression(ctx, parentData, node):
    return engine.do_eval(ctx, parentData, node["children"][0])


def null_literal(ctx, parentData, node):
    return []


def parenthesized_term(ctx, parentData, node):
    return engine.do_eval(ctx, parentData, node["children"][0])


def literal_term(ctx, parentData, node):
    term = node["children"][0]

    if term:
        return engine.do_eval(ctx, parentData, term)

    return [node["text"]]


def external_constant_term(ctx, parent_data, node):
    ext_constant = node["children"][0]
    ext_identifier = ext_constant["children"][0]
    varName = identifier(ctx, parent_data, ext_identifier)[0].replace("`", "")

    if varName not in ctx["vars"]:
        raise ValueError(f'Attempting to access an undefined environment variable: {varName}')

    value = ctx["vars"][varName]

    # For convenience, we all variable values to be passed in without their array
    # wrapper.  However, when evaluating, we need to put the array back in.

    if value is None:
        return []

    if not isinstance(value, list):
        return [value]

    return value


def match(m):
    code = m.group(1)
    return chr(int(code[1:], 16))


def string_literal(ctx, parentData, node):
    # Remove the beginning and ending quotes.
    rtn = re.sub(r"^['\"]|['\"]$", "", node["text"])

    rtn = rtn.replace("\\'", "'")
    rtn = rtn.replace("\\`", "`")
    rtn = rtn.replace('\\"', '"')
    rtn = rtn.replace("\\r", "\r")
    rtn = rtn.replace("\\n", "\n")
    rtn = rtn.replace("\\t", "\t")
    rtn = rtn.replace("\\f", "\f")
    rtn = rtn.replace("\\\\", "\\")
    rtn = re.sub(r"\\(u\d{4})", match, rtn)

    return [rtn]


def quantity_literal(ctx, parentData, node):
    valueNode = node["children"][0]
    value = Decimal(valueNode["terminalNodeText"][0])
    unitNode = valueNode["children"][0]
    if len(unitNode["terminalNodeText"]) > 0:
        unit = unitNode["terminalNodeText"][0]
    # Sometimes the unit is in a child node of the child
    elif "children" in unitNode and len(unitNode["children"]) > 0:
        unit = unitNode["children"][0]["terminalNodeText"][0]
    else:
        unit = None

    return [nodes.FP_Quantity(value, unit)]


def date_time_literal(ctx, parentData, node):
    dateStr = node["text"][1:]  # Remove the '@' prefix
    # Use get_match_data to properly create FP_Date or FP_DateTime based on format
    result = nodes.FP_TimeBase.get_match_data(dateStr)
    if result is not None:
        return [result]
    return []


def time_literal(ctx, parentData, node):
    timeStr = node["text"][2:]  # Remove the '@T' prefix
    # Use get_match_data to properly handle timezone errors
    result = nodes.FP_TimeBase.get_match_data(timeStr)
    if result is not None:
        return [result]
    return []


def create_reduce_member_invocation(model, key):
    def func(acc, res):
        res = nodes.ResourceNode.create_node(res)
        childPath = f"{res.path}.{key}" if res.path else f"_.{key}"
        fullPath = f"{res.propName}.{key}" if res.propName else childPath # The full path to the node (weill evenutally be) e.g. Patient.name[0].given
        fullPath = fullPath.replace("_", "")

        actualTypes = None
        toAdd = None
        toAdd_ = None

        if isinstance(model, dict):
            childPath = model["pathsDefinedElsewhere"].get(childPath, childPath)
            actualTypes = model["choiceTypePaths"].get(childPath)

        if isinstance(res.data, nodes.FP_Quantity):
            toAdd = res.data.value

        if actualTypes and isinstance(res.data, abc.Mapping):
            # Use actualTypes to find the field's value
            for actualType in actualTypes:
                # FHIR choice types use TitleCase suffix (e.g., deceasedBoolean)
                field = f"{key}{actualType[0].upper()}{actualType[1:]}"
                toAdd = res.data.get(field)
                toAdd_ = res.data.get(f"_{field}")
                if toAdd is not None or toAdd_ is not None:
                    childPath += f"{actualType[0].upper()}{actualType[1:]}"
                    break
        elif isinstance(res.data, abc.Mapping):
            toAdd = res.data.get(key)
            toAdd_ = res.data.get(f"_{key}")
            if key == "extension":
                childPath = "Extension"
            # Fallback for choice types when no model is available
            # Use a pre-computed lookup map for O(1) access instead of linear scan
            if toAdd is None and toAdd_ is None:
                choice_map = getattr(res.data, '_choice_type_map', None)
                if choice_map is None:
                    # Build {lower_prefix: (field_name, suffix)} map on first access
                    choice_map = {}
                    for field_name in res.data.keys():
                        for prefix_len in range(1, len(field_name)):
                            suffix = field_name[prefix_len:]
                            if suffix and suffix[0].isupper():
                                prefix = field_name[:prefix_len].lower()
                                if prefix not in choice_map:
                                    choice_map[prefix] = (field_name, suffix)
                    try:
                        res.data._choice_type_map = choice_map
                    except AttributeError:
                        pass  # Immutable mapping; map is still used for this call
                entry = choice_map.get(key.lower())
                if entry is not None:
                    field_name, potential_type = entry
                    toAdd = res.data.get(field_name)
                    toAdd_ = res.data.get(f"_{field_name}")
                    if toAdd is not None or toAdd_ is not None:
                        childPath += potential_type
        else:
            if key == "length":
                toAdd = len(res.data)

        childPath = (
            model["path2Type"].get(childPath, childPath)
            if isinstance(model, dict) and "path2Type" in model
            else childPath
        )

        # Handle primitive extensions (_fieldName) by merging with the main field
        # In FHIR, given and _given arrays should be "zipped" together
        if isinstance(toAdd, list) or isinstance(toAdd_, list):
            # Both are lists - merge them together
            toAdd_list = toAdd if isinstance(toAdd, list) else []
            toAdd__list = toAdd_ if isinstance(toAdd_, list) else []
            max_len = max(len(toAdd_list), len(toAdd__list))

            for i in range(max_len):
                val = toAdd_list[i] if i < len(toAdd_list) else None
                ext = toAdd__list[i] if i < len(toAdd__list) else None

                # If we have a primitive value, use it with extension data
                # If we only have extension (val is None), use the extension
                # The key insight: hasValue() should return false when val is None even if ext exists
                item = val if val is not None else ext
                if item is not None:
                    # Pass extension data as _data so extension() function can access it
                    acc.append(nodes.ResourceNode.create_node(item, childPath, _data=ext, propName=f"{fullPath}[{i}]", index=i))
        elif util.is_some(toAdd):
            # Pass _data for primitives with extensions
            acc.append(nodes.ResourceNode.create_node(toAdd, childPath, _data=toAdd_, propName=fullPath))
        elif util.is_some(toAdd_):
            acc.append(nodes.ResourceNode.create_node(toAdd_, childPath, propName=fullPath))
        return acc

    return func


import threading

_valid_props_cache = {}  # type -> set of valid property names
_valid_props_cache_lock = threading.Lock()
_VALID_PROPS_CACHE_MAXSIZE = 512


def _get_valid_props(model, parent_type):
    """Build/cache the set of valid direct child property names for a type."""
    with _valid_props_cache_lock:
        if parent_type in _valid_props_cache:
            return _valid_props_cache[parent_type]
    path2Type = model.get("path2Type", {})
    choiceTypePaths = model.get("choiceTypePaths", {})
    prefix = f"{parent_type}."
    props = set()
    for path in path2Type:
        if path.startswith(prefix):
            # Extract first child segment: "Patient.link.other" → "link"
            rest = path[len(prefix):]
            prop = rest.split(".")[0]
            props.add(prop)
    for path in choiceTypePaths:
        if path.startswith(prefix):
            rest = path[len(prefix):]
            prop = rest.split(".")[0]
            props.add(prop)
    with _valid_props_cache_lock:
        if len(_valid_props_cache) < _VALID_PROPS_CACHE_MAXSIZE:
            _valid_props_cache[parent_type] = props
    return props


def _strict_validate_member(ctx, parentData, key, model):
    """In strict mode, validate member access against model constraints."""
    if not ctx.get("strict_mode") or not isinstance(model, dict):
        return
    choiceTypePaths = model.get("choiceTypePaths", {})

    for item in parentData:
        rn = nodes.ResourceNode.create_node(item) if not isinstance(item, nodes.ResourceNode) else item
        parent_type = getattr(rn, 'path', None)
        if not parent_type:
            continue
        child_path = f"{parent_type}.{key}"

        # 1. Reject direct choice-type suffix access (e.g., Observation.valueQuantity)
        for choice_path, type_list in choiceTypePaths.items():
            if child_path.startswith(choice_path) and child_path != choice_path:
                suffix = child_path[len(choice_path):]
                if suffix and suffix[0].isupper() and suffix in type_list:
                    raise TypeError(
                        f"Direct polymorphic access '{key}' is not allowed in FHIRPath; "
                        f"use '{choice_path.split('.')[-1]}' instead"
                    )

        # 2. Reject unknown properties when valid props are known for this type
        valid = _get_valid_props(model, parent_type)
        if valid and key not in valid:
            # Also accept DomainResource base properties on any resource
            base_types = [parent_type, "DomainResource", "Resource", "Element"]
            pde = model.get("pathsDefinedElsewhere", {})
            resolved_type = pde.get(child_path)
            if resolved_type:
                break  # pathsDefinedElsewhere knows about it
            for base in base_types:
                if key in _get_valid_props(model, base):
                    break
            else:
                raise TypeError(
                    f"'{key}' is not a valid property of '{parent_type}'"
                )
        break  # Only need to check one parent item


def member_invocation(ctx, parentData, node):
    key = engine.do_eval(ctx, parentData, node["children"][0])[0].replace("`", "")
    model = ctx["model"]

    if isinstance(parentData, list):
        if util.is_capitalized(key):
            try:
                filtered = [
                    x for x in parentData
                    if isinstance(x, dict) and x.get("resourceType") == key
                ]
                if filtered:
                    mapped = [nodes.ResourceNode.create_node(x, key) for x in filtered]
                    return mapped
            except TypeError:
                pass

            # Strict mode: type filter found no matches and parent is a known resource
            if ctx.get("strict_mode") and parentData:
                for item in parentData:
                    rn = nodes.ResourceNode.create_node(item) if not isinstance(item, nodes.ResourceNode) else item
                    if hasattr(rn, 'path') and rn.path and rn.path != key:
                        if isinstance(rn.data, dict) and rn.data.get("resourceType") and rn.data["resourceType"] != key:
                            raise TypeError(
                                f"Resource type mismatch: expected {key} but context is {rn.path}"
                            )

        if not util.is_capitalized(key):
            _strict_validate_member(ctx, parentData, key, model)

        return list(reduce(create_reduce_member_invocation(model, key), parentData, []))

    return []


def indexer_expression(ctx, parentData, node):
    coll_node = node["children"][0]
    idx_node = node["children"][1]

    coll = engine.do_eval(ctx, parentData, coll_node)
    idx = engine.do_eval(ctx, parentData, idx_node)

    if util.is_empty(idx):
        return []

    idxNum = int(idx[0])

    if coll is not None and util.is_some(idxNum) and len(coll) > idxNum and idxNum >= 0:
        return [coll[idxNum]]

    return []


def functn(ctx, parentData, node):
    return [engine.do_eval(ctx, parentData, x) for x in node["children"]]


def function_invocation(ctx, parentData, node):
    args = engine.do_eval(ctx, parentData, node["children"][0])
    fn_name = args[0]
    args = args[1:]

    raw_params = None
    if isinstance(args, list) and len(args) > 0 and "children" in args[0]:
        raw_params = args[0]["children"]

    return engine.doInvoke(ctx, fn_name, parentData, raw_params)


def polarity_expression(ctx, parentData, node):
    sign = node["terminalNodeText"][0]
    rtn = engine.do_eval(ctx, parentData, node["children"][0])

    if len(rtn) == 0:
        return rtn  # Empty collection, return empty

    # For sort expressions, we may get collections with multiple items
    # In that case, we wrap the entire collection in a DescendingSortMarker
    if len(rtn) != 1:
        # Check if all items are non-numeric (for sort context)
        all_non_numeric = all(not util.is_number(v) for v in rtn)
        if all_non_numeric and sign == "-":
            from ...engine.invocations.collections import DescendingSortMarker
            return [DescendingSortMarker(rtn)]
        raise FHIRPathError("Unary " + sign + " can only be applied to an individual number.")

    value = rtn[0]

    # Check if it's a Quantity
    from ...engine.nodes import FP_Quantity
    if isinstance(value, FP_Quantity):
        if sign == "-":
            return [FP_Quantity(-value.value, value.unit)]
        return rtn

    if not util.is_number(value):
        # In strict mode, applying polarity to a boolean is an error
        # (e.g., -1.convertsToInteger() where dot binds tighter than unary -)
        if ctx.get("strict_mode") and isinstance(value, bool):
            raise TypeError(
                f"Unary {sign} cannot be applied to non-numeric value: {value!r}"
            )
        # For non-numbers (like strings), return a DescendingSortMarker
        # This is used in sort() to indicate descending order
        if sign == "-":
            from ...engine.invocations.collections import DescendingSortMarker
            return [DescendingSortMarker(value)]
        return rtn

    if sign == "-":
        rtn[0] = -value

    return rtn


evaluators = {
    "Functn": functn,
    "ParamList": param_list,
    "Identifier": identifier,
    # terms
    "NullLiteral": null_literal,
    "LiteralTerm": literal_term,
    "NumberLiteral": number_literal,
    "StringLiteral": string_literal,
    "BooleanLiteral": boolean_literal,
    "QuantityLiteral": quantity_literal,
    "DateTimeLiteral": date_time_literal,
    "TimeLiteral": time_literal,
    "InvocationTerm": invocation_term,
    "ParenthesizedTerm": parenthesized_term,
    "ExternalConstantTerm": external_constant_term,
    # Invocations
    "ThisInvocation": this_invocation,
    "MemberInvocation": member_invocation,
    "FunctionInvocation": function_invocation,
    "IndexInvocation": index_invocation,
    "TotalInvocation": total_invocation,
    # expressions
    "PolarityExpression": polarity_expression,
    "IndexerExpression": indexer_expression,
    "MembershipExpression": alias_op_expression({"contains": "containsOp", "in": "inOp"}),
    "TermExpression": term_expression,
    "UnionExpression": union_expression,
    "InvocationExpression": invocation_expression,
    "InequalityExpression": op_expression,
    "AdditiveExpression": op_expression,
    "MultiplicativeExpression": op_expression,
    "TypeExpression": alias_op_expression({"is": "isOp", "as": "asOp"}),
    "EqualityExpression": op_expression,
    "OrExpression": op_expression,
    "ImpliesExpression": op_expression,
    "AndExpression": op_expression,
    "XorExpression": op_expression,
}
