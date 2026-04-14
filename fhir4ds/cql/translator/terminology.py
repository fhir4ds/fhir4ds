"""
Terminology translation for CQL to SQL.

This module provides the TerminologyTranslator class that translates
CQL terminology constructs (valuesets, codesystems, codes) to SQL
using FHIRPath UDFs and terminology functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from ..parser.ast_nodes import (
    CodeDefinition,
    CodeSystemDefinition,
    ConceptDefinition,
    ValueSetDefinition,
)
from ..translator.types import (
    SQLBinaryOp,
    SQLExpression,
    SQLFunctionCall,
    SQLIdentifier,
    SQLLiteral,
)
from ..translator.fhirpath_builder import (
    build_coding_exists_expr,
    build_multi_coding_exists_expr,
)

if TYPE_CHECKING:
    from ..translator.context import SQLTranslationContext


@dataclass
class CodeLiteral:
    """
    Represents a code literal for translation.

    Attributes:
        code: The code value.
        system: The code system URL.
        display: Optional display string.
    """

    code: str
    system: str
    display: Optional[str] = None


class TerminologyTranslator:
    """
    Translates CQL terminology constructs to SQL expressions.

    Handles translation of:
    - ValueSet definitions and references
    - CodeSystem definitions and references
    - Code definitions and references
    - Code literals (Code { code: '...', system: '...', display: '...' })
    - Membership checking (in ValueSet, in CodeSystem)
    - Code equivalence (~ operator)

    SQL patterns:
    - ValueSet membership: in_valueset(resource, 'code', 'url')
    - Code equivalence: fhirpath_bool(resource, "code.coding.where(system='...' and code='...').exists()")
    - CodeSystem membership: fhirpath_bool(resource, "code.coding.where(system='...').exists()")
    """

    def __init__(self, context: SQLTranslationContext):
        """
        Initialize the terminology translator.

        Args:
            context: The translation context for symbol resolution.
        """
        self.context = context

    def register_valueset(self, valueset: ValueSetDefinition) -> None:
        """
        Register a valueset definition in the context.

        Args:
            valueset: The ValueSetDefinition AST node.
        """
        self.context.add_valueset(valueset.name, valueset.id)

    def register_codesystem(self, codesystem: CodeSystemDefinition) -> None:
        """
        Register a codesystem definition in the context.

        Args:
            codesystem: The CodeSystemDefinition AST node.
        """
        self.context.add_codesystem(codesystem.name, codesystem.id)

    def register_code(self, code: CodeDefinition) -> None:
        """
        Register a code definition in the context.

        Args:
            code: The CodeDefinition AST node.
        """
        # Resolve codesystem name to URL if available
        system_url = self.context.codesystems.get(code.codesystem, code.codesystem)
        self.context.add_code(code.name, system_url, code.code, code.display)

    def register_concept(self, concept: ConceptDefinition) -> None:
        """
        Register a concept definition in the context.

        Concepts are collections of codes that represent the same meaning.

        Args:
            concept: The ConceptDefinition AST node.
        """
        # Store concept as a special entry with multiple codes
        codes_info = []
        for code_ref in concept.codes:
            if isinstance(code_ref, CodeDefinition):
                system_url = self.context.codesystems.get(
                    code_ref.codesystem, code_ref.codesystem
                )
                codes_info.append({
                    "system": system_url,
                    "code": code_ref.code,
                    "display": code_ref.display,
                })
            elif isinstance(code_ref, str):
                # Reference to a named code
                if code_ref in self.context.codes:
                    codes_info.append(self.context.codes[code_ref])

        self.context.codes[concept.name] = {
            "codes": codes_info,
            "display": concept.display,
            "is_concept": True,
        }

    def translate_valueset_ref(
        self,
        name: str,
        context: SQLTranslationContext,
    ) -> str:
        """
        Translate a valueset reference to its URL.

        Args:
            name: The valueset name.
            context: The translation context.

        Returns:
            The valueset URL.

        Raises:
            KeyError: If the valueset is not defined.
        """
        if name not in context.valuesets:
            raise KeyError(f"ValueSet '{name}' is not defined")
        return context.valuesets[name]

    def translate_codesystem_ref(
        self,
        name: str,
        context: SQLTranslationContext,
    ) -> str:
        """
        Translate a codesystem reference to its URL.

        Args:
            name: The codesystem name.
            context: The translation context.

        Returns:
            The codesystem URL.

        Raises:
            KeyError: If the codesystem is not defined.
        """
        if name not in context.codesystems:
            raise KeyError(f"CodeSystem '{name}' is not defined")
        return context.codesystems[name]

    def translate_code_ref(
        self,
        name: str,
        context: SQLTranslationContext,
    ) -> Tuple[str, str]:
        """
        Translate a code reference to its system and code values.

        Args:
            name: The code name.
            context: The translation context.

        Returns:
            A tuple of (system_url, code_value).

        Raises:
            KeyError: If the code is not defined.
        """
        if name not in context.codes:
            raise KeyError(f"Code '{name}' is not defined")

        code_info = context.codes[name]

        # Handle concept (multiple codes)
        if code_info.get("is_concept"):
            # Return the first code's info for concept
            codes = code_info.get("codes", [])
            if codes:
                return (codes[0].get("system", ""), codes[0].get("code", ""))

        return (
            code_info.get("codesystem", code_info.get("system", "")),
            code_info.get("code", ""),
        )

    def translate_in_valueset(
        self,
        expr: SQLExpression,
        valueset_name: str,
        context: SQLTranslationContext,
        property_path: str = "code",
    ) -> SQLExpression:
        """
        Translate a ValueSet membership check to SQL.

        CQL: X in "Diabetes"
        SQL: in_valueset(resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/...')

        Args:
            expr: The SQL expression for the resource (e.g., alias.resource).
            valueset_name: The name of the valueset.
            context: The translation context.
            property_path: The property path to check (default: 'code').

        Returns:
            The SQL expression for the membership check.
        """
        valueset_url = self.translate_valueset_ref(valueset_name, context)

        return SQLFunctionCall(
            name="in_valueset",
            args=[
                expr,
                SQLLiteral(value=property_path),
                SQLLiteral(value=valueset_url),
            ],
        )

    def translate_in_codesystem(
        self,
        expr: SQLExpression,
        codesystem_name: str,
        context: SQLTranslationContext,
        property_path: str = "code",
    ) -> SQLExpression:
        """
        Translate a CodeSystem membership check to SQL.

        CQL: X in "LOINC"
        SQL: fhirpath_bool(resource, "code.coding.where(system='http://loinc.org').exists()")

        Args:
            expr: The SQL expression for the resource.
            codesystem_name: The name of the codesystem.
            context: The translation context.
            property_path: The property path to check (default: 'code').

        Returns:
            The SQL expression for the membership check.
        """
        codesystem_url = self.translate_codesystem_ref(codesystem_name, context)

        # Build FHIRPath expression for codesystem membership using shared builder
        fhirpath_expr = build_coding_exists_expr(property_path, system_url=codesystem_url)

        return SQLFunctionCall(
            name="fhirpath_bool",
            args=[
                expr,
                SQLLiteral(value=fhirpath_expr),
            ],
        )

    def translate_code_equivalence(
        self,
        expr: SQLExpression,
        code_ref: str,
        context: SQLTranslationContext,
        property_path: str = "code",
    ) -> SQLExpression:
        """
        Translate a code equivalence check to SQL.

        CQL: X ~ "Systolic BP"
        SQL: fhirpath_bool(resource, "code.coding.where(system='http://loinc.org' and code='8480-6').exists()")

        Args:
            expr: The SQL expression for the resource.
            code_ref: The name of the code reference.
            context: The translation context.
            property_path: The property path to check (default: 'code').

        Returns:
            The SQL expression for the equivalence check.
        """
        system_url, code_value = self.translate_code_ref(code_ref, context)

        # Build FHIRPath expression for code equivalence using shared builder
        fhirpath_expr = build_coding_exists_expr(
            property_path, system_url=system_url, code_value=code_value
        )

        return SQLFunctionCall(
            name="fhirpath_bool",
            args=[
                expr,
                SQLLiteral(value=fhirpath_expr),
            ],
        )

    def translate_code_literal(
        self,
        code: CodeLiteral,
    ) -> SQLExpression:
        """
        Translate a code literal to SQL.

        CQL: Code { code: '8480-6', system: 'http://loinc.org', display: 'Systolic BP' }
        SQL: JSON string or struct representation

        Args:
            code: The CodeLiteral to translate.

        Returns:
            The SQL expression representing the code.
        """
        # Build a JSON representation of the code
        code_dict: Dict[str, Any] = {
            "code": code.code,
            "system": code.system,
        }

        if code.display:
            code_dict["display"] = code.display

        # Return as a struct that can be used with code comparisons
        return SQLFunctionCall(
            name="struct_pack",
            args=[
                SQLLiteral(value="code"),
                SQLLiteral(value=code.code),
                SQLLiteral(value="system"),
                SQLLiteral(value=code.system),
                SQLLiteral(value="display"),
                SQLLiteral(value=code.display or ""),
            ],
        )

    def translate_code_literal_equivalence(
        self,
        expr: SQLExpression,
        code_literal: CodeLiteral,
        property_path: str = "code",
    ) -> SQLExpression:
        """
        Translate equivalence check with a code literal.

        CQL: X ~ Code { code: '8480-6', system: 'http://loinc.org' }
        SQL: fhirpath_bool(resource, "code.coding.where(system='...' and code='...').exists()")

        Args:
            expr: The SQL expression for the resource.
            code_literal: The CodeLiteral to compare against.
            property_path: The property path to check (default: 'code').

        Returns:
            The SQL expression for the equivalence check.
        """
        # Build FHIRPath expression for code literal equivalence using shared builder
        fhirpath_expr = build_coding_exists_expr(
            property_path, system_url=code_literal.system, code_value=code_literal.code
        )

        return SQLFunctionCall(
            name="fhirpath_bool",
            args=[
                expr,
                SQLLiteral(value=fhirpath_expr),
            ],
        )

    def translate_expanded_valueset_check(
        self,
        expr: SQLExpression,
        valueset_name: str,
        context: SQLTranslationContext,
        property_path: str = "code",
    ) -> SQLExpression:
        """
        Translate a valueset check using expanded codes.

        This is an alternative to in_valueset() that expands the valueset
        into individual code checks, useful when the valueset is small.

        SQL pattern:
        fhirpath_bool(resource, "code.coding.where(
            (system='sys1' and code='c1') or
            (system='sys2' and code='c2') or
            ...
        ).exists()")

        Args:
            expr: The SQL expression for the resource.
            valueset_name: The name of the valueset.
            context: The translation context.
            property_path: The property path to check.

        Returns:
            The SQL expression for the expanded membership check.
        """
        # Get valueset URL - this would need to be expanded via a terminology service
        # For now, delegate to in_valueset
        return self.translate_in_valueset(expr, valueset_name, context, property_path)

    def translate_concept_equivalence(
        self,
        expr: SQLExpression,
        concept_name: str,
        context: SQLTranslationContext,
        property_path: str = "code",
    ) -> SQLExpression:
        """
        Translate a concept equivalence check.

        Concepts can have multiple codes, so we check if any of them match.

        CQL: X ~ "Blood Pressure"
        SQL: fhirpath_bool(resource, "code.coding.where(
            (system='sys1' and code='c1') or
            (system='sys2' and code='c2')
        ).exists()")

        Args:
            expr: The SQL expression for the resource.
            concept_name: The name of the concept.
            context: The translation context.
            property_path: The property path to check.

        Returns:
            The SQL expression for the concept equivalence check.
        """
        if concept_name not in context.codes:
            raise KeyError(f"Concept '{concept_name}' is not defined")

        concept_info = context.codes[concept_name]

        if not concept_info.get("is_concept"):
            # It's a single code, not a concept
            return self.translate_code_equivalence(expr, concept_name, context, property_path)

        codes = concept_info.get("codes", [])
        if not codes:
            return SQLLiteral(value=False)

        # Build FHIRPath with OR'd code conditions using shared builder
        fhirpath_expr = build_multi_coding_exists_expr(property_path, codes)

        return SQLFunctionCall(
            name="fhirpath_bool",
            args=[
                expr,
                SQLLiteral(value=fhirpath_expr),
            ],
        )

    def get_code_system_and_value(
        self,
        code_ref: str,
        context: SQLTranslationContext,
    ) -> Tuple[str, str]:
        """
        Get the system URL and code value for a code reference.

        This is an alias for translate_code_ref for backward compatibility.

        Args:
            code_ref: The name of the code reference.
            context: The translation context.

        Returns:
            A tuple of (system_url, code_value).
        """
        return self.translate_code_ref(code_ref, context)


__all__ = [
    "TerminologyTranslator",
    "CodeLiteral",
]
