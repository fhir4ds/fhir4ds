"""STRICT PROFILE MODE tests.

A profile-qualified retrieve (``[ConditionProblemsHealthConcerns: …]``,
``[USQualityCore.MedicationRequest: …]``, ``[USCore.BodyWeightProfile: …]``) is a
MEMBERSHIP test: by default the generated CTE requires the profile canonical in
the resource's ``meta.profile`` (US Core / QI-Core semantics).
``strict_profiles=False`` omits that conjunct so the retrieve matches the base
resource type — for data that does not populate ``meta.profile``.

The negation-profile EXCLUSION stays active in both modes: it only removes
not-done resources and already tolerates a missing ``meta.profile``
(``IS NULL OR NOT (...)``), so disabling strict mode cannot surface a negated
record as positive evidence.
"""

from ...parser import parse_cql
from ...translator import CQLToSQLTranslator, translate_library_to_sql

# A NAMED profile (not the base resource type): only named profiles marked
# ``meta_profile_filter`` are membership-tested.
CQL = """
library Test version '1.0'

using QICore version '6.0.0'
using FHIR version '4.0.1'

valueset "Pregnancy": 'http://cts.nlm.nih.gov/fhir/ValueSet/pregnancy'

context Patient

define "Conditions":
    [ConditionProblemsHealthConcerns: "Pregnancy"]
"""

POSITIVE = "list_contains(from_json(json_extract(r.resource, '$.meta.profile')"


def _sql(strict_profiles: bool) -> str:
    library = parse_cql(CQL)
    translator = CQLToSQLTranslator(strict_profiles=strict_profiles)
    return translator.translate_library_to_population_sql(library)


class TestStrictProfileMode:
    def test_default_is_strict_and_requires_meta_profile(self):
        sql = _sql(True)
        assert POSITIVE in sql, "strict mode must test meta.profile membership"
        assert "condition-problems-health-concerns" in sql

    def test_non_strict_omits_the_membership_conjunct(self):
        strict_sql = _sql(True)
        loose_sql = _sql(False)
        # The positive membership test references the profile canonical.
        canonical = "us-quality-core-condition-problems-health-concerns"
        assert strict_sql.count(POSITIVE) > 0
        assert loose_sql.count(POSITIVE) == 0, (
            "non-strict mode must emit no meta.profile membership test"
        )
        assert canonical not in loose_sql or "meta.profile" not in loose_sql

    def test_non_strict_keeps_resource_type_and_valueset_filters(self):
        sql = _sql(False)
        assert "resourceType" in sql
        assert "in_valueset" in sql

    def test_negation_profile_exclusion_survives_non_strict_mode(self):
        """not-done profiles are still excluded when strict mode is off."""
        loose = CQL.replace(
            'valueset "Pregnancy"',
            'valueset "Pregnancy"',
        )
        sql_loose = _sql(False)
        # The sample profile family has no negation pair, so assert the general
        # invariant on a family that does: MedicationRequest.
        med_cql = """
        library Test2 version '1.0'
        using USQualityCore version '0.1.0-cibuild'
        using FHIR version '4.0.1'
        valueset "Methylphenidate": 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.1176'
        context Patient
        define "Orders": [USQualityCore.MedicationRequest: "Methylphenidate"]
        """
        strict_med = CQLToSQLTranslator(strict_profiles=True).translate_library_to_population_sql(
            parse_cql(med_cql)
        )
        loose_med = CQLToSQLTranslator(strict_profiles=False).translate_library_to_population_sql(
            parse_cql(med_cql)
        )
        assert "medicationnotrequested" in strict_med
        assert "medicationnotrequested" in loose_med, (
            "negation-profile exclusion must stay active when strict mode is off"
        )
        assert strict_med.count(POSITIVE) > loose_med.count(POSITIVE)

    def test_facade_accepts_the_flag(self):
        # translate_library_to_sql emits only the final definition, so the
        # retrieve CTE is not observable here — this is a plumbing smoke test.
        sql = translate_library_to_sql(
            parse_cql(CQL), final_definition="Conditions", strict_profiles=False
        )
        assert "Conditions" in sql

class TestFacadesForwardTheFlag:
    """A public facade that ACCEPTS ``strict_profiles`` but never passes it to

    the translator is a silent no-op — that regression was live in
    ``translate_cql`` while this mode was first implemented. These assert the
    forwarding itself, not generated SQL.
    """

    def test_translate_cql_forwards_the_flag(self):
        from unittest.mock import MagicMock, patch

        import fhir4ds.cql.translator as facade

        for flag in (True, False):
            with patch.object(facade, "CQLToSQLTranslator") as ctor:
                ctor.return_value.translate_library.return_value = {}
                facade.translate_cql(CQL, strict_profiles=flag)
                assert ctor.call_args.kwargs["strict_profiles"] is flag

    def test_translate_library_forwards_the_flag(self):
        from unittest.mock import patch

        import fhir4ds.cql.translator as facade

        library = parse_cql(CQL)
        for flag in (True, False):
            with patch.object(facade, "CQLToSQLTranslator") as ctor:
                ctor.return_value.translate_library.return_value = {}
                facade.translate_library(library, strict_profiles=flag)
                assert ctor.call_args.kwargs["strict_profiles"] is flag

    def test_translate_library_to_sql_forwards_the_flag(self):
        from unittest.mock import patch

        import fhir4ds.cql.translator as facade

        library = parse_cql(CQL)
        for flag in (True, False):
            with patch.object(facade, "CQLToSQLTranslator") as ctor:
                ctor.return_value.translate_library_to_sql.return_value = "SELECT 1"
                facade.translate_library_to_sql(library, strict_profiles=flag)
                assert ctor.call_args.kwargs["strict_profiles"] is flag
