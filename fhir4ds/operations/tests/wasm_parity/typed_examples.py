"""Typed JSON for the FHIRPath R4 example resources.

The official FHIRPath corpus names its input resources by file, and most of them are FHIR XML.
A DuckDB UDF takes JSON, and the XML form carries no type in the element names
(``<active value="true"/>``), so a conversion that types by tag name hands the engine
``"true"`` where FHIR says a Boolean is. Every type-dependent expression is then evaluated
against the wrong input.

This module converts the XML examples with the official R4 StructureDefinitions (the
``hl7.fhir.r4.core#4.0.1`` package, as FHIR tooling caches it under ``~/.fhir/packages``)
into the JSON the FHIR specification defines: Booleans as JSON Booleans, integers as JSON
integers, decimals keeping their authored digits, everything else as strings.

Only the generator needs the package. The generated files are committed, so neither the gate
nor CI does; ``shape()`` is the package-free check that a generated file still describes its
XML source.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
SYSTEM_STRING = "http://hl7.org/fhirpath/System.String"
INTEGER_TYPES = frozenset({"integer", "unsignedInt", "positiveInt", "integer64"})
# JSON represents every primitive but these three families as a string
PRIMITIVE_TYPES = frozenset(
    {
        "base64Binary", "boolean", "canonical", "code", "date", "dateTime", "decimal", "id",
        "instant", "integer", "integer64", "markdown", "oid", "positiveInt", "string", "time",
        "unsignedInt", "uri", "url", "uuid", "xhtml",
    }
)
_CHOICE = re.compile(r"\[x\]$")
INHERITED_FROM_ELEMENT = frozenset({"id", "extension", "modifierExtension"})


class TypingError(ValueError):
    """An element the StructureDefinitions do not define. Its type is never guessed."""


class DecimalText(str):
    """A FHIR decimal exactly as authored.

    JSON must keep the digits: ``5.0`` is not ``5`` and the precision of ``9.5e2`` is in its
    mantissa. A float or a ``Decimal`` round trip silently changes both.
    """

    def __new__(cls, raw: str):
        Decimal(raw)  # rejects anything that is not a decimal lexical form
        return super().__new__(cls, raw)


class StructureIndex:
    """Element definitions of one FHIR release, addressed by full path."""

    def __init__(self, package_dir: Path, release: str):
        self.package_dir = package_dir
        self.release = release
        self._by_path: dict[str, list[dict[str, Any]]] = {}
        self._known: set[str] = set()
        self._missing: set[str] = set()

    def has_type(self, type_name: str) -> bool:
        """Load ``StructureDefinition-<type_name>.json`` on first use; False when absent."""
        if type_name in self._known:
            return True
        if type_name in self._missing:
            return False
        path = self.package_dir / f"StructureDefinition-{type_name}.json"
        if not path.is_file():
            self._missing.add(type_name)
            return False
        definition = json.loads(path.read_text(encoding="utf-8"))
        found = definition.get("version")
        if found != self.release:
            raise TypingError(
                f"{path.name} is FHIR {found!r}; this index is for {self.release!r}"
            )
        for element in definition["snapshot"]["element"]:
            self._by_path.setdefault(element["path"], []).append(element)
        self._known.add(type_name)
        return True

    def resolve(self, container: str, tag: str) -> tuple[str, dict[str, Any]]:
        """The definition of the XML child ``tag`` under ``container``.

        ``container`` is a type name (``Patient``) or a path into one (``Questionnaire.item``).
        Returns the DEFINITION path (which keeps ``[x]`` for a choice) and its base element.
        """
        self.has_type(container.split(".", 1)[0])
        prefix = container + "."
        depth = container.count(".") + 1
        exact = self._by_path.get(prefix + tag)
        if exact:
            return prefix + tag, exact[0]
        for path, elements in self._by_path.items():
            if path.startswith(prefix) and path.count(".") == depth:
                name = path[len(prefix):]
                if _CHOICE.search(name) and tag.startswith(name[:-3]):
                    return path, elements[0]
        # a named slice (``Parameters.parameter:part``) may define what the base element lacks
        for path, elements in self._by_path.items():
            if path.startswith(prefix + tag + ":") and path.count(".") == depth:
                if elements[0].get("type") or "contentReference" in elements[0]:
                    return path, elements[0]
        raise TypingError(f"{container}.{tag} is not defined in FHIR {self.release}")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _type_codes(element: dict[str, Any]) -> list[str]:
    return [
        "string" if entry["code"] == SYSTEM_STRING else entry["code"]
        for entry in element.get("type", [])
    ]


def _element_type(element: dict[str, Any], definition_path: str, container: str, tag: str) -> str:
    """The type of a concrete XML element: the only type, or the choice branch its name selects."""
    if "contentReference" in element:
        return "BackboneElement"
    if not element.get("type"):
        raise TypingError(f"{definition_path} has neither a type nor a contentReference")
    codes = _type_codes(element)
    if len(codes) == 1:
        return codes[0]
    base = definition_path[len(container) + 1:]
    if not _CHOICE.search(base):
        raise TypingError(f"{definition_path}: {len(codes)} types but not a choice")
    suffix = tag[len(base) - 3:]
    for code in codes:
        if suffix == code[0].upper() + code[1:]:
            return code
    raise TypingError(f"{container}.{tag}: no type among {codes} has the suffix {suffix!r}")


def _primitive_value(raw: str, code: str, path: str) -> Any:
    if code == "boolean":
        if raw not in ("true", "false"):
            raise TypingError(f"{path}: {raw!r} is not a FHIR boolean")
        return raw == "true"
    if code in INTEGER_TYPES:
        return int(raw)
    if code == "decimal":
        return DecimalText(raw)
    return raw


def _convert(children: list[ET.Element], container: str, index: StructureIndex) -> dict[str, Any]:
    """The JSON object for the children of one element of type/path ``container``."""
    grouped: dict[str, list[ET.Element]] = {}
    for child in children:
        grouped.setdefault(_local(child.tag), []).append(child)
    result: dict[str, Any] = {}
    for tag, elements in grouped.items():
        try:
            definition_path, element = index.resolve(container, tag)
        except TypingError:
            if tag not in INHERITED_FROM_ELEMENT:
                raise
            # a path-typed element (R4 types ``Timing.repeat`` as ``Element``) does not repeat
            # the ``id`` / extension children every element has
            definition_path, element = index.resolve("Element", tag)
        code = _element_type(element, definition_path, container, tag)
        repeated = element.get("max", "1") != "1"
        if code == "xhtml":
            values = [ET.tostring(one, encoding="unicode").strip() for one in elements]
            result[tag] = values if repeated else values[0]
            continue
        if code in PRIMITIVE_TYPES:
            values, extras = [], []
            for one in elements:
                value, extra = _primitive_element(one, code, container + "." + tag, index)
                values.append(value)
                extras.append(extra)
            result[tag] = values if repeated else values[0]
            if any(extra is not None for extra in extras):
                result["_" + tag] = extras if repeated else extras[0]
            continue
        reference = element.get("contentReference")
        values = []
        for one in elements:
            value = _convert_element(one, code, container + "." + tag, reference, index)
            if isinstance(value, list):
                values.extend(value)
            else:
                values.append(value)
        result[tag] = values if repeated else values[0]
    return result


def _primitive_element(
    elem: ET.Element, code: str, path: str, index: StructureIndex
) -> tuple[Any, dict[str, Any] | None]:
    """A primitive's value and, when it carries an ``id`` or extensions, the ``_field`` object."""
    extra: dict[str, Any] | None = None
    if elem.get("id"):
        extra = {"id": elem.get("id")}
    nested = list(elem)
    if nested:
        # an ``id`` or extensions on a primitive are defined by ``Element``, not by its type
        extra = {**(extra or {}), **_convert(nested, "Element", index)}
    if "value" not in elem.attrib:
        if extra is None:
            raise TypingError(f"{path}: a primitive element with neither a value nor children")
        return None, extra
    return _primitive_value(elem.attrib["value"], code, path), extra


def _convert_element(
    elem: ET.Element, code: str, path: str, content_reference: str | None, index: StructureIndex
) -> Any:
    """One non-primitive element.

    ``path`` is where its children are defined when they hang off the element itself (a
    backbone element) rather than off a named type; a ``contentReference`` redirects there.
    """
    if code == "Resource":
        # ``<contained><Patient>...</Patient></contained>``: the element WRAPS the resources
        return [
            {"resourceType": _local(child.tag), **_convert(list(child), _local(child.tag), index)}
            for child in elem
        ]
    if code in ("BackboneElement", "Element"):
        return _convert(list(elem), (content_reference or "").lstrip("#") or path, index)
    if not index.has_type(code):
        raise TypingError(f"<{_local(elem.tag)}>: {code!r} is not a FHIR {index.release} type")
    value: dict[str, Any] = {}
    if elem.get("id"):
        value["id"] = elem.get("id")
    if code == "Extension":
        value["url"] = elem.attrib["url"]
    value.update(_convert(list(elem), code, index))
    return value


def convert_resource(xml_text: str, index: StructureIndex) -> dict[str, Any]:
    """The FHIR JSON for one XML resource, ``resourceType`` first."""
    ET.register_namespace("", XHTML_NAMESPACE)
    root = ET.fromstring(xml_text)
    name = _local(root.tag)
    if not index.has_type(name):
        raise TypingError(f"{name} is not a resource in FHIR {index.release}")
    return {"resourceType": name, **_convert(list(root), name, index)}


def to_json(resource: dict[str, Any]) -> str:
    """JSON text in which a decimal keeps its authored digits (``5.0`` stays ``5.0``).

    ``json.dumps`` cannot emit that: it has no way to write a decimal with its digits intact.
    """
    parts: list[str] = []

    def emit(value: Any, level: int) -> None:
        pad = "\n" + "  " * level
        if isinstance(value, dict):
            if not value:
                parts.append("{}")
                return
            parts.append("{")
            for i, (key, item) in enumerate(value.items()):
                parts.append(("," if i else "") + pad + json.dumps(key, ensure_ascii=False) + ": ")
                emit(item, level + 1)
            parts.append(pad[:-2] + "}")
        elif isinstance(value, list):
            if not value:
                parts.append("[]")
                return
            parts.append("[")
            for i, item in enumerate(value):
                parts.append(("," if i else "") + pad)
                emit(item, level + 1)
            parts.append(pad[:-2] + "]")
        elif isinstance(value, bool):
            parts.append("true" if value else "false")
        elif isinstance(value, DecimalText):
            parts.append(str(value))
        elif isinstance(value, int):
            parts.append(str(value))
        elif isinstance(value, str):
            parts.append(json.dumps(value, ensure_ascii=False))
        elif value is None:
            parts.append("null")
        else:
            raise TypeError(f"cannot serialize {type(value).__name__} as FHIR JSON")

    emit(resource, 1)
    return "".join(parts) + "\n"


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def xml_fingerprint(elem: ET.Element, prefix: str = "") -> list[tuple[str, str]]:
    """Every primitive leaf of an XML element as ``(dotted path, text)``.

    Package-free, so it is the staleness check for a generated file: the same leaves must come
    out of the JSON. The xhtml ``div`` is skipped (it is one string in JSON).
    """
    leaves: list[tuple[str, str]] = []
    grouped: dict[str, list[ET.Element]] = {}
    for child in elem:
        grouped.setdefault(_local(child.tag), []).append(child)
    for tag, elements in grouped.items():
        path = f"{prefix}.{tag}"
        for one in elements:
            if one.tag == f"{{{XHTML_NAMESPACE}}}div":
                continue
            if tag in ("extension", "modifierExtension") and one.get("url"):
                leaves.append((path + ".url", one.get("url")))
            if one.get("id"):
                leaves.append((path + ".id", one.get("id")))
            if "value" in one.attrib:
                leaves.append((path, one.attrib["value"]))
            if tag == "contained":
                # XML wraps the resources; in JSON ``contained`` IS the array, so the resource
                # element itself adds no path segment
                for resource in one:
                    leaves.extend(xml_fingerprint(resource, path))
                continue
            leaves.extend(xml_fingerprint(one, path))
    return leaves


def json_fingerprint(resource: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    """``xml_fingerprint`` read from the JSON side; ``_field`` objects fold into their key."""
    leaves: list[tuple[str, str]] = []
    for key, value in resource.items():
        if key == "resourceType" or key.startswith("_"):
            continue
        path = f"{prefix}.{key}"
        if key == "div":
            continue
        values = value if isinstance(value, list) else [value]
        extras = resource.get("_" + key)
        extras = [None] * len(values) if extras is None else (extras if isinstance(extras, list) else [extras])
        for item, extra in zip(values, extras, strict=True):
            if isinstance(item, dict):
                leaves.extend(json_fingerprint(item, path))
            elif item is not None:
                leaves.append((path, _text(item)))
            if extra is not None:
                leaves.extend(json_fingerprint(extra, path))
    return leaves


def _alike(path: str, text: str) -> tuple[str, str]:
    """Compare decimals by value AND precision, whatever their exponent spelling."""
    try:
        return path, repr(Decimal(text).as_tuple())
    except InvalidOperation:
        return path, text


def describes(xml_text: str, json_text: str) -> list[str]:
    """Differences between an XML resource and a generated JSON file (empty when in step)."""
    resource = json.loads(json_text, parse_float=Decimal)
    expected = sorted({_alike(path, text) for path, text in xml_fingerprint(ET.fromstring(xml_text))})
    found = sorted({_alike(path, text) for path, text in json_fingerprint(resource)})
    problems = []
    for path, text in sorted(set(expected) - set(found)):
        problems.append(f"only in XML: {path} = {text!r}")
    for path, text in sorted(set(found) - set(expected)):
        problems.append(f"only in JSON: {path} = {text!r}")
    if resource.get("resourceType") != _local(ET.fromstring(xml_text).tag):
        problems.append("resourceType differs")
    return problems


REPO_ROOT = Path(__file__).resolve().parents[4]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- the generated files -----------------------------------------------------------------------
TYPED_DIR_NAME = "examples-typed"
MANIFEST_NAME = "manifest.json"
DEFAULT_PACKAGE = Path("~/.fhir/packages/hl7.fhir.r4.core#4.0.1/package").expanduser()
GENERATOR = "fhir4ds/operations/tests/wasm_parity/typed_examples.py"


def typed_path(r4_dir: Path, input_file: str) -> Path | None:
    """The generated JSON for an XML example; None for any other input file."""
    name = Path(input_file)
    if name.suffix.lower() != ".xml":
        return None
    return r4_dir / TYPED_DIR_NAME / (name.stem + ".json")


def generate(r4_dir: Path, package_dir: Path = DEFAULT_PACKAGE, release: str = "4.0.1") -> dict[str, str]:
    """Write ``examples-typed/<name>.json`` for every XML example, plus the manifest.

    Each file is checked against its source (``describes``) before it is written, and the
    manifest records the source's sha256 so a reader can tell a stale conversion.
    """
    examples = r4_dir / "examples"
    if not package_dir.is_dir():
        raise TypingError(
            f"FHIR package directory not found: {package_dir}. Unpack the hl7.fhir.r4.core "
            f"package there (any FHIR tool that caches packages under ~/.fhir/packages) or "
            "pass --package-dir."
        )
    index = StructureIndex(package_dir, release)
    typed_dir = r4_dir / TYPED_DIR_NAME
    typed_dir.mkdir(parents=True, exist_ok=True)
    sources: dict[str, str] = {}
    for xml in sorted(examples.glob("*.xml")):
        raw = xml.read_text(encoding="utf-8")
        text = to_json(convert_resource(raw, index))
        problems = describes(raw, text)
        if problems:
            raise TypingError(f"{xml.name}: the conversion does not describe its source: {problems[:3]}")
        (typed_dir / (xml.stem + ".json")).write_text(text, encoding="utf-8")
        sources[xml.name] = sha256_of(xml)
    manifest = {
        "release": release,
        "package": f"hl7.fhir.r4.core#{release}",
        "generator": GENERATOR,
        "sources": sources,
    }
    (typed_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return sources


def load_typed(r4_dir: Path, input_file: str) -> str | None:
    """The typed JSON text for an XML example, or None when there is none.

    Refuses a conversion whose XML source has changed since it was generated.
    """
    path = typed_path(r4_dir, input_file)
    if path is None or not path.is_file():
        return None
    name = Path(input_file).name
    manifest = json.loads((r4_dir / TYPED_DIR_NAME / MANIFEST_NAME).read_text(encoding="utf-8"))
    if manifest["sources"].get(name) != sha256_of(r4_dir / "examples" / name):
        raise TypingError(
            f"{path.name} was generated from an older {name}; regenerate with "
            "python -m fhir4ds.operations.tests.wasm_parity.typed_examples"
        )
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate typed FHIR JSON for the R4 XML examples.")
    parser.add_argument("--r4-dir", type=Path, default=REPO_ROOT / "fhir4ds" / "fhirpath" / "tests" / "compliance" / "r4")
    parser.add_argument("--package-dir", type=Path, default=DEFAULT_PACKAGE)
    args = parser.parse_args(argv)
    sources = generate(args.r4_dir, args.package_dir)
    print(f"generated {len(sources)} typed examples in {args.r4_dir / TYPED_DIR_NAME}")
    return 0


if __name__ == "__main__":  # pragma: no cover - developer entry point
    raise SystemExit(main())
