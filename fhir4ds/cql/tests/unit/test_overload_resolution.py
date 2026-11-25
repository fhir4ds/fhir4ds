"""CQL function overload resolution — conversion-precedence lattice (AMUX-167).

Pins ``fhir4ds.cql.translator.overload`` against CQL 1.5 Developer's Guide
"Conversion Precedence" and Reference Table 9-E: which conversions may resolve
an overload, in what order, and when a call is ambiguous or unresolvable.
"""

from __future__ import annotations

import logging

import pytest

from fhir4ds.cql.errors import TranslationError
from fhir4ds.cql.translator import overload as ov
from fhir4ds.cql.translator.context import SQLTranslationContext

T = ov.parse_cql_type
RANK_ORDER = [
    ov.EXACT,
    ov.SUBTYPE,
    ov.COMPATIBLE,
    ov.CAST,
    ov.IMPLICIT_SIMPLE,
    ov.IMPLICIT_CLASS,
    ov.INTERVAL_PROMOTION,
    ov.LIST_DEMOTION,
    ov.INTERVAL_DEMOTION,
    ov.LIST_PROMOTION,
]


@pytest.fixture
def model() -> ov.TypeModel:
    # A real context supplies the data-model profile registry.
    return ov.TypeModel(SQLTranslationContext())


# ---------------------------------------------------------------------------
# Type text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, rendered",
    [
        ("Integer", "Integer"),
        ("System.Integer", "System.Integer"),
        ("FHIR.Condition", "FHIR.Condition"),
        ('List<"FHIR.ServiceRequest">', "List<FHIR.ServiceRequest>"),
        ("List<List<Interval<DateTime>>>", "List<List<Interval<DateTime>>>"),
        ("Choice<ConditionEncounterDiagnosis, FHIR.Period>", "Choice<ConditionEncounterDiagnosis, FHIR.Period>"),
        ("Tuple{encounter: Any, period: Interval<DateTime>}", "Tuple{encounter: Any, period: Interval<DateTime>}"),
    ],
)
def test_type_text_round_trips(text, rendered):
    assert ov.format_cql_type(T(text)) == rendered


def test_type_text_parser_rejects_non_types():
    assert T("List<Integer") is None
    assert T("Integer>") is None
    assert T("") is None
    assert T(None) is None


def test_conversion_precedence_is_ordered_least_to_most_converting():
    assert RANK_ORDER == sorted(RANK_ORDER) and len(set(RANK_ORDER)) == 10


# ---------------------------------------------------------------------------
# Table 9-E
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argument, parameter, expected",
    [
        # The complete set of Implicit cells among the System types.
        ("Integer", "Long", ov.IMPLICIT_SIMPLE),
        ("Integer", "Decimal", ov.IMPLICIT_SIMPLE),
        ("Integer", "Quantity", ov.IMPLICIT_CLASS),
        ("Long", "Decimal", ov.IMPLICIT_SIMPLE),
        ("Long", "Quantity", ov.IMPLICIT_CLASS),
        ("Decimal", "Quantity", ov.IMPLICIT_CLASS),
        ("Date", "DateTime", ov.IMPLICIT_SIMPLE),
        ("Code", "Concept", ov.IMPLICIT_CLASS),
    ],
)
def test_table_9_e_implicit_conversions(model, argument, parameter, expected):
    assert ov.conversion_rank(model, T(argument), T(parameter)) == expected


@pytest.mark.parametrize(
    "argument, parameter",
    [
        # Explicit-only cells of Table 9-E cannot resolve an overload.
        ("Decimal", "Integer"),
        ("Decimal", "Long"),
        ("Long", "Integer"),
        ("Integer", "Boolean"),
        ("Long", "Boolean"),
        ("Decimal", "Boolean"),
        ("Integer", "String"),
        ("Long", "String"),
        ("Decimal", "String"),
        ("Quantity", "String"),
        ("Date", "String"),
        ("String", "Boolean"),
        ("String", "Integer"),
        ("String", "Long"),
        ("String", "Decimal"),
        ("String", "Quantity"),
        ("String", "Date"),
        ("Boolean", "Integer"),
        ("Boolean", "Long"),
        ("Boolean", "Decimal"),
        ("Concept", "List<Code>"),
        # Implicit conversions do not run backwards.
        ("Long", "Integer"),
        ("Decimal", "Integer"),
        ("Quantity", "Integer"),
        ("Quantity", "Decimal"),
        ("DateTime", "Date"),
        ("Concept", "Code"),
    ],
)
def test_no_implicit_conversion_exists(model, argument, parameter):
    assert ov.conversion_rank(model, T(argument), T(parameter)) is ov.NO_MATCH


def test_there_is_no_decimal_to_integer_implicit_conversion(model):
    """The AMUX-167 headline: a Decimal argument never resolves an Integer overload."""
    assert ov.conversion_rank(model, T("Decimal"), T("Integer")) is ov.NO_MATCH
    # ... while Integer does resolve a Decimal overload.
    assert ov.conversion_rank(model, T("Integer"), T("Decimal")) == ov.IMPLICIT_SIMPLE


# ---------------------------------------------------------------------------
# Exact, subtype, Any
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argument, parameter, expected",
    [
        ("Integer", "Integer", ov.EXACT),
        ("System.Integer", "Integer", ov.EXACT),
        ("List<Integer>", "List<Integer>", ov.EXACT),
        ("FHIR.Condition", "Condition", ov.EXACT),
        ("Condition", "FHIR.Condition", ov.EXACT),
        ("dateTime", "FHIR.dateTime", ov.EXACT),
        # Profiles are subtypes of their base resource.
        ("ConditionProblemsHealthConcerns", "Condition", ov.SUBTYPE),
        ("ConditionProblemsHealthConcerns", "FHIR.Condition", ov.SUBTYPE),
        ("List<ConditionProblemsHealthConcerns>", "List<Condition>", ov.SUBTYPE),
        # ... but a base type is not a subtype of its profile.
        ("Condition", "ConditionProblemsHealthConcerns", ov.NO_MATCH),
        ("List<Condition>", "List<ConditionProblemsHealthConcerns>", ov.NO_MATCH),
        # Two profiles of one base type: the profile hierarchy below the base
        # resource is not known, so neither is ruled out.
        ("ConditionEncounterDiagnosis", "ConditionProblemsHealthConcerns", ov.COMPATIBLE),
        ("LaboratoryResultObservation", "ObservationClinicalResult", ov.COMPATIBLE),
        # Unrelated model types.
        ("Condition", "Observation", ov.NO_MATCH),
        ("Condition", "FHIR.Encounter", ov.NO_MATCH),
        # The FHIR type hierarchy.
        ("Encounter", "Resource", ov.SUBTYPE),
        ("Encounter", "DomainResource", ov.SUBTYPE),
        ("Encounter", "Element", ov.NO_MATCH),
        ("FHIR.Period", "Element", ov.SUBTYPE),
        ("FHIR.code", "FHIR.string", ov.SUBTYPE),
        ("FHIR.markdown", "FHIR.string", ov.SUBTYPE),
        ("FHIR.canonical", "FHIR.uri", ov.SUBTYPE),
        ("FHIR.unsignedInt", "FHIR.integer", ov.SUBTYPE),
        # Any is compatible with, and a supertype of, everything.
        ("Any", "Integer", ov.COMPATIBLE),
        ("Integer", "Any", ov.SUBTYPE),
        ("List<Integer>", "Any", ov.SUBTYPE),
        ("Interval<DateTime>", "Any", ov.SUBTYPE),
        ("Choice<Integer, String>", "Any", ov.SUBTYPE),
        ("Tuple{a: Integer}", "Any", ov.SUBTYPE),
        # A model type the hierarchy does not know (a FHIR enumeration) is a
        # code: it is compatible with text-like values and with nothing else.
        ("FHIR.code", "ObservationStatus", ov.COMPATIBLE),
        ("String", "AccountStatus", ov.COMPATIBLE),
        ("FHIR.ObservationStatus", "FHIR.code", ov.COMPATIBLE),
        ("List<FHIR.code>", "List<ObservationStatus>", ov.COMPATIBLE),
        ("Integer", "AccountStatus", ov.NO_MATCH),
        ("FHIR.Period", "ObservationStatus", ov.NO_MATCH),
    ],
)
def test_exact_and_subtype(model, argument, parameter, expected):
    assert ov.conversion_rank(model, T(argument), T(parameter)) == expected


def test_unknown_argument_type_is_compatible_but_not_exact(model):
    assert ov.conversion_rank(model, None, T("Integer")) == ov.COMPATIBLE
    assert ov.conversion_rank(model, T("Integer"), None) == ov.COMPATIBLE


# ---------------------------------------------------------------------------
# FHIR types and the System types this translator carries them as
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argument, parameter, expected",
    [
        ("FHIR.dateTime", "DateTime", ov.IMPLICIT_SIMPLE),
        ("FHIR.instant", "DateTime", ov.IMPLICIT_SIMPLE),
        ("DateTime", "FHIR.dateTime", ov.IMPLICIT_SIMPLE),
        ("FHIR.dateTime", "FHIR.dateTime", ov.EXACT),
        ("FHIR.dateTime", "Date", ov.NO_MATCH),
        ("FHIR.dateTime", "FHIR.Period", ov.NO_MATCH),
        ("FHIR.CodeableConcept", "Concept", ov.IMPLICIT_SIMPLE),
        ("FHIR.Period", "Period", ov.EXACT),
        ("FHIR.Period", "Interval<DateTime>", ov.NO_MATCH),
        ("FHIR.unsignedInt", "Integer", ov.IMPLICIT_SIMPLE),
    ],
)
def test_fhir_types_and_their_system_equivalents(model, argument, parameter, expected):
    assert ov.conversion_rank(model, T(argument), T(parameter)) == expected


# ---------------------------------------------------------------------------
# Lists, intervals, choices, tuples
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argument, parameter, expected",
    [
        ("List<Integer>", "List<Decimal>", ov.IMPLICIT_SIMPLE),
        ("List<Integer>", "List<Quantity>", ov.IMPLICIT_CLASS),
        ("List<Decimal>", "List<Integer>", ov.NO_MATCH),
        ("List<Integer>", "List<String>", ov.NO_MATCH),
        ("List<Integer>", "Integer", ov.LIST_DEMOTION),
        ("Integer", "List<Integer>", ov.LIST_PROMOTION),
        ("Interval<Integer>", "Interval<Decimal>", ov.IMPLICIT_SIMPLE),
        ("Interval<Decimal>", "Interval<Integer>", ov.NO_MATCH),
        ("Integer", "Interval<Integer>", ov.INTERVAL_PROMOTION),
        ("Interval<Integer>", "Integer", ov.INTERVAL_DEMOTION),
        ("List<Integer>", "Interval<Integer>", ov.NO_MATCH),
        ("List<Choice<Integer, String>>", "List<Integer>", ov.CAST),
        ("List<Choice<FHIR.CodeableConcept, FHIR.string>>", "List<Concept>", ov.CAST),
        ("Choice<Integer, String>", "Integer", ov.CAST),
        ("Choice<Integer, String>", "Decimal", ov.NO_MATCH),
        ("Choice<ConditionProblemsHealthConcerns, AllergyIntolerance>", "Condition", ov.CAST),
        # A choice of profiles already is a list of the base type, and a base
        # type is compatible with a choice of its profiles (Status.verified).
        ("Choice<ConditionProblemsHealthConcerns, ConditionEncounterDiagnosis>", "Condition", ov.COMPATIBLE),
        ("Condition", "Choice<ConditionProblemsHealthConcerns, ConditionEncounterDiagnosis>", ov.COMPATIBLE),
        ("Condition", "List<Choice<ConditionProblemsHealthConcerns, ConditionEncounterDiagnosis>>", ov.LIST_PROMOTION),
        ("List<Condition>", "List<Choice<ConditionProblemsHealthConcerns, ConditionEncounterDiagnosis>>", ov.COMPATIBLE),
        ("List<Choice<ConditionProblemsHealthConcerns, ConditionEncounterDiagnosis>>", "List<Condition>", ov.COMPATIBLE),
        ("Condition", "List<Observation>", ov.NO_MATCH),
        ("Integer", "Choice<Integer, String>", ov.COMPATIBLE),
        ("Choice<Integer, String>", "Choice<Integer, String, Boolean>", ov.COMPATIBLE),
        ("Choice<Integer, String, Boolean>", "Choice<Integer, String>", ov.COMPATIBLE),
        ("Choice<Integer, String>", "Choice<Boolean, Date>", ov.NO_MATCH),
        # A FHIR ``effective`` choice passed to QICoreCommon.toInterval's choice.
        (
            "Choice<FHIR.dateTime, FHIR.Period, FHIR.Timing, FHIR.instant>",
            "Choice<DateTime, Quantity, Interval<DateTime>, Interval<Quantity>, Timing>",
            ov.COMPATIBLE,
        ),
        ("Tuple{a: Integer}", "Tuple{a: Integer}", ov.COMPATIBLE),
        ("Tuple{a: Integer, b: String}", "Tuple{a: Integer}", ov.COMPATIBLE),
        ("Tuple{a: Integer}", "Tuple{b: Integer}", ov.NO_MATCH),
    ],
)
def test_lists_intervals_choices_and_tuples(model, argument, parameter, expected):
    assert ov.conversion_rank(model, T(argument), T(parameter)) == expected


# ---------------------------------------------------------------------------
# Least-converting selection
# ---------------------------------------------------------------------------


def test_an_exact_match_wins_over_an_implicit_conversion():
    # A(Integer) and A(Decimal), called with an Integer.
    assert ov.resolve_least_converting([[ov.EXACT], [ov.IMPLICIT_SIMPLE]]).outcome == ov.UNIQUE
    assert ov.resolve_least_converting([[ov.IMPLICIT_SIMPLE], [ov.EXACT]]).index == 1


def test_less_converting_wins_whatever_the_declaration_order():
    # A(Decimal) and A(Quantity), called with an Integer: one conversion to a
    # simple type beats one conversion to a class type.
    selection = ov.resolve_least_converting([[ov.IMPLICIT_CLASS], [ov.IMPLICIT_SIMPLE]])
    assert (selection.outcome, selection.index) == (ov.UNIQUE, 1)


def test_candidates_that_cannot_be_called_are_dropped():
    selection = ov.resolve_least_converting([[ov.NO_MATCH], [ov.IMPLICIT_SIMPLE], [ov.NO_MATCH]])
    assert (selection.outcome, selection.index) == (ov.UNIQUE, 1)
    assert ov.resolve_least_converting([[ov.NO_MATCH]]).outcome == ov.NO_CANDIDATE
    assert ov.resolve_least_converting([]).outcome == ov.NO_CANDIDATE


def test_equal_conversion_counts_are_ambiguous():
    # A(Long) and A(Decimal), called with an Integer: one implicit conversion each.
    selection = ov.resolve_least_converting([[ov.IMPLICIT_SIMPLE], [ov.IMPLICIT_SIMPLE]])
    assert (selection.outcome, selection.tied) == (ov.AMBIGUOUS, (0, 1))
    # A(Integer, Decimal) and A(Decimal, Integer), called with (Integer, Integer).
    selection = ov.resolve_least_converting([[ov.EXACT, ov.IMPLICIT_SIMPLE], [ov.IMPLICIT_SIMPLE, ov.EXACT]])
    assert selection.tied == (0, 1)


def test_a_candidate_better_at_every_argument_dominates():
    selection = ov.resolve_least_converting([[ov.EXACT, ov.IMPLICIT_SIMPLE], [ov.IMPLICIT_SIMPLE, ov.IMPLICIT_SIMPLE]])
    assert (selection.outcome, selection.index) == (ov.UNIQUE, 0)
    # The dominated candidate does not make the survivors ambiguous.
    selection = ov.resolve_least_converting([[ov.EXACT, ov.IMPLICIT_SIMPLE], [ov.IMPLICIT_SIMPLE, ov.EXACT], [ov.IMPLICIT_SIMPLE, ov.IMPLICIT_SIMPLE]])
    assert selection.tied == (0, 1)


# ---------------------------------------------------------------------------
# Policy: unique, provable failure, or the documented fallback
# ---------------------------------------------------------------------------

DECLARED_INT_DEC = [[T("Integer")], [T("Decimal")]]


def test_choose_overload_returns_the_least_converting_candidate():
    assert ov.choose_overload("A", DECLARED_INT_DEC, [T("Decimal")], legacy_index=1) == (1, False)
    assert ov.choose_overload("A", DECLARED_INT_DEC, [T("Integer")], legacy_index=1) == (0, False)


def test_choose_overload_raises_the_ambiguous_resolution_error():
    # cql-tests #142 AmbiguousOverload.
    with pytest.raises(TranslationError, match=r"Ambiguous call to function 'A'\(Integer\).*'A\(Long\)', 'A\(Decimal\)'"):
        ov.choose_overload("A", [[T("Long")], [T("Decimal")]], [T("Integer")], legacy_index=1)


def test_choose_overload_raises_when_no_overload_is_callable_and_names_the_types():
    with pytest.raises(TranslationError, match=r"Cannot resolve call to function 'A'\(Decimal\).*A\(Integer\)"):
        ov.choose_overload("A", [[T("Integer")], [T("String")]], [T("Decimal")], legacy_index=1)
    # Asked about a lone candidate, the policy reports that it cannot take the
    # call: there is no Decimal -> Integer conversion to carry the argument
    # into it. (The inliner does not ask about calls with a single candidate.)
    with pytest.raises(TranslationError, match=r"Cannot resolve call to function 'A'\(Decimal\).*A\(Integer\)"):
        ov.choose_overload("A", [[T("Integer")]], [T("Decimal")], legacy_index=0)


def test_choose_overload_keeps_the_declaration_order_pick_for_an_unknown_argument(caplog):
    with caplog.at_level(logging.WARNING, logger="fhir4ds.cql.translator.overload"):
        assert ov.choose_overload("A", DECLARED_INT_DEC, [None], legacy_index=1) == (1, True)
    assert "cannot be told apart statically" in caplog.text


def test_choose_overload_cannot_tell_apart_overloads_that_share_a_value_model(caplog):
    # FHIRHelpers ToDateTime(value dateTime) / ToDateTime(value instant) for an
    # argument only known as DateTime: not a provable ambiguity.
    with caplog.at_level(logging.WARNING, logger="fhir4ds.cql.translator.overload"):
        chosen = ov.choose_overload(
            "FHIRHelpers.ToDateTime",
            [[T("dateTime")], [T("instant")], [T("date")]],
            [T("DateTime")],
            legacy_index=2,
        )
    assert chosen == (2, True)
    assert "FHIRHelpers.ToDateTime" in caplog.text


def test_choose_overload_warns_once_per_call_shape(caplog):
    ov._WARNED.clear()
    with caplog.at_level(logging.WARNING, logger="fhir4ds.cql.translator.overload"):
        for _ in range(3):
            ov.choose_overload("Once", DECLARED_INT_DEC, [None], legacy_index=1)
    assert caplog.text.count("Overloads of function 'Once'") == 1


# ---------------------------------------------------------------------------
# Fluent path: context.get_function / resolve_library_function
# ---------------------------------------------------------------------------


def _fluent(name: str, parameter_name: str, type_text: str):
    from fhir4ds.cql.parser.ast_nodes import (
        ListTypeSpecifier,
        NamedTypeSpecifier,
        ParameterDefinition,
    )
    from fhir4ds.cql.translator.context import FunctionInfo

    return FunctionInfo(
        name=name,
        parameters=[ParameterDefinition(
            name=parameter_name,
            type=ListTypeSpecifier(element_type=NamedTypeSpecifier(name=type_text)),
        )],
        expression=None,
        is_fluent=True,
    )


def test_receiver_that_is_a_profile_of_a_declared_type_selects_that_overload():
    # FHIRCommon.mostRecent: Observation, Procedure, MedicationRequest,
    # ServiceRequest overloads; a US Core "Vital Signs Profile" observation is
    # an Observation, not whichever overload was declared last.
    context = SQLTranslationContext()
    for parameter_name, type_text in (
        ("observations", "FHIR.Observation"),
        ("procedures", "FHIR.Procedure"),
        ("medicationRequests", "MedicationRequest"),
        ("serviceRequests", "FHIR.ServiceRequest"),
    ):
        context.define_function(_fluent("mostRecent", parameter_name, type_text))
    chosen = context.get_function("mostRecent", resource_type="Vital Signs Profile")
    assert chosen.parameters[0].name == "observations"
    chosen = context.get_function("mostRecent", resource_type="Blood Pressure Profile")
    assert chosen.parameters[0].name == "observations"


def test_receiver_type_the_heuristic_places_is_not_rescued():
    # The name heuristic already matches a profile whose name starts with the
    # declared type, so it keeps deciding.
    context = SQLTranslationContext()
    context.define_function(_fluent("isPerformed", "obs", "Observation"))
    context.define_function(_fluent("isPerformed", "requests", "ServiceRequest"))
    assert context.get_function("isPerformed", resource_type="ObservationScreeningAssessment").parameters[0].name == "obs"


def test_receiver_no_overload_takes_keeps_the_last_declared_overload_and_says_so(caplog):
    context = SQLTranslationContext()
    context.define_function(_fluent("isPerformed", "obs", "Observation"))
    context.define_function(_fluent("isPerformed", "requests", "ServiceRequest"))
    from fhir4ds.cql.translator import overload as ov

    ov._WARNED.clear()
    with caplog.at_level(logging.WARNING, logger="fhir4ds.cql.translator.overload"):
        chosen = context.get_function("isPerformed", resource_type="Location")
    assert chosen.parameters[0].name == "requests"
    assert "No overload of function 'isPerformed' takes a receiver of type 'Location'" in caplog.text


def test_receiver_rescue_leaves_a_single_overload_alone(caplog):
    # With one candidate the last-declared fallback is that candidate: nothing to rescue.
    context = SQLTranslationContext()
    context.define_function(_fluent("resulted", "obs", "FHIR.Observation"))
    with caplog.at_level(logging.WARNING, logger="fhir4ds.cql.translator.overload"):
        chosen = context.get_function("resulted", resource_type="PediatricBMIforAgeObservationProfile")
    assert chosen is context._functions["resulted"]
    assert "resulted" not in caplog.text


def test_library_functions_resolve_the_same_way():
    from fhir4ds.cql.translator.context import LibraryInfo

    context = SQLTranslationContext()
    library = LibraryInfo(name="FHIRCommon", alias="FHIRCommon")
    library.function_overloads["mostRecent"] = []
    for parameter_name, type_text in (("observations", "FHIR.Observation"), ("serviceRequests", "FHIR.ServiceRequest")):
        function = _fluent("mostRecent", parameter_name, type_text)
        library.functions[parameter_name] = function
        library.function_overloads["mostRecent"].append(function)
    context.includes["FHIRCommon"] = library
    resolved = context.resolve_library_function("FHIRCommon", "mostRecent", resource_type="SmokingStatusProfile")
    assert resolved.parameters[0].name == "observations"


def test_type_specifier_formatting_is_lossless():
    from fhir4ds.cql.parser.ast_nodes import (
        ChoiceTypeSpecifier,
        IntervalTypeSpecifier,
        ListTypeSpecifier,
        NamedTypeSpecifier,
        TupleElement,
        TupleTypeSpecifier,
    )

    assert ov.format_type_specifier(NamedTypeSpecifier(name="FHIR.Condition")) == "FHIR.Condition"
    assert ov.format_type_specifier(
        ListTypeSpecifier(element_type=NamedTypeSpecifier(name="FHIR.Condition"))
    ) == "List<FHIR.Condition>"
    assert ov.format_type_specifier(
        IntervalTypeSpecifier(point_type=NamedTypeSpecifier(name="DateTime"))
    ) == "Interval<DateTime>"
    assert ov.format_type_specifier(
        ChoiceTypeSpecifier(choices=[NamedTypeSpecifier(name="DateTime"), NamedTypeSpecifier(name="Quantity")])
    ) == "Choice<DateTime, Quantity>"
    assert ov.format_type_specifier(
        TupleTypeSpecifier(elements=[TupleElement(name="a", type=NamedTypeSpecifier(name="Integer"))])
    ) == "Tuple{a: Integer}"
    assert ov.format_type_specifier(None) is None
    assert ov.format_type_specifier("Integer") == "Integer"


# ---------------------------------------------------------------------------
# FHIR4-53: a fluent family whose RECEIVER cannot be placed is broken by the
# ---------------------------------------------------------------------------


def _fluent_two_params(name: str, first_name: str, first_type: str,
                       second_name: str, second_type: str, second_is_list: bool):
    from fhir4ds.cql.parser.ast_nodes import (
        ListTypeSpecifier,
        Literal,
        NamedTypeSpecifier,
        ParameterDefinition,
    )
    from fhir4ds.cql.translator.context import FunctionInfo

    second = NamedTypeSpecifier(name=second_type)
    return FunctionInfo(
        name=name,
        parameters=[
            ParameterDefinition(
                name=first_name,
                type=NamedTypeSpecifier(name=first_type),
            ),
            ParameterDefinition(
                name=second_name,
                type=ListTypeSpecifier(element_type=second) if second_is_list else second,
            ),
        ],
        # Argument-based resolution only considers overloads with a body: a
        # stub has nothing to inline, so the fill does not exist for it.
        expression=Literal(value=True),
        is_fluent=True,
    )


def _overlaps_family() -> SQLTranslationContext:
    """CMS145's ``overlapsDayOfEncounter`` pair, declared in source order."""
    context = SQLTranslationContext()
    context.define_function(_fluent_two_params(
        "overlapsDayOfEncounter",
        "Diagnosis", "ConditionProblemsHealthConcerns",
        "EncounterList", "Encounter", True,
    ))
    context.define_function(_fluent_two_params(
        "overlapsDayOfEncounter",
        "Diagnosis", "ConditionProblemsHealthConcerns",
        "TheEncounter", "Encounter", False,
    ))
    return context


def test_fluent_receiver_miss_is_broken_by_the_arguments():
    # A union of two US-QUALITY-CORE Condition profiles resolves to the base
    # type `Condition`, which names NO declared receiver, so both overloads are
    # equally uncalled-for. The by-name answer would be the LAST-DECLARED one
    # ("TheEncounter" — a SINGLE Encounter); inlining that shape over a
    # List<Encounter> argument turns the whole list into the iteration source,
    # one row per element, which every strict connection rejects.
    from fhir4ds.cql.parser.ast_nodes import Retrieve

    context = _overlaps_family()
    chosen = context.get_function(
        "overlapsDayOfEncounter",
        resource_type="Condition",
        argument_nodes=[Retrieve(type="Encounter")],
    )
    assert chosen.parameters[1].name == "EncounterList"


def test_fluent_receiver_miss_without_discriminating_arguments_keeps_last_declared(caplog):
    context = _overlaps_family()
    ov._WARNED.clear()
    with caplog.at_level(logging.WARNING, logger="fhir4ds.cql.translator.overload"):
        # No arguments to discriminate with: today's answer stands, and the
        # warning now names the arguments as the reason nothing could decide.
        chosen = context.get_function("overlapsDayOfEncounter", resource_type="Condition")
    assert chosen.parameters[1].name == "TheEncounter"
    assert "do not pick one either" in caplog.text


def test_fluent_arguments_that_tie_do_not_pick_a_side():
    # Identical declared signatures: the arguments cannot discriminate, so the
    # tie must NOT be resolved by argument order (a changed answer on an
    # ambiguous call would be a regression, not a fix).
    from fhir4ds.cql.parser.ast_nodes import Retrieve

    context = SQLTranslationContext()
    context.define_function(_fluent_two_params(
        "pick", "Diagnosis", "ConditionProblemsHealthConcerns",
        "One", "Encounter", True,
    ))
    context.define_function(_fluent_two_params(
        "pick", "Diagnosis", "ConditionProblemsHealthConcerns",
        "Two", "Encounter", True,
    ))
    chosen = context.get_function(
        "pick", resource_type="Condition", argument_nodes=[Retrieve(type="Encounter")]
    )
    assert chosen.parameters[1].name == "Two"
