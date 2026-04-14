#pragma once

#include <string>
#include <vector>

namespace fhirpath {

enum class TokenType {
	// Literals
	Integer,
	Decimal,
	String,
	Boolean,
	Date,
	DateTime,
	Time,

	// Identifiers and keywords
	Identifier,
	And,
	Or,
	Xor,
	Implies,
	Not,
	Is,
	As,
	In,
	Contains,
	Div,
	Mod,
	True_,
	False_,
	Day,
	Days,
	Week,
	Weeks,
	Month,
	Months,
	Year,
	Years,
	Hour,
	Hours,
	Minute,
	Minutes,
	Second,
	Seconds,
	Millisecond,
	Milliseconds,

	// Symbols
	Dot,
	Comma,
	LParen,
	RParen,
	LBracket,
	RBracket,
	LBrace,
	RBrace,
	Plus,
	Minus,
	Star,
	Slash,
	Equals,
	NotEquals,
	Less,
	Greater,
	LessEqual,
	GreaterEqual,
	Ampersand,
	Pipe,
	At,

	// Special
	Percent,
	DollarThis,
	DollarTotal,
	DollarIndex,

	Eof,
};

struct Token {
	TokenType type;
	std::string text;
	size_t position;
};

class Lexer {
public:
	explicit Lexer(const std::string &input);
	std::vector<Token> tokenize();
	bool hasError() const { return error_; }

private:
	std::string input_;
	size_t pos_;
	bool error_ = false;

	Token nextToken();
	Token readString();
	Token readNumber();
	Token readIdentifierOrKeyword();
	Token readDateLiteral();
	void skipWhitespace();
	char peek() const;
	char advance();
	bool isAtEnd() const;
};

} // namespace fhirpath
