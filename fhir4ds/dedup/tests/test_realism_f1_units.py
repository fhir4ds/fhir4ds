"""REALISM-F1 regression: pint's bare AssertionError on exotic UCUM units.

MIMIC-IV-FHIR microbiology quantities use UCUM annotations like ``#/hpf``
(high-power field), ``#/lpf``, ``#/uL``. ``pint.ureg`` raises a bare
``AssertionError`` for some of these spellings, which the conversion helper's
except tuple missed — crashing ``quantityConvert`` and the whole
``dedup_pass`` on real data. Unconvertible units must return None
(row-resilient), never raise.
"""

from __future__ import annotations

from fhir4ds.cql.duckdb.udf.quantity import _quantity_to_pint


def test_pint_assertion_error_units_return_none() -> None:
    for code in ("#/hpf", "#/lpf", "#/uL", "#"):
        assert _quantity_to_pint({"value": 5, "code": code}) is None, code


def test_dedup_pass_survives_mimic_micro_units() -> None:
    from fhir4ds.dedup.pipeline import dedup_pass

    resources = [
        {"resourceType": "Observation", "id": "o1",
         "subject": {"reference": "Patient/p1"},
         "code": {"coding": [{"system": "http://loinc.org", "code": "11475-1"}]},
         "effectiveDateTime": "2180-05-03T13:00:00Z",
         "valueQuantity": {"value": 5, "code": "#/hpf"}},
        {"resourceType": "Observation", "id": "o2",
         "subject": {"reference": "Patient/p1"},
         "code": {"coding": [{"system": "http://loinc.org", "code": "11475-1"}]},
         "effectiveDateTime": "2180-05-03T13:00:00Z",
         "valueQuantity": {"value": 5, "code": "#/hpf"}},
    ]
    clusters = dedup_pass(resources)
    # DedupResult; the crash-free return + correct merge of the twin
    # observations is the regression pin.
    assert len(clusters.clusters) == 1
    assert len(clusters.clusters[0]) == 2
