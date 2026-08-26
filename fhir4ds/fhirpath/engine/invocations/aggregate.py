def aggregate_macro(ctx, data, expr, initial_value=None):
    missing = object()
    old_total = ctx.get("$total", missing)
    old_index = ctx.get("$index", missing)
    saved_vars = dict(ctx.get("vars", {}))
    old_chain = ctx.get("_chain_defined_vars", missing)

    try:
        ctx["$total"] = initial_value
        for i, x in enumerate(data):
            ctx["$index"] = i
            ctx["vars"] = dict(saved_vars)
            if old_chain is not missing:
                ctx["_chain_defined_vars"] = set(old_chain)
            ctx["$total"] = expr(x)
        return ctx["$total"]
    finally:
        ctx["vars"] = saved_vars
        if old_chain is missing:
            ctx.pop("_chain_defined_vars", None)
        else:
            ctx["_chain_defined_vars"] = old_chain
        if old_total is missing:
            ctx.pop("$total", None)
        else:
            ctx["$total"] = old_total

        if old_index is missing:
            ctx.pop("$index", None)
        else:
            ctx["$index"] = old_index
