"""Tests for resource_schema_tree (test-data-authoring §3.1)."""

from __future__ import annotations

import pytest

from fhir4ds.operations import resource_schema_tree
from fhir4ds.operations.capabilities.schema_tree import SchemaTreeResult


def _child(root: dict, name: str) -> dict:
    matches = [c for c in root["children"] if c["name"] == name]
    assert matches, f"no child named {name!r}"
    return matches[0]


class TestPatientTree:
    def test_root_shape(self):
        r = resource_schema_tree("Patient")
        assert isinstance(r, SchemaTreeResult)
        assert r.ok is True
        assert r.diagnostics == ()
        assert r.root["name"] == "Patient"
        assert r.root["type"] == "Patient"
        names = {c["name"] for c in r.root["children"]}
        assert "gender" in names and "birthDate" in names and "name" in names

    def test_primitive_fields_carry_type_and_cardinality(self):
        r = resource_schema_tree("Patient")
        gender = _child(r.root, "gender")
        assert gender["type"] == "code"
        assert gender["cardinality"] == "0..1"

    def test_complex_datatype_children_resolve(self):
        # Patient.name -> HumanName children via vendored datatype SD
        r = resource_schema_tree("Patient")
        name = _child(r.root, "name")
        assert name["type"] == "HumanName"
        child_names = {c["name"] for c in name["children"]}
        assert {"use", "text", "family", "given", "prefix", "suffix", "period"} <= child_names

    def test_nested_datatype_at_depth(self):
        # Patient.name.period -> Period children
        r = resource_schema_tree("Patient")
        period = _child(_child(r.root, "name"), "period")
        assert period["type"] == "Period"
        assert {c["name"] for c in period["children"]} >= {"start", "end"}

    def test_choice_arms_synthesized(self):
        r = resource_schema_tree("Patient")
        arms = {c["name"] for c in r.root["children"] if c["name"].startswith("deceased")}
        assert arms == {"deceasedBoolean", "deceasedDateTime"}
        # arms carry the arm's own concrete type
        dt = _child(r.root, "deceasedDateTime")
        assert dt["type"] == "dateTime"

    def test_backbone_children_inline(self):
        r = resource_schema_tree("Patient")
        contact = _child(r.root, "contact")
        assert contact["type"] == "BackboneElement"
        child_names = {c["name"] for c in contact["children"]}
        assert {"name", "telecom", "address", "relationship", "period"} <= child_names

    def test_backbone_datatype_recursion(self):
        # Patient.contact.name -> HumanName children (depth 3)
        r = resource_schema_tree("Patient")
        contact_name = _child(_child(r.root, "contact"), "name")
        assert contact_name["type"] == "HumanName"
        assert {"family", "given"} <= {c["name"] for c in contact_name["children"]}

    def test_array_cardinality_from_max_star(self):
        r = resource_schema_tree("Patient")
        name = _child(r.root, "name")
        assert name["cardinality"] == "0..*"

    def test_reference_targets_present(self):
        r = resource_schema_tree("Patient")
        gp = _child(r.root, "generalPractitioner")
        assert gp["type"] == "Reference"
        assert "Organization" in gp["reference_targets"]
        assert "Practitioner" in gp["reference_targets"]


class TestObservationTree:
    def test_value_choice_arms_full_set(self):
        r = resource_schema_tree("Observation")
        arms = {c["name"] for c in r.root["children"] if c["name"].startswith("value")}
        assert "valueQuantity" in arms and "valueCodeableConcept" in arms
        assert "valueDateTime" in arms and "valueString" in arms
        # arms are typed
        vq = _child(r.root, "valueQuantity")
        assert vq["type"] == "Quantity"

    def test_quantity_children_resolve(self):
        # Observation.valueQuantity.value — the trimmed resource snapshot
        # lacks it; the vendored datatype SD supplies it.
        r = resource_schema_tree("Observation")
        vq = _child(r.root, "valueQuantity")
        child_names = {c["name"] for c in vq["children"]}
        assert {"value", "unit", "system", "code", "comparator"} <= child_names

    def test_nested_backbone_choice_arms(self):
        # Observation.component.value[x] arms exist inside the backbone
        r = resource_schema_tree("Observation")
        comp = _child(r.root, "component")
        arms = {c["name"] for c in comp["children"] if c["name"].startswith("value")}
        assert "valueQuantity" in arms and "valueString" in arms

    def test_content_reference_redirect(self):
        # Observation.component.referenceRange -> #Observation.referenceRange
        r = resource_schema_tree("Observation")
        comp = _child(r.root, "component")
        rr = _child(comp, "referenceRange")
        child_names = {c["name"] for c in rr["children"]}
        assert {"low", "high"} <= child_names

    def test_code_codeableconcept_coding_depth(self):
        # Observation.code -> CodeableConcept -> Coding fields (depth 3)
        r = resource_schema_tree("Observation")
        code = _child(r.root, "code")
        coding = _child(code, "coding")
        assert coding["type"] == "Coding"
        assert {"system", "code", "display", "version"} <= {
            c["name"] for c in coding["children"]
        }


class TestDepthAndEdges:
    def test_depth_cap_emits_hatch(self):
        r = resource_schema_tree("Patient", depth=2)
        period = _child(_child(r.root, "name"), "period")
        assert period["children"] == [{"name": "__hatch__", "hatch": True}]

    def test_depth_cap_default_is_four(self):
        # Depth 4: Patient.contact.organization (Reference) is a leaf at
        # depth 1; Patient.name.period children exist; the next level hatches.
        r = resource_schema_tree("Patient")
        period = _child(_child(r.root, "name"), "period")
        assert {c["name"] for c in period["children"]} >= {"start", "end"}

    def test_unknown_resource_not_found(self):
        r = resource_schema_tree("Organization")
        assert r.ok is False
        assert r.diagnostics[0].code.value == "not_found"
        assert r.root is None

    def test_non_string_input_error(self):
        r = resource_schema_tree(None)
        assert r.ok is False
        assert r.diagnostics[0].code.value == "input_error"

    def test_empty_string_input_error(self):
        r = resource_schema_tree("   ")
        assert r.ok is False

    def test_result_to_dict_roundtrip(self):
        r = resource_schema_tree("Patient")
        d = r.to_dict()
        assert d["schema"] == 1
        assert d["ok"] is True
        assert d["resource_type"] == "Patient"
        assert d["root"]["name"] == "Patient"

    def test_envelope_shape_on_error(self):
        d = resource_schema_tree("Nope").to_dict()
        assert d["ok"] is False
        assert "root" not in d
        assert d["diagnostics"][0]["code"] == "not_found"

    def test_extension_hatches(self):
        # extension/contained etc. have SDs but are hatch-by-doctrine in
        # the builder; the tree still exposes them (UI decides the hatch).
        r = resource_schema_tree("Patient")
        ext = _child(r.root, "extension")
        assert ext["type"] == "Extension"


class TestResourceSet:
    def test_all_shipped_resource_types_build(self):
        from fhir4ds.operations.capabilities.schema_tree import _RESOURCE_SD_NAMES

        assert len(_RESOURCE_SD_NAMES) >= 15
        for name in sorted(_RESOURCE_SD_NAMES):
            r = resource_schema_tree(name)
            assert r.ok is True, name
            assert r.root["children"], name


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
