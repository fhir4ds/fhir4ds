"""
Unit tests for CQL parser FHIR-specific type handling.

Task C1: Tests for FHIR keyword types in function parameters, & concatenation operator,
and additional parser fixes (type constructor lookahead, keyword-as-identifier,
qualified codesystem refs, collapse per, return all/distinct, let clause keywords).
"""

import pytest

from ...parser import parse_cql
from ...parser.lexer import Lexer, TokenType


class TestResourceTypeInParameters:
    """Task C1 Bug 1: FHIR keyword types in function parameters."""

    def test_resource_type_in_fluent_function_param(self):
        """Resource type should be recognized in function parameter lists."""
        cql = """
        library Test version '1.0'
        using FHIR version '4.0.1'
        define fluent function references(reference Reference, resource Resource):
          resource.id = Last(Split(reference.reference, '/'))
        """
        library = parse_cql(cql)
        funcs = [d for d in library.statements if hasattr(d, 'parameters')]
        assert len(funcs) == 1
        assert funcs[0].parameters[1].type is not None
        assert funcs[0].parameters[1].type.name == "Resource"

    def test_patient_type_in_function_param(self):
        """Patient type should be recognized in function parameter lists."""
        cql = """
        library Test version '1.0'
        using FHIR version '4.0.1'
        define function getAge(p Patient):
          CalculateAgeInYearsAt(p.birthDate, Today())
        """
        library = parse_cql(cql)
        funcs = [d for d in library.statements if hasattr(d, 'parameters')]
        assert len(funcs) == 1
        assert funcs[0].parameters[0].type is not None
        assert funcs[0].parameters[0].type.name == "Patient"

    def test_practitioner_type_in_function_param(self):
        """Practitioner type should be recognized in function parameter lists."""
        cql = """
        library Test version '1.0'
        using FHIR version '4.0.1'
        define function getPractitionerName(pract Practitioner):
          practitioner.name
        """
        library = parse_cql(cql)
        funcs = [d for d in library.statements if hasattr(d, 'parameters')]
        assert len(funcs) == 1
        assert funcs[0].parameters[0].type is not None
        assert funcs[0].parameters[0].type.name == "Practitioner"

    def test_organization_type_in_function_param(self):
        """Organization type should be recognized in function parameter lists."""
        cql = """
        library Test version '1.0'
        using FHIR version '4.0.1'
        define function getOrgName(org Organization):
          org.name
        """
        library = parse_cql(cql)
        funcs = [d for d in library.statements if hasattr(d, 'parameters')]
        assert len(funcs) == 1
        assert funcs[0].parameters[0].type is not None
        assert funcs[0].parameters[0].type.name == "Organization"

    def test_location_type_in_function_param(self):
        """Location type should be recognized in function parameter lists."""
        cql = """
        library Test version '1.0'
        using FHIR version '4.0.1'
        define function getLocName(loc Location):
          loc.name
        """
        library = parse_cql(cql)
        funcs = [d for d in library.statements if hasattr(d, 'parameters')]
        assert len(funcs) == 1
        assert funcs[0].parameters[0].type is not None
        assert funcs[0].parameters[0].type.name == "Location"

    def test_bundle_type_in_function_param(self):
        """Bundle type should be recognized in function parameter lists."""
        cql = """
        library Test version '1.0'
        using FHIR version '4.0.1'
        define function getBundleEntries(b Bundle):
          b.entry
        """
        library = parse_cql(cql)
        funcs = [d for d in library.statements if hasattr(d, 'parameters')]
        assert len(funcs) == 1
        assert funcs[0].parameters[0].type is not None
        assert funcs[0].parameters[0].type.name == "Bundle"

    def test_resource_type_in_parameter_definition(self):
        """FHIR types should work in top-level parameter definitions too."""
        cql = """
        library Test version '1.0'
        using FHIR version '4.0.1'
        parameter MyResource Resource
        context Patient
        define Foo: true
        """
        library = parse_cql(cql)
        params = library.parameters
        assert len(params) == 1
        assert params[0].type is not None
        assert params[0].type.name == "Resource"

    def test_patient_type_in_parameter_definition(self):
        """Patient type should work in top-level parameter definitions."""
        cql = """
        library Test version '1.0'
        using FHIR version '4.0.1'
        parameter MyPatient Patient
        context Patient
        define Foo: true
        """
        library = parse_cql(cql)
        params = library.parameters
        assert len(params) == 1
        assert params[0].type is not None
        assert params[0].type.name == "Patient"


class TestConcatenateOperator:
    """Task C1 Bug 2: & concatenation operator."""

    def test_ampersand_lexing(self):
        """& should be lexed as CONCATENATE token."""
        lexer = Lexer("'Hello' & 'World'")
        tokens = lexer.tokenize()
        # Filter out EOF
        tokens = [t for t in tokens if t.type != TokenType.EOF]
        assert len(tokens) == 3
        assert tokens[0].type == TokenType.STRING
        assert tokens[1].type == TokenType.CONCATENATE
        assert tokens[1].value == "&"
        assert tokens[2].type == TokenType.STRING

    def test_ampersand_concatenation(self):
        """& should be lexed as CONCATENATE and parsed as binary expression."""
        cql = """
        library Test version '1.0'
        context Patient
        define Greeting: 'Hello' & ' ' & 'World'
        """
        library = parse_cql(cql)
        # Should parse without error
        assert len(library.statements) == 1

    def test_ampersand_with_property_access(self):
        """& should work between string literals and property accesses."""
        cql = """
        library Test version '1.0'
        using FHIR version '4.0.1'
        context Patient
        define Msg: 'Name: ' & Patient.name
        """
        library = parse_cql(cql)
        assert len(library.statements) == 1

    def test_ampersand_multiple_concatenations(self):
        """Multiple & operators should parse correctly."""
        cql = """
        library Test version '1.0'
        context Patient
        define FullMsg: 'Prefix: ' & 'middle' & ' suffix' & ' end'
        """
        library = parse_cql(cql)
        assert len(library.statements) == 1

    def test_ampersand_in_function_body(self):
        """& should work inside function body expressions."""
        cql = """
        library Test version '1.0'
        define function makeGreeting(name String):
          'Hello, ' & name & '!'
        """
        library = parse_cql(cql)
        funcs = [d for d in library.statements if hasattr(d, 'parameters')]
        assert len(funcs) == 1


class TestQICoreCommonParsing:
    """Integration test: QICoreCommon.cql should now parse end-to-end."""

    def test_qicorecommon_parses(self):
        """QICoreCommon.cql should parse without errors after C1 fixes."""
        import os
        qicore_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..",
            "benchmarking", "ecqm-content-qicore-2025", "input", "cql", "QICoreCommon.cql"
        )
        if not os.path.exists(qicore_path):
            pytest.skip("QICoreCommon.cql not found")
        with open(qicore_path, 'r') as f:
            cql = f.read()
        library = parse_cql(cql)
        # Should have many definitions including the `references` functions
        assert len(library.statements) > 20

    def test_fhirhelpers_parses(self):
        """FHIRHelpers.cql should parse without errors after & fix."""
        import os
        fh_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..",
            "benchmarking", "ecqm-content-qicore-2025", "input", "cql", "FHIRHelpers.cql"
        )
        if not os.path.exists(fh_path):
            pytest.skip("FHIRHelpers.cql not found")
        with open(fh_path, 'r') as f:
            cql = f.read()
        library = parse_cql(cql)
        assert len(library.statements) > 0


class TestTypeConstructorLookahead:
    """Bug 3: Type keywords like 'quantity' should only be constructors when followed by '{'."""

    def test_quantity_as_variable_name(self):
        """'quantity' without '{' should be treated as identifier, not constructor."""
        cql = """
        library Test version '1.0'
        context Patient
        define Test:
          [Observation] O
            let quantity: O.value
            return quantity
        """
        library = parse_cql(cql)
        assert len(library.statements) == 1

    def test_quantity_as_constructor(self):
        """'Quantity { value: 1, unit: 'mg' }' should still parse as constructor."""
        cql = """
        library Test version '1.0'
        context Patient
        define Test: Quantity { value: 1, unit: 'mg' }
        """
        library = parse_cql(cql)
        assert len(library.statements) == 1

    def test_code_as_variable_name(self):
        """'code' (lowercase) should be usable as identifier."""
        cql = """
        library Test version '1.0'
        context Patient
        define Test:
          [Condition] C
            let code: C.code
            return code
        """
        library = parse_cql(cql)
        assert len(library.statements) == 1


class TestKeywordAsIdentifier:
    """Bugs 4,11,12: Keywords like 'version', 'is', 'date' should work as identifiers."""

    def test_version_as_identifier(self):
        """'version' should be usable as variable/let name."""
        cql = """
        library Test version '1.0'
        context Patient
        define Test:
          [Observation] O
            let version: O.meta.versionId
            return version
        """
        library = parse_cql(cql)
        assert len(library.statements) == 1

    def test_is_as_function_name(self):
        """'is' should be usable as a function name."""
        cql = """
        library Test version '1.0'
        using FHIR version '4.0.1'
        define fluent function is(condition Condition, category String):
          condition.category.coding.code contains category
        """
        library = parse_cql(cql)
        funcs = [d for d in library.statements if hasattr(d, 'parameters')]
        assert len(funcs) == 1

    def test_code_as_parameter_type(self):
        """'code' (lowercase, CODE token) should be accepted as parameter type."""
        cql = """
        library Test version '1.0'
        define function checkCode(c code):
          c
        """
        library = parse_cql(cql)
        funcs = [d for d in library.statements if hasattr(d, 'parameters')]
        assert len(funcs) == 1
        assert funcs[0].parameters[0].type is not None

    def test_date_as_parameter_type(self):
        """'date' (lowercase, DATE_FROM token) should be accepted as parameter type."""
        cql = """
        library Test version '1.0'
        define function checkDate(d date):
          d
        """
        library = parse_cql(cql)
        funcs = [d for d in library.statements if hasattr(d, 'parameters')]
        assert len(funcs) == 1


class TestQualifiedCodesystemRef:
    """Bug 7: Qualified codesystem references like QICoreCommon."SNOMEDCT"."""

    def test_qualified_codesystem_in_code_def(self):
        """code X: 'value' from QualifiedLib."CodeSystem" should parse."""
        cql = """
        library Test version '1.0'
        codesystem "SNOMEDCT": 'http://snomed.info/sct'
        code "foo": '12345' from QICoreCommon."SNOMEDCT"
        context Patient
        define Foo: true
        """
        library = parse_cql(cql)
        assert len(library.codes) >= 1


class TestCollapsePer:
    """Bug 9: 'collapse X per day' should be supported like 'expand'."""

    def test_collapse_per_day(self):
        """collapse ... per day should parse without errors."""
        cql = """
        library Test version '1.0'
        context Patient
        define Test:
          collapse { Interval[@2024-01-01, @2024-01-05] } per day
        """
        library = parse_cql(cql)
        assert len(library.statements) == 1


class TestReturnAllDistinct:
    """Bug 10: 'return all' and 'return distinct' should be supported."""

    def test_return_all(self):
        """'return all X' should parse."""
        cql = """
        library Test version '1.0'
        context Patient
        define Test:
          [Observation] O
            return all O.value
        """
        library = parse_cql(cql)
        assert len(library.statements) == 1

    def test_return_distinct(self):
        """'return distinct X' should parse."""
        cql = """
        library Test version '1.0'
        context Patient
        define Test:
          [Observation] O
            return distinct O.code
        """
        library = parse_cql(cql)
        assert len(library.statements) == 1


class TestLetClauseKeywordIdentifiers:
    """Bug 8: Let clause comma-lookahead should handle keyword-as-identifier names."""

    def test_multiple_lets_with_keyword_names(self):
        """Multiple let bindings where names are keyword tokens should parse."""
        cql = """
        library Test version '1.0'
        context Patient
        define Test:
          [Observation] O
            let quantity: O.value,
                version: O.meta.versionId
            return quantity
        """
        library = parse_cql(cql)
        assert len(library.statements) == 1


class TestAllCQLLibrariesParse:
    """All CQL library files used in CMS165 should parse end-to-end."""

    def test_status_cql_parses(self):
        """Status.cql should parse without errors."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..",
            "benchmarking", "ecqm-content-qicore-2025", "input", "cql", "Status.cql"
        )
        if not os.path.exists(path):
            pytest.skip("Status.cql not found")
        with open(path, 'r') as f:
            cql = f.read()
        library = parse_cql(cql)
        assert len(library.statements) > 10

    def test_cumulative_medication_duration_parses(self):
        """CumulativeMedicationDuration.cql should parse without errors."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..",
            "benchmarking", "ecqm-content-qicore-2025", "input", "cql", "CumulativeMedicationDuration.cql"
        )
        if not os.path.exists(path):
            pytest.skip("CumulativeMedicationDuration.cql not found")
        with open(path, 'r') as f:
            cql = f.read()
        library = parse_cql(cql)
        assert len(library.statements) > 10
