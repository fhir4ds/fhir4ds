"""
Unit tests for include error handling (QA8-001, QA8-002).

Tests verify:
- Circular include detection raises CircularIncludeError
- Missing library_loader with includes raises TranslationError
"""

import pytest
from ...parser import parse_cql
from ...errors import CircularIncludeError, TranslationError
from ...translator import CQLToSQLTranslator


class TestCircularIncludeDetection:
    """QA8-002: Circular include detection."""

    def test_direct_circular_include_raises_error(self):
        """Two libraries that include each other raise CircularIncludeError."""
        lib_a_cql = """
        library LibA version '1.0.0'
        using QICore version '4.1.1'
        include LibB version '1.0.0' called LibB

        context Patient

        define "DefA":
            true
        """

        lib_b_cql = """
        library LibB version '1.0.0'
        using QICore version '4.1.1'
        include LibA version '1.0.0' called LibA

        context Patient

        define "DefB":
            true
        """

        lib_a = parse_cql(lib_a_cql)
        lib_b = parse_cql(lib_b_cql)

        def loader(path):
            if path == "LibB":
                return lib_b
            if path == "LibA":
                return lib_a
            return None

        translator = CQLToSQLTranslator(library_loader=loader)
        with pytest.raises(CircularIncludeError, match="Circular include detected"):
            translator.translate_library_to_population_sql(lib_a)

    def test_transitive_circular_include_raises_error(self):
        """A -> B -> C -> A raises CircularIncludeError."""
        lib_a_cql = """
        library LibA version '1.0.0'
        using QICore version '4.1.1'
        include LibB version '1.0.0' called LibB
        context Patient
        define "DefA": true
        """

        lib_b_cql = """
        library LibB version '1.0.0'
        using QICore version '4.1.1'
        include LibC version '1.0.0' called LibC
        context Patient
        define "DefB": true
        """

        lib_c_cql = """
        library LibC version '1.0.0'
        using QICore version '4.1.1'
        include LibA version '1.0.0' called LibA
        context Patient
        define "DefC": true
        """

        lib_a = parse_cql(lib_a_cql)
        lib_b = parse_cql(lib_b_cql)
        lib_c = parse_cql(lib_c_cql)

        def loader(path):
            libs = {"LibA": lib_a, "LibB": lib_b, "LibC": lib_c}
            return libs.get(path)

        translator = CQLToSQLTranslator(library_loader=loader)
        with pytest.raises(CircularIncludeError, match="Circular include detected"):
            translator.translate_library_to_population_sql(lib_a)

    def test_diamond_include_does_not_raise(self):
        """Diamond pattern (A->B, A->C, B->D, C->D) is not circular."""
        lib_a_cql = """
        library LibA version '1.0.0'
        using QICore version '4.1.1'
        include LibB version '1.0.0' called LibB
        include LibC version '1.0.0' called LibC
        context Patient
        define "DefA": true
        """

        lib_b_cql = """
        library LibB version '1.0.0'
        using QICore version '4.1.1'
        include LibD version '1.0.0' called LibD
        context Patient
        define "DefB": true
        """

        lib_c_cql = """
        library LibC version '1.0.0'
        using QICore version '4.1.1'
        include LibD version '1.0.0' called LibD
        context Patient
        define "DefC": true
        """

        lib_d_cql = """
        library LibD version '1.0.0'
        using QICore version '4.1.1'
        context Patient
        define "DefD": true
        """

        lib_a = parse_cql(lib_a_cql)
        lib_b = parse_cql(lib_b_cql)
        lib_c = parse_cql(lib_c_cql)
        lib_d = parse_cql(lib_d_cql)

        def loader(path):
            libs = {"LibA": lib_a, "LibB": lib_b, "LibC": lib_c, "LibD": lib_d}
            return libs.get(path)

        translator = CQLToSQLTranslator(library_loader=loader)
        # Should not raise — diamond is valid
        sql = translator.translate_library_to_population_sql(lib_a)
        assert sql is not None

    def test_circular_include_error_has_chain(self):
        """CircularIncludeError includes the include chain."""
        lib_a_cql = """
        library LibA version '1.0.0'
        using QICore version '4.1.1'
        include LibB version '1.0.0' called LibB
        context Patient
        define "DefA": true
        """

        lib_b_cql = """
        library LibB version '1.0.0'
        using QICore version '4.1.1'
        include LibA version '1.0.0' called LibA
        context Patient
        define "DefB": true
        """

        lib_a = parse_cql(lib_a_cql)
        lib_b = parse_cql(lib_b_cql)

        def loader(path):
            if path == "LibB":
                return lib_b
            if path == "LibA":
                return lib_a
            return None

        translator = CQLToSQLTranslator(library_loader=loader)
        with pytest.raises(CircularIncludeError) as exc_info:
            translator.translate_library_to_population_sql(lib_a)

        assert exc_info.value.library_path == "LibA"
        assert exc_info.value.include_chain is not None
        assert len(exc_info.value.include_chain) >= 2


class TestMissingLibraryLoader:
    """QA8-001: Missing library_loader with includes."""

    def test_no_loader_with_includes_raises_on_reference(self):
        """Referencing an unresolved include raises TranslationError."""
        cql = """
        library Main version '1.0.0'
        using QICore version '4.1.1'
        include SomeLib version '1.0.0' called SomeLib

        context Patient

        define "Test":
            exists SomeLib."Def1"
        """

        lib = parse_cql(cql)
        translator = CQLToSQLTranslator()  # No library_loader

        with pytest.raises(TranslationError, match="no library_loader was configured"):
            translator.translate_library_to_population_sql(lib)

    def test_no_loader_includes_registered_without_reference(self):
        """Includes are registered even without a loader, as long as they aren't referenced."""
        cql = """
        library Main version '1.0.0'
        using QICore version '4.1.1'
        include SomeLib version '1.0.0' called SomeLib

        context Patient

        define "Test":
            true
        """

        lib = parse_cql(cql)
        translator = CQLToSQLTranslator()  # No library_loader
        sql = translator.translate_library_to_population_sql(lib)
        assert sql is not None
        # Include should be registered in context
        assert "SomeLib" in translator._context.includes

    def test_no_loader_without_includes_succeeds(self):
        """Library with no includes works fine without a loader."""
        cql = """
        library Main version '1.0.0'
        using QICore version '4.1.1'

        context Patient

        define "Test":
            true
        """

        lib = parse_cql(cql)
        translator = CQLToSQLTranslator()
        sql = translator.translate_library_to_population_sql(lib)
        assert sql is not None
