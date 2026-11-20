"""Comment annotation tags (CQL 1.5 trial-use; CQL 2.0 FHIR-37827).

CQL supports declaring tags within multi-line comments immediately
preceding a declaration. Tags use the ``@`` symbol followed by a valid,
unquoted identifier, optionally followed by a colon (``:``) and a string
value. The tag value is whatever comes after the tag definition until the
next tag or the end of the comment block, whichever comes first.

CQL 2.0 (FHIR-37827) allows tags WITHOUT a value::

    /*
    @inclusion
    @author: Frederic Chopin
    @description: Defines whether the patient is included
    */

This module is a pure text-level scanner: the CQL lexer skips comments
entirely, so tags are extracted from the raw source. Translation behavior
is unchanged (tags are authoring/environment metadata); downstream
consumers (e.g. CQL 2.0 parameter constraints, FHIR-48682) read them via
:func:`parse_library_tags`.

Ground truth: CQL 2.0 Developer's Guide, "Tags" section,
https://cql.hl7.org/03-developersguide.html.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

__all__ = [
    "AnnotationTag",
    "ParameterConstraint",
    "parse_annotation_tags",
    "parse_library_tags",
    "extract_parameter_constraints",
]


@dataclass(frozen=True)
class AnnotationTag:
    """A single ``@name`` or ``@name: value`` comment tag.

    Attributes:
        name: The tag identifier (unquoted, without the leading ``@``).
        value: The tag value, or None for value-less tags (FHIR-37827).
            Values are stripped of surrounding whitespace but preserve
            interior newlines (a tag value runs to the next tag or the
            end of the comment block).
    """

    name: str
    value: Optional[str] = None


# A tag line: '@' + valid simple identifier, optionally ':' + value text.
_TAG_LINE_RE = re.compile(r"^[ \t]*@([A-Za-z_][A-Za-z0-9_]*)(?::(.*))?$")
# NOTE: all three identifier alternatives MUST be capture groups —
# parse_library_tags reads group(3) for simple (unquoted) define names.
_DEFINE_RE = re.compile(
    r"^\s*define\s+(?:\"([^\"]+)\"|`([^`]+)`|([A-Za-z_][A-Za-z0-9_]*))"
)


@dataclass(frozen=True)
class ParameterConstraint:
    """A CQL 2.0 ``@constraint`` tag set on a top-level expression define.

    FHIR-48682 (trial-use). The tagged define's expression is required to
    evaluate to ``true`` (or ``null`` — null is "satisfied" per the SQL /
    XQuery convention the spec invokes) whenever any expression of the
    library is evaluated. ``false`` violates the constraint.

    Attributes:
        definition_name: The tagged ``define`` name.
        severity: ``"error"`` or ``"warning"`` (the ``@constraint`` tag
            value; spec requires one of exactly these two).
        message: The ``@message`` tag value (empty string when absent).
        scope: The ``@constraintScope`` tag value; only ``"parameter"`` is
            defined by the spec. None when the tag is absent.
    """

    definition_name: str
    severity: str
    message: str = ""
    scope: Optional[str] = None


def extract_parameter_constraints(
    tags_by_define: Dict[str, List[AnnotationTag]],
) -> List[ParameterConstraint]:
    """Collect ``@constraint`` tag sets from per-define annotation tags.

    Args:
        tags_by_define: Output of :func:`parse_library_tags`.

    Returns:
        Parameter constraints in definition order.

    Raises:
        ValueError: On spec-invalid tag usage — a ``@constraint`` value
            outside ``error``/``warning``, a ``@constraintScope`` other
            than ``parameter``, or a ``@message``/``@constraintScope``
            tag on a define with no ``@constraint`` tag.
    """
    constraints: List[ParameterConstraint] = []
    for define_name, tags in tags_by_define.items():
        by_name: Dict[str, AnnotationTag] = {}
        for tag in tags:
            if tag.name in ("constraint", "message", "constraintScope"):
                if tag.name in by_name:
                    raise ValueError(
                        f"Duplicate '@{tag.name}' tag on define '{define_name}'"
                    )
                by_name[tag.name] = tag

        if "constraintScope" in by_name and "constraint" not in by_name:
            raise ValueError(
                f"@constraintScope tag on define '{define_name}' requires a "
                f"@constraint tag [CQL 2.0, FHIR-48682]"
            )
        if "message" in by_name and "constraint" not in by_name:
            raise ValueError(
                f"@message tag on define '{define_name}' requires a "
                f"@constraint tag [CQL 2.0, FHIR-48682]"
            )
        if "constraint" not in by_name:
            continue

        constraint_tag = by_name["constraint"]
        if constraint_tag.value is None:
            raise ValueError(
                f"@constraint tag on define '{define_name}' must have a value "
                f"of 'error' or 'warning' [CQL 2.0, FHIR-48682]"
            )
        severity = constraint_tag.value.strip()
        if severity not in ("error", "warning"):
            raise ValueError(
                f"@constraint tag on define '{define_name}' must have a value "
                f"of 'error' or 'warning', got {severity!r} "
                f"[CQL 2.0, FHIR-48682]"
            )

        scope: Optional[str] = None
        if "constraintScope" in by_name:
            scope_tag = by_name["constraintScope"]
            scope = (scope_tag.value or "").strip()
            if scope != "parameter":
                raise ValueError(
                    f"@constraintScope tag on define '{define_name}' must be "
                    f"'parameter', got {scope!r} [CQL 2.0, FHIR-48682]"
                )

        message_tag = by_name.get("message")
        message = (message_tag.value or "").strip() if message_tag is not None else ""

        constraints.append(
            ParameterConstraint(
                definition_name=define_name,
                severity=severity,
                message=message,
                scope=scope,
            )
        )
    return constraints


def parse_annotation_tags(comment_text: str) -> List[AnnotationTag]:
    """Extract tags from a single comment block's text.

    Args:
        comment_text: The interior text of one comment block (with or
            without the surrounding ``/* */`` markers; leading ``//`` line
            markers are also tolerated).

    Returns:
        Tags in declaration order. Non-tag lines before the first tag are
        ignored; non-tag lines after a tag are part of that tag's value.
    """
    inner = comment_text.strip()
    if inner.startswith("/*"):
        inner = inner[2:]
    if inner.endswith("*/"):
        inner = inner[:-2]
    lines = inner.split("\n")

    tags: List[AnnotationTag] = []
    current_name: Optional[str] = None
    had_colon = False
    value_lines: List[str] = []

    def _flush() -> None:
        nonlocal current_name, had_colon, value_lines
        if current_name is not None:
            if had_colon:
                # A colon was authored: the value is everything after the
                # tag definition until the next tag / end of the block.
                value = "\n".join(value_lines).strip()
                tags.append(AnnotationTag(name=current_name, value=value))
            else:
                # FHIR-37827: value-less tag.
                tags.append(AnnotationTag(name=current_name, value=None))
        current_name = None
        had_colon = False
        value_lines = []

    for line in lines:
        match = _TAG_LINE_RE.match(line.rstrip())
        if match:
            _flush()
            current_name = match.group(1)
            inline_value = match.group(2)
            if inline_value is not None:
                had_colon = True
                value_lines = [inline_value]
        elif current_name is not None:
            value_lines.append(line)

    _flush()
    return tags


def parse_library_tags(cql_source: str) -> Dict[str, List[AnnotationTag]]:
    """Map definition names to the tags on their immediately-preceding
    comment block.

    A comment block attaches to the declaration that directly follows it
    (no blank line between the comment block and the ``define``; other
    declarations such as ``using``/``include`` between the comment and the
    define break the association, matching the spec's "immediately
    preceding" rule).

    Returns:
        Dict mapping each tagged definition name to its tags. Definitions
        without a preceding tag block are omitted.
    """
    result: Dict[str, List[AnnotationTag]] = {}

    lines = cql_source.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.lstrip().startswith("/*"):
            # Collect the whole block.
            block: List[str] = []
            end = i
            joined = line
            while end < n and "*/" not in joined:
                end += 1
                if end < n:
                    joined += "\n" + lines[end]
            block_text = joined
            # Find the first non-empty line after the block.
            j = end + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n:
                define_match = _DEFINE_RE.match(lines[j])
                if define_match:
                    name = (
                        define_match.group(1)
                        or define_match.group(2)
                        or define_match.group(3)
                    )
                    tags = parse_annotation_tags(block_text)
                    if tags:
                        result[name] = tags
            i = end + 1
        else:
            i += 1
    return result
