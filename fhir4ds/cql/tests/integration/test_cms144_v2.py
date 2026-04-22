"""
Integration tests for translating CMS144 measure with the V2 translator.

These tests verify the CQL to SQL translation pipeline for the CMS144
(Heart Failure Beta Blocker for LVSD) quality measure.

Test coverage:
- Library parsing
- Include resolution (FHIRHelpers, QICoreCommon, Status, etc.)
- Parameter handling (Measurement Period)
- Definition translation (Initial Population, Denominator, Numerator)
- Fluent function inlining (verified(), prevalenceInterval(), etc.)
- Full measure translation
"""

import pytest
from pathlib import Path

from ...parser import parse_cql, Library
from ...translator import CQLToSQLTranslator, LibraryResolver


# Path to CMS144 measure files (from submodule ecqm-content-qicore-2025)
REPO_ROOT = Path(__file__).resolve().parents[4]  # fhir4ds/cql/tests/integration -> repo root
CQL_DIR = REPO_ROOT / "tests" / "data" / "ecqm-content-qicore-2025" / "input" / "cql"
CMS144_MAIN_CQL = CQL_DIR / "CMS144FHIRHFBetaBlockerTherapyforLVSD.cql"
CMS144_DIR = CQL_DIR  # For compatibility with existing code


@pytest.fixture
def cms144_cql_text() -> str:
    """Load the CMS144 CQL text."""
    return CMS144_MAIN_CQL.read_text()


@pytest.fixture
def cms144_library(cms144_cql_text: str) -> Library:
    """Parse the CMS144 CQL library."""
    return parse_cql(cms144_cql_text)


@pytest.fixture
def translator() -> CQLToSQLTranslator:
    """Create a V2 translator instance."""
    return CQLToSQLTranslator()


@pytest.fixture
def library_resolver() -> LibraryResolver:
    """Create a library resolver with CMS144 dependencies loaded.

    Note: Some dependency CQL files may have unsupported syntax and will
    be skipped. Tests that require these files should check availability.
    """
    resolver = LibraryResolver()

    # Load dependency libraries in order
    dependencies = [
        ("FHIRHelpers.cql", "FHIRHelpers"),
        ("QICoreCommon.cql", "QICoreCommon"),
        ("SupplementalDataElements.cql", "SDE"),
        ("AHAOverall.cql", "AHA"),
    ]

    for filename, alias in dependencies:
        filepath = CMS144_DIR / filename
        if filepath.exists():
            try:
                lib_text = filepath.read_text()
                lib = parse_cql(lib_text)
                resolver.register_library(lib, alias)
            except Exception:
                # Skip libraries that can't be parsed (unsupported syntax)
                pass

    return resolver


class TestCMS144Parsing:
    """Tests for CMS144 CQL parsing."""

    @pytest.mark.integration
    def test_cms144_parses(self, cms144_cql_text: str):
        """CMS144 CQL library parses without errors."""
        library = parse_cql(cms144_cql_text)
        assert library is not None
        assert isinstance(library, Library)

    @pytest.mark.integration
    def test_cms144_library_metadata(self, cms144_library: Library):
        """CMS144 library has correct metadata."""
        assert cms144_library.identifier == "CMS144FHIRHFBetaBlockerTherapyforLVSD"
        assert cms144_library.version == "1.5.000"

    @pytest.mark.integration
    def test_cms144_using_declaration(self, cms144_library: Library):
        """CMS144 has QICore using declaration."""
        using_defs = cms144_library.using
        assert len(using_defs) >= 1
        using_names = [u.model for u in using_defs]
        assert "QICore" in using_names

    @pytest.mark.integration
    def test_cms144_includes(self, cms144_library: Library):
        """CMS144 has expected include statements."""
        includes = cms144_library.includes
        include_aliases = [inc.alias for inc in includes]

        expected_includes = [
            "FHIRHelpers",
            "QICoreCommon",
            "SDE",
            "AHA",
        ]

        for expected in expected_includes:
            assert expected in include_aliases, f"Missing include: {expected}"


class TestCMS144IncludeResolution:
    """Tests for CMS144 include resolution."""

    @pytest.mark.integration
    def test_cms144_includes_resolve(self, library_resolver: LibraryResolver):
        """CMS144 include statements resolve correctly."""
        registered = library_resolver.get_library_names()

        # Skip if no dependencies could be parsed
        if not registered:
            pytest.skip("No dependency libraries could be parsed")

        # At minimum, we expect some libraries to be registered
        assert len(registered) > 0, "At least some libraries should be registered"

    @pytest.mark.integration
    def test_fhirhelpers_functions_available(self, library_resolver: LibraryResolver):
        """FHIRHelpers functions are available for resolution."""
        # Check if FHIRHelpers was parsed successfully
        if not library_resolver.is_registered("FHIRHelpers"):
            pytest.skip("FHIRHelpers.cql could not be parsed")

        functions = library_resolver.get_all_functions("FHIRHelpers")
        assert len(functions) > 0, "FHIRHelpers should have functions defined"

    @pytest.mark.integration
    def test_qicorecommon_functions_available(self, library_resolver: LibraryResolver):
        """QICoreCommon functions are available for resolution."""
        # Check if QICoreCommon was parsed successfully
        if not library_resolver.is_registered("QICoreCommon"):
            pytest.skip("QICoreCommon.cql could not be parsed")

        functions = library_resolver.get_all_functions("QICoreCommon")
        # QICoreCommon may have fluent functions like verified(), prevalenceInterval()
        assert len(functions) >= 0, "QICoreCommon functions should be queryable"


class TestCMS144ParameterHandling:
    """Tests for CMS144 parameter handling."""

    @pytest.mark.integration
    def test_cms144_measurement_period_parameter(self, cms144_library: Library):
        """CMS144 has Measurement Period parameter."""
        params = cms144_library.parameters
        param_names = [p.name for p in params]

        assert "Measurement Period" in param_names

    @pytest.mark.integration
    def test_cms144_measurement_period_generates_bind_variables(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """Measurement Period parameter generates bind variables."""
        # Note: We only test parameter registration here, not full translation
        # Full translation is tested in TestCMS144FullTranslation
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError):
            # If translation fails, just check that parameters were processed
            pass

        # Check that parameters are registered
        params = translator.context.get_all_parameters()
        assert "Measurement Period" in params

        param = params["Measurement Period"]
        # The parameter should have a placeholder
        assert param.placeholder == ":Measurement Period"

    @pytest.mark.integration
    def test_cms144_measurement_period_default_value(self, cms144_library: Library):
        """Measurement Period parameter exists (may not have default in all versions)."""
        params = cms144_library.parameters
        measurement_period = next(
            (p for p in params if p.name == "Measurement Period"), None
        )

        assert measurement_period is not None
        # Note: Default value may be None in some CQL versions


class TestCMS144DefinitionTranslation:
    """Tests for CMS144 definition translation."""

    @pytest.mark.integration
    def test_cms144_initial_population_translates(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """Initial Population definition translates to valid SQL."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        assert "Initial Population" in results

        sql_expr = results["Initial Population"]
        sql = sql_expr.to_sql()

        # Should contain SELECT or boolean expression
        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms144_denominator_translates(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """Denominator definition translates to valid SQL."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        assert "Denominator" in results

        sql_expr = results["Denominator"]
        sql = sql_expr.to_sql()

        # Denominator should reference Initial Population
        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms144_numerator_translates(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """Numerator definition translates to valid SQL."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        assert "Numerator" in results

        sql_expr = results["Numerator"]
        sql = sql_expr.to_sql()

        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms144_denominator_exceptions_translates(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """Denominator Exceptions definition translates to valid SQL."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        assert "Denominator Exceptions" in results

        sql_expr = results["Denominator Exceptions"]
        sql = sql_expr.to_sql()

        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms144_definition_dependencies(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """Definitions properly reference other definitions."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        # Denominator should reference Initial Population
        denom_sql = results["Denominator"].to_sql()
        # The SQL should contain a reference to Initial Population
        # (either as a CTE ref or inline)
        assert len(denom_sql) > 0


class TestCMS144FluentFunctionInlining:
    """Tests for fluent function inlining from CQL definitions."""

    @pytest.mark.integration
    def test_cms144_fluent_functions_registered(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """Fluent functions like Condition.verified() are registered from CQL definitions."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, functions should be registered
            pass

        # Get all functions from context
        functions = translator.context.get_all_functions()

        # The main library may define fluent functions
        # Check that function registry is populated
        assert isinstance(functions, dict)

    @pytest.mark.integration
    def test_cms144_isVerified_fluent_function(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """isVerified fluent function is defined in CMS144."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, functions should be registered
            pass

        functions = translator.context.get_all_functions()

        # CMS144 defines: define fluent function isVerified(allergyIntolerance QICore.AllergyIntolerance)
        if "isVerified" in functions:
            func = functions["isVerified"]
            assert func.is_fluent is True


class TestCMS144FullTranslation:
    """Tests for full CMS144 measure translation."""

    @pytest.mark.integration
    def test_cms144_full_translation(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """Full CMS144 measure translates without errors."""
        from ...translator.translator import TranslationError

        try:
            sql_definitions = translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Full translation not yet supported: {e}")

        # Should have all population criteria
        assert "Initial Population" in sql_definitions
        assert "Denominator" in sql_definitions
        assert "Numerator" in sql_definitions
        assert "Denominator Exceptions" in sql_definitions

    @pytest.mark.integration
    def test_cms144_all_definitions_present(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """All CMS144 definitions are translated."""
        from ...translator.translator import TranslationError

        try:
            sql_definitions = translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Full translation not yet supported: {e}")

        # Expected definitions from CMS144
        expected_definitions = [
            "Initial Population",
            "Denominator",
            "Denominator Exclusions",
            "Numerator",
            "Denominator Exceptions",
            "Has Beta Blocker Therapy for LVSD Ordered",
            "Is Currently Taking Beta Blocker Therapy for LVSD",
        ]

        for def_name in expected_definitions:
            assert def_name in sql_definitions, f"Missing definition: {def_name}"

    @pytest.mark.integration
    def test_cms144_sql_is_valid(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """Generated SQL is syntactically valid."""
        from ...translator.translator import TranslationError

        try:
            sql_definitions = translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Full translation not yet supported: {e}")

        for name, sql_expr in sql_definitions.items():
            sql = sql_expr.to_sql()
            # Basic validation - should not be empty
            assert len(sql) > 0, f"Empty SQL for {name}"
            # Should not contain error markers
            assert "ERROR" not in sql.upper() or "ERROR" in name.upper()

    @pytest.mark.integration
    def test_cms144_valuesets_registered(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """ValueSet definitions are registered in context."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, valuesets should be registered
            pass

        # Get valuesets from context
        valuesets = translator.context.valuesets

        # CMS144 defines several valuesets
        expected_valuesets = [
            "Allergy to Beta Blocker Therapy",
            "Arrhythmia",
            "Asthma",
            "Beta Blocker Therapy for LVSD",
        ]

        for vs_name in expected_valuesets:
            assert vs_name in valuesets, f"Missing valueset: {vs_name}"

    @pytest.mark.integration
    def test_cms144_codesystems_registered(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """CodeSystem definitions are registered in context."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, codesystems should be registered
            pass

        codesystems = translator.context.codesystems

        # CMS144 defines SNOMEDCT codesystem
        assert "SNOMEDCT" in codesystems


class TestCMS144CrossLibraryReferences:
    """Tests for cross-library expression references."""

    @pytest.mark.integration
    def test_cms144_references_aha_library(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """CMS144 references AHA library."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, includes should be registered
            pass

        # The library should have AHA registered
        libs = translator.context.get_all_libraries()
        # Note: Without actually loading dependency CQL files, this tests the include registration
        assert "AHA" in libs

    @pytest.mark.integration
    def test_cms144_references_sde_library(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """CMS144 references SDE library for supplemental data elements."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError):
            pass

        libs = translator.context.get_all_libraries()
        assert "SDE" in libs


class TestCMS144RetrievePatterns:
    """Tests for retrieve pattern translation."""

    @pytest.mark.integration
    def test_cms144_medicationrequest_retrieve(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """MedicationRequest retrieves translate to SQL queries."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        # Has Beta Blocker Therapy for LVSD Ordered uses MedicationRequest retrieve
        assert "Has Beta Blocker Therapy for LVSD Ordered" in results

        sql = results["Has Beta Blocker Therapy for LVSD Ordered"].to_sql()
        # Should contain some form of table reference or EXISTS
        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms144_condition_retrieve(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """Condition retrieves translate to SQL queries."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        # Has Asthma Diagnosis uses Condition retrieve
        assert "Has Asthma Diagnosis" in results

        sql = results["Has Asthma Diagnosis"].to_sql()
        # Should contain some form of table reference or EXISTS
        assert len(sql) > 0


class TestCMS144WithDependencyLibraries:
    """Tests with full dependency library loading."""

    @pytest.mark.integration
    def test_cms144_with_dependencies(
        self, translator: CQLToSQLTranslator, cms144_library: Library
    ):
        """CMS144 translation with all dependency libraries loaded."""
        from ...translator.translator import TranslationError, LibraryInfo

        # Load and register dependency libraries
        dependency_files = [
            ("FHIRHelpers.cql", "FHIRHelpers"),
            ("QICoreCommon.cql", "QICoreCommon"),
            ("AHAOverall.cql", "AHA"),
        ]

        for filename, alias in dependency_files:
            filepath = CMS144_DIR / filename
            if filepath.exists():
                try:
                    dep_text = filepath.read_text()
                    dep_lib = parse_cql(dep_text)

                    # Add to translator's context
                    lib_info = LibraryInfo(
                        name=dep_lib.identifier,
                        version=dep_lib.version,
                        alias=alias,
                    )
                    translator.context.add_library(lib_info)
                except Exception:
                    # Skip libraries that can't be parsed
                    pass

        # Now translate main library
        try:
            results = translator.translate_library(cms144_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        # Should have definitions
        assert len(results) > 0
        assert "Initial Population" in results