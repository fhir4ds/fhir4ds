"""
Unit tests for FHIRPath resolve() function.

Tests the resolve() function for resolving FHIR references including:
- Bundle-contained references (Patient/123 style)
- urn:uuid: references
- Missing references (returns empty)
- Non-Bundle resources
"""

from __future__ import annotations

import pytest

import fhir4ds.fhirpath as fhirpathpy


class TestResolveFunction:
    """Tests for the resolve() FHIRPath function."""

    def test_resolve_patient_reference_in_bundle(self):
        """Test resolving a Patient/123 style reference within a Bundle."""
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "patient-1",
                        "name": [{"family": "Smith", "given": ["John"]}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-1",
                        "status": "final",
                        "subject": {
                            "reference": "Patient/patient-1"
                        }
                    }
                }
            ]
        }

        # Resolve the subject reference
        result = fhirpathpy.evaluate(bundle, "Bundle.entry.resource.ofType(Observation).subject.resolve()")

        # Should return the Patient resource
        assert len(result) == 1
        assert result[0]["resourceType"] == "Patient"
        assert result[0]["id"] == "patient-1"
        assert result[0]["name"][0]["family"] == "Smith"

    def test_resolve_urn_uuid_reference(self):
        """Test resolving a urn:uuid: style reference within a Bundle."""
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "uuid-123-abc",
                        "name": [{"family": "Doe"}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-1",
                        "status": "final",
                        "subject": {
                            "reference": "urn:uuid:uuid-123-abc"
                        }
                    }
                }
            ]
        }

        result = fhirpathpy.evaluate(bundle, "Bundle.entry.resource.ofType(Observation).subject.resolve()")

        assert len(result) == 1
        assert result[0]["resourceType"] == "Patient"
        assert result[0]["id"] == "uuid-123-abc"

    def test_resolve_missing_reference_returns_empty(self):
        """Test that resolving a non-existent reference returns empty collection."""
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-1",
                        "status": "final",
                        "subject": {
                            "reference": "Patient/nonexistent"
                        }
                    }
                }
            ]
        }

        result = fhirpathpy.evaluate(bundle, "Bundle.entry.resource.ofType(Observation).subject.resolve()")

        # Should return empty collection
        assert result == []

    def test_resolve_reference_without_reference_field(self):
        """Test that a Reference without a 'reference' field returns empty."""
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-1",
                        "status": "final",
                        "subject": {
                            "display": "Some Patient Name"
                            # No 'reference' field
                        }
                    }
                }
            ]
        }

        result = fhirpathpy.evaluate(bundle, "Bundle.entry.resource.ofType(Observation).subject.resolve()")

        assert result == []

    def test_resolve_empty_collection(self):
        """Test resolve() on an empty collection."""
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": []
        }

        result = fhirpathpy.evaluate(bundle, "Bundle.entry.resource.ofType(Observation).subject.resolve()")

        assert result == []

    def test_resolve_on_non_bundle_returns_empty(self):
        """Test that resolve() on a non-Bundle resource returns empty."""
        observation = {
            "resourceType": "Observation",
            "id": "obs-1",
            "status": "final",
            "subject": {
                "reference": "Patient/patient-1"
            }
        }

        # Resolve won't work since there's no Bundle to search
        result = fhirpathpy.evaluate(observation, "Observation.subject.resolve()")

        assert result == []

    def test_resolve_multiple_references(self):
        """Test resolving multiple references in a single call."""
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "patient-1",
                        "name": [{"family": "Smith"}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "patient-2",
                        "name": [{"family": "Jones"}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-1",
                        "status": "final",
                        "subject": {"reference": "Patient/patient-1"}
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-2",
                        "status": "final",
                        "subject": {"reference": "Patient/patient-2"}
                    }
                }
            ]
        }

        # Resolve all subject references
        result = fhirpathpy.evaluate(
            bundle,
            "Bundle.entry.resource.ofType(Observation).subject.resolve()"
        )

        # Should return both patients
        assert len(result) == 2
        patient_ids = {r["id"] for r in result}
        assert patient_ids == {"patient-1", "patient-2"}

    def test_resolve_with_absolute_url(self):
        """Test resolving a reference with an absolute URL."""
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "patient-1",
                        "name": [{"family": "Smith"}]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-1",
                        "status": "final",
                        "subject": {
                            "reference": "http://example.org/fhir/Patient/patient-1"
                        }
                    }
                }
            ]
        }

        result = fhirpathpy.evaluate(bundle, "Bundle.entry.resource.ofType(Observation).subject.resolve()")

        assert len(result) == 1
        assert result[0]["resourceType"] == "Patient"
        assert result[0]["id"] == "patient-1"

    def test_resolve_chained_with_other_functions(self):
        """Test resolve() chained with other FHIRPath functions."""
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "patient-1",
                        "name": [{"family": "Smith", "given": ["John"]}],
                        "gender": "male"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-1",
                        "status": "final",
                        "subject": {"reference": "Patient/patient-1"}
                    }
                }
            ]
        }

        # Resolve and then access a property
        result = fhirpathpy.evaluate(
            bundle,
            "Bundle.entry.resource.ofType(Observation).subject.resolve().gender"
        )

        assert result == ["male"]

    def test_resolve_non_reference_object_returns_empty(self):
        """Test that resolve() on non-Reference objects returns empty."""
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "patient-1",
                        "name": [{"family": "Smith"}],
                        "gender": "male"
                    }
                }
            ]
        }

        # gender is a string, not a Reference
        result = fhirpathpy.evaluate(bundle, "Bundle.entry.resource.ofType(Patient).gender.resolve()")

        assert result == []
