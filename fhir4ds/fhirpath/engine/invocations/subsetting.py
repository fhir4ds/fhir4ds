def intersect_fn(ctx, list_1, list_2):
    import json as _json

    def _hashable(obj):
        try:
            return _json.dumps(obj, sort_keys=True)
        except TypeError:
            return str(obj)

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
