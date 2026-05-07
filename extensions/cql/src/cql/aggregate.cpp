#include "cql/aggregate.hpp"
#include <algorithm>
#include <cmath>
#include <map>
#include <numeric>

namespace cql {

Optional<double> statistical_median(const std::vector<double> &values) {
	if (values.empty()) {
		return NullOpt<double>();
	}
	std::vector<double> sorted = values;
	std::sort(sorted.begin(), sorted.end());

	size_t n = sorted.size();
	if (n % 2 == 0) {
		return (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0;
	}
	return sorted[n / 2];
}

Optional<double> statistical_mode(const std::vector<double> &values) {
	if (values.empty()) {
		return NullOpt<double>();
	}
	// Use std::map for exact double comparison with full precision
	std::map<double, size_t> counts;
	for (double v : values) {
		counts[v]++;
	}
	typedef std::map<double, size_t>::value_type count_pair;
	auto max_it = std::max_element(counts.begin(), counts.end(),
	                               [](const count_pair &a, const count_pair &b) { return a.second < b.second; });
	size_t max_count = max_it->second;
	// CQL spec: "If there are multiple values with the same highest frequency, the result is null."
	size_t max_count_freq = 0;
	for (const auto &pair : counts) {
		if (pair.second == max_count) max_count_freq++;
	}
	if (max_count_freq > 1) {
		return NullOpt<double>();
	}
	return max_it->first;
}

Optional<double> statistical_stddev(const std::vector<double> &values) {
	auto var = statistical_variance(values);
	if (!var) {
		return NullOpt<double>();
	}
	return std::sqrt(*var);
}

Optional<double> statistical_variance(const std::vector<double> &values) {
	if (values.size() < 2) {
		return NullOpt<double>();
	}
	double mean = std::accumulate(values.begin(), values.end(), 0.0) / static_cast<double>(values.size());
	double sum_sq = 0.0;
	for (double v : values) {
		double diff = v - mean;
		sum_sq += diff * diff;
	}
	// Sample variance (n-1)
	return sum_sq / static_cast<double>(values.size() - 1);
}

} // namespace cql
