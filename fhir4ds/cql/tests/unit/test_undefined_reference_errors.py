"""
Unit tests for undefined reference detection (QA9-001, QA9-002).

Tests verify:
- Undefined definition references raise TranslationError at translation time
- Unknown function calls raise TranslationError at translation time
- Valid references continue to work normally
"""

import pytest
from ...parser import parse_cql
from ...errors import TranslationError
from ...translator import CQLToSQLTranslator


class TestUndefinedDefinitionReference:
    """QA9-001: Undefined definition references should raise TranslationError."""

    def test_undefined_definition_raises_error(self):
        """Referencing a non-existent definition raises TranslationError."""
        cql = """
        library Test version '1.0.0'
        using FHIR version '4.0.1'

        context Patient

        define "MyDef":
            NonExistentDefinition
        """
        lib = parse_cql(cql)
        translator = CQLToSQLTranslator()
        with pytest.raises(TranslationError, match="Undefined reference 'NonExistentDefinition'"):
            translator.translate_library_to_population_sql(lib)

    def test_undefined_definition_error_includes_available_names(self):
        """Error message includes available definition names for discovery."""
        cql = """
        library Test version '1.0.0'
        using FHIR version '4.0.1'

        context Patient

        define "RealDef":
            true

        define "MyDef":
            TypoInDefinition
        """
        lib = parse_cql(cql)
        translator = CQLToSQLTranslator()
        with pytest.raises(TranslationError, match="Available names:.*RealDef"):
            translator.translate_library_to_population_sql(lib)

    def test_valid_definition_reference_works(self):
        """Referencing a valid definition continues to work."""
        cql = """
        library Test version '1.0.0'
        using FHIR version '4.0.1'

        context Patient

        define "BaseDef":
            true

        define "MyDef":
            "BaseDef"
        """
        lib = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(lib)
        assert sql is not None

    def test_parameter_reference_works(self):
        """Referencing a valid parameter continues to work."""
        cql = """
        library Test version '1.0.0'
        using FHIR version '4.0.1'

        parameter "Measurement Period" Interval<DateTime>

        context Patient

        define "MyDef":
            "Measurement Period"
        """
        lib = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(lib)
        assert sql is not None


class TestUnknownFunctionCall:
    """QA9-002: Unknown function calls should raise TranslationError."""

    def test_unknown_function_raises_error(self):
        """Calling a non-existent function raises TranslationError."""
        cql = """
        library Test version '1.0.0'
        using FHIR version '4.0.1'

        context Patient

        define "MyDef":
            NonExistentFunction(1, 2)
        """
        lib = parse_cql(cql)
        translator = CQLToSQLTranslator()
        with pytest.raises(TranslationError, match="Unknown function 'NonExistentFunction'"):
            translator.translate_library_to_population_sql(lib)

    def test_unknown_function_error_shows_arity(self):
        """Error message includes the arity of the unknown function call."""
        cql = """
        library Test version '1.0.0'
        using FHIR version '4.0.1'

        context Patient

        define "MyDef":
            MadeUpFunc(1, 2, 3)
        """
        lib = parse_cql(cql)
        translator = CQLToSQLTranslator()
        with pytest.raises(TranslationError, match="3 argument"):
            translator.translate_library_to_population_sql(lib)

    def test_known_function_works(self):
        """Calling a known CQL function continues to work."""
        cql = """
        library Test version '1.0.0'
        using FHIR version '4.0.1'

        context Patient

        define "MyDef":
            AgeInYears()
        """
        lib = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(lib)
        assert sql is not None
