# Generated from FHIRPath.g4 by ANTLR 4.13.1
from antlr4 import *
if "." in __name__:
    from .FHIRPathParser import FHIRPathParser
else:
    from FHIRPathParser import FHIRPathParser

# This class defines a complete generic visitor for a parse tree produced by FHIRPathParser.

class FHIRPathVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by FHIRPathParser#entireExpression.
    def visitEntireExpression(self, ctx:FHIRPathParser.EntireExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#indexerExpression.
    def visitIndexerExpression(self, ctx:FHIRPathParser.IndexerExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#polarityExpression.
    def visitPolarityExpression(self, ctx:FHIRPathParser.PolarityExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#additiveExpression.
    def visitAdditiveExpression(self, ctx:FHIRPathParser.AdditiveExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#multiplicativeExpression.
    def visitMultiplicativeExpression(self, ctx:FHIRPathParser.MultiplicativeExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#unionExpression.
    def visitUnionExpression(self, ctx:FHIRPathParser.UnionExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#orExpression.
    def visitOrExpression(self, ctx:FHIRPathParser.OrExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#andExpression.
    def visitAndExpression(self, ctx:FHIRPathParser.AndExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#membershipExpression.
    def visitMembershipExpression(self, ctx:FHIRPathParser.MembershipExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#inequalityExpression.
    def visitInequalityExpression(self, ctx:FHIRPathParser.InequalityExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#invocationExpression.
    def visitInvocationExpression(self, ctx:FHIRPathParser.InvocationExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#equalityExpression.
    def visitEqualityExpression(self, ctx:FHIRPathParser.EqualityExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#impliesExpression.
    def visitImpliesExpression(self, ctx:FHIRPathParser.ImpliesExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#termExpression.
    def visitTermExpression(self, ctx:FHIRPathParser.TermExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#typeExpression.
    def visitTypeExpression(self, ctx:FHIRPathParser.TypeExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#invocationTerm.
    def visitInvocationTerm(self, ctx:FHIRPathParser.InvocationTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#literalTerm.
    def visitLiteralTerm(self, ctx:FHIRPathParser.LiteralTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#externalConstantTerm.
    def visitExternalConstantTerm(self, ctx:FHIRPathParser.ExternalConstantTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#parenthesizedTerm.
    def visitParenthesizedTerm(self, ctx:FHIRPathParser.ParenthesizedTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#nullLiteral.
    def visitNullLiteral(self, ctx:FHIRPathParser.NullLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#booleanLiteral.
    def visitBooleanLiteral(self, ctx:FHIRPathParser.BooleanLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#stringLiteral.
    def visitStringLiteral(self, ctx:FHIRPathParser.StringLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#numberLiteral.
    def visitNumberLiteral(self, ctx:FHIRPathParser.NumberLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#dateTimeLiteral.
    def visitDateTimeLiteral(self, ctx:FHIRPathParser.DateTimeLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#timeLiteral.
    def visitTimeLiteral(self, ctx:FHIRPathParser.TimeLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#quantityLiteral.
    def visitQuantityLiteral(self, ctx:FHIRPathParser.QuantityLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#externalConstant.
    def visitExternalConstant(self, ctx:FHIRPathParser.ExternalConstantContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#memberInvocation.
    def visitMemberInvocation(self, ctx:FHIRPathParser.MemberInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#functionInvocation.
    def visitFunctionInvocation(self, ctx:FHIRPathParser.FunctionInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#thisInvocation.
    def visitThisInvocation(self, ctx:FHIRPathParser.ThisInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#indexInvocation.
    def visitIndexInvocation(self, ctx:FHIRPathParser.IndexInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#totalInvocation.
    def visitTotalInvocation(self, ctx:FHIRPathParser.TotalInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#functn.
    def visitFunctn(self, ctx:FHIRPathParser.FunctnContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#paramList.
    def visitParamList(self, ctx:FHIRPathParser.ParamListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#quantity.
    def visitQuantity(self, ctx:FHIRPathParser.QuantityContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#unit.
    def visitUnit(self, ctx:FHIRPathParser.UnitContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#dateTimePrecision.
    def visitDateTimePrecision(self, ctx:FHIRPathParser.DateTimePrecisionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#pluralDateTimePrecision.
    def visitPluralDateTimePrecision(self, ctx:FHIRPathParser.PluralDateTimePrecisionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#typeSpecifier.
    def visitTypeSpecifier(self, ctx:FHIRPathParser.TypeSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#qualifiedIdentifier.
    def visitQualifiedIdentifier(self, ctx:FHIRPathParser.QualifiedIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by FHIRPathParser#identifier.
    def visitIdentifier(self, ctx:FHIRPathParser.IdentifierContext):
        return self.visitChildren(ctx)



del FHIRPathParser