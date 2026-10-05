"""Unit tests for fhir4ds.devserver.resources (v3 Slice 1)."""
from fhir4ds.devserver.resources import (
    ValueSetEdit,
    apply_valueset_edit,
    delete_parameter,
    header_info,
    parse_parameters,
    upsert_parameter,
    validate_valueset_edit,
    valueset_used_by,
)

LIB = """library Demographics version '1.0.0'
using FHIR version '4.0.1'

parameter "MinAge" Integer default 18

// # %% [name: IsMale]
define IsMale: Patient.gender = 'male'
"""


class TestParameters:
    def test_parse_single_parameter(self):
        infos = parse_parameters(LIB)
        assert len(infos) == 1
        p = infos[0]
        assert p.name == "MinAge"
        assert p.type == "Integer"
        assert p.default == "18"

    def test_header_info_shape(self):
        h = header_info(LIB)
        assert h["library"] == "Demographics"
        assert h["includes"] == []
        assert [(p["name"], p["type"], p["default"]) for p in h["parameters"]] == [
            ("MinAge", "Integer", "18")
        ]

    def test_upsert_appends_new_parameter(self):
        out = upsert_parameter(LIB, "Gender", "String", None)
        lines = [l for l in out.splitlines() if l.startswith("parameter")]
        assert lines == ['parameter "MinAge" Integer default 18', 'parameter "Gender" String']

    def test_upsert_updates_existing_in_place(self):
        out = upsert_parameter(LIB, "MinAge", "Integer", "21")
        lines = [l for l in out.splitlines() if l.startswith("parameter")]
        assert lines == ['parameter "MinAge" Integer default 21']

    def test_delete_parameter(self):
        with_gender = upsert_parameter(LIB, "Gender", "String", None)
        out = delete_parameter(with_gender, "Gender")
        lines = [l for l in out.splitlines() if l.startswith("parameter")]
        assert lines == ['parameter "MinAge" Integer default 18']

    def test_fresh_insert_when_no_parameters(self):
        bare = "library T\nusing FHIR version '4.0.1'\n\ndefine X: true\n"
        out = upsert_parameter(bare, "P", "Boolean", "true")
        assert 'parameter "P" Boolean default true' in out

    def test_sequential_edits_compose(self):
        t1 = upsert_parameter(LIB, "Gender", "String", None)
        t2 = upsert_parameter(t1, "MinAge", "Integer", "21")
        t3 = delete_parameter(t2, "Gender")
        infos = parse_parameters(t3)
        assert [(p.name, p.default) for p in infos] == [("MinAge", "21")]


def _vs() -> dict:
    return {
        "resourceType": "ValueSet",
        "id": "vs1",
        "url": "http://example.com/vs1",
        "compose": {
            "include": [
                {"system": "http://loinc.org", "concept": [{"code": "8480-6", "display": "BP"}]}
            ]
        },
    }


class TestValueSetEdits:
    def test_add_appends_to_matching_system(self):
        out = apply_valueset_edit(
            _vs(), ValueSetEdit(action="add", system="http://loinc.org", code="8462-4", display="DBP")
        )
        codes = [c["code"] for c in out["compose"]["include"][0]["concept"]]
        assert codes == ["8480-6", "8462-4"]

    def test_add_creates_new_system_block(self):
        out = apply_valueset_edit(
            _vs(), ValueSetEdit(action="add", system="http://snomed.info/sct", code="195967001")
        )
        assert [i["system"] for i in out["compose"]["include"]] == [
            "http://loinc.org",
            "http://snomed.info/sct",
        ]

    def test_update_rewrites_code(self):
        out = apply_valueset_edit(
            _vs(),
            ValueSetEdit(action="update", system="http://loinc.org", code="8480-7", old_code="8480-6"),
        )
        assert [c["code"] for c in out["compose"]["include"][0]["concept"]] == ["8480-7"]

    def test_remove_filters(self):
        two = apply_valueset_edit(
            _vs(), ValueSetEdit(action="add", system="http://loinc.org", code="8462-4")
        )
        out = apply_valueset_edit(
            two, ValueSetEdit(action="remove", system="http://loinc.org", code="8462-4")
        )
        assert [c["code"] for c in out["compose"]["include"][0]["concept"]] == ["8480-6"]

    def test_validate_rejects_bad_system(self):
        problems = validate_valueset_edit(
            ValueSetEdit(action="add", system="not-a-uri", code="x")
        )
        assert problems and "absolute http(s) URI" in problems[0]

    def test_validate_rejects_empty_code(self):
        problems = validate_valueset_edit(
            ValueSetEdit(action="add", system="http://x.org", code="")
        )
        assert problems == ["code must be a non-empty string"]

    def test_used_by_matches_valueset_decl(self):
        lib = (
            "Demographics",
            "valueset \"VS1\": 'http://example.com/vs1'\ndefine Asthma: exists([Condition] C where C.code in VS1)",
        )
        assert valueset_used_by(_vs(), [lib]) == ["Demographics.VS1"]

    def test_used_by_empty_when_unreferenced(self):
        assert valueset_used_by(_vs(), [("Other", "define X: true")]) == []
