def or_op(ctx, a, b):
    # Handle list wrapping - extract single values from lists
    if isinstance(a, list) and len(a) == 1:
        a = a[0]
    if isinstance(b, list) and len(b) == 1:
        b = b[0]

    if isinstance(b, list):
        if a == True:
            return True
        if a == False:
            return []
        if isinstance(a, list):
            return []
    if isinstance(a, list):
        if b == True:
            return True
        return []

    return a or b


def and_op(ctx, a, b):
    # Handle list wrapping - extract single values from lists
    if isinstance(a, list) and len(a) == 1:
        a = a[0]
    if isinstance(b, list) and len(b) == 1:
        b = b[0]

    # FHIRPath and operator:
    # - If both operands are boolean, return boolean and
    # - If left is true, return right (even if not boolean)
    # - If left is false, return false
    # - If left is empty, return empty
    # - If right is empty and left is true, return empty

    if isinstance(b, list):
        # b is empty collection
        if a == True:
            return []
        if a == False:
            return False
        if isinstance(a, list):
            return []

    if isinstance(a, list):
        # a is empty collection
        if b == True:
            return []
        return False

    # Non-boolean handling per FHIRPath spec
    # and operator: if left is true, return right
    if a == True:
        return b
    if a == False:
        return False

    return a and b


def xor_op(ctx, a, b):
    # If a or b are arrays, they must be the empty set.
    # In that case, the result is always the empty set.
    if isinstance(a, list) or isinstance(b, list):
        return []

    return (a and not b) or (not a and b)


def implies_op(ctx, a, b):
    if isinstance(b, list):
        if a == True:
            return []
        if a == False:
            return True
        if isinstance(a, list):
            return []

    if isinstance(a, list):
        if b == True:
            return True
        return []

    if a == False:
        return True

    return a and b
