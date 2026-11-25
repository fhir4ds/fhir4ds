"""FHIR4-53: a promoted ``let`` CTE over a fluent-call source keeps a row key.

A query-level ``let`` variable is promoted to a ``_let_<define>_<name>`` CTE
once it is referenced often enough. The CTE is correlated to its query row by
``(patient_id, _row_key)`` — but ONLY when the promotion can tell that the
enclosing alias iterates resource rows. When it cannot, the CTE claims to be
patient-scoped, and the sibling let that consumes it

    timing: dosage.timing

lowers to ``(SELECT value FROM "_let_…_dosage" WHERE patient_id = <alias>.patient_id)``
— one row per row of the source, so every strict connection rejects the whole
statement:

    Invalid Input Error: More than one row returned by a subquery used as an
    expression - scalar subqueries can only return a single row.

CMS156's ``medicationRequestPeriodInDays`` is exactly this shape:
``Twelve lets`` over a query whose source is a FLUENT CALL
(``([MedicationRequest: VS]).moreThanOneOrder() AntiInfectives``). The receiver
is a ``MethodInvocation``, so no resource type could be inferred for the alias
and the promotion fell back to the patient-only shape.
"""

from __future__ import annotations

from fhir4ds.cql.translator.expressions._query import (
    _retrieve_resource_type_from_cte_name,
)


def test_retrieve_cte_name_yields_its_resource_type():
    # Phase-2 name: "<Type>: <terminology> (<profile>)"
    assert _retrieve_resource_type_from_cte_name(
        "MedicationRequest: http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1 (us-quality-core-medicationrequest)"
    ) == "MedicationRequest"
    # Provisional phase-3 name, before the profile is appended.
    assert _retrieve_resource_type_from_cte_name(
        "Observation: http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1"
    ) == "Observation"
    # A bare resource type (no valueset) is NOT enough to go on: definitions
    # may legally be named after a resource type.
    assert _retrieve_resource_type_from_cte_name("MedicationRequest") is None


def test_definition_cte_names_are_not_retrieves():
    assert _retrieve_resource_type_from_cte_name(
        "Two High Risk Medications with Prolonged Duration"
    ) is None
    # The prefix decides, and only a FHIR resource type prefix counts.
    assert _retrieve_resource_type_from_cte_name(
        "NotAResourceType: http://example.org/ValueSet/x"
    ) is None
    # A retrieve CTE prefix IS the resource type even mid-name.
    assert _retrieve_resource_type_from_cte_name(
        "Condition: http://example.org/ValueSet/y"
    ) == "Condition"
    assert _retrieve_resource_type_from_cte_name(None) is None
    assert _retrieve_resource_type_from_cte_name("") is None
