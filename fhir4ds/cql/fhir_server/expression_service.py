"""Evaluate expression-only CQL requests for the FHIR ``$cql`` facade."""

from __future__ import annotations

from typing import Any

from fhir4ds.cql import parse_cql, register_udfs
from fhir4ds.cql.errors import ParseError, TranslationError
from fhir4ds.cql.translator import CQLToSQLTranslator

from .parameters import cql_identifier
from .types import (
    CQLEvaluationResult,
    CQLFacadeError,
    CQLErrorCategory,
    CQLRequest,
    CQLResultMetadata,
    CQLServerConfig,
)


def evaluate_cql_request(request: CQLRequest, config: CQLServerConfig | None = None) -> CQLEvaluationResult:
    """Evaluate a parsed runner request through FHIR4DS CQL."""
    config = config or CQLServerConfig()
    source = _synthetic_library(request, config)
    try:
        import duckdb
    except ImportError as exc:
        raise CQLFacadeError(
            "duckdb is required to evaluate FHIR $cql expressions",
            category=CQLErrorCategory.EVALUATION_ERROR,
            status_code=200,
        ) from exc

    try:
        library = parse_cql(source)
    except ParseError as exc:
        raise CQLFacadeError(
            "CQL parse error",
            category=CQLErrorCategory.PARSE_ERROR,
            status_code=200,
            diagnostics=_diagnostics(str(exc), config.debug, request.expression),
        ) from exc

    conn = None
    try:
        conn = duckdb.connect()
        register_udfs(conn, use_cpp_extensions=config.use_cpp_extensions)
        translator = CQLToSQLTranslator(connection=conn)
        sql = translator.translate_library_to_sql(library, final_definition="return")
        rows = conn.execute(sql).fetchall()
        if not rows:
            value: Any = None
        else:
            value = rows[0][0]
        meta = translator.get_definition_meta("return")
        metadata = CQLResultMetadata.from_definition_meta("return", meta)
        return CQLEvaluationResult(value=value, metadata=metadata, sql=sql)
    except CQLFacadeError:
        raise
    except TranslationError as exc:
        raise CQLFacadeError(
            "CQL translation error",
            category=CQLErrorCategory.TRANSLATION_ERROR,
            status_code=200,
            diagnostics=_diagnostics(str(exc), config.debug, request.expression),
        ) from exc
    except Exception as exc:
        raise CQLFacadeError(
            "CQL evaluation error",
            category=CQLErrorCategory.EVALUATION_ERROR,
            status_code=200,
            diagnostics=_diagnostics(str(exc), config.debug, request.expression),
        ) from exc
    finally:
        if conn is not None:
            conn.close()


def _synthetic_library(request: CQLRequest, config: CQLServerConfig) -> str:
    lines = [
        f"library {config.library_name} version '1.0.0'",
        f"using FHIR version '{config.fhir_version}'",
    ]
    for parameter in request.parameters:
        lines.append(
            "parameter "
            f"{cql_identifier(parameter.name)} {parameter.cql_type} default {parameter.literal}"
        )
    lines.extend(['define "return":', f"  {request.expression}"])
    return "\n".join(lines)


def _diagnostics(message: str, debug: bool, expression: str) -> str:
    if debug:
        return f"{message}\nExpression: {expression}"
    return message
