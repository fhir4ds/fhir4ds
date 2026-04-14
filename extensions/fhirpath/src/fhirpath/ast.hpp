#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace fhirpath {

enum class NodeType {
	// Literals
	IntegerLiteral,
	DecimalLiteral,
	StringLiteral,
	BooleanLiteral,
	DateLiteral,
	DateTimeLiteral,
	TimeLiteral,
	QuantityLiteral,

	// Navigation
	MemberAccess,
	Indexer,
	TypeExpression,

	// Invocations
	FunctionCall,
	WhereCall,
	ExistsCall,
	OfTypeCall,
	ExtensionCall,

	// Operators
	BinaryOp,
	UnaryOp,

	// Collections
	UnionOp,

	// Environment
	EnvVariable,

	// Root
	This,
	Total,
	Index,
};

struct ASTNode;
using ASTNodePtr = std::shared_ptr<ASTNode>;

struct QuantityValue {
	double value;
	std::string unit;
};

// C++11-compatible tagged value (replaces std::variant)
struct NodeValue {
	enum class Tag { None, Int, Double, String, Bool, Quantity };
	Tag tag;
	int64_t int_val;
	double double_val;
	std::string string_val;
	bool bool_val;
	QuantityValue quantity_val;

	NodeValue() : tag(Tag::None), int_val(0), double_val(0.0), bool_val(false) {}

	// Assignment operators for direct assignment from value types
	NodeValue &operator=(int64_t v) { tag = Tag::Int; int_val = v; return *this; }
	NodeValue &operator=(double v) { tag = Tag::Double; double_val = v; return *this; }
	NodeValue &operator=(const std::string &v) { tag = Tag::String; string_val = v; return *this; }
	NodeValue &operator=(bool v) { tag = Tag::Bool; bool_val = v; return *this; }
	NodeValue &operator=(const QuantityValue &v) { tag = Tag::Quantity; quantity_val = v; return *this; }
};

// Typed accessors (replaces std::get<T>)
template <typename T> T node_value_get(const NodeValue &v);
template <> inline int64_t node_value_get<int64_t>(const NodeValue &v) { return v.int_val; }
template <> inline double node_value_get<double>(const NodeValue &v) { return v.double_val; }
template <> inline std::string node_value_get<std::string>(const NodeValue &v) { return v.string_val; }
template <> inline bool node_value_get<bool>(const NodeValue &v) { return v.bool_val; }
template <> inline QuantityValue node_value_get<QuantityValue>(const NodeValue &v) { return v.quantity_val; }

struct ASTNode {
	NodeType type;

	NodeValue value;

	// For MemberAccess, FunctionCall: the name
	std::string name;

	// For BinaryOp, UnaryOp: the operator
	std::string op;

	// Children: left operand, right operand, arguments, filter criteria
	std::vector<ASTNodePtr> children;

	// For function calls: the source expression (what .func() is called on)
	ASTNodePtr source;
};

} // namespace fhirpath
