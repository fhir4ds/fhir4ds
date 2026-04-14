"""Tests for the evaluator module."""

import pytest
from unittest.mock import Mock

from ..evaluator import EvaluationContext, PatientContext, PopulationContext


def test_evaluation_context_abstract():
    """Test that EvaluationContext is abstract and cannot be instantiated directly."""
    with pytest.raises(TypeError):
        EvaluationContext()


def test_patient_context_creation():
    """Test PatientContext initialization."""
    mock_con = Mock()
    patient_id = "patient-123"

    context = PatientContext(mock_con, patient_id)

    assert context.con == mock_con
    assert context.patient_id == patient_id
    assert context.resources_table == "resources"


def test_patient_context_get_patient_id():
    """Test PatientContext.get_patient_id()."""
    mock_con = Mock()
    patient_id = "patient-123"

    context = PatientContext(mock_con, patient_id)

    assert context.get_patient_id() == patient_id


def test_patient_context_get_context_type():
    """Test PatientContext.get_context_type()."""
    mock_con = Mock()

    context = PatientContext(mock_con, "patient-123")

    assert context.get_context_type() == "Patient"


def test_patient_context_evaluate_expression_not_implemented():
    """Test that PatientContext.evaluate_expression() raises NotImplementedError."""
    mock_con = Mock()

    context = PatientContext(mock_con, "patient-123")

    with pytest.raises(NotImplementedError, match="FHIRPath evaluation not yet implemented"):
        context.evaluate_expression("Patient.name.first()")


def test_population_context_creation():
    """Test PopulationContext initialization."""
    mock_con = Mock()

    context = PopulationContext(mock_con)

    assert context.con == mock_con
    assert context.resources_table == "resources"


def test_population_context_get_patient_id():
    """Test PopulationContext.get_patient_id()."""
    mock_con = Mock()

    context = PopulationContext(mock_con)

    assert context.get_patient_id() is None


def test_population_context_get_context_type():
    """Test PopulationContext.get_context_type()."""
    mock_con = Mock()

    context = PopulationContext(mock_con)

    assert context.get_context_type() == "Population"


def test_population_context_evaluate_expression_not_implemented():
    """Test that PopulationContext.evaluate_expression() raises NotImplementedError."""
    mock_con = Mock()

    context = PopulationContext(mock_con)

    with pytest.raises(NotImplementedError, match="Population-level evaluation not yet implemented"):
        context.evaluate_expression("Count(*)")


def test_patient_context_custom_resources_table():
    """Test PatientContext with custom resources table name."""
    mock_con = Mock()
    patient_id = "patient-123"
    custom_table = "fhir_resources"

    context = PatientContext(mock_con, patient_id, custom_table)

    assert context.resources_table == custom_table