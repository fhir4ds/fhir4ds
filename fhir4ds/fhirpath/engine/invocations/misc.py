import re
from decimal import Decimal

from ...engine import util as util
from ...engine import nodes as nodes
from ...engine.errors import FHIRPathError

# This file holds code to hande the FHIRPath Existence functions (5.1 in the
# specification).

intRegex = re.compile(r"^[+-]?\d+$")
numRegex = re.compile(r"^[+-]?\d+(\.\d+)?$")


def iif_macro(ctx, data, cond, ok, fail=None):
    # iif can only be called on an empty or singleton collection
    if len(data) > 1:
        raise FHIRPathError("iif() can only be called on an empty or singleton collection")

    if util.is_true(cond(data)):
        return ok(data)
    elif fail:
        return fail(data)
    else:
        return []


def trace_fn(ctx, x, label=""):
    # Check if a custom trace callback is provided in the context
    if "traceFn" in ctx and callable(ctx["traceFn"]):
        ctx["traceFn"](label, x)
    else:
        # Extract underlying FHIR data from ResourceNode wrappers
        display = [util.get_data(item) for item in x] if isinstance(x, list) else x
        print("TRACE:[" + label + "]", str(display))
    return x


def to_integer(ctx, coll):
    if len(coll) != 1:
        return []

    value = util.get_data(coll[0])

    if value == False:
        return 0

    if value == True:
        return 1

    if util.is_number(value):
        if int(value) == value:
            int_val = int(value)
            # FHIRPath Integer is 32-bit signed
            if -2147483648 <= int_val <= 2147483647:
                return int_val
        return []

    if isinstance(value, str):
        if re.match(intRegex, value) is not None:
            int_val = int(value)
            if -2147483648 <= int_val <= 2147483647:
                return int_val

    return []


quantity_regex = re.compile(r"^((\+|-)?\d+(\.\d+)?)\s*(('[^']+')|([a-zA-Z]+))?$")
quantity_regex_map = {"value": 1, "unit": 5, "time": 6}


def to_quantity(ctx, coll, to_unit=None):
    result = None

    # Surround UCUM unit code in the to_unit parameter with single quotes
    if to_unit and not nodes.FP_Quantity.timeUnitsToUCUM.get(to_unit):
        to_unit = f"'{to_unit}'"

    if len(coll) > 1:
        raise FHIRPathError("Could not convert to quantity: input collection contains multiple items")
    elif len(coll) == 1:
        v = util.val_data_converted(coll[0])
        quantity_regex_res = None

        if isinstance(v, (int, Decimal)):
            result = nodes.FP_Quantity(v, "'1'")
        elif isinstance(v, nodes.FP_Quantity):
            result = v
        elif isinstance(v, bool):
            result = nodes.FP_Quantity(1 if v else 0, "'1'")
        elif isinstance(v, str):
            quantity_regex_res = quantity_regex.match(v)
            if quantity_regex_res:
                value = quantity_regex_res.group(quantity_regex_map["value"])
                unit = quantity_regex_res.group(quantity_regex_map["unit"])
                time = quantity_regex_res.group(quantity_regex_map["time"])

                if not time or nodes.FP_Quantity.timeUnitsToUCUM.get(time):
                    result = nodes.FP_Quantity(Decimal(value), unit or time or "'1'")

        if result and to_unit and result.unit != to_unit:
            result = nodes.FP_Quantity.conv_unit_to(result.unit, result.value, to_unit)

    return result if result else []


def to_decimal(ctx, coll):
    if len(coll) != 1:
        return []

    value = util.get_data(coll[0])

    if value is False:
        return Decimal(0)

    if value is True:
        return Decimal(1.0)

    if util.is_number(value):
        return Decimal(value)

    if isinstance(value, str):
        if re.match(numRegex, value) is not None:
            return Decimal(value)

    return []


def to_string(ctx, coll):
    if len(coll) != 1:
        return []

    value = util.get_data(coll[0])

    # Handle boolean values - FHIRPath uses lowercase 'true'/'false'
    if isinstance(value, bool):
        return 'true' if value else 'false'

    return str(value)


# Defines a function on engine called to+timeType (e.g., toDateTime, etc.).
# @param timeType The string name of a class for a time type (e.g. "FP_DateTime").


def to_date_time(ctx, coll):
    ln = len(coll)
    rtn = []
    if ln > 1:
        raise FHIRPathError("to_date_time called for a collection of length " + str(ln))

    if ln == 1:
        value = util.get_data(coll[0])

        # First try FP_DateTime directly
        dateTimeObject = nodes.FP_DateTime(value)

        if dateTimeObject:
            rtn.append(dateTimeObject)
        else:
            # If that fails, try FP_Date for date-only strings (e.g., "2015", "2015-02")
            # and convert them to FP_DateTime by appending 'T'
            dateObject = nodes.FP_Date(value)
            if dateObject:
                # Convert FP_Date string to FP_DateTime format by appending 'T'
                dateTimeObject = nodes.FP_DateTime(value + 'T')
                if dateTimeObject:
                    rtn.append(dateTimeObject)

    return util.get_data(rtn[0]) if rtn else []


def to_time(ctx, coll):
    ln = len(coll)
    rtn = []
    if ln > 1:
        raise FHIRPathError("to_time called for a collection of length " + str(ln))

    if ln == 1:
        value = util.get_data(coll[0])

        timeObject = nodes.FP_Time(value)

        if timeObject:
            rtn.append(timeObject)

    return util.get_data(rtn[0]) if rtn else []


def to_date(ctx, coll):
    ln = len(coll)
    rtn = []

    if ln > 1:
        raise FHIRPathError("to_date called for a collection of length " + str(ln))

    if ln == 1:
        value = util.get_data(coll[0])

        # Try FP_Date first for date-only strings (e.g., "2015", "2015-02", "2015-02-04")
        dateObject = nodes.FP_Date(value)

        if dateObject:
            rtn.append(dateObject)

    return util.get_data(rtn[0]) if rtn else []


def create_converts_to_fn(to_function, _type):
    if isinstance(_type, str):
        def in_function(ctx, coll):
            if len(coll) != 1:
                return []
            return type(to_function(ctx, coll)).__name__ == _type
        return in_function

    def in_function(ctx, coll):
        if len(coll) != 1:
            return []

        return isinstance(to_function(ctx, coll), _type)

    return in_function


def to_boolean(ctx, coll):
    true_strings = ['true', 't', 'yes', 'y', '1', '1.0']
    false_strings = ['false', 'f', 'no', 'n', '0', '0.0']

    if len(coll) != 1:
        return []

    val = util.get_data(coll[0])
    var_type = type(val).__name__

    if var_type == "bool":
        return val
    elif var_type == "int" or var_type == "float" or var_type == "Decimal":
        if val == 1 or val == Decimal('1') or val == 1.0:
            return True
        elif val == 0 or val == Decimal('0') or val == 0.0:
            return False
    elif var_type == "str":
        lower_case_var = val.lower()
        if lower_case_var in true_strings:
            return True
        if lower_case_var in false_strings:
            return False

    return []


def boolean_singleton(coll):
    d = util.get_data(coll[0])
    if isinstance(d, bool):
        return d
    elif len(coll) == 1:
        return True

def string_singleton(coll):
    d = util.get_data(coll[0])
    if isinstance(d, str):
        return d

singleton_eval_by_type = {
    "Boolean": boolean_singleton,
    "String": string_singleton,
}

def singleton(coll, type):
    if len(coll) > 1:
        raise FHIRPathError("Unexpected collection {coll}; expected singleton of type {type}".format(coll=coll, type=type))
    elif len(coll) == 0:
        return []
    to_singleton = singleton_eval_by_type[type]
    if to_singleton:
        val = to_singleton(coll)
        if (val is not None):
            return val
        raise FHIRPathError("Expected {type}, but got: {coll}".format(type=type.lower(), coll=coll))
    raise FHIRPathError("Not supported type {}".format(type))


def _normalize_profile_url(url: str) -> str:
    """Strip version suffix from profile URL for comparison."""
    # Remove |version suffix if present (e.g., "...Patient|4.0.1" -> "...Patient")
    return url.split("|")[0].rstrip("/")


def conforms_to(ctx, coll, structure_definition_url):
    """
    Returns true if the input collection contains a single item that
    conforms to the given structure definition URL.

    This is a basic implementation that checks if the resource's resourceType
    matches the expected type from the URL using exact URL comparison
    (after stripping any version suffix).

    For example:
    - conformsTo('http://hl7.org/fhir/StructureDefinition/Patient') -> true for Patient resources
    - conformsTo('http://hl7.org/fhir/StructureDefinition/Person') -> false for Patient resources
    - conformsTo('http://trash') -> execution error (invalid URL)
    """
    if len(coll) != 1:
        return []

    item = coll[0]
    data = util.get_data(item)

    # Check if this is a FHIR resource
    if not isinstance(data, dict) or 'resourceType' not in data:
        return [False]

    resource_type = data['resourceType']

    # Check if URL is a valid FHIR StructureDefinition URL
    if not structure_definition_url:
        raise FHIRPathError("conformsTo requires a valid StructureDefinition URL")

    # For invalid/non-FHIR URLs, raise an error per FHIRPath spec
    if not structure_definition_url.startswith('http://hl7.org/fhir') and \
       not structure_definition_url.startswith('https://hl7.org/fhir'):
        raise FHIRPathError(f"Unable to resolve structure definition: {structure_definition_url}")

    # Normalize URL by stripping version suffix
    normalized = _normalize_profile_url(structure_definition_url)

    # Exact match against the canonical StructureDefinition URL for this resource type
    expected = f"http://hl7.org/fhir/StructureDefinition/{resource_type}"
    if normalized == expected:
        return [True]

    # Handle FHIR core types that are base types
    # Per FHIR R4: Bundle, Binary, Parameters extend Resource directly.
    # All other resources extend DomainResource which extends Resource.
    _RESOURCE_ONLY_TYPES = frozenset({'Bundle', 'Binary', 'Parameters'})

    expected_type = normalized.split('/')[-1]

    if resource_type in _RESOURCE_ONLY_TYPES:
        ancestors = ['Resource']
    else:
        ancestors = ['DomainResource', 'Resource']

    if expected_type in ancestors:
        return [True]

    return [False]
