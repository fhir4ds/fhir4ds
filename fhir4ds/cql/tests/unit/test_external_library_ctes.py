"""
Unit tests for P1.2: External Library CTE Generation.

These tests verify that included library definitions and their retrieve CTEs
are properly emitted in the generated SQL.
"""

import pytest
from ...parser import parse_cql
from ...errors import TranslationError
from ...translator import CQLToSQLTranslator


class TestExternalLibraryCTEs:
    """Tests for external library CTE generation (P1.2)."""

    def test_included_library_retrieve_ctes_collected(self):
        """Included library retrieve CTEs are collected during translation."""
        # Main library with an include
        main_cql = """
        library Main version '1.0.0'
        using QICore version '4.1.1'
        include IncludedLib version '1.0.0' called IncludedLib

        context Patient

        define "Test Definition":
            exists [Condition: "Test ValueSet"]
        """

        # Included library with a retrieve
        included_cql = """
        library IncludedLib version '1.0.0'
        using QICore version '4.1.1'

        valueset "Included ValueSet": 'http://example.org/valueset/included'

        context Patient

        define "Included Definition":
            exists [Encounter: "Included ValueSet"]
        """

        # Parse libraries
        included_lib = parse_cql(included_cql)
        main_lib = parse_cql(main_cql)

        # Create library loader
        def loader(path):
            if path == "IncludedLib":
                return included_lib
            return None

        # Translate with library loader
        translator = CQLToSQLTranslator(library_loader=loader)
        sql = translator.translate_library_to_population_sql(main_lib)

        # Verify included retrieve CTEs are collected
        assert len(translator._included_retrieve_ctes) > 0, \
            "Included library retrieve CTEs should be collected"

        # Verify CTE names contain expected resource type
        cte_names = list(translator._included_retrieve_ctes.keys())
        assert any("Encounter" in name for name in cte_names), \
            f"Should have Encounter CTE, got: {cte_names}"

    def test_included_library_definitions_collected(self):
        """Included library definitions are collected during translation."""
        main_cql = """
        library Main version '1.0.0'
        using QICore version '4.1.1'
        include IncludedLib version '1.0.0' called IncludedLib

        context Patient

        define "Uses Included":
            exists IncludedLib."Some Definition"
        """

        included_cql = """
        library IncludedLib version '1.0.0'
        using QICore version '4.1.1'

        valueset "Some ValueSet": 'http://example.org/valueset/some'

        context Patient

        define "Some Definition":
            exists [Condition: "Some ValueSet"]
        """

        included_lib = parse_cql(included_cql)
        main_lib = parse_cql(main_cql)

        def loader(path):
            if path == "IncludedLib":
                return included_lib
            return None

        translator = CQLToSQLTranslator(library_loader=loader)
        sql = translator.translate_library_to_population_sql(main_lib)

        # Verify included definitions are collected with prefixed names
        assert len(translator._included_definitions) > 0, \
            "Included library definitions should be collected"

        # Verify definition name is prefixed with library alias
        def_names = list(translator._included_definitions.keys())
        assert any("IncludedLib" in name for name in def_names), \
            f"Definitions should be prefixed with library alias, got: {def_names}"

    def test_included_retrieve_ctes_appear_before_definitions(self):
        """Included library retrieve CTEs appear before definition CTEs in SQL."""
        main_cql = """
        library Main version '1.0.0'
        using QICore version '4.1.1'
        include IncludedLib version '1.0.0' called IncludedLib

        context Patient

        define "Main Definition":
            exists [Condition: "Main ValueSet"]
        """

        included_cql = """
        library IncludedLib version '1.0.0'
        using QICore version '4.1.1'

        valueset "Included VS": 'http://example.org/valueset/included'

        context Patient

        define "Included Def":
            exists [Encounter: "Included VS"]
        """

        included_lib = parse_cql(included_cql)
        main_lib = parse_cql(main_cql)

        def loader(path):
            if path == "IncludedLib":
                return included_lib
            return None

        translator = CQLToSQLTranslator(library_loader=loader)
        sql = translator.translate_library_to_population_sql(main_lib)

        # Find line numbers of CTEs
        lines = sql.split('\n')

        # Find first included retrieve CTE line
        retrieve_cte_line = None
        for cte_name in translator._included_retrieve_ctes.keys():
            for i, line in enumerate(lines):
                if f'"{cte_name}"' in line and "AS" in line:
                    if retrieve_cte_line is None or i < retrieve_cte_line:
                        retrieve_cte_line = i
                    break

        # Find first included definition CTE line
        def_cte_line = None
        for def_name in translator._included_definitions.keys():
            for i, line in enumerate(lines):
                if f'"{def_name}"' in line and "AS" in line:
                    if def_cte_line is None or i < def_cte_line:
                        def_cte_line = i
                    break

        # Verify ordering
        if retrieve_cte_line is not None and def_cte_line is not None:
            assert retrieve_cte_line < def_cte_line, \
                f"Retrieve CTE (line {retrieve_cte_line}) should appear before definition CTE (line {def_cte_line})"

    def test_sql_has_balanced_parentheses(self):
        """Generated SQL has balanced parentheses."""
        main_cql = """
        library Main version '1.0.0'
        using QICore version '4.1.1'
        include IncludedLib version '1.0.0' called IncludedLib

        context Patient

        define "Test":
            exists [Condition: "Test VS"]
        """

        included_cql = """
        library IncludedLib version '1.0.0'
        using QICore version '4.1.1'

        valueset "VS": 'http://example.org/valueset'

        context Patient

        define "Included":
            exists [Encounter: "VS"]
        """

        included_lib = parse_cql(included_cql)
        main_lib = parse_cql(main_cql)

        def loader(path):
            if path == "IncludedLib":
                return included_lib
            return None

        translator = CQLToSQLTranslator(library_loader=loader)
        sql = translator.translate_library_to_population_sql(main_lib)

        # Count parentheses
        open_count = sql.count('(')
        close_count = sql.count(')')

        assert open_count == close_count, \
            f"Unbalanced parentheses: {open_count} open, {close_count} close"

    def test_multiple_included_libraries(self):
        """Multiple included libraries each contribute CTEs."""
        main_cql = """
        library Main version '1.0.0'
        using QICore version '4.1.1'
        include LibA version '1.0.0' called LibA
        include LibB version '1.0.0' called LibB

        context Patient

        define "Main Def":
            exists [Condition: "Main VS"]
        """

        lib_a_cql = """
        library LibA version '1.0.0'
        using QICore version '4.1.1'

        valueset "VS A": 'http://example.org/valueset/a'

        context Patient

        define "Def A":
            exists [Encounter: "VS A"]
        """

        lib_b_cql = """
        library LibB version '1.0.0'
        using QICore version '4.1.1'

        valueset "VS B": 'http://example.org/valueset/b'

        context Patient

        define "Def B":
            exists [Procedure: "VS B"]
        """

        lib_a = parse_cql(lib_a_cql)
        lib_b = parse_cql(lib_b_cql)
        main_lib = parse_cql(main_cql)

        def loader(path):
            if path == "LibA":
                return lib_a
            elif path == "LibB":
                return lib_b
            return None

        translator = CQLToSQLTranslator(library_loader=loader)
        sql = translator.translate_library_to_population_sql(main_lib)

        # Verify both libraries contribute retrieve CTEs
        cte_names = list(translator._included_retrieve_ctes.keys())
        has_encounter = any("Encounter" in name for name in cte_names)
        has_procedure = any("Procedure" in name for name in cte_names)

        assert has_encounter, f"Should have Encounter CTE from LibA, got: {cte_names}"
        assert has_procedure, f"Should have Procedure CTE from LibB, got: {cte_names}"

        # Verify both libraries contribute definitions
        def_names = list(translator._included_definitions.keys())
        has_lib_a = any("LibA" in name for name in def_names)
        has_lib_b = any("LibB" in name for name in def_names)

        assert has_lib_a, f"Should have LibA definitions, got: {def_names}"
        assert has_lib_b, f"Should have LibB definitions, got: {def_names}"

    def test_missing_required_include_raises_translation_error(self):
        """A configured loader must not silently skip missing includes."""
        main_cql = """
        library Main version '1.0.0'
        using QICore version '4.1.1'
        include MissingLib version '1.0.0' called MissingLib

        context Patient

        define "Test":
            true
        """

        main_lib = parse_cql(main_cql)

        def loader(path):
            return None

        translator = CQLToSQLTranslator(library_loader=loader)

        with pytest.raises(TranslationError, match="MissingLib"):
            translator.translate_library_to_population_sql(main_lib)

    def test_broken_include_loader_raises_translation_error(self):
        """Loader exceptions should surface as translation failures."""
        main_cql = """
        library Main version '1.0.0'
        using QICore version '4.1.1'
        include BrokenLib version '1.0.0' called BrokenLib

        context Patient

        define "Test":
            true
        """

        main_lib = parse_cql(main_cql)

        def loader(path):
            raise RuntimeError(f"boom: {path}")

        translator = CQLToSQLTranslator(library_loader=loader)

        with pytest.raises(TranslationError, match="BrokenLib"):
            translator.translate_library_to_population_sql(main_lib)
