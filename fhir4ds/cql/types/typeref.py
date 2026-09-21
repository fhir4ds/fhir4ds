"""Canonical structural representation of CQL type names.

This module is the single authoritative home of :class:`CQLTypeRef`, the
structural type reference used by the CQL type map (``translator/type_map``),
the translator's :class:`~fhir4ds.cql.translator.context.DefinitionMeta`
(``cql_type_ref`` field) and the ``$cql`` facade serializer.

Dependency direction: the translator imports from this package; the facade
re-imports from here for backwards compatibility. Nothing in this module may
import from ``fhir4ds.cql.translator`` or ``fhir4ds.cql.fhir_server``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CQLTypeRef:
    """Small structural representation of a CQL type name."""

    name: str
    args: tuple["CQLTypeRef", ...] = ()
    fields: tuple[tuple[str, "CQLTypeRef"], ...] = ()
    raw: str | None = None

    @property
    def bare_name(self) -> str:
        name = self.name.split(".")[-1]
        if name.startswith("System."):
            name = name.split(".")[-1]
        return name

    @property
    def element_type(self) -> "CQLTypeRef":
        if self.bare_name == "List" and self.args:
            return self.args[0]
        return ANY_TYPE

    @property
    def point_type(self) -> "CQLTypeRef":
        if self.bare_name == "Interval" and self.args:
            return self.args[0]
        return ANY_TYPE

    def canonical(self) -> str:
        if self.bare_name == "Tuple":
            inner = ", ".join(f"{name}: {field.canonical()}" for name, field in self.fields)
            return f"Tuple{{{inner}}}"
        if self.args:
            return f"{self.bare_name}<{', '.join(arg.canonical() for arg in self.args)}>"
        return self.bare_name

    @classmethod
    def parse(cls, value: str | None) -> "CQLTypeRef":
        text = (value or "Any").strip()
        if not text:
            return ANY_TYPE
        parser = _TypeParser(text)
        parsed = parser.parse()
        return parsed


ANY_TYPE = CQLTypeRef("Any", raw="Any")


class _TypeParser:
    """Tiny parser for CQL type names such as ``List<Tuple{a: Integer}>``."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def parse(self) -> CQLTypeRef:
        result = self._parse_type()
        self._skip_ws()
        if self.pos != len(self.text):
            return CQLTypeRef(self.text, raw=self.text)
        return result

    def _parse_type(self) -> CQLTypeRef:
        self._skip_ws()
        name = self._parse_name()
        bare = name.split(".")[-1]
        self._skip_ws()
        if bare == "Tuple" and self._peek() == "{":
            self.pos += 1
            fields: list[tuple[str, CQLTypeRef]] = []
            while True:
                self._skip_ws()
                if self._peek() == "}":
                    self.pos += 1
                    break
                field_name = self._parse_name()
                self._skip_ws()
                if self._peek() == ":":
                    self.pos += 1
                self._skip_ws()
                fields.append((field_name, self._parse_type()))
                self._skip_ws()
                if self._peek() == ",":
                    self.pos += 1
                    continue
                if self._peek() == "}":
                    self.pos += 1
                    break
                break
            return CQLTypeRef("Tuple", fields=tuple(fields), raw=self.text)
        if self._peek() == "<":
            self.pos += 1
            args: list[CQLTypeRef] = []
            while True:
                args.append(self._parse_type())
                self._skip_ws()
                if self._peek() == ",":
                    self.pos += 1
                    continue
                if self._peek() == ">":
                    self.pos += 1
                    break
                break
            return CQLTypeRef(bare, args=tuple(args), raw=self.text)
        return CQLTypeRef(bare, raw=self.text)

    def _parse_name(self) -> str:
        self._skip_ws()
        start = self.pos
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char.isalnum() or char in "._":
                self.pos += 1
                continue
            break
        return self.text[start:self.pos] or "Any"

    def _skip_ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def _peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""
