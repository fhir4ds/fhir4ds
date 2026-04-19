# QICore Update Process

This document describes the process of updating a pure FHIR-based measure to a QICore-based measure

## Extract MAT Bundle

Place the MAT export in the bundles\mat directory and extract the contents into a sub-folder. For example:

```
bundles\mat\CMS143FHIR-v0-0-003-FHIR-4-0-1\CMS143FHIR-v0-0-003-FHIR-4-0-1.json
```

Use the CQFTooling ExtractMatBundle operation to extract the contents of the bundle:

```
java -jar input-cache\tooling-2.5.0-SNAPSHOT.jar -ExtractMatBundle bundles\mat\CMS143FHIR-v0-0-003-FHIR-4-0-1\CMS143FHIR-v0-0-003-FHIR-4-0-1.json
```

## Revert FHIR-based Library Changes

Revert the changes to the following CQL libraries, because they are the FHIR-based versions and we do not want those, there are QICore versions already in the repository:

1. FHIRHelpers
2. QICoreCommon

## Copy Primary Measure Library

Copy the primary measure library and rename it using the QICore4 postfix:

```
input\cql\POAGOpticNerveEvaluationQICore4.cql
```

## Update Primary Measure Library

1. Open the QICore named file
2. Update the postfix on the library name from FHIR to QICore4
3. Update the using statement to `using QICore version '4.1.1'`
3. Update the version of the FHIRHelpers reference to 4.0.013 (the current version for QICore support in this repository)
4. Change the SupplementalDataElementsFHIR4 reference to SupplementalDataElementsQICore4
5. Change the MATGlobalCommonFunctionsFHIR4 reference to MATGlobalCommonFunctionsQICore4
6. Remove the reference to FHIRCommon
7. Update references to MATGlobalCommonFunctionsFHIR4 functions that were moved to QICoreCommon:
    1. Normalize Interval -> ToInterval
    1. Abatement Period -> ToAbatementInterval
    1. Prevalence Period -> ToPrevalenceInterval
    1. Has Start -> HasStart
    1. Has End -> HasEnd
    1. Latest -> Latest
    1. Earliest -> Earliest
    1. Interval To Day Numbers -> Interval To Day Numbers
    1. Days in Period -> Days in Period
8. Update references to QICore profiles (https://hl7.org/fhir/us/qicore/profiles.html)
    1. Note that when the intent is looking for negation, use the negation profile: https://hl7.org/fhir/us/qicore/#negation-rationale
    1. Note that for QICore profiles, the profiles will enforce any "fixed" constraints, so you don't need to check those values (for example status = 'not-done' in a negation profile isn't necessary because the profile enforces that specifically)
9. Update references to extensions that are using the extension functions to the element names (the "slice name" of the extension element defined in the profile)
