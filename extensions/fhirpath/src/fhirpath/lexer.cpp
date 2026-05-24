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

static bool isDigitAt(const std::string &value, size_t pos) {
	return pos < value.size() && std::isdigit(static_cast<unsigned char>(value[pos]));
}

static bool isFhirPathWhitespace(char c) {
	return c == ' ' || c == '\t' || c == '\n' || c == '\r';
}

static bool consumeTimezoneFormat(const std::string &value, size_t &pos) {
	if (pos >= value.size()) {
		return true;
	}
	if (value[pos] == 'Z') {
		pos++;
		return pos == value.size();
	}
	if (value[pos] != '+' && value[pos] != '-') {
		return false;
	}
	if (pos + 6 > value.size() || value[pos + 3] != ':') {
		return false;
	}
	if (!isDigitAt(value, pos + 1) || !isDigitAt(value, pos + 2) ||
	    !isDigitAt(value, pos + 4) || !isDigitAt(value, pos + 5)) {
		return false;
	}
	pos += 6;
	return pos == value.size();
}

static bool consumeTimeFormat(const std::string &value, size_t &pos, bool allow_timezone) {
	if (!isDigitAt(value, pos) || !isDigitAt(value, pos + 1)) {
		return false;
	}
	pos += 2;
	if (pos >= value.size()) {
		return true;
	}
	if (allow_timezone && (value[pos] == 'Z' || value[pos] == '+' || value[pos] == '-')) {
		return consumeTimezoneFormat(value, pos);
	}
	if (value[pos] != ':') {
		return false;
	}
	pos++;
	if (!isDigitAt(value, pos) || !isDigitAt(value, pos + 1)) {
		return false;
	}
	pos += 2;
	if (pos >= value.size()) {
		return true;
	}
	if (allow_timezone && (value[pos] == 'Z' || value[pos] == '+' || value[pos] == '-')) {
		return consumeTimezoneFormat(value, pos);
	}
	if (value[pos] != ':') {
		return false;
	}
	pos++;
	if (!isDigitAt(value, pos) || !isDigitAt(value, pos + 1)) {
		return false;
	}
	pos += 2;
	if (pos < value.size() && value[pos] == '.') {
		pos++;
		size_t fraction_start = pos;
		while (isDigitAt(value, pos)) {
			pos++;
		}
		if (pos == fraction_start) {
			return false;
		}
	}
	if (pos >= value.size()) {
		return true;
	}
	if (allow_timezone && (value[pos] == 'Z' || value[pos] == '+' || value[pos] == '-')) {
		return consumeTimezoneFormat(value, pos);
	}
	return false;
}

static bool isValidDateLiteralFormat(const std::string &value) {
	size_t pos = 0;
	if (!isDigitAt(value, 0) || !isDigitAt(value, 1) || !isDigitAt(value, 2) || !isDigitAt(value, 3)) {
		return false;
	}
	pos = 4;
	if (pos < value.size() && value[pos] == '-') {
		pos++;
		if (!isDigitAt(value, pos) || !isDigitAt(value, pos + 1)) {
			return false;
		}
		pos += 2;
		if (pos < value.size() && value[pos] == '-') {
			pos++;
			if (!isDigitAt(value, pos) || !isDigitAt(value, pos + 1)) {
				return false;
			}
			pos += 2;
		}
	}
	if (pos >= value.size()) {
		return true;
	}
	if (value[pos] != 'T') {
		return false;
	}
	pos++;
	if (pos >= value.size()) {
		return true;
	}
	return consumeTimeFormat(value, pos, true) && pos == value.size();
}

static bool isValidTimeLiteralFormat(const std::string &value) {
	if (value.empty() || value[0] != 'T') {
		return false;
	}
	size_t pos = 1;
	return consumeTimeFormat(value, pos, false) && pos == value.size();
}

static bool hasLaterSingleQuote(const std::string &value, size_t pos) {
	for (size_t i = pos; i < value.size(); ++i) {
		if (value[i] == '\'') {
			return true;
		}
	}
	return false;
}

static bool isHex4At(const std::string &value, size_t pos) {
	if (pos + 4 > value.size()) {
		return false;
	}
	for (size_t i = pos; i < pos + 4; ++i) {
		if (!std::isxdigit(static_cast<unsigned char>(value[i]))) {
			return false;
		}
	}
	return true;
}

static unsigned int parseHex4At(const std::string &value, size_t pos) {
	return static_cast<unsigned int>(std::stoul(value.substr(pos, 4), nullptr, 16));
}

static void appendUtf8(std::string &value, unsigned int cp) {
	if (cp < 0x80) {
		value += static_cast<char>(cp);
	} else if (cp < 0x800) {
		value += static_cast<char>(0xC0 | (cp >> 6));
		value += static_cast<char>(0x80 | (cp & 0x3F));
	} else if (cp < 0x10000) {
		value += static_cast<char>(0xE0 | (cp >> 12));
		value += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
		value += static_cast<char>(0x80 | (cp & 0x3F));
	} else {
		value += static_cast<char>(0xF0 | (cp >> 18));
		value += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
		value += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
		value += static_cast<char>(0x80 | (cp & 0x3F));
	}
}

static bool appendUnicodeEscape(std::string &out, const std::string &input, size_t &pos, const std::string &hex) {
	bool valid_hex = hex.size() == 4;
	for (char h : hex) {
		if (!std::isxdigit(static_cast<unsigned char>(h))) {
			valid_hex = false;
			break;
		}
	}
	if (!valid_hex) {
		out += 'u';
		out += hex;
		return false;
	}

	unsigned int cp = static_cast<unsigned int>(std::stoul(hex, nullptr, 16));
	if (cp >= 0xD800 && cp <= 0xDBFF && pos + 6 <= input.size() &&
	    input[pos] == '\\' && input[pos + 1] == 'u' && isHex4At(input, pos + 2)) {
		unsigned int low = parseHex4At(input, pos + 2);
		if (low >= 0xDC00 && low <= 0xDFFF) {
			cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00);
			pos += 6;
		}
	}
	appendUtf8(out, cp);
	return true;
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
		if (isFhirPathWhitespace(c)) {
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
		// externalConstant is '%' followed by an identifier or STRING in the
		// formal grammar; whitespace/comments are hidden tokens between them.
		skipWhitespace();
		std::string name;
		// Handle backtick-delimited names
		if (!isAtEnd() && peek() == '`') {
			name = readDelimitedIdentifier().text;
		} else if (!isAtEnd() && peek() == '\'') {
			name = readString().text;
		} else {
			while (!isAtEnd() && (std::isalnum(static_cast<unsigned char>(peek())) || peek() == '_' || peek() == '-')) {
				name += advance();
			}
		}
		return {TokenType::Percent, "%" + name, start};
	}

	// Backtick-delimited identifier
	if (c == '`') {
		return readDelimitedIdentifier();
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

Token Lexer::readDelimitedIdentifier() {
	size_t start = pos_;
	advance(); // skip opening backtick
	std::string value;
	while (!isAtEnd()) {
		char c = peek();
		if (c == '\\') {
			advance();
			if (isAtEnd()) {
				break;
			}
			char escaped = advance();
			switch (escaped) {
			case '\'':
				value += '\'';
				break;
			case '"':
				value += '"';
				break;
			case '`':
				value += '`';
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
			case 'f':
				value += '\f';
				break;
				case 'u': {
					std::string hex;
					for (int i = 0; i < 4 && !isAtEnd() && peek() != '`'; ++i) {
						hex += advance();
					}
					appendUnicodeEscape(value, input_, pos_, hex);
					break;
				}
			default:
				value += escaped;
				break;
			}
		} else if (c == '`') {
			advance(); // skip closing backtick
			return {TokenType::Identifier, value, start};
		} else {
			value += advance();
		}
	}
	throw std::runtime_error("Unterminated delimited identifier at position " + std::to_string(start));
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
					if (!hasLaterSingleQuote(input_, pos_)) {
						return {TokenType::String, value, start};
					}
					value += '\'';
					break;
				case '"':
					value += '"';
					break;
				case '`':
					value += '`';
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
				case 'f':
					value += '\f';
					break;
				case 'u': {
					// Unicode escape: \uXXXX
					std::string hex;
					for (int i = 0; i < 4 && !isAtEnd() && peek() != '\''; ++i) {
						hex += advance();
					}
					appendUnicodeEscape(value, input_, pos_, hex);
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
				if (has_dot) {
					throw std::runtime_error("Invalid numeric literal at position " + std::to_string(start));
				}
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

	auto looks_like_timezone_offset = [this]() -> bool {
		return pos_ + 5 < input_.size() &&
		       (input_[pos_] == '+' || input_[pos_] == '-') &&
		       std::isdigit(static_cast<unsigned char>(input_[pos_ + 1])) &&
		       std::isdigit(static_cast<unsigned char>(input_[pos_ + 2])) &&
		       input_[pos_ + 3] == ':' &&
		       std::isdigit(static_cast<unsigned char>(input_[pos_ + 4])) &&
		       std::isdigit(static_cast<unsigned char>(input_[pos_ + 5]));
	};

	// Read date/datetime/time characters
	while (!isAtEnd()) {
		char c = peek();
		if (std::isdigit(static_cast<unsigned char>(c)) || c == ':' || c == 'T' || c == 'Z') {
			value += advance();
		} else if (c == '-') {
			bool date_prefix = (value.size() == 4 || value.size() == 7);
			bool date_separator =
			    date_prefix && pos_ + 2 < input_.size() &&
			    std::isdigit(static_cast<unsigned char>(input_[pos_ + 1])) &&
			    std::isdigit(static_cast<unsigned char>(input_[pos_ + 2]));
			if (date_separator || looks_like_timezone_offset()) {
				value += advance();
			} else if (date_prefix) {
				error_ = true;
				value += advance();
			} else {
				break;
			}
		} else if (c == '+') {
			if (looks_like_timezone_offset()) {
				value += advance();
			} else if (value.find('T') != std::string::npos &&
			           pos_ + 2 < input_.size() &&
			           std::isdigit(static_cast<unsigned char>(input_[pos_ + 1])) &&
			           std::isdigit(static_cast<unsigned char>(input_[pos_ + 2])) &&
			           (pos_ + 3 >= input_.size() ||
			            (!std::isdigit(static_cast<unsigned char>(input_[pos_ + 3])) &&
			             !isFhirPathWhitespace(input_[pos_ + 3])))) {
				error_ = true;
				value += advance();
			} else {
				break;
			}
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
		if (!isValidTimeLiteralFormat(value)) {
			error_ = true;
		}
		return {TokenType::Time, value, start};
	}
	if (!isValidDateLiteralFormat(value)) {
		error_ = true;
	}
	if (value.find('T') != std::string::npos) {
		return {TokenType::DateTime, value, start};
	}
	return {TokenType::Date, value, start};
}

} // namespace fhirpath
