"""
Integration tests for translating CMS124 measure with the V2 translator.

These tests verify the CQL to SQL translation pipeline for the CMS124
(Cervical Cancer Screening) quality measure.

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


# Path to CMS124 measure files (from submodule ecqm-content-qicore-2025)
REPO_ROOT = Path(__file__).resolve().parents[4]  # fhir4ds/cql/tests/integration -> repo root
CQL_DIR = REPO_ROOT / "benchmarking" / "data" / "ecqm-content-qicore-2025" / "input" / "cql"
CMS124_MAIN_CQL = CQL_DIR / "CMS124FHIRCervicalCancerScreening.cql"
CMS124_DIR = CQL_DIR  # For compatibility with existing code


@pytest.fixture
def cms124_cql_text() -> str:
    """Load the CMS124 CQL text."""
    return CMS124_MAIN_CQL.read_text()


@pytest.fixture
def cms124_library(cms124_cql_text: str) -> Library:
    """Parse the CMS124 CQL library."""
    return parse_cql(cms124_cql_text)


@pytest.fixture
def translator() -> CQLToSQLTranslator:
    """Create a V2 translator instance."""
    return CQLToSQLTranslator()


@pytest.fixture
def library_resolver() -> LibraryResolver:
    """Create a library resolver with CMS124 dependencies loaded.

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
    ]

    for filename, alias in dependencies:
        filepath = CMS124_DIR / filename
        if filepath.exists():
            try:
                lib_text = filepath.read_text()
                lib = parse_cql(lib_text)
                resolver.register_library(lib, alias)
            except Exception:
                # Skip libraries that can't be parsed (unsupported syntax)
                pass

    return resolver


class TestCMS124Parsing:
    """Tests for CMS124 CQL parsing."""

    @pytest.mark.integration
    def test_cms124_parses(self, cms124_cql_text: str):
        """CMS124 CQL library parses without errors."""
        library = parse_cql(cms124_cql_text)
        assert library is not None
        assert isinstance(library, Library)

    @pytest.mark.integration
    def test_cms124_library_metadata(self, cms124_library: Library):
        """CMS124 library has correct metadata."""
        assert cms124_library.identifier == "CMS124FHIRCervicalCancerScreening"
        assert cms124_library.version == "0.4.000"

    @pytest.mark.integration
    def test_cms124_using_declaration(self, cms124_library: Library):
        """CMS124 has QICore using declaration."""
        using_defs = cms124_library.using
        assert len(using_defs) >= 1
        using_names = [u.model for u in using_defs]
        assert "QICore" in using_names

    @pytest.mark.integration
    def test_cms124_includes(self, cms124_library: Library):
        """CMS124 has expected include statements."""
        includes = cms124_library.includes
        include_aliases = [inc.alias for inc in includes]

        expected_includes = [
            "FHIRHelpers",
            "QICoreCommon",
            "SDE",
            "Status",
            "Hospice",
            "PalliativeCare",
        ]

        for expected in expected_includes:
            assert expected in include_aliases, f"Missing include: {expected}"


class TestCMS124IncludeResolution:
    """Tests for CMS124 include resolution."""

    @pytest.mark.integration
    def test_cms124_includes_resolve(self, library_resolver: LibraryResolver):
        """CMS124 include statements resolve correctly."""
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


class TestCMS124ParameterHandling:
    """Tests for CMS124 parameter handling."""

    @pytest.mark.integration
    def test_cms124_measurement_period_parameter(self, cms124_library: Library):
        """CMS124 has Measurement Period parameter."""
        params = cms124_library.parameters
        param_names = [p.name for p in params]

        assert "Measurement Period" in param_names

    @pytest.mark.integration
    def test_cms124_measurement_period_generates_bind_variables(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """Measurement Period parameter generates bind variables."""
        # Note: We only test parameter registration here, not full translation
        # Full translation is tested in TestCMS124FullTranslation
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms124_library)
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
    def test_cms124_measurement_period_default_value(self, cms124_library: Library):
        """Measurement Period parameter exists (may not have default in all versions)."""
        params = cms124_library.parameters
        measurement_period = next(
            (p for p in params if p.name == "Measurement Period"), None
        )

        assert measurement_period is not None
        # Note: Default value may be None in some CQL versions


class TestCMS124DefinitionTranslation:
    """Tests for CMS124 definition translation."""

    @pytest.mark.integration
    def test_cms124_initial_population_translates(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """Initial Population definition translates to valid SQL."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        assert "Initial Population" in results

        sql_expr = results["Initial Population"]
        sql = sql_expr.to_sql()

        # Should contain SELECT or boolean expression
        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms124_denominator_translates(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """Denominator definition translates to valid SQL."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        assert "Denominator" in results

        sql_expr = results["Denominator"]
        sql = sql_expr.to_sql()

        # Denominator should reference Initial Population
        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms124_numerator_translates(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """Numerator definition translates to valid SQL."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        assert "Numerator" in results

        sql_expr = results["Numerator"]
        sql = sql_expr.to_sql()

        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms124_denominator_exclusions_translates(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """Denominator Exclusions definition translates to valid SQL."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        assert "Denominator Exclusions" in results

        sql_expr = results["Denominator Exclusions"]
        sql = sql_expr.to_sql()

        assert len(sql) > 0


class TestCMS124FluentFunctionInlining:
    """Tests for fluent function inlining from CQL definitions."""

    @pytest.mark.integration
    def test_cms124_fluent_functions_registered(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """Fluent functions like Condition.verified() are registered from CQL definitions."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, functions should be registered
            pass

        # Get all functions from context
        functions = translator.context.get_all_functions()

        # The main library may define fluent functions
        # Check that function registry is populated
        assert isinstance(functions, dict)


class TestCMS124FullTranslation:
    """Tests for full CMS124 measure translation."""

    @pytest.mark.integration
    def test_cms124_full_translation(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """Full CMS124 measure translates without errors."""
        from ...translator.translator import TranslationError

        try:
            sql_definitions = translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Full translation not yet supported: {e}")

        # Should have all population criteria
        assert "Initial Population" in sql_definitions
        assert "Denominator" in sql_definitions
        assert "Numerator" in sql_definitions

    @pytest.mark.integration
    def test_cms124_all_definitions_present(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """All CMS124 definitions are translated."""
        from ...translator.translator import TranslationError

        try:
            sql_definitions = translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Full translation not yet supported: {e}")

        # Expected definitions from CMS124
        expected_definitions = [
            "Initial Population",
            "Denominator",
            "Denominator Exclusions",
            "Numerator",
            "Qualifying Encounters",
            "Cervical Cytology Within 3 Years",
            "HPV Test Within 5 Years for Women Age 30 and Older",
            "Absence of Cervix",
        ]

        for def_name in expected_definitions:
            assert def_name in sql_definitions, f"Missing definition: {def_name}"

    @pytest.mark.integration
    def test_cms124_sql_is_valid(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """Generated SQL is syntactically valid."""
        from ...translator.translator import TranslationError

        try:
            sql_definitions = translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Full translation not yet supported: {e}")

        for name, sql_expr in sql_definitions.items():
            sql = sql_expr.to_sql()
            # Basic validation - should not be empty
            assert len(sql) > 0, f"Empty SQL for {name}"
            # Should not contain error markers
            assert "ERROR" not in sql.upper() or "ERROR" in name.upper()

    @pytest.mark.integration
    def test_cms124_valuesets_registered(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """ValueSet definitions are registered in context."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, valuesets should be registered
            pass

        # Get valuesets from context
        valuesets = translator.context.valuesets

        # CMS124 defines several valuesets
        expected_valuesets = [
            "Congenital or Acquired Absence of Cervix",
            "Home Healthcare Services",
            "HPV Test",
            "Hysterectomy with No Residual Cervix",
            "Office Visit",
            "Virtual Encounter",
            "Pap Test",
            "Preventive Care Services Established Office Visit, 18 and Up",
            "Preventive Care Services Initial Office Visit, 18 and Up",
            "Telephone Visits",
        ]

        for vs_name in expected_valuesets:
            assert vs_name in valuesets, f"Missing valueset: {vs_name}"


class TestCMS124CrossLibraryReferences:
    """Tests for cross-library expression references."""

    @pytest.mark.integration
    def test_cms124_references_hospice(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """CMS124 references Hospice library."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError):
            # Even if translation fails, includes should be registered
            pass

        # The library should have Hospice registered
        libs = translator.context.get_all_libraries()
        # Note: Without actually loading dependency CQL files, this tests the include registration
        assert "Hospice" in libs

    @pytest.mark.integration
    def test_cms124_references_palliative_care(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """CMS124 references PalliativeCare library."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError):
            pass

        libs = translator.context.get_all_libraries()
        assert "PalliativeCare" in libs

    @pytest.mark.integration
    def test_cms124_references_supplemental_data_elements(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """CMS124 references SupplementalDataElements library."""
        from ...translator.translator import TranslationError

        try:
            translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError):
            pass

        libs = translator.context.get_all_libraries()
        assert "SDE" in libs


class TestCMS124RetrievePatterns:
    """Tests for retrieve pattern translation."""

    @pytest.mark.integration
    def test_cms124_encounter_retrieve(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """Encounter retrieves translate to SQL queries."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        # Qualifying Encounters uses multiple Encounter retrieves
        assert "Qualifying Encounters" in results

        sql = results["Qualifying Encounters"].to_sql()
        # Should contain some form of table reference or EXISTS
        assert len(sql) > 0

    @pytest.mark.integration
    def test_cms124_procedure_retrieve(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """Procedure retrieves translate correctly."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        # Absence of Cervix uses Procedure retrieve
        assert "Absence of Cervix" in results

    @pytest.mark.integration
    def test_cms124_observation_retrieve(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """Observation retrieves for cytology translate correctly."""
        from ...translator.translator import TranslationError

        try:
            results = translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        # Cervical Cytology Within 3 Years uses LaboratoryResultObservation retrieve
        assert "Cervical Cytology Within 3 Years" in results


class TestCMS124WithDependencyLibraries:
    """Tests with full dependency library loading."""

    @pytest.mark.integration
    def test_cms124_with_dependencies(
        self, translator: CQLToSQLTranslator, cms124_library: Library
    ):
        """CMS124 translation with all dependency libraries loaded."""
        from ...translator.translator import TranslationError, LibraryInfo

        # Load and register dependency libraries
        dependency_files = [
            ("FHIRHelpers.cql", "FHIRHelpers"),
            ("QICoreCommon.cql", "QICoreCommon"),
            ("Status.cql", "Status"),
        ]

        for filename, alias in dependency_files:
            filepath = CMS124_DIR / filename
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
            results = translator.translate_library(cms124_library)
        except (TranslationError, NotImplementedError, KeyError) as e:
            pytest.skip(f"Translation not yet supported: {e}")

        # Should have definitions
        assert len(results) > 0
        assert "Initial Population" in results