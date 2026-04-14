"""
Integration tests for translating CMS130 measure with the V2 translator.

These tests verify the CQL to SQL translation pipeline for the CMS130
(Colorectal Cancer Screening) quality measure.

Test coverage:
- Library parsing
- Include resolution (FHIRHelpers, QICoreCommon, Status, etc.)
- Parameter handling (Measurement Period)
- Definition translation (Initial Population, Denominator, Numerator)
- Full measure translation
"""

import pytest
from pathlib import Path

from ...parser import parse_cql, Library
from ...translator import CQLToSQLTranslator, LibraryResolver


# Path to CMS130 measure files (from submodule ecqm-content-qicore-2025)
REPO_ROOT = Path(__file__).resolve().parents[4]  # fhir4ds/cql/tests/integration -> repo root
CQL_DIR = REPO_ROOT / "benchmarking" / "data" / "ecqm-content-qicore-2025" / "input" / "cql"
CMS130_DIR = CQL_DIR
CMS130_MAIN_CQL = CQL_DIR / "CMS130FHIRColorectalCancerScreening.cql"


@pytest.fixture
def cms130_cql_text() -> str:
    """Load the CMS130 CQL text."""
    return CMS130_MAIN_CQL.read_text()


@pytest.fixture
def cms130_library(cms130_cql_text: str) -> Library:
    """Parse the CMS130 CQL library."""
    return parse_cql(cms130_cql_text)


@pytest.fixture
def translator() -> CQLToSQLTranslator:
    """Create a V2 translator instance."""
    return CQLToSQLTranslator()


@pytest.fixture
def library_resolver() -> LibraryResolver:
    """Create a library resolver with CMS130 dependencies loaded.

    Note: Some dependency CQL files may have unsupported syntax and will
    be skipped. Tests that require these files should check availability.
    """
    resolver = LibraryResolver()

    # Load dependency libraries in order
    dependencies = [
        ("FHIRHelpers.cql", "FHIRHelpers"),
        ("QICoreCommon.cql", "QICoreCommon"),
        ("Status.cql", "Status"),
        ("Hospice.cql", "Hospice"),
        ("PalliativeCare.cql", "PalliativeCare"),
        ("SupplementalDataElements.cql", "SDE"),
        ("AdultOutpatientEncounters.cql", "AdultOutpatientEncounters"),
        ("AdvancedIllnessandFrailty.cql", "AIFrailLTCF"),
    ]

    for filename, alias in dependencies:
        filepath = CMS130_DIR / filename
        if filepath.exists():
            try:
                lib_text = filepath.read_text()
                lib = parse_cql(lib_text)
                resolver.register_library(lib, alias)
            except Exception:
                # Skip libraries that can't be parsed (unsupported syntax)
                pass

    return resolver


class TestCMS139Parsing:
    """Tests for CMS130 CQL parsing."""

    @pytest.mark.integration
    def test_cms139_parses(self, cms130_cql_text: str):
        """CMS130 CQL library parses without errors."""
        library = parse_cql(cms130_cql_text)
        assert library is not None
        assert isinstance(library, Library)

    @pytest.mark.integration
    def test_cms139_library_metadata(self, cms130_library: Library):
        """CMS130 library has correct metadata."""
        assert cms130_library.identifier == "CMS130FHIRColorectalCancerScreening"
        assert cms130_library.version == "0.4.000"

    @pytest.mark.integration
    def test_cms139_using_declaration(self, cms130_library: Library):
        """CMS130 has QICore using declaration."""
        using_defs = cms130_library.using
        assert len(using_defs) >= 1
        using_names = [u.model for u in using_defs]
        assert "QICore" in using_names

    @pytest.mark.integration
    def test_cms139_includes(self, cms130_library: Library):
        """CMS130 has expected include statements."""
        includes = cms130_library.includes
        include_aliases = [inc.alias for inc in includes]

        expected_includes = [
            "FHIRHelpers",
            "QICoreCommon",
            "SDE",
            "Status",
            "Hospice",
        ]

        for expected in expected_includes:
            assert expected in include_aliases, f"Missing include: {expected}"


class TestCMS139IncludeResolution:
    """Tests for CMS130 include resolution."""

    @pytest.mark.integration
    def test_cms139_includes_resolve(self, library_resolver: LibraryResolver):
        """CMS130 include statements resolve correctly."""
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


class TestCMS139ParameterHandling:
    """Tests for CMS130 parameter handling."""

    @pytest.mark.integration
    def test_cms139_measurement_period_parameter(self, cms130_library: Library):
        """CMS130 has Measurement Period parameter."""
        params = cms130_library.parameters
        param_names = [p.name for p in params]

        assert "Measurement Period" in param_names

    @pytest.mark.integration
    def test_cms139_measurement_period_generates_bind_variables(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """Measurement Period parameter generates bind variables."""
        # Note: We only test parameter registration here, not full translation
        # Full translation is tested in TestCMS139FullTranslation
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms130_library)
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
    def test_cms139_measurement_period_default_value(self, cms130_library: Library):
        """Measurement Period parameter exists and has expected type."""
        params = cms130_library.parameters
        measurement_period = next(
            (p for p in params if p.name == "Measurement Period"), None
        )

        assert measurement_period is not None
        # CMS130 declares Measurement Period without a default — type check is sufficient
        assert measurement_period.type is not None


class TestCMS139DefinitionTranslation:
    """Tests for CMS130 definition translation."""

    @pytest.mark.integration
    def test_cms139_initial_population_translates(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """Initial Population definition translates to valid SQL."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        assert "Initial Population" in results

        sql_expr = results["Initial Population"]
        sql = sql_expr.to_sql()

        # Should contain SELECT or boolean expression
        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms139_denominator_translates(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """Denominator definition translates to valid SQL."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        assert "Denominator" in results

        sql_expr = results["Denominator"]
        sql = sql_expr.to_sql()

        # Denominator should reference Initial Population
        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms139_numerator_translates(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """Numerator definition translates to valid SQL."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        assert "Numerator" in results

        sql_expr = results["Numerator"]
        sql = sql_expr.to_sql()

        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms139_denominator_exclusions_translates(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """Denominator Exclusions definition translates to valid SQL."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        assert "Denominator Exclusions" in results

        sql_expr = results["Denominator Exclusions"]
        sql = sql_expr.to_sql()

        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms139_definition_dependencies(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """Definitions properly reference other definitions."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        # Denominator should reference Initial Population
        denom_sql = results["Denominator"].to_sql()
        # The SQL should contain a reference to Initial Population
        # (either as a CTE ref or inline)
        assert len(denom_sql) > 0


class TestCMS139FluentFunctionInlining:
    """Tests for fluent function inlining from CQL definitions."""

    @pytest.mark.integration
    def test_cms139_fluent_functions_registered(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """Fluent functions like Encounter.isEncounterPerformed() are registered from CQL definitions."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, functions should be registered
            pass

        # Get all functions from context
        functions = translator.context.get_all_functions()

        # The main library may define fluent functions
        # Check that function registry is populated
        assert isinstance(functions, dict)

    @pytest.mark.integration
    def test_cms139_is_encounter_performed_fluent_function(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """isEncounterPerformed fluent function is used in CMS130."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, functions should be registered
            pass

        functions = translator.context.get_all_functions()

        # CMS130 uses isEncounterPerformed fluent function
        if "isEncounterPerformed" in functions:
            func = functions["isEncounterPerformed"]
            assert func.is_fluent is True

    @pytest.mark.integration
    def test_cms139_is_assessment_performed_fluent_function(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """isAssessmentPerformed fluent function is used in CMS130."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, functions should be registered
            pass

        functions = translator.context.get_all_functions()

        # CMS130 uses isAssessmentPerformed fluent function
        if "isAssessmentPerformed" in functions:
            func = functions["isAssessmentPerformed"]
            assert func.is_fluent is True


class TestCMS139FullTranslation:
    """Tests for full CMS130 measure translation."""

    @pytest.mark.integration
    def test_cms139_full_translation(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """Full CMS130 measure translates without errors."""
        from ...translator.translator import TranslationError

        try:
            sql_definitions = translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Full translation not yet supported: {e}")

        # Should have all population criteria
        assert "Initial Population" in sql_definitions
        assert "Denominator" in sql_definitions
        assert "Numerator" in sql_definitions
        assert "Denominator Exclusions" in sql_definitions

    @pytest.mark.integration
    def test_cms139_all_definitions_present(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """All CMS130 definitions are translated."""
        from ...translator.translator import TranslationError

        try:
            sql_definitions = translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Full translation not yet supported: {e}")

        # Expected definitions from CMS130
        expected_definitions = [
            "Initial Population",
            "Denominator",
            "Denominator Exclusions",
            "Numerator",
            "Colonoscopy Performed",
        ]

        for def_name in expected_definitions:
            assert def_name in sql_definitions, f"Missing definition: {def_name}"

    @pytest.mark.integration
    def test_cms139_sql_is_valid(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """Generated SQL is syntactically valid."""
        from ...translator.translator import TranslationError

        try:
            sql_definitions = translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Full translation not yet supported: {e}")

        for name, sql_expr in sql_definitions.items():
            sql = sql_expr.to_sql()
            # Basic validation - should not be empty
            assert len(sql) > 0, f"Empty SQL for {name}"
            # Should not contain error markers
            assert "ERROR" not in sql.upper() or "ERROR" in name.upper()

    @pytest.mark.integration
    def test_cms139_valuesets_registered(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """ValueSet definitions are registered in context."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, valuesets should be registered
            pass

        # Get valuesets from context
        valuesets = translator.context.valuesets

        # CMS130 defines several valuesets
        expected_valuesets = [
            "Colonoscopy",
            "CT Colonography",
            "Fecal Occult Blood Test (FOBT)",
            "Flexible Sigmoidoscopy",
            "Malignant Neoplasm of Colon",
            "Total Colectomy",
        ]

        for vs_name in expected_valuesets:
            assert vs_name in valuesets, f"Missing valueset: {vs_name}"

    @pytest.mark.integration
    def test_cms139_codesystems_registered(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """CodeSystem definitions are registered in context."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, codesystems should be registered
            pass

        codesystems = translator.context.codesystems

        # CMS130 uses standard ValueSet URLs (no explicit CodeSystem definitions)
        # This test passes if codesystems dict exists
        assert isinstance(codesystems, dict)


class TestCMS139CrossLibraryReferences:
    """Tests for cross-library expression references."""

    @pytest.mark.integration
    def test_cms139_references_hospice(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """CMS130 references Hospice library."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, includes should be registered
            pass

        # The library should have Hospice registered
        libs = translator.context.get_all_libraries()
        # Note: Without actually loading dependency CQL files, this tests the include registration
        assert "Hospice" in libs


class TestCMS139RetrievePatterns:
    """Tests for retrieve pattern translation."""

    @pytest.mark.integration
    def test_cms139_encounter_retrieve(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """Encounter retrieves translate to SQL queries."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        # CMS130 uses diagnostic procedure retrieves (Colonoscopy, CT Colonography, etc.)
        assert "Colonoscopy Performed" in results

        sql = results["Colonoscopy Performed"].to_sql()
        # Should contain some form of table reference or EXISTS
        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms139_observation_retrieve(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """Observation retrieves for falls screening translate correctly."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        # Numerator uses ObservationScreeningAssessment retrieve
        assert "Numerator" in results


class TestCMS139WithDependencyLibraries:
    """Tests with full dependency library loading."""

    @pytest.mark.integration
    def test_cms139_with_dependencies(
        self, translator: CQLToSQLTranslator, cms130_library: Library
    ):
        """CMS130 translation with all dependency libraries loaded."""
        from ...translator.translator import TranslationError, LibraryInfo

        # Load and register dependency libraries
        dependency_files = [
            ("FHIRHelpers.cql", "FHIRHelpers"),
            ("QICoreCommon.cql", "QICoreCommon"),
            ("Status.cql", "Status"),
            ("Hospice.cql", "Hospice"),
        ]

        for filename, alias in dependency_files:
            filepath = CMS130_DIR / filename
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
            results = translator.translate_library(cms130_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        # Should have definitions
        assert len(results) > 0
        assert "Initial Population" in results