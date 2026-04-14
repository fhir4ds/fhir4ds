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


def parse(value, strict_mode=False):
    if strict_mode:
        _check_syntax_strict(value)

    textStream = InputStream(value)

    astPathListener = ASTPathListener()
    errorListener = ErrorListener()

    lexer = FHIRPathLexer(textStream)
    lexer.recover = recover
    lexer.removeErrorListeners()
    lexer.addErrorListener(errorListener)

    parser = FHIRPathParser(CommonTokenStream(lexer))
    parser.buildParseTrees = True
    parser.removeErrorListeners()
    parser.addErrorListener(errorListener)

    walker = ParseTreeWalker()
    walker.walk(astPathListener, parser.expression())

    return astPathListener.parentStack[0]
