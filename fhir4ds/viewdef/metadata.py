"""Shared metadata validators for SQL-on-FHIR ViewDefinition root fields."""

VIEWDEFINITION_RESOURCE_TYPE = "https://sql-on-fhir.org/ig/StructureDefinition/ViewDefinition"
SHAREABLE_VIEWDEFINITION_PROFILE = (
    "https://sql-on-fhir.org/ig/StructureDefinition/ShareableViewDefinition"
)
TABULAR_VIEWDEFINITION_PROFILE = (
    "https://sql-on-fhir.org/ig/StructureDefinition/TabularViewDefinition"
)

PUBLICATION_STATUS_CODES = frozenset({
    "draft",
    "active",
    "retired",
    "unknown",
})

KNOWN_FHIR_RESOURCE_TYPES = frozenset({
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
})


FHIR_VERSION_CODES = frozenset({
    "0.01", "0.05", "0.06", "0.11", "0.0.80", "0.0.81", "0.0.82",
    "0.4.0", "0.5.0", "1.0.0", "1.0.1", "1.0.2", "1.1.0", "1.4.0",
    "1.6.0", "1.8.0", "3.0.0", "3.0.1", "3.0.2", "3.3.0", "3.5.0",
    "4.0.0", "4.0.1", "4.1.0", "4.2.0", "4.3.0", "4.4.0", "4.5.0",
    "4.6.0", "5.0.0", "5.0.0-snapshot1", "5.0.0-snapshot3", "5.0.0-ballot",
    "5.0.0-ballot2", "5.0.0-ballot3", "6.0.0-ballot1", "6.0.0-ballot2",
    "6.0.0-ballot3", "6.0.0-ballot4",
})
