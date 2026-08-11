"""Unit tests for constant resolution.

Tests the resolution of constants defined in ViewDefinitions
into SQL values, including simple values, Codings, and
CodeableConcepts.
"""

import pytest

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
        """FHIR JSON encodes integer64 as string, but FHIRPath receives a number."""
        const = Constant(name="Large", value="1234567890123", value_type="integer64")
        result = resolve_constant(const)

        assert result == "1234567890123"


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
