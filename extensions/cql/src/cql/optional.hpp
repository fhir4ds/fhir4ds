#pragma once

namespace cql {

// Simple C++11 optional replacement (DuckDB uses C++11, std::optional is C++17)
template <typename T>
class Optional {
public:
	Optional() : has_val(false), val() {
	}
	Optional(const T &value) : has_val(true), val(value) { // NOLINT
	}
	Optional(T &&value) : has_val(true), val(std::move(value)) { // NOLINT
	}

	bool has_value() const {
		return has_val;
	}
	explicit operator bool() const {
		return has_val;
	}

	const T &value() const {
		return val;
	}
	T &value() {
		return val;
	}

	const T &operator*() const {
		return val;
	}
	T &operator*() {
		return val;
	}

	const T *operator->() const {
		return &val;
	}
	T *operator->() {
		return &val;
	}

private:
	bool has_val;
	T val;
};

// Factory function (replaces std::nullopt returns)
template <typename T>
Optional<T> NullOpt() {
	return Optional<T>();
}

// Factory function (replaces std::optional<T>(value) construction)
template <typename T>
Optional<T> MakeOptional(const T &value) {
	return Optional<T>(value);
}

template <typename T>
Optional<T> MakeOptional(T &&value) {
	return Optional<T>(std::move(value));
}

} // namespace cql
