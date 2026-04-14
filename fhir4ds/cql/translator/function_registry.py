"""
Function Translation Registry — data-driven SQL generation strategies.

Maps (function_name_lower, arity) → translation strategy.

Three strategy types:
  - SimpleRename: CQL function name → DuckDB function name, args passed through.
  - ParameterizedTranslation: Custom callable receiving translated SQL args.
  - PreTranslateStrategy: Needs raw CQL AST before arg translation (aggregates).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple, Union, Any


SQLExpression = Any  # avoid circular import; actual type from cql_py.translator.types
SQLTranslationContext = Any


@dataclass
class SimpleRename:
    """CQL function name → DuckDB function name, args passed through."""
    sql_name: str


@dataclass
class ParameterizedTranslation:
    """CQL function → custom callable that receives translated SQL args."""
    translator: Callable[[List[SQLExpression], SQLTranslationContext], SQLExpression]


@dataclass
class PreTranslateStrategy:
    """Function that needs access to raw CQL AST before arg translation.

    Used for aggregates that must inspect whether their argument is a Query
    before deciding how to translate.
    """
    translator: Callable  # (FunctionRef, ExpressionTranslator) → Optional[SQLExpression]


FunctionStrategy = Union[SimpleRename, ParameterizedTranslation, PreTranslateStrategy]


class FunctionTranslationRegistry:
    """
    Maps (function_name_lower, arity) → SQL generation strategy.

    Supports three strategy types for built-in CQL functions:
      - SimpleRename for direct CQL→SQL name mappings
      - ParameterizedTranslation for functions needing arg manipulation
      - PreTranslateStrategy for functions needing raw CQL AST access

    Pre-translate strategies are stored separately so they don't conflict
    with the post-translate strategy for the same function name.
    """

    def __init__(self) -> None:
        self._entries: Dict[Tuple[str, Optional[int]], FunctionStrategy] = {}
        self._pre_entries: Dict[Tuple[str, Optional[int]], PreTranslateStrategy] = {}

    def register_rename(
        self,
        cql_name: str,
        sql_name: str,
        arity: Optional[int] = None,
    ) -> None:
        """Register a simple CQL→SQL function name mapping."""
        self._entries[(cql_name.lower(), arity)] = SimpleRename(sql_name)

    def register(
        self,
        name: str,
        translator: Callable[[List[SQLExpression], SQLTranslationContext], SQLExpression],
        arity: Optional[int] = None,
    ) -> None:
        """Register a parameterized translation (custom callable).

        Args:
            name: CQL function name (matched case-insensitively).
            translator: Callable (args, context) → SQLExpression.
            arity: If provided, only match calls with exactly this arity.
                   If None, match any arity.
        """
        self._entries[(name.lower(), arity)] = ParameterizedTranslation(translator)

    def register_pre_translate(
        self,
        name: str,
        translator: Callable,
        arity: Optional[int] = None,
    ) -> None:
        """Register a strategy that operates on CQL AST before arg translation.

        This does NOT overwrite any existing SimpleRename or ParameterizedTranslation
        for the same function — both can coexist.
        """
        self._pre_entries[(name.lower(), arity)] = PreTranslateStrategy(translator)

    def get_pre_translate(self, name: str, arity: int) -> Optional[PreTranslateStrategy]:
        """Look up pre-translate strategy for (name, arity)."""
        exact = self._pre_entries.get((name.lower(), arity))
        if exact is not None:
            return exact
        return self._pre_entries.get((name.lower(), None))

    def get(self, name: str, arity: int) -> Optional[FunctionStrategy]:
        """Look up post-translate strategy for (name, arity).

        Tries exact arity first, then wildcard (arity=None).
        Returns None if no entry found.
        """
        exact = self._entries.get((name.lower(), arity))
        if exact is not None:
            return exact
        return self._entries.get((name.lower(), None))
