"""
Unit tests for the FHIRPath extension() function.

Tests the extension() function for accessing FHIR extension values:
- extension() with no URL returns all extensions
- extension(url) with matching URL returns matching extensions
- extension(url) with non-matching URL returns empty
- Works on resources without extensions
- Supports chaining: resource.extension('url').value
"""

from __future__ import annotations

import pytest

from fhir4ds.fhirpath.engine.invocations.filtering import extension
from fhir4ds.fhirpath.engine.nodes import ResourceNode


class TestExtensionNoUrl:
    """Tests for extension() with no URL - returns all extensions."""

    def test_extension_no_url_returns_all(self) -> None:
        """Test that extension() with no URL returns all extensions."""
        resource = {
            "extension": [
                {"url": "http://example.org/ext1", "valueString": "value1"},
                {"url": "http://example.org/ext2", "valueString": "value2"},
            ]
        }
        result = extension({}, [resource])
        assert len(result) == 2

    def test_extension_no_url_single_extension(self) -> None:
        """Test extension() with a single extension."""
        resource = {
            "extension": {"url": "http://example.org/ext", "valueString": "value"}
        }
        result = extension({}, [resource])
        assert len(result) == 1

    def test_extension_no_url_empty_when_no_extensions(self) -> None:
        """Test extension() returns empty when no extensions exist."""
        resource = {"id": "123", "name": "Test"}
        result = extension({}, [resource])
        assert result == []

    def test_extension_no_url_on_empty_collection(self) -> None:
        """Test extension() on empty collection returns empty."""
        result = extension({}, [])
        assert result == []


class TestExtensionWithUrl:
    """Tests for extension(url) - filters by URL."""

    def test_extension_with_matching_url(self) -> None:
        """Test extension(url) returns matching extension."""
        resource = {
            "extension": [
                {"url": "http://example.org/ext1", "valueString": "value1"},
                {"url": "http://example.org/ext2", "valueString": "value2"},
            ]
        }
        result = extension({}, [resource], "http://example.org/ext1")
        assert len(result) == 1
        # The result is a ResourceNode, check its data attribute
        assert result[0].data.get("valueString") == "value1"

    def test_extension_with_non_matching_url(self) -> None:
        """Test extension(url) returns empty when no match."""
        resource = {
            "extension": [
                {"url": "http://example.org/ext1", "valueString": "value1"},
            ]
        }
        result = extension({}, [resource], "http://example.org/nonexistent")
        assert result == []

    def test_extension_url_empty_when_no_extensions(self) -> None:
        """Test extension(url) returns empty when no extensions exist."""
        resource = {"id": "123", "name": "Test"}
        result = extension({}, [resource], "http://example.org/ext")
        assert result == []

    def test_extension_url_on_empty_collection(self) -> None:
        """Test extension(url) on empty collection returns empty."""
        result = extension({}, [], "http://example.org/ext")
        assert result == []


class TestExtensionPrimitiveExtensions:
    """Tests for extension() on primitive values with _data extensions."""

    def test_extension_on_primitive_with_data(self) -> None:
        """Test extension() on a primitive value with _data extensions."""
        # Simulate a ResourceNode with _data containing extensions
        # This happens for primitive extensions like Patient.birthDate.extension()
        primitive_node = ResourceNode.create_node("2014-01-15", "date")
        primitive_node._data = {
            "extension": [
                {"url": "http://hl7.org/fhir/StructureDefinition/patient-birthTime", "valueDateTime": "2014-01-15T10:30:00Z"}
            ]
        }
        result = extension({}, [primitive_node], "http://hl7.org/fhir/StructureDefinition/patient-birthTime")
        assert len(result) == 1

    def test_extension_on_primitive_no_url(self) -> None:
        """Test extension() with no URL on primitive with _data extensions."""
        primitive_node = ResourceNode.create_node("2014-01-15", "date")
        primitive_node._data = {
            "extension": [
                {"url": "http://example.org/ext1", "valueString": "val1"},
                {"url": "http://example.org/ext2", "valueString": "val2"},
            ]
        }
        result = extension({}, [primitive_node])
        assert len(result) == 2


class TestExtensionChaining:
    """Tests for chaining extension() with other operations."""

    def test_extension_returns_wrapped_nodes(self) -> None:
        """Test that extension() returns ResourceNodes for chaining."""
        resource = {
            "extension": [
                {"url": "http://example.org/ext", "valueString": "test_value"},
            ]
        }
        result = extension({}, [resource], "http://example.org/ext")
        assert len(result) == 1
        # Verify it's a ResourceNode
        assert isinstance(result[0], ResourceNode)

    def test_extension_node_has_extension_data(self) -> None:
        """Test that returned ResourceNode contains extension data."""
        resource = {
            "extension": [
                {
                    "url": "http://example.org/ext",
                    "valueString": "test_value",
                    "valueInteger": 42,
                },
            ]
        }
        result = extension({}, [resource], "http://example.org/ext")
        node_data = result[0].data
        assert node_data.get("url") == "http://example.org/ext"
        assert node_data.get("valueString") == "test_value"
        assert node_data.get("valueInteger") == 42


class TestExtensionEdgeCases:
    """Edge case tests for extension() function."""

    def test_extension_non_dict_input(self) -> None:
        """Test extension() on non-dict input returns empty."""
        result = extension({}, ["string_value", 123, True])
        assert result == []

    def test_extension_non_dict_extensions_ignored(self) -> None:
        """Test that non-dict extension entries are ignored."""
        resource = {
            "extension": [
                {"url": "http://example.org/ext", "valueString": "valid"},
                "invalid_string",
                123,
                None,
            ]
        }
        result = extension({}, [resource])
        assert len(result) == 1  # Only the valid dict extension

    def test_extension_multiple_resources(self) -> None:
        """Test extension() across multiple resources."""
        resources = [
            {"extension": [{"url": "http://example.org/ext", "valueString": "r1"}]},
            {"extension": [{"url": "http://example.org/ext", "valueString": "r2"}]},
            {"extension": [{"url": "http://example.org/other", "valueString": "r3"}]},
        ]
        result = extension({}, resources, "http://example.org/ext")
        assert len(result) == 2

    def test_extension_missing_url_field(self) -> None:
        """Test extension entries without url field are handled."""
        resource = {
            "extension": [
                {"valueString": "no_url"},  # Missing url
                {"url": "http://example.org/ext", "valueString": "has_url"},
            ]
        }
        # With no URL filter, both should be returned (url check only matters when filtering)
        result_no_filter = extension({}, [resource])
        assert len(result_no_filter) == 2

        # With URL filter, only matching should be returned
        result_filtered = extension({}, [resource], "http://example.org/ext")
        assert len(result_filtered) == 1
