#pragma once
#include <cstddef>
#include <cstring>
#include <memory>
#include <vector>

namespace fhirpath {

// Phase 7: Per-batch arena allocator for temporary strings.
// Allocates from a contiguous block, freeing all at once when the arena is reset or destroyed.
// Avoids per-string heap allocations during FHIRPath evaluation of a single DataChunk.
class ArenaAllocator {
public:
	static constexpr size_t DEFAULT_BLOCK_SIZE = 64 * 1024; // 64 KB blocks

	explicit ArenaAllocator(size_t block_size = DEFAULT_BLOCK_SIZE) : block_size_(block_size) {
		allocate_block();
	}

	// Allocate n bytes (uninitialized) from the arena
	char *allocate(size_t n) {
		// Align to 8 bytes
		n = (n + 7) & ~size_t(7);
		if (offset_ + n > current_block_size_) {
			allocate_block(n > block_size_ ? n : block_size_);
		}
		char *ptr = blocks_.back().get() + offset_;
		offset_ += n;
		return ptr;
	}

	// Copy a string into the arena, returns pointer to null-terminated copy
	const char *copy_string(const char *str, size_t len) {
		char *dest = allocate(len + 1);
		std::memcpy(dest, str, len);
		dest[len] = '\0';
		return dest;
	}

	// Reset the arena for reuse (keeps allocated memory)
	void reset() {
		blocks_.resize(1);
		offset_ = 0;
		current_block_size_ = block_size_;
	}

	// Total bytes allocated across all blocks
	size_t total_allocated() const {
		size_t total = 0;
		for (size_t i = 0; i < blocks_.size() - 1; i++) {
			total += block_size_; // approximation
		}
		total += offset_;
		return total;
	}

private:
	void allocate_block(size_t size = 0) {
		if (size == 0) {
			size = block_size_;
		}
		blocks_.push_back(std::unique_ptr<char[]>(new char[size]));
		current_block_size_ = size;
		offset_ = 0;
	}

	size_t block_size_;
	size_t current_block_size_ = 0;
	size_t offset_ = 0;
	std::vector<std::unique_ptr<char[]>> blocks_;
};

} // namespace fhirpath
