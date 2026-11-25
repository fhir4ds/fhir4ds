"""WP-3 — the FHIRPath R4 corpus evaluates against typed FHIR JSON.

The XML examples are converted with the official R4 StructureDefinitions into
``examples-typed/``. These tests need no FHIR package: they pin that the committed
conversions are complete, current and typed the way FHIR defines, and that the evaluator
feeds them to the UDF with the official runner's own input resolution.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest

from fhir4ds.operations.tests.wasm_parity import typed_examples
from fhir4ds.operations.tests.wasm_parity.evaluators import fhirpath

EXAMPLES = fhirpath.R4_DIR / "examples"
TYPED = fhirpath.R4_DIR / typed_examples.TYPED_DIR_NAME
REGENERATE = "python -m fhir4ds.operations.tests.wasm_parity.typed_examples"


def _xml_examples() -> list[Path]:
    return sorted(EXAMPLES.glob("*.xml"))


# --- the committed conversions -----------------------------------------------------------------


def test_every_xml_example_has_a_current_conversion():
    xml_examples = _xml_examples()
    assert xml_examples, f"no XML examples under {EXAMPLES}"
    manifest = json.loads((TYPED / typed_examples.MANIFEST_NAME).read_text(encoding="utf-8"))
    missing = [
        name
        for name in (x.name for x in xml_examples)
        if not typed_examples.typed_path(fhirpath.R4_DIR, name).is_file()
    ]
    assert not missing, f"no typed conversion for {missing}; regenerate: {REGENERATE}"
    stale = [
        x.name
        for x in xml_examples
        if manifest["sources"].get(x.name) != typed_examples.sha256_of(x)
    ]
    assert not stale, f"converted from an older XML: {stale}; regenerate: {REGENERATE}"


def test_each_conversion_still_describes_its_source():
    for xml in _xml_examples():
        problems = typed_examples.describes(
            xml.read_text(encoding="utf-8"), typed_examples.load_typed(fhirpath.R4_DIR, xml.name)
        )
        assert problems == [], f"{xml.name}: {problems[:3]}"


def test_types_follow_the_specification_not_the_tag_names():
    patient = json.loads(
        typed_examples.load_typed(fhirpath.R4_DIR, "patient-example.xml"), parse_float=Decimal
    )
    assert patient["resourceType"] == "Patient"
    assert patient["active"] is True
    assert patient["deceasedBoolean"] is False
    assert patient["birthDate"] == "1974-12-25"
    assert isinstance(patient["name"], list) and isinstance(patient["name"][0]["given"], list)


def test_decimals_keep_their_authored_digits():
    text = typed_examples.load_typed(fhirpath.R4_DIR, "parameters-example-decimals.xml")
    # a JSON number whose digits are the authored ones
    assert '"valueDecimal": 9.5e2' in text
    assert '"valueDecimal": -9.5e2' in text


def test_contained_resources_become_json_objects():
    observation = json.loads(
        typed_examples.load_typed(fhirpath.R4_DIR, "observation-example-20minute-apgar-score.xml")
    )
    assert [c["resourceType"] for c in observation["contained"]] == ["Patient"]
    assert observation["contained"][0]["active"] is True


def test_a_stale_conversion_is_refused(tmp_path):
    r4 = tmp_path / "r4"
    (r4 / "examples").mkdir(parents=True)
    (r4 / typed_examples.TYPED_DIR_NAME).mkdir()
    (r4 / "examples" / "a.xml").write_text("<Patient/>", encoding="utf-8")
    (r4 / typed_examples.TYPED_DIR_NAME / "a.json").write_text("{}", encoding="utf-8")
    (r4 / typed_examples.TYPED_DIR_NAME / typed_examples.MANIFEST_NAME).write_text(
        json.dumps({"sources": {"a.xml": "0" * 64}}), encoding="utf-8"
    )
    with pytest.raises(typed_examples.TypingError, match="older a.xml"):
        typed_examples.load_typed(r4, "a.xml")


def test_a_json_example_is_not_reconverted():
    assert typed_examples.typed_path(fhirpath.R4_DIR, "bundle-document-ips.json") is None


# --- the conversion rules, on a small definition set written here --------------------------------


def _definition(root: str, elements: list[tuple[str, list[str], str]]) -> dict:
    return {
        "resourceType": "StructureDefinition",
        "version": "4.0.1",
        "type": root,
        "snapshot": {
            "element": [
                {
                    "path": path,
                    "max": maximum,
                    "type": [{"code": code} for code in codes] if codes else [],
                }
                for path, codes, maximum in elements
            ]
        },
    }


@pytest.fixture
def index(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    definitions = {
        "Patient": [
            ("Patient", [], "*"),
            ("Patient.active", ["boolean"], "1"),
            ("Patient.birthDate", ["date"], "1"),
            ("Patient.deceased[x]", ["boolean", "dateTime"], "1"),
            ("Patient.multipleBirthInteger", ["integer"], "1"),
            ("Patient.name", ["HumanName"], "*"),
            ("Patient.contained", ["Resource"], "*"),
        ],
        "HumanName": [
            ("HumanName", [], "*"),
            ("HumanName.family", ["string"], "1"),
            ("HumanName.given", ["string"], "*"),
        ],
        "Element": [("Element", [], "*"), ("Element.id", ["string"], "1"),
                    ("Element.extension", ["Extension"], "*")],
        "Extension": [
            ("Extension", [], "*"),
            ("Extension.url", ["uri"], "1"),
            ("Extension.value[x]", ["boolean", "string", "decimal"], "1"),
        ],
    }
    for name, elements in definitions.items():
        (package / f"StructureDefinition-{name}.json").write_text(
            json.dumps(_definition(name, elements)), encoding="utf-8"
        )
    return typed_examples.StructureIndex(package, "4.0.1")


PATIENT_XML = """<Patient xmlns="http://hl7.org/fhir">
  <active value="true"/>
  <birthDate value="1974-12-25">
    <extension url="http://example.org/ext"><valueString value="a"/></extension>
  </birthDate>
  <deceasedBoolean value="false"/>
  <multipleBirthInteger value="2"/>
  <name><family value="Chalmers"/><given value="Peter"/><given value="James"/></name>
  <contained><Patient><active value="true"/></Patient></contained>
</Patient>"""


def test_conversion_rules(index):
    assert typed_examples.convert_resource(PATIENT_XML, index) == {
        "resourceType": "Patient",
        "active": True,
        "birthDate": "1974-12-25",
        "_birthDate": {"extension": [{"url": "http://example.org/ext", "valueString": "a"}]},
        "deceasedBoolean": False,
        "multipleBirthInteger": 2,
        "name": [{"family": "Chalmers", "given": ["Peter", "James"]}],
        "contained": [{"resourceType": "Patient", "active": True}],
    }


def test_an_undefined_element_is_an_error_not_a_guess(index):
    head, close, tail = PATIENT_XML.rpartition("</Patient>")  # the resource's own close tag
    with pytest.raises(typed_examples.TypingError, match="Patient.maritalStatus"):
        typed_examples.convert_resource(head + "<maritalStatus/>" + close + tail, index)


def test_json_keeps_a_decimal_verbatim():
    resource = {"valueDecimal": typed_examples.DecimalText("9.5e2"), "n": typed_examples.DecimalText("5.0")}
    text = typed_examples.to_json(resource)
    assert '"valueDecimal": 9.5e2' in text and '"n": 5.0' in text
    with pytest.raises(InvalidOperation):
        typed_examples.DecimalText("1974-12-25")


# --- the evaluator's input resolution ----------------------------------------------------------


def _tests_by_name():
    run_r4 = fhirpath.runner()
    return run_r4, {t.name: t for t in run_r4.parse_test_xml(fhirpath.XML_FILE)}


def test_evaluator_reads_an_xml_example_from_its_typed_conversion():
    run_r4, by_name = _tests_by_name()
    test = next(t for t in by_name.values() if t.input_file == "patient-example.xml")
    assert '"active": true' in fhirpath._input_text(run_r4, test)


def test_evaluator_prefers_a_json_twin_over_an_xml_stub_like_the_official_runner():
    run_r4, by_name = _tests_by_name()
    test = next(t for t in by_name.values() if t.input_file == "questionnaire-example.xml")
    # the XML is a two-element stub; the official runner loads the JSON twin instead
    assert '"item"' in fhirpath._input_text(run_r4, test)


def test_an_xml_example_without_a_conversion_is_gated_not_misjudged(monkeypatch, tmp_path):
    run_r4, by_name = _tests_by_name()
    test = next(
        t
        for t in by_name.values()
        if t.input_file == "patient-example.xml" and fhirpath._gating_reason(run_r4, t) is None
    )
    monkeypatch.setattr(
        typed_examples, "typed_path", lambda r4_dir, input_file: tmp_path / "missing.json"
    )
    assert fhirpath._input_text(run_r4, test) is None
    reason = fhirpath._gating_reason(run_r4, test)
    assert reason is not None and "without a typed JSON conversion" in reason
