/**
 * Sample SDC-compliant Questionnaires for the interactive forms demo.
 */
import type { Questionnaire } from "./sdc-types";

export interface SDCSample {
  id: string;
  label: string;
  description: string;
  questionnaire: Questionnaire;
  /** If true, this sample appears in the "Common Core" set shown in smart-flow */
  commonCore?: boolean;
}

// ── PHQ-9 Depression Screening ─────────────────────────────────

const PHQ9_OPTIONS = [
  { valueCoding: { code: "0", display: "Not at all" } },
  { valueCoding: { code: "1", display: "Several days" } },
  { valueCoding: { code: "2", display: "More than half the days" } },
  { valueCoding: { code: "3", display: "Nearly every day" } },
];

function phq9Question(linkId: string, text: string) {
  return {
    linkId,
    text,
    type: "choice" as const,
    required: true,
    answerOption: PHQ9_OPTIONS,
  };
}

const PHQ9_QUESTIONNAIRE: Questionnaire = {
  resourceType: "Questionnaire",
  id: "phq-9",
  title: "PHQ-9 Patient Health Questionnaire",
  status: "active",
  item: [
    {
      linkId: "intro",
      text: "Over the last 2 weeks, how often have you been bothered by any of the following problems?",
      type: "display",
    },
    {
      linkId: "symptoms",
      text: "Symptom Assessment",
      type: "group",
      item: [
        {
          linkId: "mood",
          text: "Mood & Interest",
          type: "group",
          item: [
            phq9Question("q1", "1. Little interest or pleasure in doing things"),
            phq9Question("q2", "2. Feeling down, depressed, or hopeless"),
          ],
        },
        {
          linkId: "physical",
          text: "Physical Symptoms",
          type: "group",
          item: [
            phq9Question("q3", "3. Trouble falling or staying asleep, or sleeping too much"),
            phq9Question("q4", "4. Feeling tired or having little energy"),
            phq9Question("q5", "5. Poor appetite or overeating"),
          ],
        },
        {
          linkId: "cognitive",
          text: "Cognitive & Behavioral",
          type: "group",
          item: [
            phq9Question("q6", "6. Feeling bad about yourself — or that you are a failure"),
            phq9Question("q7", "7. Trouble concentrating on things"),
            phq9Question("q8", "8. Moving or speaking so slowly that others noticed"),
            phq9Question("q9", "9. Thoughts that you would be better off dead"),
          ],
        },
      ],
    },
    {
      linkId: "total-score",
      text: "Total Score",
      type: "integer",
      readOnly: true,
      extension: [
        {
          url: "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-calculatedExpression",
          valueExpression: {
            language: "text/fhirpath",
            description: "Sum of all PHQ-9 question scores",
            expression:
              "%resource.item.repeat(item).where(linkId='q1' or linkId='q2' or linkId='q3' or linkId='q4' or linkId='q5' or linkId='q6' or linkId='q7' or linkId='q8' or linkId='q9').select(answer.valueCoding.code.toInteger()).aggregate($this + $total, 0)",
          },
        },
      ],
    },
    {
      linkId: "severity",
      text: "Depression Severity",
      type: "string",
      readOnly: true,
      extension: [
        {
          url: "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-calculatedExpression",
          valueExpression: {
            language: "text/fhirpath",
            description: "Depression severity category based on total score",
            expression:
              "iif(%resource.item.where(linkId='total-score').answer.valueInteger < 5, 'None/Minimal', iif(%resource.item.where(linkId='total-score').answer.valueInteger < 10, 'Mild', iif(%resource.item.where(linkId='total-score').answer.valueInteger < 15, 'Moderate', iif(%resource.item.where(linkId='total-score').answer.valueInteger < 20, 'Moderately Severe', 'Severe'))))",
          },
        },
      ],
    },
  ],
};

// ── Patient Demographics ───────────────────────────────────────

const DEMOGRAPHICS_QUESTIONNAIRE: Questionnaire = {
  resourceType: "Questionnaire",
  id: "demographics",
  title: "Patient Demographics Form",
  status: "active",
  item: [
    {
      linkId: "name-group",
      text: "Patient Name",
      type: "group",
      item: [
        {
          linkId: "family-name",
          text: "Last Name",
          type: "string",
          required: true,
          extension: [
            {
              url: "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression",
              valueExpression: {
                language: "text/fhirpath",
                expression: "%patient.name.first().family",
              },
            },
          ],
        },
        {
          linkId: "given-name",
          text: "First Name",
          type: "string",
          required: true,
          extension: [
            {
              url: "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression",
              valueExpression: {
                language: "text/fhirpath",
                expression: "%patient.name.first().given.first()",
              },
            },
          ],
        },
      ],
    },
    {
      linkId: "dob",
      text: "Date of Birth",
      type: "date",
      required: true,
      extension: [
        {
          url: "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression",
          valueExpression: {
            language: "text/fhirpath",
            expression: "%patient.birthDate",
          },
        },
      ],
    },
    {
      linkId: "gender",
      text: "Gender",
      type: "choice",
      required: true,
      answerOption: [
        { valueCoding: { code: "male", display: "Male" } },
        { valueCoding: { code: "female", display: "Female" } },
        { valueCoding: { code: "other", display: "Other" } },
        { valueCoding: { code: "unknown", display: "Unknown" } },
      ],
      extension: [
        {
          url: "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression",
          valueExpression: {
            language: "text/fhirpath",
            expression: "%patient.gender",
          },
        },
      ],
    },
    {
      linkId: "active",
      text: "Active Patient",
      type: "boolean",
    },
    {
      linkId: "contact-group",
      text: "Contact Information",
      type: "group",
      item: [
        { linkId: "phone", text: "Phone Number", type: "string" },
        { linkId: "email", text: "Email Address", type: "string" },
        {
          linkId: "address-group",
          text: "Address",
          type: "group",
          item: [
            { linkId: "street", text: "Street", type: "string" },
            { linkId: "city", text: "City", type: "string" },
            { linkId: "state", text: "State", type: "string" },
            { linkId: "zip", text: "ZIP Code", type: "string" },
          ],
        },
      ],
    },
  ],
};

// ── Lab Results (SQL-on-FHIR Demo) ───────────────────────────

const LABS_QUESTIONNAIRE: Questionnaire = {
  resourceType: "Questionnaire",
  id: "lab-results",
  title: "Clinical Lab & Vitals Review",
  status: "active",
  item: [
    {
      linkId: "patient-info",
      text: "Patient Context",
      type: "group",
      item: [
        {
          linkId: "p-name",
          text: "Patient Name",
          type: "string",
          readOnly: true,
          extension: [
            {
              url: "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression",
              valueExpression: {
                language: "text/fhirpath",
                expression: "%patient.name.first().family",
              },
            },
          ],
        },
      ],
    },
    {
      linkId: "lab-group",
      text: "Recent Results",
      type: "group",
      item: [
        {
          linkId: "sbp",
          text: "Latest Measurement",
          type: "decimal",
          extension: [
            {
              url: "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression",
              valueExpression: {
                language: "text/fhirpath",
                expression: "[Observation] last().value.value",
              },
            },
          ],
        },
      ],
    },
  ],
};

// ── Patient Intake & History Review ────────────────────────────

const INTAKE_QUESTIONNAIRE: Questionnaire = {
  resourceType: "Questionnaire",
  id: "patient-intake",
  title: "Patient Intake & History Review",
  status: "active",
  item: [
    {
      linkId: "patient-info",
      text: "Patient Information",
      type: "group",
      item: [
        {
          linkId: "intake-family",
          text: "Last Name",
          type: "string",
          required: true,
          extension: [
            {
              url: "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression",
              valueExpression: {
                language: "text/fhirpath",
                expression: "%patient.name.first().family",
              },
            },
          ],
        },
        {
          linkId: "intake-given",
          text: "First Name",
          type: "string",
          required: true,
          extension: [
            {
              url: "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression",
              valueExpression: {
                language: "text/fhirpath",
                expression: "%patient.name.first().given.first()",
              },
            },
          ],
        },
        {
          linkId: "intake-dob",
          text: "Date of Birth",
          type: "date",
          extension: [
            {
              url: "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression",
              valueExpression: {
                language: "text/fhirpath",
                expression: "%patient.birthDate",
              },
            },
          ],
        },
      ],
    },
    {
      linkId: "condition-count",
      text: "Active Conditions on File",
      type: "integer",
      readOnly: true,
      extension: [
        {
          url: "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression",
          valueExpression: {
            language: "text/fhirpath",
            description: "Count of conditions in local DuckDB",
            expression: "[Condition] count()",
          },
        },
      ],
    },
    {
      linkId: "reason-for-visit",
      text: "Reason for Visit",
      type: "text",
    },
  ],
};

// ── Exports ────────────────────────────────────────────────────

export const SDC_SAMPLES: SDCSample[] = [
  {
    id: "patient-intake",
    label: "Patient Intake & History",
    description: "Smart intake form with initialExpression pre-population and risk scoring",
    commonCore: true,
    questionnaire: INTAKE_QUESTIONNAIRE,
  },
  {
    id: "lab-results",
    label: "Lab Results & Vitals",
    description: "Demo of pre-populating data from DuckDB resources using SQL-on-FHIR expressions",
    commonCore: true,
    questionnaire: LABS_QUESTIONNAIRE,
  },
  {
    id: "phq-9",
    label: "PHQ-9 Depression Screening",
    description:
      "Standard 9-item depression screening with auto-calculated total score and severity classification",
    commonCore: true,
    questionnaire: PHQ9_QUESTIONNAIRE,
  },
  {
    id: "demographics",
    label: "Patient Demographics",
    description:
      "Demographics form with initialExpression pre-population from patient context and nested address groups",
    questionnaire: DEMOGRAPHICS_QUESTIONNAIRE,
  },
];
