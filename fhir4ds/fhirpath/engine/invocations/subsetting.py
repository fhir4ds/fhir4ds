def intersect_fn(ctx, list_1, list_2):
    """FHIRPath §5.3.8 — intersect using equality semantics on unwrapped data."""
    import json as _json
    from ...engine import util as _util

    def _hashable(obj):
        data = _util.get_data(obj) if hasattr(obj, '__class__') and hasattr(_util, 'get_data') else obj
        try:
            return _json.dumps(data, sort_keys=True)
        except TypeError:
            return repr(data)

    seen = {_hashable(obj) for obj in list_2}
    intersection = [obj for obj in list_1 if _hashable(obj) in seen]

    # Deduplicate while preserving order
    result = []
    result_keys = set()
    for obj in intersection:
        key = _hashable(obj)
        if key not in result_keys:
            result_keys.add(key)
            result.append(obj)
    return result
