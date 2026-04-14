#include "fhirpath/lexer.hpp"
#include <cctype>
#include <stdexcept>
#include <unordered_map>

namespace fhirpath {

static const std::unordered_map<std::string, TokenType> KEYWORDS = {
    {"and", TokenType::And},
    {"or", TokenType::Or},
    {"xor", TokenType::Xor},
    {"implies", TokenType::Implies},
    {"not", TokenType::Not},
    {"is", TokenType::Is},
    {"as", TokenType::As},
    {"in", TokenType::In},
    {"contains", TokenType::Contains},
    {"div", TokenType::Div},
    {"mod", TokenType::Mod},
    {"true", TokenType::True_},
    {"false", TokenType::False_},
    {"day", TokenType::Day},
    {"days", TokenType::Days},
    {"week", TokenType::Week},
    {"weeks", TokenType::Weeks},
    {"month", TokenType::Month},
    {"months", TokenType::Months},
    {"year", TokenType::Year},
    {"years", TokenType::Years},
    {"hour", TokenType::Hour},
    {"hours", TokenType::Hours},
    {"minute", TokenType::Minute},
    {"minutes", TokenType::Minutes},
    {"second", TokenType::Second},
    {"seconds", TokenType::Seconds},
    {"millisecond", TokenType::Millisecond},
    {"milliseconds", TokenType::Milliseconds},
};

Lexer::Lexer(const std::string &input) : input_(input), pos_(0) {
}

std::vector<Token> Lexer::tokenize() {
	std::vector<Token> tokens;
	while (!isAtEnd()) {
		skipWhitespace();
		if (isAtEnd()) {
			break;
		}
		tokens.push_back(nextToken());
	}
	tokens.push_back({TokenType::Eof, "", pos_});
	return tokens;
}

void Lexer::skipWhitespace() {
	while (!isAtEnd()) {
		char c = input_[pos_];
		if (std::isspace(static_cast<unsigned char>(c))) {
			pos_++;
			continue;
		}
		// Single-line comment: // ... until end of line
		if (c == '/' && pos_ + 1 < input_.size() && input_[pos_ + 1] == '/') {
			pos_ += 2;
			while (!isAtEnd() && input_[pos_] != '\n') {
				pos_++;
			}
			if (!isAtEnd()) {
				pos_++; // skip the newline
			}
			continue;
		}
		// Multi-line comment: /* ... */
		if (c == '/' && pos_ + 1 < input_.size() && input_[pos_ + 1] == '*') {
			pos_ += 2;
			bool closed = false;
			while (!isAtEnd()) {
				if (input_[pos_] == '*' && pos_ + 1 < input_.size() && input_[pos_ + 1] == '/') {
					pos_ += 2;
					closed = true;
					break;
				}
				pos_++;
			}
			if (!closed) {
				// Unterminated comment - set error flag
				error_ = true;
			}
			continue;
		}
		break;
	}
}

char Lexer::peek() const {
	if (isAtEnd()) {
		return '\0';
	}
	return input_[pos_];
}

char Lexer::advance() {
	return input_[pos_++];
}

bool Lexer::isAtEnd() const {
	return pos_ >= input_.size();
}

Token Lexer::nextToken() {
	size_t start = pos_;
	char c = peek();

	// String literal
	if (c == '\'') {
		return readString();
	}

	// Date/time literal (@)
	if (c == '@') {
		return readDateLiteral();
	}

	// Number
	if (std::isdigit(static_cast<unsigned char>(c))) {
		return readNumber();
	}

	// Identifier or keyword
	if (std::isalpha(static_cast<unsigned char>(c)) || c == '_') {
		return readIdentifierOrKeyword();
	}

	// $ special variables
	if (c == '$') {
		advance();
		std::string word;
		while (!isAtEnd() && (std::isalnum(static_cast<unsigned char>(peek())) || peek() == '_')) {
			word += advance();
		}
		if (word == "this") {
			return {TokenType::DollarThis, "$this", start};
		}
		if (word == "total") {
			return {TokenType::DollarTotal, "$total", start};
		}
		if (word == "index") {
			return {TokenType::DollarIndex, "$index", start};
		}
		throw std::runtime_error("Unknown special variable $" + word + " at position " + std::to_string(start));
	}

	// % environment variable
	if (c == '%') {
		advance();
		std::string name;
		// Handle backtick-delimited names
		if (!isAtEnd() && peek() == '`') {
			advance(); // skip opening backtick
			while (!isAtEnd() && peek() != '`') {
				name += advance();
			}
			if (!isAtEnd()) {
				advance(); // skip closing backtick
			}
		} else {
			while (!isAtEnd() && (std::isalnum(static_cast<unsigned char>(peek())) || peek() == '_' || peek() == '-')) {
				name += advance();
			}
		}
		return {TokenType::Percent, "%" + name, start};
	}

	// Backtick-delimited identifier
	if (c == '`') {
		advance(); // skip opening backtick
		std::string name;
		while (!isAtEnd() && peek() != '`') {
			name += advance();
		}
		if (!isAtEnd()) {
			advance(); // skip closing backtick
		}
		return {TokenType::Identifier, name, start};
	}

	// Symbols
	advance();
	switch (c) {
	case '.':
		return {TokenType::Dot, ".", start};
	case ',':
		return {TokenType::Comma, ",", start};
	case '(':
		return {TokenType::LParen, "(", start};
	case ')':
		return {TokenType::RParen, ")", start};
	case '[':
		return {TokenType::LBracket, "[", start};
	case ']':
		return {TokenType::RBracket, "]", start};
	case '{':
		return {TokenType::LBrace, "{", start};
	case '}':
		return {TokenType::RBrace, "}", start};
	case '+':
		return {TokenType::Plus, "+", start};
	case '-':
		return {TokenType::Minus, "-", start};
	case '*':
		return {TokenType::Star, "*", start};
	case '/':
		return {TokenType::Slash, "/", start};
	case '&':
		return {TokenType::Ampersand, "&", start};
	case '|':
		return {TokenType::Pipe, "|", start};
	case '=':
		return {TokenType::Equals, "=", start};
	case '!':
		if (!isAtEnd() && peek() == '=') {
			advance();
			return {TokenType::NotEquals, "!=", start};
		}
		if (!isAtEnd() && peek() == '~') {
			advance();
			return {TokenType::NotEquals, "!~", start};
		}
		throw std::runtime_error("Unexpected character '!' at position " + std::to_string(start));
	case '~':
		return {TokenType::Equals, "~", start};
	case '<':
		if (!isAtEnd() && peek() == '=') {
			advance();
			return {TokenType::LessEqual, "<=", start};
		}
		return {TokenType::Less, "<", start};
	case '>':
		if (!isAtEnd() && peek() == '=') {
			advance();
			return {TokenType::GreaterEqual, ">=", start};
		}
		return {TokenType::Greater, ">", start};
	default:
		throw std::runtime_error("Unexpected character '" + std::string(1, c) + "' at position " +
		                         std::to_string(start));
	}
}

Token Lexer::readString() {
	size_t start = pos_;
	advance(); // skip opening quote
	std::string value;
	while (!isAtEnd()) {
		char c = peek();
		if (c == '\\') {
			advance();
			if (!isAtEnd()) {
				char escaped = advance();
				switch (escaped) {
				case '\'':
					value += '\'';
					break;
				case '\\':
					value += '\\';
					break;
				case 'n':
					value += '\n';
					break;
				case 'r':
					value += '\r';
					break;
				case 't':
					value += '\t';
					break;
				case '/':
					value += '/';
					break;
				case 'f':
					value += '\f';
					break;
				case 'u': {
					// Unicode escape: \uXXXX
					std::string hex;
					for (int i = 0; i < 4 && !isAtEnd(); ++i) {
						hex += advance();
					}
					if (hex.size() == 4) {
						unsigned int cp = std::stoul(hex, nullptr, 16);
						if (cp < 0x80) {
							value += static_cast<char>(cp);
						} else if (cp < 0x800) {
							value += static_cast<char>(0xC0 | (cp >> 6));
							value += static_cast<char>(0x80 | (cp & 0x3F));
						} else {
							value += static_cast<char>(0xE0 | (cp >> 12));
							value += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
							value += static_cast<char>(0x80 | (cp & 0x3F));
						}
					}
					break;
				}
				default:
					value += escaped;
					break;
				}
			}
		} else if (c == '\'') {
			advance(); // skip closing quote
			return {TokenType::String, value, start};
		} else {
			value += advance();
		}
	}
	throw std::runtime_error("Unterminated string at position " + std::to_string(start));
}

Token Lexer::readNumber() {
	size_t start = pos_;
	std::string number;
	bool has_dot = false;

	while (!isAtEnd() && (std::isdigit(static_cast<unsigned char>(peek())) || peek() == '.')) {
		if (peek() == '.') {
			// Look ahead to distinguish decimal from member access
			if (pos_ + 1 < input_.size() && std::isdigit(static_cast<unsigned char>(input_[pos_ + 1]))) {
				has_dot = true;
				number += advance();
			} else {
				break;
			}
		} else {
			number += advance();
		}
	}

	return {has_dot ? TokenType::Decimal : TokenType::Integer, number, start};
}

Token Lexer::readIdentifierOrKeyword() {
	size_t start = pos_;
	std::string word;
	while (!isAtEnd() && (std::isalnum(static_cast<unsigned char>(peek())) || peek() == '_')) {
		word += advance();
	}

	auto it = KEYWORDS.find(word);
	if (it != KEYWORDS.end()) {
		return {it->second, word, start};
	}
	return {TokenType::Identifier, word, start};
}

Token Lexer::readDateLiteral() {
	size_t start = pos_;
	advance(); // skip @

	std::string value;
	bool is_time_only = false;

	if (!isAtEnd() && peek() == 'T') {
		is_time_only = true;
	}

	// Read date/datetime/time characters
	while (!isAtEnd()) {
		char c = peek();
		if (std::isdigit(static_cast<unsigned char>(c)) || c == '-' || c == ':' || c == 'T' || c == '+' ||
		    c == 'Z') {
			value += advance();
		} else if (c == '.') {
			// Only consume '.' if followed by a digit (milliseconds), not if followed by a letter (member access)
			if (pos_ + 1 < input_.size() && std::isdigit(static_cast<unsigned char>(input_[pos_ + 1]))) {
				value += advance();
			} else {
				break;
			}
		} else {
			break;
		}
	}

	if (is_time_only) {
		// FHIRPath Time literals don't support timezone (Z or +/-offset)
		if (value.find('Z') != std::string::npos || value.find('+') != std::string::npos) {
			error_ = true;
			return {TokenType::Time, value, start};
		}
		// Check for negative offset (but '-' is also used in the value itself before T, so only check after digits)
		for (size_t i = 1; i < value.size(); i++) {
			if (value[i] == '-' && i > 1) {
				error_ = true;
				return {TokenType::Time, value, start};
			}
		}
		return {TokenType::Time, value, start};
	}
	if (value.find('T') != std::string::npos) {
		return {TokenType::DateTime, value, start};
	}
	return {TokenType::Date, value, start};
}

} // namespace fhirpath
