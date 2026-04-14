"""Unit tests for statistical aggregate functions."""
import pytest
import sys

from ....parser.parser import parse_expression
from ....translator import CQLTranslator


class TestMedianFunction:
    def test_median_translation(self):
        """Test Median() translates to statisticalMedian()"""
        expr = parse_expression("Median({1, 2, 3, 4, 5})")
        translator = CQLTranslator()
        result = translator.translate_expression(expr)
        assert "statisticalMedian" in result

    def test_median_with_identifier(self):
        """Test Median with identifier argument."""
        expr = parse_expression("Median(values)")
        translator = CQLTranslator()
        result = translator.translate_expression(expr)
        assert "statisticalMedian" in result

    def test_median_lowercase(self):
        """Test lowercase median function."""
        expr = parse_expression("median({1, 2, 3})")
        translator = CQLTranslator()
        result = translator.translate_expression(expr)
        assert "statisticalMedian" in result


class TestModeFunction:
    def test_mode_translation(self):
        """Test Mode() translates to statisticalMode()"""
        expr = parse_expression("Mode({1, 2, 2, 3})")
        translator = CQLTranslator()
        result = translator.translate_expression(expr)
        assert "statisticalMode" in result

    def test_mode_with_list(self):
        """Test Mode with list literal."""
        expr = parse_expression("Mode({1, 1, 1, 2, 3})")
        translator = CQLTranslator()
        result = translator.translate_expression(expr)
        assert "statisticalMode" in result


class TestStdDevFunction:
    def test_stddev_translation(self):
        """Test StdDev() translates to statisticalStdDev()"""
        expr = parse_expression("StdDev({1, 2, 3, 4, 5})")
        translator = CQLTranslator()
        result = translator.translate_expression(expr)
        assert "statisticalStdDev" in result

    def test_stddev_lowercase(self):
        """Test lowercase stddev function."""
        expr = parse_expression("stddev({1, 2, 3})")
        translator = CQLTranslator()
        result = translator.translate_expression(expr)
        assert "statisticalStdDev" in result


class TestVarianceFunction:
    def test_variance_translation(self):
        """Test Variance() translates to statisticalVariance()"""
        expr = parse_expression("Variance({1, 2, 3, 4, 5})")
        translator = CQLTranslator()
        result = translator.translate_expression(expr)
        assert "statisticalVariance" in result

    def test_variance_with_identifier(self):
        """Test Variance with identifier."""
        expr = parse_expression("Variance(observations)")
        translator = CQLTranslator()
        result = translator.translate_expression(expr)
        assert "statisticalVariance" in result


class TestAggregateInQuery:
    def test_aggregate_in_where(self):
        """Test aggregate function in where clause."""
        expr = parse_expression("from [Observation] O where StdDev(O.values) > 5")
        translator = CQLTranslator()
        result = translator.translate_expression(expr)
        assert "statisticalStdDev" in result
