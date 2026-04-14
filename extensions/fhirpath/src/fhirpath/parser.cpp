#include "fhirpath/parser.hpp"
#include <stdexcept>

namespace fhirpath {

static bool isTimeUnitKeyword(TokenType t) {
	return t == TokenType::Day || t == TokenType::Days ||
	       t == TokenType::Week || t == TokenType::Weeks ||
	       t == TokenType::Month || t == TokenType::Months ||
	       t == TokenType::Year || t == TokenType::Years ||
	       t == TokenType::Hour || t == TokenType::Hours ||
	       t == TokenType::Minute || t == TokenType::Minutes ||
	       t == TokenType::Second || t == TokenType::Seconds ||
	       t == TokenType::Millisecond || t == TokenType::Milliseconds;
}

ASTNodePtr Parser::parse(const std::string &expression) {
	Lexer lexer(expression);
	tokens_ = lexer.tokenize();
	pos_ = 0;

	if (lexer.hasError()) {
		throw std::runtime_error("Lexer error: unterminated comment");
	}

	if (tokens_.empty() || (tokens_.size() == 1 && tokens_[0].type == TokenType::Eof)) {
		return nullptr;
	}

	auto result = parseExpression();
	if (!isAtEnd() && current().type != TokenType::Eof) {
		throw std::runtime_error("Unexpected token '" + current().text + "' at position " +
		                         std::to_string(current().position));
	}
	return result;
}

const Token &Parser::current() const {
	return tokens_[pos_];
}

const Token &Parser::peek() const {
	if (pos_ + 1 < tokens_.size()) {
		return tokens_[pos_ + 1];
	}
	return tokens_.back();
}

bool Parser::check(TokenType type) const {
	return !isAtEnd() && current().type == type;
}

bool Parser::match(TokenType type) {
	if (check(type)) {
		advance();
		return true;
	}
	return false;
}

Token Parser::consume(TokenType type, const std::string &message) {
	if (check(type)) {
		Token tok = current();
		advance();
		return tok;
	}
	throw std::runtime_error(message + " at position " +
	                         std::to_string(isAtEnd() ? tokens_.back().position : current().position));
}

bool Parser::isAtEnd() const {
	return pos_ >= tokens_.size() || tokens_[pos_].type == TokenType::Eof;
}

void Parser::advance() {
	if (!isAtEnd()) {
		pos_++;
	}
}

// expression: impliesExpression
ASTNodePtr Parser::parseExpression() {
	return parseImpliesExpression();
}

// impliesExpression: orExpression ('implies' orExpression)*
ASTNodePtr Parser::parseImpliesExpression() {
	auto left = parseOrExpression();
	while (check(TokenType::Implies)) {
		advance();
		auto right = parseOrExpression();
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::BinaryOp;
		node->op = "implies";
		node->children = {left, right};
		left = node;
	}
	return left;
}

// orExpression: andExpression (('or' | 'xor') andExpression)*
ASTNodePtr Parser::parseOrExpression() {
	auto left = parseAndExpression();
	while (check(TokenType::Or) || check(TokenType::Xor)) {
		std::string op = current().text;
		advance();
		auto right = parseAndExpression();
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::BinaryOp;
		node->op = op;
		node->children = {left, right};
		left = node;
	}
	return left;
}

// andExpression: membershipExpression ('and' membershipExpression)*
ASTNodePtr Parser::parseAndExpression() {
	auto left = parseTypeExpression();
	while (check(TokenType::And)) {
		advance();
		auto right = parseTypeExpression();
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::BinaryOp;
		node->op = "and";
		node->children = {left, right};
		left = node;
	}
	return left;
}

// membershipExpression: inequalityExpression (('in' | 'contains') inequalityExpression)*
ASTNodePtr Parser::parseMembershipExpression() {
	auto left = parseInequalityExpression();
	while (check(TokenType::In) || check(TokenType::Contains)) {
		std::string op = current().text;
		advance();
		auto right = parseInequalityExpression();
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::BinaryOp;
		node->op = op;
		node->children = {left, right};
		left = node;
	}
	return left;
}

// inequalityExpression: equalityExpression (('<' | '>' | '<=' | '>=') equalityExpression)*
ASTNodePtr Parser::parseInequalityExpression() {
	auto left = parseEqualityExpression();
	while (check(TokenType::Less) || check(TokenType::Greater) || check(TokenType::LessEqual) ||
	       check(TokenType::GreaterEqual)) {
		std::string op = current().text;
		advance();
		auto right = parseEqualityExpression();
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::BinaryOp;
		node->op = op;
		node->children = {left, right};
		left = node;
	}
	return left;
}

// equalityExpression: typeExpression (('=' | '!=' | '~' | '!~') typeExpression)*
ASTNodePtr Parser::parseEqualityExpression() {
	auto left = parseUnionExpression();
	while (check(TokenType::Equals) || check(TokenType::NotEquals)) {
		std::string op = current().text;
		advance();
		auto right = parseUnionExpression();
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::BinaryOp;
		node->op = op;
		node->children = {left, right};
		left = node;
	}
	return left;
}

// typeExpression: unionExpression ('is' | 'as') typeSpecifier
ASTNodePtr Parser::parseTypeExpression() {
	auto left = parseMembershipExpression();
	if (check(TokenType::Is) || check(TokenType::As)) {
		std::string op = current().text;
		advance();
		std::string type_name;
		if (check(TokenType::Identifier)) {
			type_name = current().text;
			advance();
			// Handle qualified type names like FHIR.Patient
			while (check(TokenType::Dot) && pos_ + 1 < tokens_.size() &&
			       tokens_[pos_ + 1].type == TokenType::Identifier) {
				advance(); // skip dot
				type_name += "." + current().text;
				advance();
			}
		}
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::TypeExpression;
		node->op = op;
		node->name = type_name;
		node->children = {left};
		return node;
	}
	return left;
}

// unionExpression: additiveExpression ('|' additiveExpression)*
ASTNodePtr Parser::parseUnionExpression() {
	auto left = parseAdditiveExpression();
	while (check(TokenType::Pipe)) {
		advance();
		auto right = parseAdditiveExpression();
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::UnionOp;
		node->op = "|";
		node->children = {left, right};
		left = node;
	}
	return left;
}

// additiveExpression: multiplicativeExpression (('+' | '-' | '&') multiplicativeExpression)*
ASTNodePtr Parser::parseAdditiveExpression() {
	auto left = parseMultiplicativeExpression();
	while (check(TokenType::Plus) || check(TokenType::Minus) || check(TokenType::Ampersand)) {
		std::string op = current().text;
		advance();
		auto right = parseMultiplicativeExpression();
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::BinaryOp;
		node->op = op;
		node->children = {left, right};
		left = node;
	}
	return left;
}

// multiplicativeExpression: unaryExpression (('*' | '/' | 'div' | 'mod') unaryExpression)*
ASTNodePtr Parser::parseMultiplicativeExpression() {
	auto left = parseUnaryExpression();
	while (check(TokenType::Star) || check(TokenType::Slash) || check(TokenType::Div) || check(TokenType::Mod)) {
		std::string op = current().text;
		advance();
		auto right = parseUnaryExpression();
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::BinaryOp;
		node->op = op;
		node->children = {left, right};
		left = node;
	}
	return left;
}

// unaryExpression: ('+' | '-') unaryExpression | invocationExpression
ASTNodePtr Parser::parseUnaryExpression() {
	if (check(TokenType::Plus) || check(TokenType::Minus)) {
		std::string op = current().text;
		advance();
		auto operand = parseUnaryExpression();
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::UnaryOp;
		node->op = op;
		node->children = {operand};
		return node;
	}
	return parseInvocationExpression();
}

// invocationExpression: primaryExpression ('.' invocation | '[' expression ']')*
ASTNodePtr Parser::parseInvocationExpression() {
	auto expr = parsePrimaryExpression();

	while (true) {
		if (check(TokenType::Dot)) {
			advance();
			if (check(TokenType::Identifier) || check(TokenType::Contains) || check(TokenType::As) ||
			    check(TokenType::Is) || check(TokenType::Not) || check(TokenType::In) ||
			    check(TokenType::Div) || check(TokenType::Mod)) {
				std::string name = current().text;
				size_t name_pos = current().position;
				advance();

				// Check if this is a function call
				if (check(TokenType::LParen)) {
					auto func_node = std::make_shared<ASTNode>();
					func_node->name = name;
					func_node->source = expr;

					advance(); // skip (

					// Special handling for known filter/invocation functions
					if (name == "where" || name == "exists" || name == "all" || name == "select" ||
					    name == "repeat" || name == "aggregate") {
						if (name == "where") {
							func_node->type = NodeType::WhereCall;
						} else if (name == "exists") {
							func_node->type = NodeType::ExistsCall;
						} else {
							func_node->type = NodeType::FunctionCall;
						}
						if (!check(TokenType::RParen)) {
							func_node->children.push_back(parseExpression());
							while (match(TokenType::Comma)) {
								func_node->children.push_back(parseExpression());
							}
						}
					} else if (name == "ofType") {
						func_node->type = NodeType::OfTypeCall;
						if (!check(TokenType::RParen)) {
							// Parse the type name, handling qualified names like FHIR.Patient or FHIR.`Patient`
							func_node->children.push_back(parseExpression());
						}
					} else if (name == "extension") {
						func_node->type = NodeType::ExtensionCall;
						if (!check(TokenType::RParen)) {
							func_node->children.push_back(parseExpression());
						}
					} else if (name == "iif") {
						func_node->type = NodeType::FunctionCall;
						// iif(criterion, true-result [, false-result])
						func_node->children.push_back(parseExpression());
						consume(TokenType::Comma, "Expected ',' in iif()");
						func_node->children.push_back(parseExpression());
						if (match(TokenType::Comma)) {
							func_node->children.push_back(parseExpression());
						}
					} else {
						func_node->type = NodeType::FunctionCall;
						if (!check(TokenType::RParen)) {
							func_node->children.push_back(parseExpression());
							while (match(TokenType::Comma)) {
								func_node->children.push_back(parseExpression());
							}
						}
					}

					consume(TokenType::RParen, "Expected ')' after function arguments");
					expr = func_node;
				} else {
					// Simple member access
					auto member = std::make_shared<ASTNode>();
					member->type = NodeType::MemberAccess;
					member->name = name;
					member->source = expr;
					expr = member;
				}
			} else {
				throw std::runtime_error("Expected identifier after '.' at position " +
				                         std::to_string(current().position));
			}
		} else if (check(TokenType::LBracket)) {
			advance();
			auto index_expr = parseExpression();
			consume(TokenType::RBracket, "Expected ']'");

			auto indexer = std::make_shared<ASTNode>();
			indexer->type = NodeType::Indexer;
			indexer->source = expr;
			indexer->children = {index_expr};
			expr = indexer;
		} else {
			break;
		}
	}

	return expr;
}

ASTNodePtr Parser::parsePrimaryExpression() {
	// Parenthesized expression
	if (check(TokenType::LParen)) {
		advance();
		auto expr = parseExpression();
		consume(TokenType::RParen, "Expected ')'");
		return expr;
	}

	// Literal values
	if (check(TokenType::Integer) || check(TokenType::Decimal) || check(TokenType::String) ||
	    check(TokenType::True_) || check(TokenType::False_) || check(TokenType::Date) ||
	    check(TokenType::DateTime) || check(TokenType::Time)) {
		return parseLiteral();
	}

	// Quantity literal: number followed by unit string
	// Handled after number parsing in invocation

	// Special variables
	if (check(TokenType::DollarThis)) {
		advance();
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::This;
		return node;
	}
	if (check(TokenType::DollarTotal)) {
		advance();
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::Total;
		return node;
	}
	if (check(TokenType::DollarIndex)) {
		advance();
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::Index;
		return node;
	}

	// Environment variables
	if (check(TokenType::Percent)) {
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::EnvVariable;
		node->name = current().text;
		advance();
		return node;
	}

	// Identifier (member access from root, or type name)
	// Also allow keywords that can appear as identifiers/field names
	if (check(TokenType::Identifier) || check(TokenType::Contains) || check(TokenType::In) ||
	    check(TokenType::As) || check(TokenType::Is) || check(TokenType::Div) || check(TokenType::Mod)) {
		std::string name = current().text;
		advance();

		// Check if it's a function call without a source (standalone function)
		if (check(TokenType::LParen)) {
			auto func_node = std::make_shared<ASTNode>();
			func_node->type = NodeType::FunctionCall;
			func_node->name = name;
			advance(); // skip (
			if (!check(TokenType::RParen)) {
				func_node->children.push_back(parseExpression());
				while (match(TokenType::Comma)) {
					func_node->children.push_back(parseExpression());
				}
			}
			consume(TokenType::RParen, "Expected ')' after function arguments");
			return func_node;
		}

		// Simple identifier → MemberAccess from implicit context
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::MemberAccess;
		node->name = name;
		return node;
	}

	// Empty collection: {}
	if (check(TokenType::LBrace)) {
		advance();
		consume(TokenType::RBrace, "Expected '}' for empty collection");
		auto node = std::make_shared<ASTNode>();
		node->type = NodeType::FunctionCall;
		node->name = "empty_collection";
		return node;
	}

	throw std::runtime_error("Unexpected token '" + current().text + "' at position " +
	                         std::to_string(current().position));
}

ASTNodePtr Parser::parseLiteral() {
	auto node = std::make_shared<ASTNode>();
	Token tok = current();
	advance();

	switch (tok.type) {
	case TokenType::Integer: {
		node->type = NodeType::IntegerLiteral;
		node->value = static_cast<int64_t>(std::stoll(tok.text));
		// Check for quantity: integer followed by string literal or time unit keyword
		if (check(TokenType::String)) {
			node->type = NodeType::QuantityLiteral;
			std::string unit = current().text;
			advance();
			node->value = QuantityValue {static_cast<double>(std::stoll(tok.text)), unit};
		} else if (isTimeUnitKeyword(current().type)) {
			node->type = NodeType::QuantityLiteral;
			std::string unit = current().text;
			advance();
			node->value = QuantityValue {static_cast<double>(std::stoll(tok.text)), unit};
		}
		break;
	}
	case TokenType::Decimal: {
		node->type = NodeType::DecimalLiteral;
		node->value = std::stod(tok.text);
		node->value.string_val = tok.text;  // Preserve original text for precision tracking
		// Check for quantity
		if (check(TokenType::String)) {
			node->type = NodeType::QuantityLiteral;
			std::string unit = current().text;
			advance();
			node->value = QuantityValue {std::stod(tok.text), unit};
			node->value.string_val = tok.text;  // Preserve decimal text
		} else if (isTimeUnitKeyword(current().type)) {
			node->type = NodeType::QuantityLiteral;
			std::string unit = current().text;
			advance();
			node->value = QuantityValue {std::stod(tok.text), unit};
			node->value.string_val = tok.text;  // Preserve decimal text
		}
		break;
	}
	case TokenType::String:
		node->type = NodeType::StringLiteral;
		node->value = tok.text;
		break;
	case TokenType::True_:
		node->type = NodeType::BooleanLiteral;
		node->value = true;
		break;
	case TokenType::False_:
		node->type = NodeType::BooleanLiteral;
		node->value = false;
		break;
	case TokenType::Date:
		node->type = NodeType::DateLiteral;
		node->value = tok.text;
		break;
	case TokenType::DateTime:
		node->type = NodeType::DateTimeLiteral;
		node->value = tok.text;
		break;
	case TokenType::Time:
		node->type = NodeType::TimeLiteral;
		node->value = tok.text;
		break;
	default:
		throw std::runtime_error("Unexpected literal token at position " + std::to_string(tok.position));
	}

	return node;
}

} // namespace fhirpath
