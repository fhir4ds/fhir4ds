"""
fhirpath-py - FHIRPath expression evaluator for Python

Usage:
    from .import evaluate

    patient = {"resourceType": "Patient", "id": "123"}
    result = evaluate(patient, "Patient.id")
"""

from .engine.invocations.constants import Constants
from .parser import parse
from .engine import do_eval
from .engine.util import arraify, get_data, set_paths, process_user_invocation_table
from .engine.nodes import FP_Type, ResourceNode

__title__ = "fhir4ds.fhirpath"
__version__ = "0.0.1"
__author__ = "FHIR4DS Team"
__license__ = "AGPL-3.0-only"
__copyright__ = "Copyright 2026 FHIR4DS Team"

# Version synonym
VERSION = __version__


def apply_parsed_path(resource, parsedPath, context=None, model=None, options=None):
    eval_constants = Constants()
    dataRoot = arraify(resource)

    """
    do_eval takes a "ctx" object, and we store things in that as we parse, so we
    need to put user-provided variable data in a sub-object, ctx['vars'].
    Set up default standard variables, and allow override from the variables.
    However, we'll keep our own copy of dataRoot for internal processing.
    """
    vars = {
        "context": resource,
        "sct": "http://snomed.info/sct",
        "loinc": "http://loinc.org",
        "ucum": "http://unitsofmeasure.org",
        # Standard FHIR environment variables (R4)
        "vs-administrative-gender": "http://hl7.org/fhir/ValueSet/administrative-gender",
        "ext-patient-birthTime": "http://hl7.org/fhir/StructureDefinition/patient-birthTime",
    }
    vars.update(context or {})

    _options = options or {}
    ctx = {
        "dataRoot": dataRoot,
        "vars": vars,
        "model": model,
        "strict_mode": _options.get("strict_mode", False),
        "userInvocationTable": process_user_invocation_table(
            _options.get("userInvocationTable", {})
        ),
        "_constants": eval_constants,
    }

    # Add trace callback if provided in options
    if options and "traceFn" in options:
        ctx["traceFn"] = options["traceFn"]

    node = do_eval(ctx, dataRoot, parsedPath["children"][0])

    # Resolve any internal "ResourceNode" instances.  Continue to let FP_Type
    # subclasses through.

    if options and options.get("returnRawData", False):
        if isinstance(node, list):
            res = []
            # Filter out intenal representation of primitive extensions
            # even in this raw data mode (as they are not a part of the output)
            for item in node:
                if isinstance(item, ResourceNode):
                    if isinstance(item.data, dict):
                        keys = list(item.data.keys())
                        if keys == ["extension"]:
                            continue
                res.append(item)
            return res
        return node

    def visit(node):
        data = get_data(node)

        if isinstance(node, list):
            res = []
            for item in data:
                # Filter out intenal representation of primitive extensions
                i = visit(item)
                if isinstance(i, dict):
                    keys = list(i.keys())
                    if keys == ["extension"]:
                        continue
                res.append(i)
            return res

        if isinstance(data, dict) and not isinstance(data, FP_Type):
            for key, value in data.items():
                data[key] = visit(value)

        return data

    return visit(node)


def evaluate(resource, path, context=None, model=None, options=None):
    """
    Evaluates the "path" FHIRPath expression on the given resource, using data
    from "context" for variables mentioned in the "path" expression.

    Parameters:
    resource (dict|list): FHIR resource, bundle as js object or array of resources This resource will be modified by this function to add type information.
    path (string): fhirpath expression, sample 'Patient.name.given'
    context (dict): a hash of variable name/value pairs.
    model (dict): The "model" data object specific to a domain, e.g. R4.
    options (dict): Optional settings. Supports:
        - strict_mode (bool): Enable spec-strict evaluation (default False).
        - traceFn: Trace callback function.
        - returnRawData (bool): Return raw data structures.
        - userInvocationTable (dict): Custom invocation functions.

    Returns:
    list: Result of evaluating the FHIRPath expression.
    """
    _strict = (options or {}).get("strict_mode", False)
    if isinstance(path, dict):
        node = parse(path["expression"], strict_mode=_strict)
        if "base" in path:
            resource = ResourceNode.create_node(resource, path["base"])
    else:
        node = parse(path, strict_mode=_strict)

    return apply_parsed_path(resource, node, context or {}, model, options)


def compile(path, model=None, options=None):
    """
    Returns a function that takes a resource and an optional context hash (see
    "evaluate"), and returns the result of evaluating the given FHIRPath
    expression on that resource.  The advantage of this function over "evaluate"
    is that if you have multiple resources, the given FHIRPath expression will
    only be parsed once.

    Parameters:
    path (string) - the FHIRPath expression to be parsed.
    model (dict) - The "model" data object specific to a domain, e.g. R4.

    For example, you could pass in the result of require("fhirpath/fhir-context/r4")
    """
    return set_paths(apply_parsed_path, parsedPath=parse(path), model=model, options=options)


__all__ = ["evaluate", "compile", "parse", "apply_parsed_path", "VERSION"]
