#pragma once

#include "ast.hpp"
#include <list>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>

namespace fhirpath {

// Thread-safe LRU cache for compiled FHIRPath expressions
class ExpressionCache {
public:
	explicit ExpressionCache(size_t max_size = 1024) : max_size_(max_size) {
	}

	std::shared_ptr<ASTNode> get(const std::string &expression) {
		std::lock_guard<std::mutex> lock(mutex_);

		auto it = cache_map_.find(expression);
		if (it != cache_map_.end()) {
			lru_list_.splice(lru_list_.begin(), lru_list_, it->second.lru_iter);
			return it->second.ast;
		}
		return nullptr;
	}

	void put(const std::string &expression, std::shared_ptr<ASTNode> ast) {
		std::lock_guard<std::mutex> lock(mutex_);

		auto it = cache_map_.find(expression);
		if (it != cache_map_.end()) {
			lru_list_.splice(lru_list_.begin(), lru_list_, it->second.lru_iter);
			it->second.ast = ast;
			return;
		}

		if (cache_map_.size() >= max_size_) {
			auto &oldest_key = lru_list_.back();
			cache_map_.erase(oldest_key);
			lru_list_.pop_back();
		}

		lru_list_.push_front(expression);
		cache_map_[expression] = {ast, lru_list_.begin()};
	}

	void clear() {
		std::lock_guard<std::mutex> lock(mutex_);
		cache_map_.clear();
		lru_list_.clear();
	}

private:
	struct CacheEntry {
		std::shared_ptr<ASTNode> ast;
		std::list<std::string>::iterator lru_iter;
	};

	size_t max_size_;
	std::mutex mutex_;
	std::unordered_map<std::string, CacheEntry> cache_map_;
	std::list<std::string> lru_list_;
};

} // namespace fhirpath
