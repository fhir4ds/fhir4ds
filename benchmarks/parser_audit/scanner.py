"""
CQL corpus scanner: parse every .cql file and collect structured error results.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Match the recursion limit used by the main runner
sys.setrecursionlimit(8000)


@dataclass
class ParseResult:
    """Result of attempting to parse a single CQL file."""
    file: Path
    success: bool
    duration_ms: float

    # Populated on failure
    error_type: Optional[str] = None   # e.g. "ParseError", "LexerError", "RecursionError"
    message: Optional[str] = None
    position: Optional[tuple] = None   # (line, col) or None
    expected: Optional[str] = None     # ParseError.expected
    found: Optional[str] = None        # ParseError.found
    feature_name: Optional[str] = None # UnsupportedFeatureError.feature_name

    @property
    def is_library(self) -> bool:
        """True if this file is a shared library (no CMS/NHSN prefix)."""
        name = self.file.stem
        return not (name.startswith("CMS") or name.startswith("NHSN"))


def scan_corpus(cql_dir: Path, verbose: bool = False) -> List[ParseResult]:
    """
    Parse every .cql file in cql_dir and return one ParseResult per file.

    Files are processed in alphabetical order so output is deterministic.
    """
    from fhir4ds.cql.parser.parser import parse_cql
    from fhir4ds.cql.errors import ParseError, LexerError, UnsupportedFeatureError

    cql_files = sorted(cql_dir.glob("*.cql"))
    results: List[ParseResult] = []

    for cql_file in cql_files:
        if verbose:
            print(f"  Parsing {cql_file.name}...", end=" ", flush=True)

        source = cql_file.read_text(encoding="utf-8")
        t0 = time.perf_counter()

        try:
            parse_cql(source)
            duration_ms = (time.perf_counter() - t0) * 1000
            results.append(ParseResult(file=cql_file, success=True, duration_ms=duration_ms))
            if verbose:
                print(f"OK ({duration_ms:.0f}ms)")

        except ParseError as e:
            duration_ms = (time.perf_counter() - t0) * 1000
            results.append(ParseResult(
                file=cql_file,
                success=False,
                duration_ms=duration_ms,
                error_type="ParseError",
                message=e.message,
                position=e.position,
                expected=e.expected,
                found=e.found,
            ))
            if verbose:
                loc = f" (line {e.position[0]})" if e.position else ""
                print(f"FAIL{loc}: {e.message[:80]}")

        except LexerError as e:
            duration_ms = (time.perf_counter() - t0) * 1000
            results.append(ParseResult(
                file=cql_file,
                success=False,
                duration_ms=duration_ms,
                error_type="LexerError",
                message=e.message,
                position=e.position,
            ))
            if verbose:
                print(f"LEXER FAIL: {e.message[:80]}")

        except UnsupportedFeatureError as e:
            duration_ms = (time.perf_counter() - t0) * 1000
            results.append(ParseResult(
                file=cql_file,
                success=False,
                duration_ms=duration_ms,
                error_type="UnsupportedFeatureError",
                message=e.message,
                feature_name=e.feature_name,
                position=e.position,
            ))
            if verbose:
                print(f"UNSUPPORTED: {e.feature_name or e.message[:80]}")

        except RecursionError:
            duration_ms = (time.perf_counter() - t0) * 1000
            results.append(ParseResult(
                file=cql_file,
                success=False,
                duration_ms=duration_ms,
                error_type="RecursionError",
                message="Maximum recursion depth exceeded during parsing",
            ))
            if verbose:
                print("RECURSION FAIL")

        except Exception as e:
            duration_ms = (time.perf_counter() - t0) * 1000
            results.append(ParseResult(
                file=cql_file,
                success=False,
                duration_ms=duration_ms,
                error_type=type(e).__name__,
                message=str(e),
            ))
            if verbose:
                print(f"ERROR ({type(e).__name__}): {str(e)[:80]}")

    return results
