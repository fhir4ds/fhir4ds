from ...engine import util
from ...engine.invocations.existence import count_fn
from ...engine.invocations.math import div


def _unwrap(x):
    """Unwrap ResourceNode wrappers so Python builtins can operate on raw values."""
    return [util.get_data(v) for v in x]


def avg_fn(ctx, x):
    if count_fn(ctx, x) == 0:
        return []

    return div(ctx, sum_fn(ctx, x), count_fn(ctx, x))


def sum_fn(ctx, x):
    return sum(_unwrap(x))


def min_fn(ctx, x):
    if count_fn(ctx, x) == 0:
        return []

    return min(_unwrap(x))


def max_fn(ctx, x):
    if count_fn(ctx, x) == 0:
        return []

    return max(_unwrap(x))


def aggregate_macro(ctx, data, expr, initial_value=None):
    ctx["$total"] = initial_value
    for i, x in enumerate(data):
        ctx["$index"] = i
        ctx["$total"] = expr(x)
    return ctx["$total"]
