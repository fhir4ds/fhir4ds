"""Fast synthetic coverage for function CTE promotion behavior.

These tests intentionally avoid DQM measure discovery and execution. They use
tiny CQL libraries to exercise the SQL-size optimization path directly.
"""

from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator import CQLToSQLTranslator


def _translate(cql: str) -> tuple[str, CQLToSQLTranslator]:
    library = parse_cql(cql)
    translator = CQLToSQLTranslator()
    sql = translator.translate_library_to_population_sql(
        library,
        output_columns={"A": "A"},
    )
    return sql, translator


def test_promoted_function_cte_can_depend_on_another_definition() -> None:
    """A promoted function CTE may be emitted after the definition it reads."""
    sql, translator = _translate(
        """library Test version '1.0.0'
using FHIR version '4.0.1'

define "Other":
  [Condition]

define "Obs":
  [Observation]

define function Foo(o FHIR.Observation):
  exists("Other")

define "A":
  "Obs" O where Foo(O) or Foo(O) or Foo(O)
"""
    )

    assert ("Foo", "Obs") in translator._context._promoted_cte_keys
    assert translator._context._function_cte_deps[("Foo", "Obs")] == {"Other"}

    other_pos = sql.index('"Other" AS')
    fn_pos = sql.index('"_fn_Foo_Obs_5f33f7" AS')
    consumer_pos = sql.index('"A" AS')
    assert other_pos < fn_pos < consumer_pos
    assert 'FROM "Other" AS sub' in sql


def test_promotes_repeated_calls_on_with_clause_alias() -> None:
    """Repeated function calls on a relationship alias should be promotion candidates."""
    sql, translator = _translate(
        """library Test version '1.0.0'
using FHIR version '4.0.1'

define "Source":
  [Encounter]

define "Related":
  [Encounter]

define function Foo(e FHIR.Encounter):
  e.status = 'finished'

define "A":
  "Source" S
    with "Related" R such that Foo(R) or Foo(R) or Foo(R)
"""
    )

    assert ("Foo", "Related") in translator._context.promoted_functions
    assert ("Foo", "Related") in translator._context._promoted_cte_keys
    assert '"_fn_Foo_Related_978079" AS' in sql
    assert "_fv.patient_id = R.patient_id" in sql
    assert "_fv._row_key = fhirpath_text(R.resource, 'id')" in sql


def test_source_resource_type_inference_uses_query_row_shape_not_relationship_retrieves() -> None:
    """A with-clause retrieve should not decide the source definition's row type."""
    library = parse_cql(
        """library Test version '1.0.0'
using FHIR version '4.0.1'

define "Base Encounter":
  [Encounter]

define "Encounter With Procedure":
  "Base Encounter" E
    with [Procedure] P such that P.status = 'completed'
"""
    )
    translator = CQLToSQLTranslator()

    assert translator._get_source_definition_resource_type(library, "Encounter With Procedure") == "Encounter"


def test_choice_case_prunes_dead_temporal_branch_for_concrete_source_type() -> None:
    """Choice-type case expressions should skip incompatible resource branches."""
    sql, _translator = _translate(
        """library Test version '1.0.0'
using FHIR version '4.0.1'

context Patient

define "Procedures":
  [Procedure]

define fluent function ChoiceDate(choice Choice<Procedure, Observation>):
  case
    when choice is Procedure then (choice as Procedure).performed
    when choice is Observation then (choice as Observation).effective
    else null
  end

define "A":
  "Procedures" P
    return P.ChoiceDate()
"""
    )

    assert "= 'Observation'" not in sql
    assert "effective" not in sql
    assert "performed" in sql
