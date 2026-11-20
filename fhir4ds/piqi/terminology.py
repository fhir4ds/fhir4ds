"""Terminology-backed PIQI SAMs (the deferred FHIR4-17 family).

Implemented against the ``TerminologyEndpoint`` PROTOCOL
(``fhir4ds.cql/terminology/endpoint.py``) — NEVER a hard medterm4ds
import. The endpoint is supplied explicitly or left unset; the env
factory (:func:`fhir4ds.cql.terminology.factory.get_terminology_endpoint`)
is consulted only when ``endpoint`` is omitted AND an explicit
``use_env`` flag is passed, so evaluation stays deterministic in tests.

Assessment sources, in order [determinism doctrine]:

* ``Concept_IsValidMember(valueset=...)`` — LOCAL ValueSet cache first
  (the connection's ``valueset_codes`` table, the DQM loader's cache
  shape) with provenance ``local_valueset_cache``; otherwise the
  endpoint's ``expand()`` with provenance ``terminology_endpoint``.
* ``Concept_IsConsistent(valueset=...)`` — display consistency against
  the local ValueSet cache's ``display`` column (a cache that carries
  displays is the only deterministic display oracle we have; the
  endpoint protocol has no display-lookup operation).
* ``Concept_IsActive`` — the TerminologyEndpoint protocol defines no
  code-status lookup operation (expand/search only), so this SAM is
  **could not assess** everywhere today. Needs a protocol extension —
  flagged as a Joel decision in the campaign notes.

NO endpoint configured and no local cache ⇒ every element gets
``result = 'could not assess'`` (NOT pass/fail) plus a human-readable
detail. Rubric arithmetic treats could-not-assess per the HB
prerequisite convention — the item is SKIPPED (row absence), never
scored — so :func:`run_terminology_sam` keeps the third value explicit
on this PYTHON surface while the SQL SAM contract (pass/fail only,
could-not-assess = row absence) remains untouched.
"""

from __future__ import annotations

import json
import logging
import typing as _t

from .registry import DATA_CLASS_TO_VIEW, get_view
from .taxonomy import TERMINOLOGY_DEPENDENT_SAMS
from .codesystems import resolve_code_system
from ..viewdef.generator import SQLGenerator
from ..viewdef.parser import parse_view_definition

_logger = logging.getLogger(__name__)

#: The result vocabulary on this surface (SQL SAMs stay pass/fail).
COULD_NOT_ASSESS = "could not assess"

_RESULT_COLUMNS = ("patient_id", "element_id", "data_class", "entity",
                   "sam_mnemonic", "result", "detail", "provenance")

_SUPPORTED = frozenset({"Concept_IsValidMember", "Concept_IsConsistent",
                        "Concept_IsActive"})


def _endpoint_or_none(endpoint, use_env: bool):
    if endpoint is not None:
        return endpoint
    if use_env:
        from ..cql.terminology.factory import get_terminology_endpoint

        return get_terminology_endpoint()
    return None


def _provenance(source: str, endpoint=None) -> dict:
    prov = {"source": source}
    if endpoint is not None:
        prov["endpoint"] = type(endpoint).__name__
        # Determinism doctrine: record the index version when the
        # endpoint can state one. expand() returns CodeRef (no version
        # field), so record it only when the adapter exposes it.
        version = getattr(endpoint, "index_version", None)
        prov["index_version"] = version if isinstance(version, str) else None
    return prov


def _view_rows(connection, data_class: str, entity: str, patient_id,
               source_table: str):
    """Materialize (patient_id, element_id, codings) from the class view."""
    view_name = DATA_CLASS_TO_VIEW[data_class]
    vd = parse_view_definition(get_view(view_name))
    sql = SQLGenerator(source_table=source_table).generate(vd)
    codings_col = f"{entity}_codings"
    rows = connection.execute(
        f"SELECT patient_id, element_id, {codings_col} FROM ({sql}) s "
        f"WHERE (? IS NULL OR s.patient_id = ?)",
        [patient_id, patient_id]).fetchall()
    out = []
    for pid, eid, codings in rows:
        parsed = []
        if codings:
            for c in codings:
                try:
                    parsed.append(json.loads(c) if isinstance(c, str) else c)
                except (TypeError, ValueError):
                    continue
        out.append((pid, eid, parsed))
    return out


def _local_cache_members(connection, valueset: str):
    """(system, code, display) rows from the connection's valueset_codes
    table, or None when the table does not exist. Column shape matches
    the canonical CQL/DQM cache (``valueset_url``, NOT ``url`` — the
    loader schema at cql/duckdb/udf/valueset.py and macros/valueset.py)."""
    try:
        rows = connection.execute(
            "SELECT system, code, display FROM valueset_codes "
            "WHERE valueset_url = ?", [valueset]).fetchall()
    except Exception as exc:
        # missing table / wrong shape => no cache (expected path); a
        # present-but-unreadable cache is logged, never silently zero.
        name = getattr(exc, "__class__", object).__name__
        if "Catalog" in name or "Binder" in name or "not exist" in str(exc):
            return None
        _logger.warning("valueset_codes cache unreadable for %r: %s",
                        valueset, exc)
        return None
    return [(r[0], r[1], r[2]) for r in rows]


def _endpoint_members(endpoint, valueset: str):
    codes = endpoint.expand(valueset)
    return [(getattr(c, "system", None), getattr(c, "code", None),
             getattr(c, "display", None)) for c in (codes or [])]


def _emit(pid, eid, data_class, entity, mnemonic, result, detail, prov):
    return dict(zip(_RESULT_COLUMNS,
                    (pid, eid, data_class, entity, mnemonic, result,
                     detail, prov)))


def _could_not_assess_rows(rows, data_class, entity, mnemonic, reason, prov):
    return [
        _emit(pid, eid, data_class, entity, mnemonic, COULD_NOT_ASSESS,
              reason, prov)
        for pid, eid, _codings in rows
    ]


def run_terminology_sam(connection, mnemonic: str, *, data_class: str,
                        entity: str, valueset: _t.Optional[str] = None,
                        endpoint=None, use_env: bool = False,
                        patient_id: _t.Optional[str] = None,
                        source_table: str = "resources") -> list[dict]:
    """Evaluate a terminology-dependent SAM over one coded attribute.

    Args:
        connection: DuckDB connection with the ``resources`` table.
        mnemonic: one of ``Concept_IsValidMember``, ``Concept_IsConsistent``,
            ``Concept_IsActive``.
        data_class / entity: the coded attribute to assess (the class
            view must carry ``<entity>_codings``).
        valueset: ValueSet canonical URL (required for IsValidMember and
            the local-cache IsConsistent path).
        endpoint: an explicit TerminologyEndpoint (protocol-shaped).
        use_env: consult the env-driven factory when ``endpoint`` is
            omitted (opt-in so tests stay deterministic).
        patient_id / source_table: the usual scoping knobs.

    Returns:
        Rows with the standard SAM columns plus ``provenance``; ``result``
        is ``pass``/``fail`` when assessable, else ``could not assess``.
    """
    if mnemonic not in _SUPPORTED:
        raise ValueError(
            f"unsupported terminology SAM {mnemonic!r}; supported: "
            f"{sorted(_SUPPORTED)} (deferred family: "
            f"{sorted(TERMINOLOGY_DEPENDENT_SAMS)})")
    if data_class not in DATA_CLASS_TO_VIEW:
        raise ValueError(
            f"unknown data class {data_class!r}; known: "
            f"{sorted(DATA_CLASS_TO_VIEW)}")
    # <entity>_codings reaches a SQL identifier position — reject
    # fragments (build_rubric lesson / AMUX-152 #17 family).
    from .authoring import assert_sql_identifier

    assert_sql_identifier(entity, "entity")
    ep = _endpoint_or_none(endpoint, use_env)
    rows = _view_rows(connection, data_class, entity, patient_id,
                      source_table)

    if mnemonic == "Concept_IsActive":
        return _could_not_assess_rows(
            rows, data_class, entity, mnemonic,
            "TerminologyEndpoint protocol defines no code-status lookup "
            "(expand/search only); Concept_IsActive needs a protocol "
            "extension", _provenance("none", ep))

    if not valueset:
        raise ValueError(
            f"{mnemonic} requires a valueset= canonical URL")

    members = _local_cache_members(connection, valueset)
    prov = _provenance("local_valueset_cache")
    if members is None:
        if ep is None:
            return _could_not_assess_rows(
                rows, data_class, entity, mnemonic,
                f"no local ValueSet cache for {valueset!r} and no "
                "terminology endpoint configured", _provenance("none"))
        try:
            members = _endpoint_members(ep, valueset)
        except Exception as exc:  # endpoint failures degrade, not crash
            _logger.warning("terminology endpoint expand(%r) failed: %s",
                            valueset, exc)
            return _could_not_assess_rows(
                rows, data_class, entity, mnemonic,
                f"terminology endpoint failed for {valueset!r}: {exc}",
                _provenance("terminology_endpoint", ep))
        prov = _provenance("terminology_endpoint", ep)

    members_norm = {}
    for m in members:
        if m[1]:
            entry = resolve_code_system(m[0])
            members_norm[(entry["identifier"] if entry else m[0], m[1])] = m[2]
    out: list[dict] = []
    for pid, eid, codings in rows:
        def _key(c):
            entry = resolve_code_system(c.get("system"))
            return (entry["identifier"] if entry else c.get("system"),
                    c.get("code"))
        if not codings:
            out.append(_emit(pid, eid, data_class, entity, mnemonic,
                             COULD_NOT_ASSESS,
                             "attribute carries no codings", prov))
            continue
        if mnemonic == "Concept_IsValidMember":
            hit = any(_key(c) in members_norm
                      for c in codings if c.get("code"))
            out.append(_emit(
                pid, eid, data_class, entity, mnemonic,
                "pass" if hit else "fail",
                "at least one coding is a member of the value set" if hit
                else "no coding is a member of the value set", prov))
        else:  # Concept_IsConsistent — display vs cache display
            judged = False
            consistent = True
            for c in codings:
                key = _key(c)
                if not c.get("code") or key not in members_norm:
                    continue
                expected = members_norm[key]
                if not expected:
                    continue
                judged = True
                if (c.get("display") or "") != expected:
                    consistent = False
            if not judged:
                out.append(_emit(pid, eid, data_class, entity, mnemonic,
                                 COULD_NOT_ASSESS,
                                 "no cached display available for any "
                                 "coding", prov))
            else:
                out.append(_emit(
                    pid, eid, data_class, entity, mnemonic,
                    "pass" if consistent else "fail",
                    "coding displays match the value set displays"
                    if consistent else
                    "coding display diverges from the value set display",
                    prov))
    return out


__all__ = ["run_terminology_sam", "COULD_NOT_ASSESS"]
