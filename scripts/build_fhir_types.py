#!/usr/bin/env python3
"""
Build script to generate FHIR type data for type checking.

This script generates optimized Python data structures containing:
- FHIR type hierarchy (primitives, complex types, resources)
- Choice type mappings (e.g., Observation.value[x] -> valueQuantity, valueString, etc.)
- Type aliases (URI to name mapping)

Run this script during build to generate fhir_types_generated.py
"""

import json
import os
import sys
from pathlib import Path
from typing import Any


# FHIR R4 Primitives
FHIR_PRIMITIVES = {
    "boolean": {"parent": None, "kind": "primitive", "python_type": "bool"},
    "integer": {"parent": None, "kind": "primitive", "python_type": "int"},
    "decimal": {"parent": None, "kind": "primitive", "python_type": "float"},
    "string": {"parent": None, "kind": "primitive", "python_type": "str"},
    "date": {"parent": None, "kind": "primitive", "python_type": "str"},
    "dateTime": {"parent": None, "kind": "primitive", "python_type": "str"},
    "time": {"parent": None, "kind": "primitive", "python_type": "str"},
    "uri": {"parent": None, "kind": "primitive", "python_type": "str"},
    "url": {"parent": "uri", "kind": "primitive", "python_type": "str"},
    "canonical": {"parent": "uri", "kind": "primitive", "python_type": "str"},
    "code": {"parent": "string", "kind": "primitive", "python_type": "str"},
    "id": {"parent": "string", "kind": "primitive", "python_type": "str"},
    "markdown": {"parent": "string", "kind": "primitive", "python_type": "str"},
    "unsignedInt": {"parent": "integer", "kind": "primitive", "python_type": "int"},
    "positiveInt": {"parent": "integer", "kind": "primitive", "python_type": "int"},
    "uuid": {"parent": "uri", "kind": "primitive", "python_type": "str"},
    "oid": {"parent": "uri", "kind": "primitive", "python_type": "str"},
    "instant": {"parent": "dateTime", "kind": "primitive", "python_type": "str"},
    "base64Binary": {"parent": None, "kind": "primitive", "python_type": "str"},
}

# FHIR R4 Complex Types (DataTypes)
FHIR_DATATYPES = {
    "Quantity": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["value", "comparator", "unit", "system", "code"],
        "identifying_fields": ["value", "unit"],
    },
    "Period": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["start", "end"],
        "identifying_fields": ["start", "end"],
    },
    "Coding": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["system", "version", "code", "display", "userSelected"],
        "identifying_fields": ["system", "code"],
    },
    "CodeableConcept": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["coding", "text"],
        "identifying_fields": ["coding"],
    },
    "Reference": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["reference", "type", "identifier", "display"],
        "identifying_fields": ["reference"],
    },
    "Identifier": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["use", "type", "system", "value", "period", "assigner"],
        "identifying_fields": ["system", "value"],
    },
    "HumanName": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["use", "text", "family", "given", "prefix", "suffix"],
        "identifying_fields": ["family", "given"],
    },
    "Address": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["use", "type", "text", "line", "city", "district", "state", "postalCode", "country", "period"],
        "identifying_fields": ["line", "city"],
    },
    "ContactPoint": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["system", "value", "use", "rank", "period"],
        "identifying_fields": ["system", "value"],
    },
    "Attachment": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["contentType", "language", "data", "url", "size", "hash", "title", "creation"],
        "identifying_fields": ["contentType"],
    },
    "Ratio": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["numerator", "denominator"],
        "identifying_fields": ["numerator", "denominator"],
    },
    "Range": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["low", "high"],
        "identifying_fields": ["low", "high"],
    },
    "SampledData": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["origin", "period", "factor", "lowerLimit", "upperLimit", "dimensions", "data"],
        "identifying_fields": ["origin", "data"],
    },
    "Duration": {
        "parent": "Quantity",
        "kind": "datatype",
        "elements": ["value", "comparator", "unit", "system", "code"],
        "identifying_fields": ["value", "unit"],
    },
    "Age": {
        "parent": "Quantity",
        "kind": "datatype",
        "elements": ["value", "comparator", "unit", "system", "code"],
        "identifying_fields": ["value", "unit"],
    },
    "Distance": {
        "parent": "Quantity",
        "kind": "datatype",
        "elements": ["value", "comparator", "unit", "system", "code"],
        "identifying_fields": ["value", "unit"],
    },
    "Count": {
        "parent": "Quantity",
        "kind": "datatype",
        "elements": ["value", "comparator", "unit", "system", "code"],
        "identifying_fields": ["value", "unit"],
    },
    "Money": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["value", "currency"],
        "identifying_fields": ["value", "currency"],
    },
    "Annotation": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["authorReference", "authorString", "time", "text"],
        "identifying_fields": ["text"],
    },
    "Signature": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["type", "when", "who", "onBehalfOf", "targetFormat", "sigFormat", "data"],
        "identifying_fields": ["type", "who"],
    },
    "Timing": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["event", "repeat", "code"],
        "identifying_fields": ["event", "repeat"],
    },
    "Dosage": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["sequence", "text", "additionalInstruction", "patientInstruction", "timing", "asNeededBoolean", "asNeededCodeableConcept", "site", "route", "method", "doseAndRate", "maxDosePerPeriod", "maxDosePerAdministration", "maxDosePerLifetime", "route", "method"],
        "identifying_fields": ["doseAndRate"],
    },
    "Element": {
        "parent": None,
        "kind": "datatype",
        "elements": ["id", "extension"],
        "identifying_fields": [],
    },
    "Extension": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["url", "value"],
        "identifying_fields": ["url"],
    },
    "Narrative": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["status", "div"],
        "identifying_fields": ["div"],
    },
    "Meta": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["versionId", "lastUpdated", "source", "profile", "security", "tag"],
        "identifying_fields": ["versionId", "lastUpdated"],
    },
    "BackboneElement": {
        "parent": "Element",
        "kind": "datatype",
        "elements": ["modifierExtension"],
        "identifying_fields": [],
    },
}

# FHIR R4 Resources
FHIR_RESOURCES = {
    "Resource": {
        "parent": None,
        "kind": "resource",
        "elements": ["id", "meta", "implicitRules", "language"],
    },
    "DomainResource": {
        "parent": "Resource",
        "kind": "resource",
        "elements": ["text", "contained", "extension", "modifierExtension"],
    },
    "Patient": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "active", "name", "telecom", "gender", "birthDate", "deceasedBoolean", "deceasedDateTime", "address", "maritalStatus", "multipleBirthBoolean", "multipleBirthInteger", "photo", "contact", "communication", "generalPractitioner", "managingOrganization", "link"],
    },
    "Observation": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "basedOn", "partOf", "status", "category", "code", "subject", "focus", "encounter", "effectiveDateTime", "effectivePeriod", "effectiveTiming", "effectiveInstant", "issued", "performer", "valueQuantity", "valueCodeableConcept", "valueString", "valueBoolean", "valueInteger", "valueRange", "valueRatio", "valueSampledData", "valueTime", "valueDateTime", "valuePeriod", "dataAbsentReason", "interpretation", "note", "bodySite", "method", "specimen", "device", "referenceRange", "hasMember", "derivedFrom", "component"],
    },
    "Condition": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "clinicalStatus", "verificationStatus", "category", "severity", "code", "bodySite", "subject", "encounter", "onsetDateTime", "onsetAge", "onsetPeriod", "onsetRange", "onsetString", "abatementDateTime", "abatementAge", "abatementPeriod", "abatementRange", "abatementString", "recordedDate", "recorder", "asserter", "stage", "evidence", "note"],
    },
    "Encounter": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "status", "statusHistory", "class", "classHistory", "type", "serviceType", "priority", "subject", "episodeOfCare", "basedOn", "participant", "appointment", "period", "length", "reasonCode", "reasonReference", "diagnosis", "account", "hospitalization", "location", "serviceProvider", "partOf"],
    },
    "Practitioner": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "active", "name", "telecom", "address", "gender", "birthDate", "photo", "qualification", "communication"],
    },
    "Organization": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "active", "type", "name", "alias", "telecom", "address", "partOf", "contact", "endpoint"],
    },
    "Location": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "status", "operationalStatus", "name", "alias", "description", "mode", "type", "telecom", "address", "physicalType", "position", "managingOrganization", "partOf", "hoursOfOperation", "availabilityExceptions", "endpoint"],
    },
    "Medication": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "code", "status", "manufacturer", "form", "amount", "ingredient", "batch"],
    },
    "MedicationRequest": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "status", "statusReason", "intent", "category", "priority", "doNotPerform", "reportedBoolean", "reportedReference", "medicationCodeableConcept", "medicationReference", "subject", "encounter", "supportingInformation", "authoredOn", "requester", "performer", "performerType", "recorder", "reasonCode", "reasonReference", "instantiatesCanonical", "instantiatesUri", "basedOn", "groupIdentifier", "courseOfTherapyType", "insurance", "note", "dosageInstruction", "dispenseRequest", "substitution", "priorPrescription", "detectedIssue", "eventHistory"],
    },
    "Procedure": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "instantiatesCanonical", "instantiatesUri", "basedOn", "partOf", "status", "statusReason", "category", "code", "subject", "encounter", "recorder", "asserter", "performedDateTime", "performedPeriod", "performedString", "performedAge", "performedRange", "performer", "location", "reasonCode", "reasonReference", "bodySite", "outcome", "report", "complication", "complicationDetail", "followUp", "note", "focalDevice", "usedReference", "usedCode"],
    },
    "DiagnosticReport": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "basedOn", "status", "category", "code", "subject", "encounter", "effectiveDateTime", "effectivePeriod", "issued", "performer", "resultsInterpreter", "specimen", "result", "imagingStudy", "media", "conclusion", "conclusionCode", "presentedForm"],
    },
    "AllergyIntolerance": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "clinicalStatus", "verificationStatus", "type", "category", "criticality", "code", "patient", "encounter", "onsetDateTime", "onsetAge", "onsetPeriod", "onsetRange", "onsetString", "recordedDate", "recorder", "asserter", "lastOccurrence", "note", "reaction"],
    },
    "Immunization": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "status", "statusReason", "vaccineCode", "patient", "encounter", "occurrenceDateTime", "occurrenceString", "recorded", "primarySource", "reportOrigin", "location", "manufacturer", "lotNumber", "expirationDate", "site", "route", "doseQuantity", "performer", "note", "reasonCode", "reasonReference", "isSubpotent", "subpotentReason", "education", "programEligibility", "fundingSource", "reaction"],
    },
    "CarePlan": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "instantiatesCanonical", "instantiatesUri", "basedOn", "replaces", "partOf", "status", "intent", "category", "title", "description", "subject", "encounter", "period", "created", "author", "contributor", "careTeam", "addresses", "supportingInfo", "goal", "activity", "note"],
    },
    "DocumentReference": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "status", "docStatus", "type", "category", "subject", "date", "author", "authenticator", "custodian", "relatesTo", "description", "securityLabel", "content", "context"],
    },
    "Specimen": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "accessionIdentifier", "status", "type", "subject", "receivedTime", "parent", "request", "collection", "processing", "container", "condition", "note"],
    },
    "ServiceRequest": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "instantiatesCanonical", "instantiatesUri", "basedOn", "replaces", "requisition", "status", "intent", "category", "priority", "doNotPerform", "code", "orderDetail", "quantityQuantity", "quantityRatio", "quantityRange", "subject", "encounter", "occurrenceDateTime", "occurrencePeriod", "occurrenceTiming", "asNeededBoolean", "asNeededCodeableConcept", "authoredOn", "requester", "performerType", "performer", "locationCode", "locationReference", "reasonCode", "reasonReference", "insurance", "supportingInfo", "specimen", "bodySite", "note", "patientInstruction", "relevantHistory"],
    },
    "Bundle": {
        "parent": "Resource",
        "kind": "resource",
        "elements": ["identifier", "type", "timestamp", "total", "link", "entry", "signature"],
    },
    "OperationOutcome": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["issue"],
    },
    "Composition": {
        "parent": "DomainResource",
        "kind": "resource",
        "elements": ["identifier", "status", "type", "category", "subject", "encounter", "date", "author", "title", "confidentiality", "attester", "custodian", "relatesTo", "event", "section"],
    },
}

# Choice Type Mappings (polymorphic fields)
# Format: "ResourceType.field" -> ["concreteField1", "concreteField2", ...]
CHOICE_TYPES = {
    # Observation choice types
    "Observation.value": [
        "valueQuantity",
        "valueCodeableConcept",
        "valueString",
        "valueBoolean",
        "valueInteger",
        "valueRange",
        "valueRatio",
        "valueSampledData",
        "valueTime",
        "valueDateTime",
        "valuePeriod",
    ],
    "Observation.effective": [
        "effectiveDateTime",
        "effectivePeriod",
        "effectiveTiming",
        "effectiveInstant",
    ],
    "Observation.subject": ["subjectReference"],
    "Observation.focus": ["focusReference"],
    "Observation.encounter": ["encounterReference"],
    "Observation.performer": ["performerReference"],
    "Observation.specimen": ["specimenReference"],
    "Observation.device": ["deviceReference"],
    "Observation.hasMember": ["hasMemberReference"],
    "Observation.derivedFrom": ["derivedFromReference"],

    # Patient choice types
    "Patient.deceased": ["deceasedBoolean", "deceasedDateTime"],
    "Patient.multipleBirth": ["multipleBirthBoolean", "multipleBirthInteger"],

    # Condition choice types
    "Condition.onset": [
        "onsetDateTime",
        "onsetAge",
        "onsetPeriod",
        "onsetRange",
        "onsetString",
    ],
    "Condition.abatement": [
        "abatementDateTime",
        "abatementAge",
        "abatementPeriod",
        "abatementRange",
        "abatementString",
    ],

    # Procedure choice types
    "Procedure.performed": [
        "performedDateTime",
        "performedPeriod",
        "performedString",
        "performedAge",
        "performedRange",
    ],

    # DiagnosticReport choice types
    "DiagnosticReport.effective": [
        "effectiveDateTime",
        "effectivePeriod",
    ],

    # MedicationRequest choice types
    "MedicationRequest.reported": ["reportedBoolean", "reportedReference"],
    "MedicationRequest.medication": ["medicationCodeableConcept", "medicationReference"],

    # ServiceRequest choice types
    "ServiceRequest.occurrence": [
        "occurrenceDateTime",
        "occurrencePeriod",
        "occurrenceTiming",
    ],
    "ServiceRequest.asNeeded": ["asNeededBoolean", "asNeededCodeableConcept"],
    "ServiceRequest.quantity": ["quantityQuantity", "quantityRatio", "quantityRange"],

    # AllergyIntolerance choice types
    "AllergyIntolerance.onset": [
        "onsetDateTime",
        "onsetAge",
        "onsetPeriod",
        "onsetRange",
        "onsetString",
    ],

    # Immunization choice types
    "Immunization.occurrence": ["occurrenceDateTime", "occurrenceString"],

    # Timing repeat bounds
    "Timing.repeat.bounds": ["boundsDuration", "boundsRange", "boundsPeriod"],

    # Dosage doseAndRate
    "Dosage.doseAndRate.dose": ["doseQuantity", "doseRange"],
    "Dosage.doseAndRate.rate": ["rateRatio", "rateRange", "rateQuantity"],

    # Annotation author
    "Annotation.author": ["authorReference", "authorString"],

    # Reference variants (common pattern)
    "Resource.contained": ["containedResource"],

    # Extension value
    "Extension.value": [
        "valueBase64Binary",
        "valueBoolean",
        "valueCanonical",
        "valueCode",
        "valueDate",
        "valueDateTime",
        "valueDecimal",
        "valueId",
        "valueInstant",
        "valueInteger",
        "valueMarkdown",
        "valueOid",
        "valuePositiveInt",
        "valueString",
        "valueTime",
        "valueUnsignedInt",
        "valueUri",
        "valueUrl",
        "valueUuid",
        "valueAddress",
        "valueAge",
        "valueAnnotation",
        "valueAttachment",
        "valueCodeableConcept",
        "valueCoding",
        "valueContactPoint",
        "valueCount",
        "valueDistance",
        "valueDuration",
        "valueHumanName",
        "valueIdentifier",
        "valueMoney",
        "valuePeriod",
        "valueQuantity",
        "valueRange",
        "valueRatio",
        "valueReference",
        "valueSampledData",
        "valueSignature",
        "valueTiming",
        "valueContactDetail",
        "valueContributor",
        "valueDataRequirement",
        "valueExpression",
        "valueParameterDefinition",
        "valueRelatedArtifact",
        "valueTriggerDefinition",
        "valueUsageContext",
        "valueDosage",
        "valueMeta",
    ],
}

# Type URI to name mapping (for resolving type references)
TYPE_ALIASES = {
    # Primitive types
    "http://hl7.org/fhirpath/System.Boolean": "boolean",
    "http://hl7.org/fhirpath/System.Integer": "integer",
    "http://hl7.org/fhirpath/System.Decimal": "decimal",
    "http://hl7.org/fhirpath/System.String": "string",
    "http://hl7.org/fhirpath/System.Date": "date",
    "http://hl7.org/fhirpath/System.DateTime": "dateTime",
    "http://hl7.org/fhirpath/System.Time": "time",
    "http://hl7.org/fhirpath/System.Quantity": "Quantity",

    # FHIR R4 StructureDefinitions
    "http://hl7.org/fhir/StructureDefinition/boolean": "boolean",
    "http://hl7.org/fhir/StructureDefinition/integer": "integer",
    "http://hl7.org/fhir/StructureDefinition/decimal": "decimal",
    "http://hl7.org/fhir/StructureDefinition/string": "string",
    "http://hl7.org/fhir/StructureDefinition/date": "date",
    "http://hl7.org/fhir/StructureDefinition/dateTime": "dateTime",
    "http://hl7.org/fhir/StructureDefinition/time": "time",
    "http://hl7.org/fhir/StructureDefinition/uri": "uri",
    "http://hl7.org/fhir/StructureDefinition/url": "url",
    "http://hl7.org/fhir/StructureDefinition/canonical": "canonical",
    "http://hl7.org/fhir/StructureDefinition/code": "code",
    "http://hl7.org/fhir/StructureDefinition/id": "id",
    "http://hl7.org/fhir/StructureDefinition/markdown": "markdown",
    "http://hl7.org/fhir/StructureDefinition/unsignedInt": "unsignedInt",
    "http://hl7.org/fhir/StructureDefinition/positiveInt": "positiveInt",
    "http://hl7.org/fhir/StructureDefinition/uuid": "uuid",
    "http://hl7.org/fhir/StructureDefinition/oid": "oid",
    "http://hl7.org/fhir/StructureDefinition/instant": "instant",
    "http://hl7.org/fhir/StructureDefinition/base64Binary": "base64Binary",

    # Complex types
    "http://hl7.org/fhir/StructureDefinition/Quantity": "Quantity",
    "http://hl7.org/fhir/StructureDefinition/Period": "Period",
    "http://hl7.org/fhir/StructureDefinition/Coding": "Coding",
    "http://hl7.org/fhir/StructureDefinition/CodeableConcept": "CodeableConcept",
    "http://hl7.org/fhir/StructureDefinition/Reference": "Reference",
    "http://hl7.org/fhir/StructureDefinition/Identifier": "Identifier",
    "http://hl7.org/fhir/StructureDefinition/HumanName": "HumanName",
    "http://hl7.org/fhir/StructureDefinition/Address": "Address",
    "http://hl7.org/fhir/StructureDefinition/ContactPoint": "ContactPoint",
    "http://hl7.org/fhir/StructureDefinition/Attachment": "Attachment",
    "http://hl7.org/fhir/StructureDefinition/Ratio": "Ratio",
    "http://hl7.org/fhir/StructureDefinition/Range": "Range",
    "http://hl7.org/fhir/StructureDefinition/SampledData": "SampledData",
    "http://hl7.org/fhir/StructureDefinition/Duration": "Duration",
    "http://hl7.org/fhir/StructureDefinition/Age": "Age",
    "http://hl7.org/fhir/StructureDefinition/Distance": "Distance",
    "http://hl7.org/fhir/StructureDefinition/Count": "Count",
    "http://hl7.org/fhir/StructureDefinition/Money": "Money",
    "http://hl7.org/fhir/StructureDefinition/Annotation": "Annotation",
    "http://hl7.org/fhir/StructureDefinition/Signature": "Signature",
    "http://hl7.org/fhir/StructureDefinition/Timing": "Timing",
    "http://hl7.org/fhir/StructureDefinition/Dosage": "Dosage",
    "http://hl7.org/fhir/StructureDefinition/Element": "Element",
    "http://hl7.org/fhir/StructureDefinition/Extension": "Extension",
    "http://hl7.org/fhir/StructureDefinition/Narrative": "Narrative",
    "http://hl7.org/fhir/StructureDefinition/Meta": "Meta",
    "http://hl7.org/fhir/StructureDefinition/BackboneElement": "BackboneElement",

    # Resources
    "http://hl7.org/fhir/StructureDefinition/Resource": "Resource",
    "http://hl7.org/fhir/StructureDefinition/DomainResource": "DomainResource",
    "http://hl7.org/fhir/StructureDefinition/Patient": "Patient",
    "http://hl7.org/fhir/StructureDefinition/Observation": "Observation",
    "http://hl7.org/fhir/StructureDefinition/Condition": "Condition",
    "http://hl7.org/fhir/StructureDefinition/Encounter": "Encounter",
    "http://hl7.org/fhir/StructureDefinition/Practitioner": "Practitioner",
    "http://hl7.org/fhir/StructureDefinition/Organization": "Organization",
    "http://hl7.org/fhir/StructureDefinition/Location": "Location",
    "http://hl7.org/fhir/StructureDefinition/Medication": "Medication",
    "http://hl7.org/fhir/StructureDefinition/MedicationRequest": "MedicationRequest",
    "http://hl7.org/fhir/StructureDefinition/Procedure": "Procedure",
    "http://hl7.org/fhir/StructureDefinition/DiagnosticReport": "DiagnosticReport",
    "http://hl7.org/fhir/StructureDefinition/AllergyIntolerance": "AllergyIntolerance",
    "http://hl7.org/fhir/StructureDefinition/Immunization": "Immunization",
    "http://hl7.org/fhir/StructureDefinition/CarePlan": "CarePlan",
    "http://hl7.org/fhir/StructureDefinition/DocumentReference": "DocumentReference",
    "http://hl7.org/fhir/StructureDefinition/Specimen": "Specimen",
    "http://hl7.org/fhir/StructureDefinition/ServiceRequest": "ServiceRequest",
    "http://hl7.org/fhir/StructureDefinition/Bundle": "Bundle",
    "http://hl7.org/fhir/StructureDefinition/OperationOutcome": "OperationOutcome",
    "http://hl7.org/fhir/StructureDefinition/Composition": "Composition",
}

# Type inheritance mapping (child -> parent)
TYPE_HIERARCHY = {}

def build_type_hierarchy():
    """Build the type inheritance mapping."""
    global TYPE_HIERARCHY

    # Add primitives
    for name, info in FHIR_PRIMITIVES.items():
        if info.get("parent"):
            TYPE_HIERARCHY[name] = info["parent"]

    # Add datatypes
    for name, info in FHIR_DATATYPES.items():
        if info.get("parent"):
            TYPE_HIERARCHY[name] = info["parent"]

    # Add resources
    for name, info in FHIR_RESOURCES.items():
        if info.get("parent"):
            TYPE_HIERARCHY[name] = info["parent"]


def generate_python_code() -> str:
    """Generate the Python code for fhir_types_generated.py."""

    build_type_hierarchy()

    code = '''"""
FHIR Type Definitions - AUTO-GENERATED

This file is generated by scripts/build_fhir_types.py.
DO NOT EDIT MANUALLY - regenerate by running: python scripts/build_fhir_types.py

Contains:
- FHIR_TYPES: All FHIR types (primitives, datatypes, resources)
- CHOICE_TYPES: Polymorphic field mappings
- TYPE_ALIASES: URI to type name mappings
- TYPE_HIERARCHY: Type inheritance (child -> parent)
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any


# =============================================================================
# FHIR Types
# =============================================================================

FHIR_TYPES: Dict[str, Dict[str, Any]] = {
'''

    # Add primitives
    code += "    # --- Primitives ---\n"
    for name, info in sorted(FHIR_PRIMITIVES.items()):
        code += f'    "{name}": {{\n'
        code += f'        "parent": {repr(info.get("parent"))},\n'
        code += f'        "kind": "primitive",\n'
        code += f'        "python_type": "{info.get("python_type", "str")}",\n'
        code += '    },\n'

    # Add datatypes
    code += "\n    # --- Complex Types (DataTypes) ---\n"
    for name, info in sorted(FHIR_DATATYPES.items()):
        code += f'    "{name}": {{\n'
        code += f'        "parent": {repr(info.get("parent"))},\n'
        code += f'        "kind": "datatype",\n'
        code += f'        "elements": {repr(info.get("elements", []))},\n'
        code += f'        "identifying_fields": {repr(info.get("identifying_fields", []))},\n'
        code += '    },\n'

    # Add resources
    code += "\n    # --- Resources ---\n"
    for name, info in sorted(FHIR_RESOURCES.items()):
        code += f'    "{name}": {{\n'
        code += f'        "parent": {repr(info.get("parent"))},\n'
        code += f'        "kind": "resource",\n'
        code += f'        "elements": {repr(info.get("elements", []))},\n'
        code += '    },\n'

    code += "}\n\n"

    # Choice types
    code += '''# =============================================================================
# Choice Type Mappings
# =============================================================================

CHOICE_TYPES: Dict[str, List[str]] = {
'''
    for path, choices in sorted(CHOICE_TYPES.items()):
        code += f'    "{path}": [\n'
        for choice in choices:
            code += f'        "{choice}",\n'
        code += '    ],\n'

    code += "}\n\n"

    # Type aliases
    code += '''# =============================================================================
# Type URI Aliases
# =============================================================================

TYPE_ALIASES: Dict[str, str] = {
'''
    for uri, name in sorted(TYPE_ALIASES.items()):
        code += f'    "{uri}": "{name}",\n'

    code += "}\n\n"

    # Type hierarchy
    code += '''# =============================================================================
# Type Hierarchy (child -> parent)
# =============================================================================

TYPE_HIERARCHY: Dict[str, str] = {
'''
    for child, parent in sorted(TYPE_HIERARCHY.items()):
        code += f'    "{child}": "{parent}",\n'

    code += "}\n\n"

    # Helper functions
    code += '''# =============================================================================
# Helper Functions
# =============================================================================

def is_fhir_type(type_name: str) -> bool:
    """Check if a type name is a known FHIR type."""
    return type_name in FHIR_TYPES


def get_type_info(type_name: str) -> Optional[Dict[str, Any]]:
    """Get type information for a FHIR type."""
    return FHIR_TYPES.get(type_name)


def get_parent_type(type_name: str) -> Optional[str]:
    """Get the parent type of a FHIR type."""
    return TYPE_HIERARCHY.get(type_name)


def is_subclass_of(type_name: str, parent_type: str) -> bool:
    """
    Check if a type is a subclass of another type.

    Args:
        type_name: The type to check
        parent_type: The potential parent type

    Returns:
        True if type_name is a subclass of (or equal to) parent_type
    """
    if type_name == parent_type:
        return True

    current = type_name
    while current:
        parent = TYPE_HIERARCHY.get(current)
        if parent == parent_type:
            return True
        current = parent

    return False


def get_choice_type_fields(resource_type: str, field_name: str) -> List[str]:
    """
    Get the concrete field choices for a choice type field.

    Args:
        resource_type: The FHIR resource type (e.g., "Observation")
        field_name: The base field name (e.g., "value")

    Returns:
        List of concrete field names (e.g., ["valueQuantity", "valueString", ...])
    """
    key = f"{resource_type}.{field_name}"
    return CHOICE_TYPES.get(key, [])


def resolve_choice_type(resource_type: str, field_name: str, resource_data: Dict[str, Any]) -> Optional[str]:
    """
    Resolve a choice type field to its concrete implementation.

    Args:
        resource_type: The FHIR resource type
        field_name: The base field name
        resource_data: The actual resource data

    Returns:
        The concrete field name that exists in the data, or None
    """
    choices = get_choice_type_fields(resource_type, field_name)
    for choice in choices:
        if choice in resource_data and resource_data[choice] is not None:
            return choice
    return None


def infer_fhir_type_from_value(value: Any) -> Optional[str]:
    """
    Infer the FHIR type from a Python value.

    Args:
        value: A Python value

    Returns:
        The inferred FHIR type name, or None
    """
    # Check for None
    if value is None:
        return None

    # Check for specific FHIR types (dict with identifying fields)
    if isinstance(value, dict):
        # Check for Quantity
        if "value" in value and "unit" in value:
            return "Quantity"

        # Check for Period
        if ("start" in value or "end" in value) and len(value) <= 4:
            return "Period"

        # Check for Coding
        if "system" in value and "code" in value:
            return "Coding"

        # Check for CodeableConcept
        if "coding" in value:
            return "CodeableConcept"

        # Check for Reference
        if "reference" in value:
            return "Reference"

        # Check for Identifier
        if "system" in value and "value" in value and len(value) <= 6:
            return "Identifier"

        # Check for HumanName
        if "family" in value or "given" in value:
            return "HumanName"

        # Check for Address
        if "line" in value or "city" in value or "postalCode" in value:
            return "Address"

        # Check for ContactPoint
        if "system" in value and "value" in value and len(value) <= 5:
            return "ContactPoint"

        # Check for Range
        if "low" in value and "high" in value:
            return "Range"

        # Check for Ratio
        if "numerator" in value and "denominator" in value:
            return "Ratio"

        # Check for resource type
        if "resourceType" in value:
            return value["resourceType"]

        # Generic object
        return "object"

    # Check for list
    if isinstance(value, list):
        return "Collection"

    # Check for boolean (must come before int since bool is subclass of int)
    if isinstance(value, bool):
        return "boolean"

    # Check for integer
    if isinstance(value, int):
        return "integer"

    # Check for float
    if isinstance(value, float):
        return "decimal"

    # Check for string (could be date/time)
    if isinstance(value, str):
        import re
        # Check for date pattern
        if re.match(r"^\\d{4}(-\\d{2}(-\\d{2})?)?$", value):
            if "T" in value:
                return "dateTime"
            return "date"
        # Check for time pattern
        if re.match(r"^T?\\d{2}(:\\d{2}(:\\d{2})?)?", value):
            return "time"
        return "string"

    return None


def get_type_kind(type_name: str) -> Optional[str]:
    """
    Get the kind of a FHIR type.

    Args:
        type_name: The FHIR type name

    Returns:
        One of "primitive", "datatype", "resource", or None
    """
    info = FHIR_TYPES.get(type_name)
    return info.get("kind") if info else None


def is_primitive(type_name: str) -> bool:
    """Check if a type is a FHIR primitive."""
    return get_type_kind(type_name) == "primitive"


def is_datatype(type_name: str) -> bool:
    """Check if a type is a FHIR datatype."""
    return get_type_kind(type_name) == "datatype"


def is_resource(type_name: str) -> bool:
    """Check if a type is a FHIR resource."""
    return get_type_kind(type_name) == "resource"


def resolve_type_uri(uri: str) -> Optional[str]:
    """
    Resolve a type URI to a type name.

    Args:
        uri: A type URI (e.g., "http://hl7.org/fhir/StructureDefinition/Patient")

    Returns:
        The type name (e.g., "Patient"), or None if not found
    """
    return TYPE_ALIASES.get(uri)
'''

    return code


def main():
    """Main entry point."""
    # Determine output path
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_path = project_root / "src" / "duckdb_fhirpath" / "fhir_types_generated.py"

    # Generate the code
    code = generate_python_code()

    # Write the output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(code)

    print(f"Generated: {output_path}")
    print(f"  - FHIR types: {len(FHIR_PRIMITIVES) + len(FHIR_DATATYPES) + len(FHIR_RESOURCES)}")
    print(f"    - Primitives: {len(FHIR_PRIMITIVES)}")
    print(f"    - DataTypes: {len(FHIR_DATATYPES)}")
    print(f"    - Resources: {len(FHIR_RESOURCES)}")
    print(f"  - Choice type mappings: {len(CHOICE_TYPES)}")
    print(f"  - Type aliases: {len(TYPE_ALIASES)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
