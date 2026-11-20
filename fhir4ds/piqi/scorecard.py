"""PIQI scorecard facade — evaluation, scoring and the [HB p.24] contract.

Scoring rules [HB pp.23-24]:

* numerator = passed SCORING items; denominator = all scoring items;
  PIQI Index = num/den × 100 (0.0 when the denominator is 0 — a message
  with nothing to score has no quality signal).
* Prerequisite-SAM failure ⇒ the item FAILS (denominator +1, numerator
  +0) attributed to the PREREQUISITE's dimension [HB p.21, p.23].
* Conditional-SAM failure ⇒ the item is SKIPPED (neither) [HB p.23] —
  implemented as row absence in the rubric SQL.
* Informational criteria (weight 0) contribute statistics only.
* Critical failures count separately without touching the unweighted
  index. Weighted variants are produced when any weight ≠ 1.
"""

from __future__ import annotations

import base64
import typing as _t
from dataclasses import dataclass, field

from .registry import DATA_CLASS_TO_VIEW, get_rubric, get_view, piqi_resolver
from .taxonomy import PIQIDimension, dimension_for_sam
from ..sqlquery import SQLQueryRunner
from ..sqlquery.types import SQLQUERY_PROFILE_CANONICAL
from ..viewdef.generator import SQLGenerator
from ..viewdef.parser import parse_view_definition
from ..viewdef.utils import quote_identifier

RESULT_COLUMNS = ("patient_id", "element_id", "data_class", "entity",
                  "sam_mnemonic", "result", "detail")


@dataclass(frozen=True)
class PIQIIssue:
    """One failed assessment item — the root-cause insight surface."""

    patient_id: _t.Optional[str]
    element_id: _t.Optional[str]
    data_class: str
    entity: str
    sam_mnemonic: str
    dimension: PIQIDimension
    detail: _t.Optional[str]


@dataclass(frozen=True)
class PIQIScorecard:
    """The [HB p.24] scorecard contract (field names in ``to_dict``)."""

    message_id: _t.Optional[str]
    data_provider_id: _t.Optional[str]
    data_source_id: _t.Optional[str]
    potential_item_score: int
    total_item_score: int
    piqi_index: float
    critical_failure_count: int
    data_class_frequency: dict
    potential_weighted_item_score: _t.Optional[int]
    total_weighted_item_score: _t.Optional[int]
    piqi_weighted_index: _t.Optional[float]
    dimension_rollup: dict
    issues: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "MessageID": self.message_id,
            "DataProviderID": self.data_provider_id,
            "DataSourceID": self.data_source_id,
            "PotentialItemScore": self.potential_item_score,
            "TotalItemScore": self.total_item_score,
            "PIQIIndex": self.piqi_index,
            "CriticalFailureCount": self.critical_failure_count,
            "DataClassFrequency": dict(self.data_class_frequency),
        }
        if self.potential_weighted_item_score is not None:
            d["PotentialWeightedItemScore"] = self.potential_weighted_item_score
            d["TotalWeightedItemScore"] = self.total_weighted_item_score
            d["PIQIWeightedIndex"] = self.piqi_weighted_index
        return d


def load_piqi_views(connection, *, source_table: str = "resources") -> list[str]:
    """Materialize every packaged PIQI ViewDefinition as ``piqi.<name>``."""
    connection.execute("CREATE SCHEMA IF NOT EXISTS piqi")
    created = []
    gen = SQLGenerator(source_table=source_table)
    for view_name in sorted(DATA_CLASS_TO_VIEW.values()):
        vd = parse_view_definition(get_view(view_name))
        sql = gen.generate(vd)
        connection.execute(
            f"CREATE OR REPLACE VIEW piqi.{quote_identifier(view_name)} AS {sql}")
        created.append(view_name)
    return created


def run_sam(connection, sam, *, patient_id: _t.Optional[str] = None,
            source_table: str = "resources") -> list[dict]:
    """Execute one SAM instance, optionally scoped by patient (BOUND).

    ``sam`` is either a packaged SAM name/instance id
    (``"piqi-sam-labresult-resultvalue-ispopulated"``) or a custom SAM
    Library DICT (AMUX-152 #22): a dict is materialized through a
    dict-identity/url resolver fallback, so user-authored SAMs execute
    against the same runner while their packaged canonical dependencies
    (data-class views, prerequisite SAMs) still resolve from the
    packaged registry.

    ``source_table`` (AMUX-152 #24) is the physical DuckDB table the
    generated ViewDefinition SQL reads from (default ``"resources"``).
    """
    from .registry import get_sam as _get

    sam_dict = _get(sam) if isinstance(sam, str) else sam
    canonical = sam_dict["url"]
    wrapper = {
        "resourceType": "Library",
        "id": "piqi-run-" + sam_dict["id"],
        "url": canonical + "-run",
        "name": "PIQI_Run_" + sam_dict["id"].replace("piqi-sam-", "")
                .replace("-", "_"),
        "status": "active",
        "type": {"coding": [{"code": "sql-query"}]},
        "meta": {"profile": [SQLQUERY_PROFILE_CANONICAL]},
        "relatedArtifact": [{"type": "depends-on", "label": "sam",
                             "resource": canonical}],
        "parameter": [{"name": "patient_id", "use": "in", "min": 0,
                       "max": "1", "type": "string"}],
        "content": [{
            "contentType": "application/sql;dialect=duckdb",
            "data": base64.b64encode((
                "SELECT patient_id, element_id, data_class, entity, "
                "sam_mnemonic, result, detail FROM \"sam\" "
                "WHERE ($patient_id IS NULL OR patient_id = $patient_id) "
                "ORDER BY patient_id, element_id"
            ).encode("utf-8")).decode("ascii"),
        }],
    }
    # AMUX-152 #22 (+ batch-4 review): a CUSTOM SAM dict (non-packaged
    # url) must still materialize — resolve the dict itself by
    # identity/url as a FALLBACK, with the packaged registry ALWAYS
    # taking precedence so a dict can never shadow a packaged canonical.
    # A dict that CLAIMS a packaged url is rejected loudly instead of
    # silently replacing the packaged SAM's semantics.
    _packaged = piqi_resolver()
    _own = {canonical: sam_dict}
    _is_dict = not isinstance(sam, str)
    if _is_dict:
        try:
            _packaged(canonical)
        except KeyError:
            pass
        else:
            raise ValueError(
                "custom SAM dict reuses the packaged canonical "
                f"{canonical!r}; give it a unique url")

    def _resolver(resolved_canonical: str) -> dict:
        try:
            return _packaged(resolved_canonical)
        except KeyError:
            if resolved_canonical in _own:
                return _own[resolved_canonical]
            raise

    rows = SQLQueryRunner(connection, _resolver,
                          source_table=source_table).execute(
        wrapper, {"patient_id": patient_id})
    return [dict(zip(RESULT_COLUMNS, r)) for r in rows]


def _data_class_frequency(connection, criteria: list[dict],
                          patient_id: _t.Optional[str], *,
                          source_table: str = "resources") -> dict:
    """Count elements per rubric-referenced data class [HB p.24]."""
    freq: dict[str, int] = {}
    for dc in sorted({c["data_class"] for c in criteria}):
        view_name = DATA_CLASS_TO_VIEW[dc]
        vd = parse_view_definition(get_view(view_name))
        sql = SQLGenerator(source_table=source_table).generate(vd)
        count = connection.execute(
            f"SELECT count(*) FROM ({sql}) s WHERE (? IS NULL OR "
            f"s.patient_id = ?)", [patient_id, patient_id]).fetchone()[0]
        freq[dc] = int(count)
    return freq


def evaluate_rubric(connection, rubric, *, patient_id: _t.Optional[str] = None,
                    message_id: _t.Optional[str] = None,
                    data_provider_id: _t.Optional[str] = None,
                    data_source_id: _t.Optional[str] = None,
                    source_table: str = "resources",
                    verbose: bool = False) -> PIQIScorecard:
    """Evaluate a rubric and produce the [HB p.24] scorecard.

    ``rubric``: a packaged rubric NAME (``"sample"``), a rubric Library
    dict from :func:`fhir4ds.piqi.build_rubric`, or the Library dict's
    tuple form. Weights/criticality are rubric-authored static content
    [RG p.6]. ``source_table`` (AMUX-152 #24) is the physical table the
    generated ViewDefinition SQL reads from.
    """
    rubric_dict = get_rubric(rubric) if isinstance(rubric, str) else rubric
    if isinstance(rubric_dict, tuple):
        rubric_dict, criteria_meta = rubric_dict
    else:
        # AMUX-152 #24: a FHIR-pure rubric Library (no criteria
        # metadata) cannot be scored — fail typed, not KeyError.
        criteria_meta = rubric_dict.get("piqiCriteria")
        if not criteria_meta:
            raise ValueError(
                "rubric Library carries no 'piqiCriteria' metadata "
                "(FHIR-pure rubric); pass the (library, criteria) tuple "
                "returned by build_rubric or a packaged rubric name")

    runner = SQLQueryRunner(connection, piqi_resolver(),
                            source_table=source_table)
    raw = runner.execute(rubric_dict, {"patient_id": patient_id})
    cols = ("patient_id", "element_id", "sequence", "data_class", "entity",
            "attributed_mnemonic", "scoring_effect", "weight", "criticality",
            "result", "detail")
    items = [dict(zip(cols, r)) for r in raw]

    scoring = [i for i in items if i["scoring_effect"] == "scoring"]
    potential = len(scoring)
    total = sum(1 for i in scoring if i["result"] == "pass")
    index = round(total / potential * 100.0, 4) if potential else 0.0
    critical = sum(1 for i in scoring
                   if i["result"] == "fail" and i["criticality"])

    weights_used = any(int(i["weight"]) not in (0, 1) for i in items)
    if weights_used:
        w_potential = sum(int(i["weight"]) for i in scoring)
        w_total = sum(int(i["weight"]) for i in scoring
                      if i["result"] == "pass")
        w_index = round(w_total / w_potential * 100.0, 4) if w_potential else 0.0
    else:
        w_potential = w_total = None
        w_index = None

    failed = [i for i in items if i["result"] == "fail"]
    rollup: dict[str, dict[str, int]] = {}
    for i in failed:
        dim = dimension_for_sam(i["attributed_mnemonic"])
        rollup.setdefault(dim.category, {})
        rollup[dim.category][dim.name] = (
            rollup[dim.category].get(dim.name, 0) + 1)

    issues = [
        PIQIIssue(
            patient_id=i["patient_id"], element_id=i["element_id"],
            data_class=i["data_class"], entity=i["entity"],
            sam_mnemonic=i["attributed_mnemonic"],
            dimension=dimension_for_sam(i["attributed_mnemonic"]),
            detail=i["detail"])
        for i in failed
    ] if verbose else []

    return PIQIScorecard(
        message_id=message_id,
        data_provider_id=data_provider_id,
        data_source_id=data_source_id,
        potential_item_score=potential,
        total_item_score=total,
        piqi_index=index,
        critical_failure_count=critical,
        data_class_frequency=_data_class_frequency(
            connection, criteria_meta, patient_id,
            source_table=source_table),
        potential_weighted_item_score=w_potential,
        total_weighted_item_score=w_total,
        piqi_weighted_index=w_index,
        dimension_rollup=rollup,
        issues=issues,
    )


__all__ = [
    "PIQIScorecard",
    "PIQIIssue",
    "evaluate_rubric",
    "run_sam",
    "load_piqi_views",
]
