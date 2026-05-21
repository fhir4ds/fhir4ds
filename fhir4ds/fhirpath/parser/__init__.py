import sys
import re
from antlr4 import *
from antlr4.tree.Tree import ParseTreeWalker
from antlr4.error.ErrorListener import ErrorListener
from antlr4.error.Errors import LexerNoViableAltException
from ..parser.generated.FHIRPathLexer import FHIRPathLexer
from ..parser.generated.FHIRPathParser import FHIRPathParser
from ..parser.ASTPathListener import ASTPathListener
from ..engine.errors import FHIRPathSyntaxError


def recover(e):
    raise e


_UNFINISHED_COMMENT = re.compile(r'/\*(?!\*/)(?:(?!\*/).)*$', re.DOTALL)


def _check_syntax_strict(expression: str) -> None:
    """Pre-scan for syntax issues that ANTLR silently ignores."""
    # Detect unfinished block comments: /* without matching */
    if '/*' in expression:
        idx = expression.find('/*')
        close = expression.find('*/', idx + 2)
        if close == -1:
            raise FHIRPathSyntaxError(
                "Unfinished block comment",
                expression=expression,
                position=idx,
            )


class _FHIRPathErrorListener(ErrorListener):
    def __init__(self, expression: str) -> None:
        super().__init__()
        self.expression = expression

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        token = getattr(offendingSymbol, "text", None)
        raise FHIRPathSyntaxError(
            msg or "Invalid FHIRPath syntax",
            expression=self.expression,
            position=column,
            token=token,
        )


def parse(value, strict_mode=False):
    if not isinstance(value, str):
        raise FHIRPathSyntaxError(
            f"FHIRPath expression must be a string, got {type(value).__name__}"
        )
    if not value.strip():
        raise FHIRPathSyntaxError(
            "FHIRPath expression must be a non-empty string",
            expression=value,
            position=0,
        )
    if strict_mode:
        _check_syntax_strict(value)

    textStream = InputStream(value)

    astPathListener = ASTPathListener()
    errorListener = _FHIRPathErrorListener(value)

    lexer = FHIRPathLexer(textStream)
    lexer.recover = recover
    lexer.removeErrorListeners()
    lexer.addErrorListener(errorListener)

    parser = FHIRPathParser(CommonTokenStream(lexer))
    parser.buildParseTrees = True
    parser.removeErrorListeners()
    parser.addErrorListener(errorListener)

    walker = ParseTreeWalker()
    try:
        tree = parser.expression()
        current = parser.getCurrentToken()
        if current.type != Token.EOF:
            raise FHIRPathSyntaxError(
                "Unexpected trailing token",
                expression=value,
                position=current.column,
                token=current.text,
            )
        walker.walk(astPathListener, tree)
        return astPathListener.parentStack[0]
    except FHIRPathSyntaxError:
        raise
    except (LexerNoViableAltException, IndexError, KeyError) as exc:
        raise FHIRPathSyntaxError(
            "Invalid FHIRPath syntax",
            expression=value,
        ) from exc
