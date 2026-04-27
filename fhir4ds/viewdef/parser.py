"""
ViewDefinition parser for SQL-on-FHIR v2.

Parses JSON ViewDefinitions into Python dataclasses for SQL generation.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
import json
import logging

from .types import Column, Select, Constant, Join, JoinType, ViewDefinition
from .errors import ParseError, ValidationError

_logger = logging.getLogger(__name__)


def _parse_column(col_data: Dict[str, Any]) -> Column:
    """Parse a column definition from JSON dict.

    Args:
        col_data: Dictionary with column properties

    Returns:
        Column dataclass instance
    """
    path = col_data.get('path', '')
    name = col_data.get('name', '')

    if not path:
        raise ParseError(f"Column missing required 'path' field: {col_data}")
    if not name:
        raise ParseError(f"Column missing required 'name' field: {col_data}")

    return Column(
        path=path,
        name=name,
        type=col_data.get('type'),
        collection=col_data.get('collection', False),
        description=col_data.get('description')
    )


def _parse_where(where_data: List[Any]) -> List[Dict[str, str]]:
    """Parse where conditions from JSON.

    Accepts both spec-compliant dict format ({"path": "expr"}) and
    convenience string format ("expr") which is wrapped automatically.

    Args:
        where_data: List of where condition objects or strings

    Returns:
        List of condition dictionaries with 'path' keys

    Raises:
        ParseError: If a where condition has an unsupported type
    """
    result = []
    for w in where_data:
        if isinstance(w, dict):
            result.append(dict(w))
        elif isinstance(w, str):
            result.append({"path": w})
        else:
            raise ParseError(
                f"Where condition must be a string or object, got {type(w).__name__}: {w!r}"
            )
    return result


def _parse_select(select_data: Dict[str, Any]) -> Select:
    """Parse a select structure from JSON dict.

    Args:
        select_data: Dictionary with select properties

    Returns:
        Select dataclass instance
    """
    # Parse columns
    columns = []
    for col in select_data.get('column', []):
        columns.append(_parse_column(col))

    # Parse nested selects
    nested_selects = []
    for sel in select_data.get('select', []):
        nested_selects.append(_parse_select(sel))

    # Parse unionAll
    union_all = []
    for u in select_data.get('unionAll', []):
        union_all.append(_parse_select(u))

    # Parse where conditions
    where = _parse_where(select_data.get('where', []))

    # Parse repeat (list of FHIRPath expressions for recursive traversal)
    repeat = select_data.get('repeat')
    if repeat is not None:
        if isinstance(repeat, str):
            repeat = [repeat]
        elif not isinstance(repeat, list):
            repeat = list(repeat)

    return Select(
        column=columns,
        select=nested_selects,
        forEach=select_data.get('forEach'),
        forEachOrNull=select_data.get('forEachOrNull'),
        unionAll=union_all,
        where=where,
        repeat=repeat,
    )


def _parse_constant(const_data: Dict[str, Any]) -> Constant:
    """Parse a constant definition from JSON dict.

    Handles various constant value types per SQL-on-FHIR v2 spec:
    - valueString, valueCode, valueInteger, valueBoolean, valueDecimal
    - valueDate, valueDateTime, valueTime, valueInstant
    - valueUri, valueUrl, valueUuid, valueOid, valueBase64Binary, valueId
    - valuePositiveInt, valueUnsignedInt
    - valueCoding, valueCodeableConcept

    Args:
        const_data: Dictionary with constant properties

    Returns:
        Constant dataclass instance with value and value_type set
    """
    name = const_data.get('name', '')
    if not name:
        raise ParseError(f"Constant missing required 'name' field: {const_data}")

    # Map value keys to their type names
    value_type_map = {
        'valueString': 'string',
        'valueCode': 'code',
        'valueInteger': 'integer',
        'valueBoolean': 'boolean',
        'valueDecimal': 'decimal',
        'valueDate': 'date',
        'valueDateTime': 'dateTime',
        'valueTime': 'time',
        'valueInstant': 'instant',
        'valueUri': 'uri',
        'valueUrl': 'url',
        'valueUuid': 'uuid',
        'valueOid': 'oid',
        'valueBase64Binary': 'base64Binary',
        'valueId': 'id',
        'valuePositiveInt': 'positiveInt',
        'valueUnsignedInt': 'unsignedInt',
        'valueCoding': 'Coding',
        'valueCodeableConcept': 'CodeableConcept',
    }

    # Try various value keys
    value = None
    value_type = None

    for key, vtype in value_type_map.items():
        if key in const_data:
            value = const_data[key]
            value_type = vtype
            break

    # Fallback: check for any key starting with 'value'
    if value is None:
        for key, val in const_data.items():
            if key.startswith('value') and key != 'value_type':
                value = val
                # Try to extract type from key name
                type_name = key[5:]  # Remove 'value' prefix
                if type_name:
                    value_type = type_name
                break

    if value is None and value_type is None:
        raise ParseError(
            f"Constant '{name}' has no value. "
            f"A constant must include a typed value property (e.g., valueString, valueInteger)."
        )

    return Constant(name=name, value=value, value_type=value_type)


def _parse_join(join_data: Dict[str, Any]) -> Join:
    """Parse a join definition from JSON dict.

    Args:
        join_data: Dictionary with join properties

    Returns:
        Join dataclass instance
    """
    name = join_data.get('name', '')
    resource = join_data.get('resource', '')

    if not name:
        raise ParseError(f"Join missing required 'name' field: {join_data}")
    if not resource:
        raise ParseError(f"Join missing required 'resource' field: {join_data}")

    # Parse on conditions
    on_conditions = []
    for on_item in join_data.get('on', []):
        if isinstance(on_item, dict):
            on_conditions.append(dict(on_item))

    return Join(
        name=name,
        resource=resource,
        on=on_conditions,
        type=join_data.get('type', 'inner')
    )


def parse_view_definition(json_str_or_dict) -> ViewDefinition:
    """Parse a JSON string or dict into a ViewDefinition dataclass.

    Args:
        json_str_or_dict: JSON string or dict containing a ViewDefinition

    Returns:
        ViewDefinition dataclass instance

    Raises:
        ParseError: If JSON is invalid or required fields are missing
        TypeError: If the input type is not supported
    """
    if isinstance(json_str_or_dict, dict):
        data = json_str_or_dict
    elif isinstance(json_str_or_dict, str):
        try:
            data = json.loads(json_str_or_dict)
        except json.JSONDecodeError as e:
            raise ParseError(f"Invalid JSON: {e}")
    else:
        raise TypeError(
            f"Expected str or dict, got {type(json_str_or_dict).__name__}"
        )

    if not isinstance(data, dict):
        raise ParseError("ViewDefinition must be a JSON object")

    # Parse required fields
    resource = data.get('resource', '')
    if not resource:
        raise ParseError("ViewDefinition missing required 'resource' field")

    # Validate resource type(s) — accept string or list of strings
    if isinstance(resource, list):
        if not all(isinstance(r, str) for r in resource):
            raise ParseError("'resource' list must contain only strings")
        if len(resource) == 0:
            raise ParseError("'resource' list must not be empty")
    elif not isinstance(resource, str):
        raise ParseError(
            f"'resource' must be a string or list of strings, got {type(resource).__name__}"
        )

    # Warn on unrecognized resource type names (non-blocking)
    _KNOWN_FHIR_RESOURCES = {
        "Account", "ActivityDefinition", "ActorDefinition", "AdministrableProductDefinition",
        "AdverseEvent", "AllergyIntolerance", "Appointment", "AppointmentResponse",
        "ArtifactAssessment", "AuditEvent", "Basic", "Binary", "BiologicallyDerivedProduct",
        "BiologicallyDerivedProductDispense", "BodyStructure", "Bundle",
        "CapabilityStatement", "CarePlan", "CareTeam", "ChargeItem",
        "ChargeItemDefinition", "Citation", "Claim", "ClaimResponse",
        "ClinicalImpression", "ClinicalUseDefinition", "CodeSystem", "Communication",
        "CommunicationRequest", "CompartmentDefinition", "Composition", "ConceptMap",
        "Condition", "ConditionDefinition", "Consent", "Contract", "Coverage",
        "CoverageEligibilityRequest", "CoverageEligibilityResponse", "DetectedIssue",
        "Device", "DeviceAssociation", "DeviceDefinition", "DeviceDispense",
        "DeviceMetric", "DeviceRequest", "DeviceUsage", "DiagnosticReport",
        "DocumentReference", "Encounter", "EncounterHistory", "Endpoint",
        "EnrollmentRequest", "EnrollmentResponse", "EpisodeOfCare",
        "EventDefinition", "Evidence", "EvidenceReport", "EvidenceVariable",
        "ExampleScenario", "ExplanationOfBenefit", "FamilyMemberHistory", "Flag",
        "FormularyItem", "GenomicStudy", "Goal", "GraphDefinition", "Group",
        "GuidanceResponse", "HealthcareService", "ImagingSelection", "ImagingStudy",
        "Immunization", "ImmunizationEvaluation", "ImmunizationRecommendation",
        "ImplementationGuide", "Ingredient", "InsurancePlan", "InventoryItem",
        "InventoryReport", "Invoice", "Library", "Linkage", "List", "Location",
        "ManufacturedItemDefinition", "Measure", "MeasureReport", "Medication",
        "MedicationAdministration", "MedicationDispense", "MedicationKnowledge",
        "MedicationRequest", "MedicationStatement", "MedicinalProductDefinition",
        "MessageDefinition", "MessageHeader", "MolecularSequence", "NamingSystem",
        "NutritionIntake", "NutritionOrder", "NutritionProduct", "Observation",
        "ObservationDefinition", "OperationDefinition", "OperationOutcome",
        "Organization", "OrganizationAffiliation", "PackagedProductDefinition",
        "Parameters", "Patient", "PaymentNotice", "PaymentReconciliation",
        "Permission", "Person", "PlanDefinition", "Practitioner",
        "PractitionerRole", "Procedure", "Provenance", "Questionnaire",
        "QuestionnaireResponse", "RegulatedAuthorization", "RelatedPerson",
        "RequestOrchestration", "Requirements", "ResearchStudy", "ResearchSubject",
        "RiskAssessment", "Schedule", "SearchParameter", "ServiceRequest", "Slot",
        "Specimen", "SpecimenDefinition", "StructureDefinition", "StructureMap",
        "Subscription", "SubscriptionStatus", "SubscriptionTopic", "Substance",
        "SubstanceDefinition", "SubstanceNucleicAcid", "SubstancePolymer",
        "SubstanceProtein", "SubstanceReferenceInformation", "SubstanceSourceMaterial",
        "SupplyDelivery", "SupplyRequest", "Task", "TerminologyCapabilities",
        "TestPlan", "TestReport", "TestScript", "Transport", "ValueSet",
        "VerificationResult", "VisionPrescription",
    }
    import logging as _logging
    _vd_logger = _logging.getLogger(__name__)
    _resource_names = [resource] if isinstance(resource, str) else resource
    for _rn in _resource_names:
        if _rn not in _KNOWN_FHIR_RESOURCES:
            _vd_logger.warning(
                "ViewDefinition resource type '%s' is not a recognized FHIR resource type. "
                "Possible typo? Known types include Patient, Observation, Condition, etc.", _rn
            )

    # Parse select structures
    selects = []
    select_data = data.get('select', [])
    if not select_data:
        raise ParseError("ViewDefinition missing required 'select' field")

    for sel in select_data:
        selects.append(_parse_select(sel))

    # Parse constants (spec uses 'constant' singular, also accept 'constants')
    constants = []
    const_raw = data.get('constant', data.get('constants', []))
    if isinstance(const_raw, list):
        for const in const_raw:
            if isinstance(const, dict):
                constants.append(_parse_constant(const))
            else:
                raise ParseError(
                    f"Each constant must be a JSON object, got {type(const).__name__}: {const!r}"
                )
    elif const_raw:
        raise ParseError(
            f"'constant' must be a JSON array, got {type(const_raw).__name__}"
        )

    # Parse joins
    joins = []
    for j in data.get('joins', []):
        joins.append(_parse_join(j))

    # Parse top-level where conditions
    where = _parse_where(data.get('where', []))

    return ViewDefinition(
        resource=resource,
        select=selects,
        name=data.get('name'),
        description=data.get('description'),
        constants=constants,
        joins=joins,
        where=where
    )


def validate_view_definition(vd: ViewDefinition) -> List[str]:
    """Validate a ViewDefinition per SQL-on-FHIR spec (permissive mode).

    This function returns warnings rather than raising exceptions,
    allowing for permissive parsing where minor issues are flagged
    but don't prevent processing.

    Args:
        vd: ViewDefinition to validate

    Returns:
        List of warning messages (empty if valid)
    """
    warnings = []

    # Check required fields
    if not vd.resource:
        warnings.append("Missing required field: resource")

    if not vd.select:
        warnings.append("Missing required field: select")

    # Check column name uniqueness at top level
    all_names = collect_column_names(vd.select)
    seen = set()
    duplicates = set()
    for name in all_names:
        if name in seen:
            duplicates.add(name)
        seen.add(name)

    if duplicates:
        warnings.append(f"Duplicate column names: {sorted(duplicates)}")

    # Validate nested structures
    warnings.extend(_validate_selects(vd.select, "select"))

    # Validate constants
    const_names = set()
    for const in vd.constants:
        if const.name in const_names:
            warnings.append(f"Duplicate constant name: {const.name}")
        const_names.add(const.name)

        if const.value is None:
            warnings.append(f"Constant '{const.name}' has no value")

    # Validate joins
    join_names = set()
    for join in vd.joins:
        if join.name in join_names:
            warnings.append(f"Duplicate join name: {join.name}")
        join_names.add(join.name)

        if not join.on:
            warnings.append(f"Join '{join.name}' has no 'on' conditions")

        if join.type not in (JoinType.INNER, JoinType.LEFT, JoinType.RIGHT, JoinType.FULL):
            warnings.append(f"Join '{join.name}' has invalid type: {join.type}")

    return warnings


def _validate_selects(selects: List[Select], path: str) -> List[str]:
    """Recursively validate select structures.

    Args:
        selects: List of Select structures to validate
        path: Current path for error messages

    Returns:
        List of warning messages
    """
    warnings = []

    for i, sel in enumerate(selects):
        current_path = f"{path}[{i}]"

        # Check for both forEach and forEachOrNull (mutually exclusive per spec)
        if sel.forEach and sel.forEachOrNull:
            raise ValidationError(
                f"{current_path}: Both forEach and forEachOrNull specified "
                "(they are mutually exclusive per the SQL-on-FHIR v2 specification)"
            )

        # Check for empty select (no columns, no nested selects, no unionAll)
        if (not sel.column and not sel.select and not sel.unionAll and
            not sel.forEach and not sel.forEachOrNull):
            warnings.append(f"{current_path}: Empty select structure")

        # Validate columns
        for j, col in enumerate(sel.column):
            col_path = f"{current_path}.column[{j}]"
            if not col.path:
                warnings.append(f"{col_path}: Missing 'path'")
            if not col.name:
                warnings.append(f"{col_path}: Missing 'name'")

        # Recursively validate nested selects
        if sel.select:
            warnings.extend(_validate_selects(sel.select, f"{current_path}.select"))

        # Recursively validate unionAll
        if sel.unionAll:
            warnings.extend(_validate_selects(sel.unionAll, f"{current_path}.unionAll"))

    return warnings


def collect_column_names(select: List[Select]) -> List[str]:
    """Collect all column names from a list of Select structures.

    Recursively traverses the select structure to find all column names,
    including those in nested selects and unionAll branches.

    Args:
        select: List of Select structures to process

    Returns:
        List of all column names found (may include duplicates)
    """
    names = []

    for sel in select:
        # Add column names from this select
        for col in sel.column:
            names.append(col.name)

        # Recursively collect from nested selects
        names.extend(collect_column_names(sel.select))

        # Recursively collect from unionAll branches
        names.extend(collect_column_names(sel.unionAll))

    return names


# Convenience function to load from file
def load_view_definition(file_path: str) -> ViewDefinition:
    """Load a ViewDefinition from a JSON file.

    Args:
        file_path: Path to JSON file containing a ViewDefinition

    Returns:
        ViewDefinition dataclass instance

    Raises:
        FileNotFoundError: If file doesn't exist
        ParseError: If JSON is invalid or required fields are missing
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return parse_view_definition(f.read())
