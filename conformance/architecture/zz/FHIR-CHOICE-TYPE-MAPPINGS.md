# FHIR Choice Type Patterns in QICore

## Overview

This document researches FHIR choice type patterns (the `[x]` suffix) used in QICore CQL measures and their SQL translation strategies.

## Research Stage 5: Choice Type Patterns

### 1. effective[x] - Choice Type Pattern

**Pattern Usage:**
- Found in `CMS165FHIRControllingHighBP.cql` with `.latest()` function
- `BPReading.effective.latest() same day as "Most Recent Blood Pressure Day"`
- `BloodPressure.effective.latest() during day of DisqualifyingEncounter.period`

**CQL Access Pattern:**
```cql
Observation.effective.latest()
```

**SQL Translation Strategy:**
From `PLAN-CQL-TO-SQL-TRANSLATOR.md`:
```python
# effective[x] choice type: try effectiveDateTime, fallback to effectivePeriod.end
def resolve_choice_type(resource_var: str, field: str, expected_type: str) -> str:
    """Generate SQL to handle FHIR choice types."""
    # effective[x] -> effectiveDateTime, effectivePeriod, effectiveTiming, effectiveInstant
    if field == "effective":
        # For latest(), prefer effectiveDateTime
        if expected_type == "DateTime":
            return f"{resource_var}->>'effectiveDateTime'"
        # Fallback to effectivePeriod.end if no effectiveDateTime
        elif expected_type == "Instant":
            return f"COALESCE({resource_var}->>'effectiveDateTime', {resource_var}->'effectivePeriod'->>'end')"
    # Other patterns...
```

**Choice Type Mapping:**
```python
"Observation.effective": [
    "effectiveDateTime",
    "effectivePeriod",
    "effectiveTiming",
    "effectiveInstant",
]
```

### 2. onset[x] - Choice Type Pattern

**Pattern Usage:**
- Found in multiple measures via `prevalenceInterval()`
- `Hypertension.prevalenceInterval() overlaps Interval[...]`
- `AdvancedIllnessDiagnosis.prevalenceInterval() starts during day of Interval[...]`

**CQL Access Pattern:**
```cql
// In QICoreCommon.cql (likely)
define function prevalenceInterval():
  // Construct interval from onsetDateTime to abatementDateTime
  Interval[Condition.onsetDateTime, Condition.abatementDateTime]
```

**SQL Translation Strategy:**
```python
# onset[x] choice type for prevalenceInterval
def handle_onset_abatement_patterns(resource_var: str) -> str:
    """Handle onset[x] and abatement[x] for prevalenceInterval"""
    # onset[x] -> onsetDateTime, onsetAge, onsetPeriod, onsetRange, onsetString
    onset_resolution = """
    COALESCE(
        {resource_var}->>'onsetDateTime',
        {resource_var}->'onsetPeriod'->>'start',
        {resource_var}->'onsetRange'->>'low',
        {resource_var}->>'onsetString'
    )
    """

    # abatement[x] -> abatementDateTime, abatementAge, abatementPeriod, etc.
    abatement_resolution = """
    COALESCE(
        {resource_var}->>'abatementDateTime',
        {resource_var}->'abatementPeriod'->>'end',
        {resource_var}->'abatementRange'->>'high',
        {resource_var}->>'abatementString'
    )
    """

    return f"Interval[{onset_resolution}, {abatement_resolution}]"
```

**Choice Type Mappings:**
```python
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
```

### 3. performed[x] - Choice Type Pattern

**Pattern Usage:**
- Found in Procedure resources
- Not directly used in current QICore measures but pattern is supported

**CQL Access Pattern:**
```cql
// This pattern would be used in Procedure contexts
Procedure.performed[x] where performed[x] during "Measurement Period"
```

**SQL Translation Strategy:**
```python
# performed[x] choice type
def handle_performed_pattern(resource_var: str) -> str:
    """Procedure.performed[x] choice type handling"""
    # performed[x] -> performedDateTime, performedPeriod, performedString, etc.
    return """
    CASE
        WHEN {resource_var}->>'performedDateTime' IS NOT NULL THEN {resource_var}->>'performedDateTime'
        WHEN {resource_var}->'performedPeriod'->>'start' IS NOT NULL THEN {resource_var}->'performedPeriod'->>'start'
        WHEN {resource_var}->'performedPeriod'->>'end' IS NOT NULL THEN {resource_var}->'performedPeriod'->>'end'
        ELSE {resource_var}->>'performedString'
    END
    """
```

**Choice Type Mapping:**
```python
"Procedure.performed": [
    "performedDateTime",
    "performedPeriod",
    "performedString",
    "performedAge",
    "performedRange",
],
```

### 4. value[x] - Choice Type Pattern

**Pattern Usage:**
- Found in Observation resources
- Supports multiple data types for observation values

**CQL Access Pattern:**
```cql
// Observation.value[x] patterns
Observation.valueQuantity
Observation.valueString
Observation.valueBoolean
Observation.valueInteger
Observation.valueRange
// etc.
```

**SQL Translation Strategy:**
```python
# value[x] choice type for Observation
def handle_value_x_pattern(resource_var: str, target_type: str) -> str:
    """Observation.value[x] choice type handling"""
    value_fields = [
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
        "valuePeriod"
    ]

    # Build COALESCE statement to check each possible field
    coalesce_clauses = []
    for field in value_fields:
        if target_type in ["Quantity", "Decimal"]:
            if field == "valueQuantity":
                coalesce_clauses.append(f"{resource_var}->'{field}'->>'value'")
        elif target_type == "String":
            if field in ["valueString", "valueCodeableConcept"]:
                coalesce_clauses.append(f"COALESCE({resource_var}->'{field}'->>'text', {resource_var}->'{field}'->>'value')")
        elif target_type == "Boolean":
            if field == "valueBoolean":
                coalesce_clauses.append(f"{resource_var}->>'{field}'")
        # ... other type handling

    return f"COALESCE({', '.join(coalesce_clauses)})"
```

**Choice Type Mapping:**
```python
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
```

### 5. Special Patterns in CQL

#### Latest Pattern for effective[x]
```cql
// From CMS165FHIRControllingHighBP.cql
BPReading.effective.latest() same day as "Most Recent Blood Pressure Day"
```

**SQL Implementation:**
```sql
-- Latest function implementation
CREATE OR REPLACE FUNCTION Latest(resources JSONB, date_path TEXT)
RETURNS JSONB AS $$
DECLARE
    latest_resource JSONB;
    latest_date TIMESTAMPTZ;
BEGIN
    -- Extract date from resources based on path
    -- Handle effective[x] choice type
    SELECT INTO latest_resource
    r FROM (
        SELECT r,
               COALESCE(r->>'effectiveDateTime',
                       r->'effectivePeriod'->>'end') as eff_date
        FROM jsonb_array_elements(resources) as r
        WHERE eff_date IS NOT NULL
    ) subq
    ORDER BY eff_date DESC
    LIMIT 1;

    RETURN latest_resource;
END;
$$ LANGUAGE plpgsql;
```

#### PrevalenceInterval Pattern
```cql
// From multiple measures
Hypertension.prevalenceInterval() overlaps Interval[...]
```

**CQL Definition (inferred):**
```cql
define function prevalenceInterval():
    Interval[Condition.onset, Condition.abatement]
```

**SQL Implementation:**
```sql
-- Prevalence interval construction
CREATE OR REPLACE FUNCTION prevalence_interval(condition JSONB)
RETURNS TIMESTAMPTZ RANGE AS $$
DECLARE
    start_date TIMESTAMPTZ;
    end_date TIMESTAMPTZ;
BEGIN
    -- Handle onset[x] choice type
    start_date := COALESCE(
        (condition->>'onsetDateTime')::TIMESTAMPTZ,
        (condition->'onsetPeriod'->>'start')::TIMESTAMPTZ,
        (condition->'onsetRange'->>'low')::TIMESTAMPTZ,
        (condition->>'onsetString')::TIMESTAMPTZ
    );

    -- Handle abatement[x] choice type
    end_date := COALESCE(
        (condition->>'abatementDateTime')::TIMESTAMPTZ,
        (condition->'abatementPeriod'->>'end')::TIMESTAMPTZ,
        (condition->'abatementRange'->>'high')::TIMESTAMPTZ,
        (condition->>'abatementString')::TIMESTAMPTZ
    );

    RETURN tsrange(start_date, end_date);
END;
$$ LANGUAGE plpgsql;
```

## Summary: Choice Type Translation Strategies

| Choice Type | Resource | Possible Fields | SQL Strategy | Special Handling |
|-------------|----------|----------------|--------------|------------------|
| **effective[x]** | Observation | effectiveDateTime, effectivePeriod, effectiveTiming, effectiveInstant | COALESCE with DateTime preference | For .latest(): prefer effectiveDateTime |
| **onset[x]** | Condition | onsetDateTime, onsetAge, onsetPeriod, onsetRange, onsetString | COALESCE from various onset types | Used in prevalenceInterval() |
| **abatement[x]** | Condition | abatementDateTime, abatementAge, abatementPeriod, abatementRange, abatementString | COALESCE from various abatement types | Used in prevalenceInterval() |
| **performed[x]** | Procedure | performedDateTime, performedPeriod, performedString, performedAge, performedRange | CASE statement with priority | Period handling for date ranges |
| **value[x]** | Observation | valueQuantity, valueString, valueBoolean, etc. | Type-specific extraction | Multiple target types supported |

## Key Implementation Insights

1. **Choice Type Resolution**: Always use COALESCE to check all possible concrete fields in priority order
2. **DateTime Preference**: For temporal choice types (effective[x], onset[x]), prefer DateTime fields first
3. **Period Handling**: For Period types, extract start/end appropriately based on context
4. **Fluent Functions**: The .latest() and prevalenceInterval() patterns show how CQL abstracts choice type complexity
5. **Type-Specific Handling**: Different choice types may require different resolution strategies based on expected target types

## Files Referenced

- `cql-measures/CMS165/FHIRHelpers.cql` - FHIR helper functions
- `cql-measures/CMS165/QICoreCommon.cql` - Common QICore functions including prevalenceInterval
- `cql-measures/CMS165/CMS165FHIRControllingHighBP.cql` - Examples of .latest() usage
- `docs/PLAN-CQL-TO-SQL-TRANSLATOR.md` - Translation strategies for choice types
- `scripts/build_fhir_types.py` - CHOICE_TYPES mapping definition