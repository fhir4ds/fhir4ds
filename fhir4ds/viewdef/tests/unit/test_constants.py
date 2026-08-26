"""Unit tests for constant resolution.

Tests the resolution of constants defined in ViewDefinitions
into SQL values, including simple values, Codings, and
CodeableConcepts.
"""

import json

import pytest
from decimal import Decimal

from ...errors import ConstantResolutionError
from ...types import Constant
from ...constants import (
    resolve_constant,
    resolve_constants_in_path,
    ConstantResolver,
    extract_constant_references,
    FHIRPATH_BUILTIN_VARIABLES,
)


class TestResolveConstant:
    """Tests for constant value resolution."""

    def test_resolve_string_constant(self):
        """Test resolving a string constant."""
        const = Constant(name="TestValue", value="test", value_type="string")
        result = resolve_constant(const)

        assert result == "'test'"

    def test_resolve_code_constant(self):
        """Test resolving a code constant."""
        const = Constant(name="StatusCode", value="active", value_type="code")
        result = resolve_constant(const)

        assert result == "'active'"

    def test_resolve_integer_constant(self):
        """Test resolving an integer constant."""
        const = Constant(name="MaxCount", value=10, value_type="integer")
        result = resolve_constant(const)

        assert result == "10"

    def test_resolve_decimal_constant(self):
        """Test resolving a decimal constant."""
        const = Constant(name="Ratio", value=3.14, value_type="decimal")
        result = resolve_constant(const)

        assert result == "3.14"

    def test_resolve_boolean_true_constant(self):
        """Test resolving a boolean true constant."""
        const = Constant(name="IsActive", value=True, value_type="boolean")
        result = resolve_constant(const)

        assert result == "true"

    def test_resolve_boolean_false_constant(self):
        """Test resolving a boolean false constant."""
        const = Constant(name="IsInactive", value=False, value_type="boolean")
        result = resolve_constant(const)

        assert result == "false"

    def test_resolve_null_constant(self):
        """Test resolving a null constant (resolver defensive branch).

        Per SQL-on-FHIR v2, ``constant.value[x]`` is 1..1, so a real
        ``Constant`` cannot carry ``value=None`` after SOF-VD-02 SKEPTIC
        fresh rerun (2026-07-03) added ``Constant.__post_init__`` validation.
        The resolver still guards the None branch defensively; we exercise
        it here by mutating the value of a valid Constant.
        """
        const = Constant(name="Placeholder", value="x", value_type="string")
        const.value = None
        const.value_type = None
        result = resolve_constant(const)

        assert result == "null"

    def test_resolve_string_constant_uses_fhirpath_escaping(self):
        """String constants are FHIRPath literals, not SQL literals."""
        const = Constant(name="Target", value="O'Reilly \\ lab\n", value_type="string")
        result = resolve_constant(const)

        assert result == r"'O\'Reilly \\ lab\n'"

    def test_resolve_integer64_string_as_numeric_literal(self):
        """FHIR JSON encodes integer64 as string, but FHIRPath receives a number.

        Values beyond the FHIRPath Integer (32-bit) literal range raise an
        explicit ConstantResolutionError — see TestInteger64Range.
        """
        const = Constant(name="Large", value="2147483646", value_type="integer64")
        result = resolve_constant(const)

        assert result == "2147483646"


class TestResolveCodingConstant:
    """Tests for Coding constant resolution (resolver defensive branch).

    Per SQL-on-FHIR v2, ``ViewDefinition.constant.value[x]`` is constrained
    to a primitive choice list and does NOT include Coding. After
    SOF-VD-02 SKEPTIC fresh rerun (2026-07-03) added
    ``Constant.__post_init__`` validation, no real ``Constant`` can carry a
    Coding value. The resolver still guards the Coding branch defensively;
    we exercise it here by mutating a valid Constant.
    """

    @staticmethod
    def _coding_constant(name: str, coding: dict) -> Constant:
        const = Constant(name=name, value="placeholder", value_type="string")
        const.value = coding
        const.value_type = "Coding"
        return const

    def test_resolve_simple_coding(self):
        """Test resolving a simple Coding constant."""
        coding = {
            "system": "http://hl7.org/fhir/gender-identity",
            "code": "female"
        }
        const = self._coding_constant("FemaleCoding", coding)
        result = resolve_constant(const)

        assert "Coding{" in result
        assert "system: 'http://hl7.org/fhir/gender-identity'" in result
        assert "code: 'female'" in result

    def test_resolve_coding_with_display(self):
        """Test resolving a Coding with display."""
        coding = {
            "system": "http://snomed.info/sct",
            "code": "73211009",
            "display": "Diabetes mellitus"
        }
        const = self._coding_constant("DiabetesCode", coding)
        result = resolve_constant(const)

        assert "Coding{" in result
        assert "display: 'Diabetes mellitus'" in result

    def test_resolve_coding_escapes_quotes(self):
        """Test that quotes in Coding values are escaped."""
        coding = {
            "system": "http://example.org",
            "code": "test's code"
        }
        const = self._coding_constant("EscapedCoding", coding)
        result = resolve_constant(const)

        # Single quotes should be doubled
        assert "test''s code" in result


class TestResolveCodeableConceptConstant:
    """Tests for CodeableConcept constant resolution (resolver defensive branch).

    Per SQL-on-FHIR v2, ``ViewDefinition.constant.value[x]`` is constrained
    to a primitive choice list and does NOT include CodeableConcept. After
    SOF-VD-02 SKEPTIC fresh rerun (2026-07-03) added
    ``Constant.__post_init__`` validation, no real ``Constant`` can carry a
    CodeableConcept value. The resolver still guards the CodeableConcept
    branch defensively; we exercise it here by mutating a valid Constant.
    """

    @staticmethod
    def _concept_constant(name: str, concept: dict) -> Constant:
        const = Constant(name=name, value="placeholder", value_type="string")
        const.value = concept
        const.value_type = "CodeableConcept"
        return const

    def test_resolve_simple_codeable_concept(self):
        """Test resolving a simple CodeableConcept."""
        concept = {
            "coding": [
                {"system": "http://snomed.info/sct", "code": "73211009"}
            ]
        }
        const = self._concept_constant("DiabetesConcept", concept)
        result = resolve_constant(const)

        assert "CodeableConcept{" in result
        assert "coding: [" in result
        assert "Coding{" in result

    def test_resolve_codeable_concept_with_text(self):
        """Test resolving a CodeableConcept with text."""
        concept = {
            "coding": [
                {"system": "http://loinc.org", "code": "718-7"}
            ],
            "text": "Hemoglobin"
        }
        const = self._concept_constant("HemoglobinConcept", concept)
        result = resolve_constant(const)

        assert "text: 'Hemoglobin'" in result

    def test_resolve_codeable_concept_multiple_codings(self):
        """Test resolving a CodeableConcept with multiple codings."""
        concept = {
            "coding": [
                {"system": "http://snomed.info/sct", "code": "73211009"},
                {"system": "http://icd.codes", "code": "E11"}
            ]
        }
        const = self._concept_constant("MultiCodingConcept", concept)
        result = resolve_constant(const)

        assert result.count("Coding{") == 2


class TestResolveConstantsInPath:
    """Tests for resolving constants in FHIRPath expressions."""

    def test_resolve_single_constant(self):
        """Test resolving a single constant reference."""
        constants = {
            "Female": Constant(name="Female", value="female", value_type="code")
        }
        result = resolve_constants_in_path("gender = %Female", constants)

        assert result == "gender = 'female'"

    def test_resolve_multiple_constants(self):
        """Test resolving multiple constant references."""
        constants = {
            "Female": Constant(name="Female", value="female", value_type="code"),
            "Active": Constant(name="Active", value="active", value_type="code")
        }
        result = resolve_constants_in_path("gender = %Female and status = %Active", constants)

        assert result == "gender = 'female' and status = 'active'"

    def test_unknown_constant_raises(self):
        """Undefined user constant references fail explicitly."""
        constants = {}

        with pytest.raises(ConstantResolutionError, match="UnknownConstant"):
            resolve_constants_in_path("value = %UnknownConstant", constants)

    def test_builtin_fhirpath_variables_are_preserved(self):
        """FHIRPath built-ins are not user-defined constants."""
        result = resolve_constants_in_path("%resource.id & %context.id", {})

        assert result == "%resource.id & %context.id"

    def test_constant_reference_inside_string_literal_is_not_resolved(self):
        """Percent-name text inside a FHIRPath string literal is not a constant."""
        constants = {
            "Code1": Constant(name="Code1", value=1, value_type="integer")
        }
        result = resolve_constants_in_path("'%Code1' & %Code1", constants)

        assert result == "'%Code1' & 1"

    def test_extract_constant_references_ignores_literals_and_comments(self):
        """Validation uses the same lexical boundaries as substitution."""
        path = "'%literal' & `field%name` & %Real // %comment\n and %Other"

        assert extract_constant_references(path) == {"Real", "Other"}

    def test_constant_in_function_call(self):
        """Test resolving constant in function call."""
        constants = {
            "HomeSystem": Constant(name="HomeSystem", value="http://home.org", value_type="string")
        }
        result = resolve_constants_in_path("telecom.where(system = %HomeSystem)", constants)

        assert "'http://home.org'" in result


class TestConstantResolver:
    """Tests for ConstantResolver class."""

    def test_initialization_empty(self):
        """Test initializing empty resolver."""
        resolver = ConstantResolver()

        assert len(resolver) == 0
        assert resolver.constants == {}

    def test_initialization_with_constants(self):
        """Test initializing resolver with constants."""
        constants = {
            "Test": Constant(name="Test", value="value", value_type="string")
        }
        resolver = ConstantResolver(constants)

        assert len(resolver) == 1
        assert "Test" in resolver

    def test_from_list_with_dict(self):
        """Test creating resolver from list of dicts."""
        constants_list = [
            {"name": "Female", "valueCode": "female"},
            {"name": "Male", "valueCode": "male"}
        ]
        resolver = ConstantResolver.from_list(constants_list)

        assert len(resolver) == 2
        assert "Female" in resolver
        assert "Male" in resolver

    def test_from_list_with_constant_objects(self):
        """Test creating resolver from list of Constant objects."""
        constants_list = [
            Constant(name="Active", value="active", value_type="code")
        ]
        resolver = ConstantResolver.from_list(constants_list)

        assert len(resolver) == 1
        assert resolver.has_constant("Active")

    def test_add_constant(self):
        """Test adding a constant."""
        resolver = ConstantResolver()
        const = Constant(name="New", value="value", value_type="string")

        resolver.add_constant(const)

        assert len(resolver) == 1
        assert resolver.get_constant("New") == const

    def test_add_from_dict(self):
        """Test adding a constant from dict."""
        resolver = ConstantResolver()

        resolver.add_from_dict({"name": "Test", "valueString": "test_value"})

        assert len(resolver) == 1
        assert resolver.has_constant("Test")

    def test_get_constant(self):
        """Test getting a constant by name."""
        const = Constant(name="Test", value="value", value_type="string")
        resolver = ConstantResolver({"Test": const})

        result = resolver.get_constant("Test")
        assert result == const

        result = resolver.get_constant("Nonexistent")
        assert result is None

    def test_resolve(self):
        """Test resolving a constant by name."""
        const = Constant(name="Test", value="test_value", value_type="string")
        resolver = ConstantResolver({"Test": const})

        result = resolver.resolve("Test")
        assert result == "'test_value'"

    def test_resolve_nonexistent_raises(self):
        """Test resolving nonexistent constant raises KeyError."""
        resolver = ConstantResolver()

        with pytest.raises(KeyError):
            resolver.resolve("Nonexistent")

    def test_resolve_in_path(self):
        """Test resolving constants in a path."""
        resolver = ConstantResolver.from_list([
            {"name": "Female", "valueCode": "female"}
        ])

        result = resolver.resolve_in_path("gender = %Female")
        assert result == "gender = 'female'"

    def test_has_constant(self):
        """Test checking if constant exists."""
        const = Constant(name="Test", value="value", value_type="string")
        resolver = ConstantResolver({"Test": const})

        assert resolver.has_constant("Test") is True
        assert resolver.has_constant("Nonexistent") is False

    def test_contains_operator(self):
        """Test 'in' operator."""
        const = Constant(name="Test", value="value", value_type="string")
        resolver = ConstantResolver({"Test": const})

        assert "Test" in resolver
        assert "Nonexistent" not in resolver

    def test_len(self):
        """Test len() returns count of constants."""
        resolver = ConstantResolver.from_list([
            {"name": "A", "valueCode": "a"},
            {"name": "B", "valueCode": "b"},
            {"name": "C", "valueCode": "c"}
        ])

        assert len(resolver) == 3

    def test_repr(self):
        """Test string representation."""
        resolver = ConstantResolver.from_list([
            {"name": "A", "valueCode": "a"}
        ])

        repr_str = repr(resolver)
        assert "ConstantResolver" in repr_str
        assert "1" in repr_str


class TestEdgeCases:
    """Tests for edge cases in constant resolution."""

    def test_empty_string_value(self):
        """Resolver would emit empty FHIRPath literal (resolver defensive branch).

        Per FHIR R4, ``string`` is non-empty (length >= 1). After
        SOF-VD-02 SKEPTIC fresh rerun (2026-07-03) added
        ``Constant.__post_init__`` validation, no real ``Constant`` can
        carry an empty string. The resolver still handles it defensively;
        we exercise it here by mutating a valid Constant.
        """
        const = Constant(name="Placeholder", value="x", value_type="string")
        const.value = ""
        result = resolve_constant(const)

        assert result == "''"

    def test_value_with_special_fhirpath_chars(self):
        """Test value with characters that need FHIRPath escaping."""
        const = Constant(name="Special", value="it's a test", value_type="string")
        result = resolve_constant(const)

        assert result == r"'it\'s a test'"

    def test_zero_integer(self):
        """Test resolving zero."""
        const = Constant(name="Zero", value=0, value_type="integer")
        result = resolve_constant(const)

        assert result == "0"

    def test_negative_number(self):
        """Test resolving negative number."""
        const = Constant(name="Negative", value=-5.5, value_type="decimal")
        result = resolve_constant(const)

        assert result == "-5.5"

    def test_constant_name_with_underscore(self):
        """Test constant name with underscore."""
        constants = {
            "My_Constant": Constant(name="My_Constant", value="value", value_type="string")
        }
        result = resolve_constants_in_path("test = %My_Constant", constants)

        assert result == "test = 'value'"

    def test_constant_name_with_numbers(self):
        """Test constant name with numbers."""
        constants = {
            "Code1": Constant(name="Code1", value="value1", value_type="string")
        }
        result = resolve_constants_in_path("test = %Code1", constants)

        assert result == "test = 'value1'"

    def test_from_dict_rejects_invalid_constant_name(self):
        """Direct Constant.from_dict uses the same sql-name guard as the parser."""
        with pytest.raises(ValueError, match="sql-name"):
            Constant.from_dict({"name": "_bad", "valueString": "value"})

    def test_from_dict_rejects_multiple_value_choices(self):
        """Direct Constant.from_dict enforces value[x] exactly-one behavior."""
        with pytest.raises(ValueError, match="exactly one"):
            Constant.from_dict({
                "name": "Ambiguous",
                "valueString": "value",
                "valueInteger": 1,
            })

    def test_from_dict_supports_canonical_and_integer64(self):
        """Direct Constant.from_dict supports all primitive choices in this chunk."""
        canonical = Constant.from_dict({
            "name": "ProfileUrl",
            "valueCanonical": "http://example.org/Profile",
        })
        integer64 = Constant.from_dict({
            "name": "Large",
            "valueInteger64": "1234567890123",
        })

        assert canonical.valueCanonical == "http://example.org/Profile"
        assert canonical.value_type == "canonical"
        assert integer64.valueInteger64 == "1234567890123"
        assert integer64.value_type == "integer64"

    def test_from_dict_rejects_integer64_json_number(self):
        """FHIR JSON represents integer64 as a JSON string."""
        with pytest.raises(ValueError, match="valueInteger64"):
            Constant.from_dict({
                "name": "Large",
                "valueInteger64": 1234567890123,
            })

    def test_from_dict_rejects_non_primitive_value_choices(self):
        """Direct Constant.from_dict uses the SQL-on-FHIR primitive value[x] allowlist."""
        with pytest.raises(ValueError, match="Unsupported"):
            Constant.from_dict({
                "name": "FemaleCoding",
                "valueCoding": {
                    "system": "http://hl7.org/fhir/gender-identity",
                    "code": "female",
                },
            })

    def test_from_dict_rejects_invalid_primitive_values(self):
        """Direct Constant.from_dict validates FHIR primitive values."""
        with pytest.raises(ValueError, match="valuePositiveInt"):
            Constant.from_dict({
                "name": "BadPositive",
                "valuePositiveInt": -1,
            })

    def test_to_dict_rejects_invalid_constant_name(self):
        """Constant construction validates constant.name (SOF-VD-02 SKEPTIC)."""
        # Construction itself raises since __post_init__ validates.
        with pytest.raises(ValueError, match="sql-name"):
            Constant(name="_bad", value="value", value_type="string")

    def test_to_dict_rejects_invalid_primitive_values(self):
        """Constant construction validates value[x] shape (SOF-VD-02 SKEPTIC)."""
        with pytest.raises(ValueError, match="valueInteger"):
            Constant(name="BadInteger", value="1", value_type="integer")

        with pytest.raises(ValueError, match="valueDateTime"):
            Constant(name="BadDateTime", value="2024T00:00:00Z", value_type="dateTime")

        with pytest.raises(ValueError, match="valueInstant"):
            Constant(name="BadInstant", value="2024-01T00:00:00Z", value_type="instant")

    def test_to_dict_rejects_unsupported_value_type(self):
        """Constant construction limits value_type to spec primitive choices."""
        # Construction itself raises since __post_init__ validates.
        with pytest.raises(ValueError, match="Unsupported Constant.value_type"):
            Constant(name="BadType", value="x", value_type="notatype")

    def test_resolver_rejects_duplicate_names_from_list(self):
        """ConstantResolver construction cannot silently overwrite duplicates."""
        with pytest.raises(ValueError, match="Duplicate constant name"):
            ConstantResolver.from_list([
                {"name": "Duplicate", "valueString": "first"},
                {"name": "Duplicate", "valueString": "second"},
            ])


class TestDirectDataclassValidation:
    """SOF-VD-02 SKEPTIC fresh rerun (2026-07-03).

    Direct Constant dataclass construction must validate spec-defined fields
    via __post_init__, matching the validation pattern used by sibling
    dataclasses Column, ColumnTag, and Join. SQL-on-FHIR requires
    constant.name to satisfy sql-name and constant.value[x] to be exactly one
    of the 19 supported primitive choices.
    """

    def test_direct_construct_rejects_invalid_sql_name(self):
        """Constant(name='_bad') must raise ValueError at construction."""
        with pytest.raises(ValueError, match="sql-name"):
            Constant(name="_bad", value="f", value_type="code")

    @pytest.mark.parametrize("bad_name", ["", "bad-name", "bad.name", "9bad", "bad name"])
    def test_direct_construct_rejects_other_invalid_names(self, bad_name: str):
        """All sql-name violations are rejected at construction."""
        with pytest.raises(ValueError, match="sql-name|non-empty"):
            Constant(name=bad_name, value="f", value_type="code")

    def test_direct_construct_rejects_unsupported_value_type(self):
        """value_type must be one of the 19 supported primitives."""
        with pytest.raises(ValueError, match="Unsupported Constant.value_type"):
            Constant(name="C", value="x", value_type="markdown")

    def test_direct_construct_rejects_complex_value_types(self):
        """Coding/CodeableConcept/Address are not in the spec choice list."""
        for bad in ("Coding", "CodeableConcept", "Address"):
            with pytest.raises(ValueError, match="Unsupported Constant.value_type"):
                Constant(name="C", value={"x": "y"}, value_type=bad)

    def test_direct_construct_rejects_missing_value_type(self):
        """value_type=None is not a valid primitive choice."""
        with pytest.raises(ValueError, match="value_type is required"):
            Constant(name="C", value="x", value_type=None)

    def test_direct_construct_rejects_invalid_primitive_value(self):
        """Primitive lexical/range validation runs at construction."""
        with pytest.raises(ValueError, match="valueInteger"):
            Constant(name="C", value=2147483648, value_type="integer")

    def test_direct_construct_accepts_valid_constant(self):
        """A spec-compliant Constant still constructs normally."""
        c = Constant(name="Female", value="female", value_type="code")
        assert c.name == "Female"
        assert c.value == "female"
        assert c.value_type == "code"

    def test_direct_construct_round_trips_to_dict(self):
        """A directly constructed valid Constant serializes correctly."""
        c = Constant(name="Max", value=42, value_type="integer")
        assert c.to_dict() == {"name": "Max", "valueInteger": 42}


class TestBuiltinVariablePrecedencePerSpecSofVd02Explorer:
    """SOF-VD-02 EXPLORER iter 1 (2026-07-03): FHIRPath §Environment variables.

    Per FHIRPath v3.0.0-ballot §"Environment variables"
    (https://build.fhir.org/ig/HL7/FHIRPath/) the environment variables
    ``%ucum`` and ``%context`` are "set for all contexts"; per the FHIR
    spec (https://build.fhir.org/fhirpath.html) ``%resource`` and
    ``%rootResource`` are "Defined in FHIR"; SQL-on-FHIR v2 additionally
    defines ``%rowIndex`` as a runtime variable. These reserved runtime
    variables MUST NOT be shadowable by user-defined constants. If a user
    authors ``Constant(name='resource', ...)`` and references ``%resource``
    in a FHIRPath expression, the resolver must preserve ``%resource`` for
    runtime evaluation rather than substituting the user's literal value.
    """

    @pytest.mark.parametrize("builtin_name", sorted(FHIRPATH_BUILTIN_VARIABLES))
    def test_user_constant_named_after_builtin_does_not_shadow_runtime_var(
        self, builtin_name
    ):
        """A user constant whose name collides with a FHIRPath builtin
        must NOT have its value substituted in place of the runtime
        variable reference."""
        resolver = ConstantResolver.from_list(
            [Constant(name=builtin_name, value="user-value", value_type="string")]
        )
        resolved = resolver.resolve_in_path(f"%{builtin_name}")
        # The %<builtin> reference must be preserved verbatim for runtime
        # evaluation, NOT replaced with the user's "'user-value'" literal.
        assert resolved == f"%{builtin_name}", (
            f"user constant value leaked into builtin %{builtin_name} substitution: "
            f"resolved={resolved!r}"
        )

    def test_user_constant_named_after_builtin_in_larger_expression(self):
        """A user constant named 'resource' must not corrupt a larger
        FHIRPath expression that legitimately references the runtime
        %resource variable."""
        resolver = ConstantResolver.from_list(
            [Constant(name="resource", value="evil", value_type="string")]
        )
        resolved = resolver.resolve_in_path(
            "%resource.id = 'p1' and active = true"
        )
        assert resolved == "%resource.id = 'p1' and active = true"

    def test_user_constant_named_after_builtin_does_not_block_other_constants(self):
        """A user constant named 'resource' must still allow OTHER user
        constants to resolve normally."""
        resolver = ConstantResolver.from_list(
            [
                Constant(name="resource", value="evil", value_type="string"),
                Constant(name="Female", value="female", value_type="code"),
            ]
        )
        resolved = resolver.resolve_in_path(
            "%resource.gender = %Female"
        )
        assert resolved == "%resource.gender = 'female'"

    def test_resolver_still_uses_user_constants_for_non_builtin_names(self):
        """Sanity: ordinary user constants still resolve normally."""
        resolver = ConstantResolver.from_list(
            [Constant(name="MyConst", value="hello", value_type="string")]
        )
        assert resolver.resolve_in_path("%MyConst") == "'hello'"


class TestInteger64Range:
    """SOF-VD-02: integer64 constants must be representable as FHIRPath
    Integer literals (32-bit signed) when substituted textually."""

    def test_integer64_in_range_resolves(self):
        const = Constant(name="Big", value="2147483647", value_type="integer64")
        assert resolve_constant(const) == "2147483647"

    def test_integer64_in_range_negative_resolves(self):
        const = Constant(name="Small", value="-2147483648", value_type="integer64")
        assert resolve_constant(const) == "-2147483648"

    def test_integer64_out_of_range_raises(self):
        const = Constant(name="Big", value="5000000000", value_type="integer64")
        with pytest.raises(ConstantResolutionError, match="FHIRPath Integer literal range"):
            resolve_constant(const)

    def test_integer64_max_int64_raises(self):
        const = Constant(name="Max", value="9223372036854775807", value_type="integer64")
        with pytest.raises(ConstantResolutionError):
            resolve_constant(const)

    def test_out_of_range_integer64_reference_raises_at_resolution(self):
        resolver = ConstantResolver.from_list(
            [{"name": "big", "valueInteger64": "5000000000"}]
        )
        with pytest.raises(ConstantResolutionError, match="big"):
            resolver.resolve_in_path("%big = 5000000000")

    def test_undefined_reference_still_raises(self):
        resolver = ConstantResolver.from_list(
            [{"name": "big", "valueInteger64": "5000000000"}]
        )
        with pytest.raises(ConstantResolutionError, match="Undefined constant"):
            resolver.resolve_in_path("%other")


class TestDecimalPlainNotation:
    """Decimal constants must substitute as valid FHIRPath Number literals.

    The FHIRPath N1 grammar has no exponent notation, so Python ``str()``
    scientific notation (|v| < 1e-4 or |v| >= 1e16) would silently produce
    empty results in both evaluation engines (SQL-on-FHIR v2 constant
    value[x] "effectively converts the FHIR literal ... to a FHIRPath
    literal").
    """

    def test_small_decimal_not_scientific(self):
        const = Constant(name="Tiny", value=0.00001, value_type="decimal")
        assert resolve_constant(const) == "0.00001"

    def test_very_small_decimal_not_scientific(self):
        const = Constant(name="Tiny", value=0.0000001, value_type="decimal")
        assert resolve_constant(const) == "0.0000001"

    def test_large_decimal_not_scientific(self):
        const = Constant(name="Big", value=1e21, value_type="decimal")
        assert resolve_constant(const) == "1000000000000000000000.0"

    def test_decimal_integral_value_has_fractional_part(self):
        const = Constant(name="Whole", value=3, value_type="decimal")
        assert resolve_constant(const) == "3.0"

    def test_decimal_preserves_authored_precision(self):
        const = Constant(
            name="Precise",
            value=Decimal("12345678901234567890.12345"),
            value_type="decimal",
        )
        assert resolve_constant(const) == "12345678901234567890.12345"

    def test_negative_exponent_float_round_trips(self):
        const = Constant(name="Neg", value=-1.5e-8, value_type="decimal")
        assert resolve_constant(const) == "-0.000000015"

    def test_ordinary_decimal_unchanged(self):
        const = Constant(name="Ratio", value=3.14, value_type="decimal")
        assert resolve_constant(const) == "3.14"


class TestDecimalLosslessParsing:
    """ViewDefinition JSON decimals must parse without float precision loss."""

    def test_parser_preserves_18_digit_decimal_constant(self):
        from ...parser import parse_view_definition

        view = parse_view_definition(
            '{"resource":"Patient",'
            '"constant":[{"name":"Precise","valueDecimal":12345678901234567890.12345}],'
            '"select":[{"column":[{"name":"pid","path":"id"}]}]}'
        )
        value = view.constants[0].value
        assert isinstance(value, Decimal)
        assert str(value) == "12345678901234567890.12345"
        assert resolve_constant(view.constants[0]) == "12345678901234567890.12345"

    def test_parser_decimal_substitutes_plain_literal_end_to_end(self):
        from ...parser import parse_view_definition
        from ...generator import SQLGenerator

        view = parse_view_definition(
            '{"resource":"Patient",'
            '"constant":[{"name":"Tiny","valueDecimal":0.00001}],'
            '"select":[{"column":[{"name":"flag","path":"%Tiny < 0.001","type":"boolean"}]}]}'
        )
        sql = SQLGenerator().generate(view)
        assert "0.00001 < 0.001" in sql
        assert "1e-05" not in sql


class TestBacktickConstantReferences:
    """FHIRPath permits backtick-delimited environment variable names (%`name`).

    SQL-on-FHIR constants are substituted before evaluation, so the backtick
    spelling must resolve identically to the plain %name form (FHIRPath spec,
    Environment Variables; SQL-on-FHIR v2 notes: placeholders are "effectively
    replaced by the value of the constant before the FHIRPath expression is
    evaluated"). Regression for SOF-VD-08 EXPLORER QA-001: the backtick form
    previously fell through to the delimited-identifier skip-region and
    silently evaluated to an empty collection (NULL columns, all-rows-dropped
    where filters).
    """

    def _consts(self):
        return {"lbl": Constant(name="lbl", value="LAB", value_type="string")}

    def test_backtick_reference_resolves(self):
        assert (
            resolve_constants_in_path("x = %`lbl`", self._consts()) == "x = 'LAB'"
        )

    def test_backtick_reference_inside_string_literal_untouched(self):
        path = "'%`lbl`'"
        assert resolve_constants_in_path(path, self._consts()) == path

    def test_plain_reference_unchanged(self):
        assert resolve_constants_in_path("x = %lbl", self._consts()) == "x = 'LAB'"

    def test_builtin_runtime_variable_normalized_to_plain_form(self):
        # Runtime variables are resolved by the engines, which do not accept
        # the backtick form; normalize %`rowIndex` -> %rowIndex.
        assert resolve_constants_in_path("%`rowIndex`", {}) == "%rowIndex"

    def test_undefined_backtick_reference_raises_loudly(self):
        with pytest.raises(ConstantResolutionError):
            resolve_constants_in_path("x = %`nope`", self._consts())

    def test_escaped_backtick_name_cannot_be_defined_so_raises(self):
        # Constant names must satisfy the sql-name invariant (no backticks),
        # so a backtick-escaped name is never defined and must fail loudly
        # rather than silently evaluating to an empty collection.
        with pytest.raises(ConstantResolutionError):
            resolve_constants_in_path(r"%`a\`b`", self._consts())

    def test_backtick_constant_in_unionall_branch_end_to_end(self):
        import duckdb

        from ...parser import parse_view_definition
        from ...generator import SQLGenerator
        from ....fhirpath.duckdb import register_fhirpath

        view = parse_view_definition(
            '{"resource":"Patient",'
            '"constant":[{"name":"lbl","valueString":"LAB"}],'
            '"select":[{"unionAll":[{"column":['
            '{"name":"v","path":"%`lbl`"},{"name":"pid","path":"id"}]}]}]}'
        )
        sql = SQLGenerator().generate(view)
        con = duckdb.connect()
        try:
            register_fhirpath(con)
            con.execute("CREATE TABLE patients (resource JSON)")
            con.execute(
                "INSERT INTO patients VALUES (?)",
                [json.dumps({"resourceType": "Patient", "id": "p1"})],
            )
            assert con.execute(sql).fetchall() == [("LAB", "p1")]
        finally:
            con.close()

    def test_backtick_constant_in_where_end_to_end(self):
        import duckdb

        from ...parser import parse_view_definition
        from ...generator import SQLGenerator
        from ....fhirpath.duckdb import register_fhirpath

        view = parse_view_definition(
            '{"resource":"Patient",'
            '"constant":[{"name":"lbl","valueString":"LAB"}],'
            '"where":[{"path":"%`lbl` = \'LAB\'"}],'
            '"select":[{"column":[{"name":"pid","path":"id"}]}]}'
        )
        sql = SQLGenerator().generate(view)
        con = duckdb.connect()
        try:
            register_fhirpath(con)
            con.execute("CREATE TABLE patients (resource JSON)")
            con.execute(
                "INSERT INTO patients VALUES (?)",
                [json.dumps({"resourceType": "Patient", "id": "p1"})],
            )
            assert con.execute(sql).fetchall() == [("p1",)]
        finally:
            con.close()


class TestDecimalToDictJsonSerialization:
    """SOF-VD-12 EXPLORER QA-001: to_dict must emit JSON-serializable numbers.

    The parser keeps valueDecimal as Decimal (lossless FHIRPath literal
    doctrine), but Constant.to_dict previously emitted the Decimal verbatim,
    so json.dumps(vd.to_dict()) raised TypeError and the output type depended
    on the input path (JSON string -> Decimal, dict -> float).
    """

    def test_to_dict_output_is_json_serializable(self):
        from ...parser import parse_view_definition

        view = parse_view_definition(
            '{"resource":"Patient",'
            '"constant":[{"name":"Ratio","valueDecimal":1.2}],'
            '"select":[{"column":[{"name":"pid","path":"id"}]}]}'
        )
        encoded = json.dumps(view.to_dict())
        assert json.loads(encoded)["constant"][0]["valueDecimal"] == 1.2

    def test_to_dict_matches_dict_input_path(self):
        from ...parser import parse_view_definition

        via_string = parse_view_definition(
            '{"resource":"Patient",'
            '"constant":[{"name":"Ratio","valueDecimal":1.2}],'
            '"select":[{"column":[{"name":"pid","path":"id"}]}]}'
        )
        via_dict = parse_view_definition(
            {
                "resource": "Patient",
                "constant": [{"name": "Ratio", "valueDecimal": 1.2}],
                "select": [{"column": [{"name": "pid", "path": "id"}]}],
            }
        )
        assert via_string.to_dict() == via_dict.to_dict()

    def test_integral_decimal_serializes_as_int(self):
        const = Constant(name="Whole", value=Decimal("2.0"), value_type="decimal")
        assert const.to_dict() == {"name": "Whole", "valueDecimal": 2}

    def test_float_passthrough_unchanged(self):
        const = Constant(name="Half", value=1.5, value_type="decimal")
        assert const.to_dict() == {"name": "Half", "valueDecimal": 1.5}

    def test_unrepresentable_decimal_fails_fast(self):
        const = Constant(
            name="Precise", value=Decimal("1.23456789012345678"),
            value_type="decimal",
        )
        with pytest.raises(ValueError, match="valueDecimal"):
            const.to_dict()

    def test_dataclass_value_stays_decimal_for_generator(self):
        from ...parser import parse_view_definition

        view = parse_view_definition(
            '{"resource":"Patient",'
            '"constant":[{"name":"Tiny","valueDecimal":0.00001}],'
            '"select":[{"column":[{"name":"pid","path":"id"}]}]}'
        )
        assert isinstance(view.constants[0].value, Decimal)
        assert resolve_constant(view.constants[0]) == "0.00001"
