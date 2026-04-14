#pragma once

#include "ast.hpp"
#include "lexer.hpp"
#include <string>
#include <vector>

namespace fhirpath {

class Parser {
public:
	ASTNodePtr parse(const std::string &expression);

private:
	std::vector<Token> tokens_;
	size_t pos_;

	// Recursive descent parser methods following FHIRPath R4 grammar
	ASTNodePtr parseExpression();
	ASTNodePtr parseImpliesExpression();
	ASTNodePtr parseOrExpression();
	ASTNodePtr parseAndExpression();
	ASTNodePtr parseMembershipExpression();
	ASTNodePtr parseInequalityExpression();
	ASTNodePtr parseEqualityExpression();
	ASTNodePtr parseUnionExpression();
	ASTNodePtr parseTypeExpression();
	ASTNodePtr parseAdditiveExpression();
	ASTNodePtr parseMultiplicativeExpression();
	ASTNodePtr parseUnaryExpression();
	ASTNodePtr parseInvocationExpression();
	ASTNodePtr parsePrimaryExpression();
	ASTNodePtr parseLiteral();
	ASTNodePtr parseFunctionCall(ASTNodePtr source);
	ASTNodePtr parseIndexer(ASTNodePtr source);

	// Token management
	const Token &current() const;
	const Token &peek() const;
	bool check(TokenType type) const;
	bool match(TokenType type);
	Token consume(TokenType type, const std::string &message);
	bool isAtEnd() const;
	void advance();
};

} // namespace fhirpath
