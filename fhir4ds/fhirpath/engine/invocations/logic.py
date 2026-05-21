from ...engine import util
from ...engine.errors import FHIRPathError


def _singleton_boolean(value):
    data = util.arraify(value)
    if len(data) == 0:
        return None
    if len(data) > 1:
        raise FHIRPathError("Cannot convert a collection with multiple items to a boolean")
    item = util.get_data(data[0])
    if item is True:
        return True
    if item is False:
        return False
    return True


def or_op(ctx, a, b):
    a_bool = _singleton_boolean(a)
    b_bool = _singleton_boolean(b)

    if a_bool is True or b_bool is True:
        return True
    if a_bool is False and b_bool is False:
        return False
    return []


def and_op(ctx, a, b):
    a_bool = _singleton_boolean(a)
    b_bool = _singleton_boolean(b)

    if a_bool is False or b_bool is False:
        return False
    if a_bool is True and b_bool is True:
        return True
    return []


def xor_op(ctx, a, b):
    a_bool = _singleton_boolean(a)
    b_bool = _singleton_boolean(b)

    if a_bool is None or b_bool is None:
        return []
    return a_bool != b_bool


def implies_op(ctx, a, b):
    a_bool = _singleton_boolean(a)
    if a_bool is False:
        return True

    b_bool = _singleton_boolean(b)
    if a_bool is None:
        if b_bool is True:
            return True
        return []
    if b_bool is None:
        return []
    return b_bool
