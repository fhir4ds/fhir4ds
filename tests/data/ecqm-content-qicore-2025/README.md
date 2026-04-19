# ecqm-content-qicore-2025
eCQM Measure Content (Using QICore 6.0.0, based on FHIR R4 v4.0.1)

These draft FHIR-based measures and shared libraries are translated from the QDM-based versions of eCQMs that were published in May 2025 for the 2026 reporting year as they existed in MADiE as of June 2025 or later.

Commits to this repository will automatically trigger a build of the continuous integration build, available here:

https://build.fhir.org/ig/cqframework/ecqm-content-qicore-2025

## Connectathon Scenarios

### Measure Testing

This repository is populated with FHIR-based measure specifications developed using the MADiE tool and based on published AU2025 eCQMs. See the [Measure Content Index](https://docs.google.com/spreadsheets/d/1DocNOIX3ZYWCzOxSHw00sl21WHWx5SeazrlSCUcjqqs/edit#gid=1008487491) for a complete listing of available measure content for measure testing.

### Multi-Provider Patient Scenario

For systems that house data from multiple providers, it is often the case that individual patients may have encounters with multiple providers. In these cases, there must be a way to support identifying the data that should be reported with an individual based on the provider being reported. This is often referred to as the attribution of a patient (and their associated data for reporting) to a provider. Because attribution models vary based on where and why a measure is being evaluated (i.e. for what reporting program), attribution is not included as part of the measure specification. This means that currently, reporting systems must partition data differently when running the same measure for different programs. To support formal description of the attribution model, this scenario will look at ways to describe the attribution as part of the program, rather than as part of the measure itself.

The testing scenario we are using to support these investigations is as follows:

![Multi-provider patient scenario](input/images/MultiProviderPatient.png)

The patient, Jane Doe, has 9 encounters, one at the beginning of each month. The first four encounters are with practitioners Jane Smith and John Smith, practicing at Organization A with CCN `CCN-123` and TIN `EIN-00123`. The last five encounters are with practitioners Kelly Smith and John Smith, practicing at Organization B with CCN `CCN-999` and TIN `EIN-00999`.

To support identifying the provider being reported, use the `provider` parameter of the R5 [$evaluate-measure](https://hl7.org/fhir/measure-operation-evaluate-measure.html):

```
GET [base]/Measure/<measure-id>/$evaluate-measure?subject=Patient/MultiProviderPatient&periodStart=2024-01-01&periodEnd=2024-12-31&provider=Organization/organization-a
```

This provides the needed input to the attribution criteria to determine what data should be attributed to the provider for the given patient.

There are two test measures defined to support this scenario testing, a "hospital" encounter-based measure `MPPEncounterLevel`, and a "clinic" patient-based measure `MPPPatientLevel`.

In addition, there is an `AttributionModel` library that introduces two fluent functions, `isAttributable(Patient)` and `isAttributable(Encounter)`:

```cql
parameter "Measurement Period" Interval<DateTime> default Interval[@2024-01-01T00:00:00.0Z, @2024-12-31T23:59:59.999Z]
parameter "Provider" String

context Patient

define fluent function isAttributable(patient Patient):
  "Provider" is not null implies Patient.managingOrganization.reference.endsWith("Provider")

define fluent function isAttributable(encounter Encounter):
  encounter.period during "Measurement Period"
    and "Provider" is not null implies encounter.serviceProvider.reference.endsWith("Provider")
```

These functions are then referenced in the initial population criteria for each of these measures:

```cql
define "Initial Population":
  "Encounter with Principal Diagnosis and Age" Encounter
    where Encounter.isAttributable()
```

```cql
define "Has Qualifying Encounter During First 240 Days of Measurement Period":
  exists ( ( ["Encounter": "Office Visit"]
      union ["Encounter": "Outpatient Consultation"]
      union ["Encounter": "Annual Wellness Visit"]
      union ["Encounter": "Face-to-Face Interaction"]
      union ["Encounter": "Home Healthcare Services"]
      union ["Encounter": "Preventive Care Services Established Office Visit, 18 and Up"]
      union ["Encounter": "Preventive Care Services Initial Office Visit, 18 and Up"]
      union ["Encounter": "Preventive Care Services, Initial Office Visit, 0 to 17"]
      union ["Encounter": "Preventive Care, Established Office Visit, 0 to 17"]
      union ["Encounter": "Telephone Visits"]
    ) QualifyingEncounter
      where QualifyingEncounter.period during day of Interval[start of "Measurement Period", start of "Measurement Period" + 240 days]
        and QualifyingEncounter.isAttributable()
  )

define "Initial Population":
  "Has Qualifying Encounter During First 240 Days of Measurement Period"
```

The "default" attribution model defined by this library is simply that the Patient's managing organization matches the given Provider, and that the Encounter's serviceProvider matches the given Provider.

Whenever measure intent requires the determination of attribution (usually in the qualifying encounter, but sometimes in partitioning encounters to be considered as part of the measure logic below population criteria), these functions can be used to include attribution consideration, but in a way that keeps the attribution model used isolated from the rest of the measure logic.

Subsequently, different attribution logic can be provided by specifying a different version of the AttributionModel library using an artifact manifest:

```json
{
  "resourceType": "Library",
  "id": "MPPManifest",
  "contained": [{
    "resourceType": "Parameters",
    "id": "expansion-parameters",
    "parameter": [{
      "name": "forceCanonicalVersion",
      "valueCanonical": "http://ecqi.healthit.gov/ecqms/Library/AttributionModel|1.0.0-custom"
    }]
  }],
  "extension": [{
    "url": "http://hl7.org/fhir/us/cqfmeasures/StructureDefinition/cqfm-expansionParameters",
    "valueReference": {
      "reference": "#expansion-parameters"
    }
  }],
  "url": "http://ecqi.healthit.gov/ecqms/Library/MPPManifest",
  "name": "MPPManifest",
  ...
}
```

> NOTE: May want to keep expansion parameters limited to only those parameters that would be supplied to the $expand operation, and provide a separate set of parameters for "resolutionParameters"?

> NOTE: May want to expand this beyond just version override to actual canonical reference override?

In this way, the measure specification itself can remain unchanged and computable descriptions of different attribution models can be provided.

### Terminology API Testing

To continue verifying terminology service capabilities as described by the Measure Terminology Service in the Quality Measure IG. Specifically, validating that:

1. The service supports read and search for CodeSystem and ValueSet resources
2. The service supports hosted as well as authored content for ValueSet resources
3. The service returns resources that conform to the Shareable/Publishable/Computable/Executable profiles for ValueSet resources
4. The service supports the use of manifest libraries to provide expansion parameters
5. The service supports the $expand operation with manifest libraries

The current set of tests is available here:

[https://github.com/HL7/fhir-cqm/tree/main/postman-tests](https://github.com/HL7/fhir-cqm/tree/main/postman-tests)

In particular, we are testing the expansion of a grouping value set that requires versions of the component value sets:

[Cancer ValueSet 2.16.840.1.113883.3.526.3.1010 (2020-03-06)](input/tests/terminology/GroupingValueSet/ValueSet-2.16.840.113883.3.526.3.1010-20200306.json)

This version of the value set references two component value sets:

|ValueSet |Name |
|----|----|
|2.16.840.1.113883.3.526.2.1078|Cancer (ICD-10) |
|2.16.840.1.113883.3.526.2.1079|Cancer (SNOMED) |

Each of these value sets has multiple versions as they have changed over time:

|ValueSet |Version |
|----|----|
|2.16.840.1.113883.3.526.2.1078 (Cancer ICD-10)|[2019-03-15](input/tests/terminology/GroupingValueSet/ValueSet-2.16.840.113883.3.526.2.1078-20190315.json)|
| |[2021-02-18](input/tests/terminology/GroupingValueSet/ValueSet-2.16.840.113883.3.526.2.1078-20210218.json)|
| |[2022-02-18](input/tests/terminology/GroupingValueSet/ValueSet-2.16.840.113883.3.526.2.1078-20220218.json)|

|ValueSet |Version |
|----|----|
|2.16.840.1.113883.3.526.2.1079 (Cancer SNOMED)|[2019-03-15](input/tests/terminology/GroupingValueSet/ValueSet-2.16.840.113883.3.526.2.1079-20190315.json)|
| |[2020-03-06](input/tests/terminology/GroupingValueSet/ValueSet-2.16.840.113883.3.526.2.1079-20200306.json)|
| |[2021-02-18](input/tests/terminology/GroupingValueSet/ValueSet-2.16.840.113883.3.526.2.1079-20210218.json)|
| |[2022-02-18](input/tests/terminology/GroupingValueSet/ValueSet-2.16.840.113883.3.526.2.1079-20220218.json)|
| |[2023-02-17](input/tests/terminology/GroupingValueSet/ValueSet-2.16.840.113883.3.526.2.1079-20230217.json)|

In the `eCQM Update 2022-05-05` release, this value set was expanded with the following binding parameters:

|ValueSet |CodeSystem (Version) |
|----|----|
|2.16.840.1.113883.3.526.2.1078 |ICD10CM (2022) |
|2.16.840.1.113883.3.526.2.1079 |SNOMEDCT (2021-09, 2021-03, 2020-09, 2020-03, 2019-09, 2019-03, 2018-09, 2018-03, 2017-09, 2017-03, 2016-09, 2015-09) |

In the `eCQM Update 2023-05-04` release, this value set was expanded with the following binding parameters:

|ValueSet |CodeSystem (Version) |
|----|----|
|2.16.840.1.113883.3.526.2.1078 |ICD10CM (2023) |
|2.16.840.1.113883.3.526.2.1079 |SNOMEDCT (2022-09, 2022-03, 2021-09, 2021-03, 2020-09, 2020-03, 2019-09, 2019-03, 2018-09, 2018-03, 2017-09, 2017-03, 2016-09, 2015-09) |

If we just request an expansion of the value set as follows:

```
https://uat-cts.nlm.nih.gov/fhir/res/ValueSet/$expand?url=http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1010&_format=json
```

The response is an expansion using the latest version of the value set, the latest version of the component value sets, and the latest version of the code systems used:

[2.16.840.1.113883.3.526.3.1010-latest-expansion](input/tests/terminology/GroupingValueSet/ValueSet-2.16.840.113883.3.526.3.1010-latest-expansion.json)

However, if we ask for the expansion with expansion identifier `eCQM Update 2022-05-05`:

```
https://uat-cts.nlm.nih.gov/fhir/res/ValueSet/$expand?url=http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1010&expansion=eCQM%20Update%202022-05-05&_format=json
```

The response is an expansion with the expansion profile parameters as established by the `eCQM Update 2022-05-05` release:

[2.16.840.1.113883.3.526.3.1010-eCQM-Update-2022-05-05-expansion](input/tests/terminology/GroupingValueSet/ValueSet-2.16.840.113883.3.526.3.1010-eCQM-Update-2022-05-05-expansion.json)

Similarly, if we ask for the expansion with expansion identifier `eCQM Update 2023-05-04`:

```
https://uat-cts.nlm.nih.gov/fhir/res/ValueSet/$expand?url=http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1010&expansion=eCQM%20Update%202023-05-04&_format=json
```

The response is an expansion with the expansion profile parameters as established by the `eCQM Update 2023-05-04` release:

```
https://uat-cts.nlm.nih.gov/fhir/res/ValueSet/$expand?url=http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1010&expansion=eCQM%20Update%202023-05-04&_format=json
```

[2.16.840.1.113883.3.526.3.1010-eCQM-Update-2023-05-04-expansion](input/tests/terminology/GroupingValueSet/ValueSet-2.16.840.113883.3.526.3.1010-eCQM-Update-2023-05-04-expansion.json)

Note that this expansion includes an expansion parameter that is a reference to a _manifest_:

```json
{
  "name": "manifest",
  "valueString": "http://cts.nlm.nih.gov/fhir/Library/eCQM Update 2023-05-04"
}
```

Note that the manifest value here is supposed to be a canonical, and encoding it as such and searching for libraries with that URL gives:

```
https://uat-cts.nlm.nih.gov/fhir/res/Library?url=http://cts.nlm.nih.gov/fhir/Library/eCQM%20Update%202023-05-04
```

Although this does result in a library, the returned library does not have a url element. The expected result is a library manifest that provides the appropriate code system and value set versions for use in expanding value sets as part of the release:

[Library/ecqm-update-2023-05-04](input/tests/terminology/GroupingValueSet/Library-ecqm-update-2023-05-04.json)

This library contains an `expansionParameters` extension that references a contained `Parameters` resource with the relevant expansion parameters:

```json
{
    "resourceType": "Parameters",
    "id": "expansion-parameters",
    "parameter": [{
        "name": "activeOnly",
        "valueBoolean": false
    }, {
        "name": "system-version",
        "valueCanonical": "http://hl7.org/fhir/sid/icd-10-cm|2022"
    }, {
        "name": "system-version",
        "valueCanonical": "http://snomed.info/sct|http://snomed.info/sct/731000124108/version/20220901"
    }, {
        "name": "canonicalVersion",
        "valueCanonical": "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1010|20200306"
    }, {
        "name": "canonicalVersion",
        "valueCanonical": "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.2.1078|20220218"
    }, {
        "name": "canonicalVersion",
        "valueCanonical": "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.2.1079|20230217"
    }]
}
```

In this case, the expansion parameters indicate:

* activeOnly: false - This means that if codes are listed in the definition of a value set that are no longer active in the version of the code system being used, they should still be included in the resulting expansion.
* system-version: "http://hl7.org/fhir/sid/icd-10-cm|2022" - This indicates the 2022 version of the ICD-10-CM code system should be used to expand value sets as part of this release
* system-version: "http://snomed.info/sct|http://snomed.info/sct/731000124108/version/20220901" - This indicates the 2022-09-01 release of SNOMED-CT should be used to expand value sets as part of this release
* canonicalVersion: "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1010|20200306" - This indicates that the 2020-03-06 version of this value set should be used to expand this value set, or when expanding grouper value sets that reference this value set
* canonicalVersion: "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.2.1078|20220218" - This indicates that the 2022-02-18 version of this value set should be used to expand this value set, or when expanding grouper value sets that reference this value set
* canonicalVersion: "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.2.1079|20230217" - This indicates that the 2023-02-17 version of this value set should be used to expand this value set, or when expanding grouper value sets that reference this value set

Note that some terminology services use the concept of an _expansion profile_ to establish these parameters for a particular release. The _manifest_ approach described here is making those parameters explicit as part of the definition of a release, rather than relying on a terminology-server-specific construct to provide this capability.

To make this explicit, the CQF Measures IG defines an extension to the ValueSet/$expand operation to support specifying value set versions:

[CQFM ValueSet Expand](http://build.fhir.org/ig/HL7/cqf-measures/OperationDefinition-ValueSet-expand.html)

Using these parameters in the ValueSet/$expand directly would look like:

```
[GET] https://uat-cts.nlm.nih.gov/fhir/res/ValueSet/$expand?url=http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1010&valueSetVersion=20200306&activeOnly=false&system-version=http%3A%2F%2Fhl7.org%2Ffhir%2Fsid%2Ficd-10-cm%7C2022&system-version=http%3A%2F%2Fsnomed.info%2Fsct%7Chttp%3A%2F%2Fsnomed.info%2Fsct%2F731000124108%2Fversion%2F20220901&canonicalVersion=http%3A%2F%2Fcts.nlm.nih.gov%2Ffhir%2FValueSet%2F2.16.840.1.113883.3.526.2.1078%7C20220218&canonicalVersion=http%3A%2F%2Fcts.nlm.nih.gov%2Ffhir%2FValueSet%2F2.16.840.1.113883.3.526.2.1079%7C20230217&_format=json
```

Rather than having to encode these parameters directly in the expand, the _manifest_ parameter allows them to be specified by reference to a manifest library:

```
[GET] https://uat-cts.nlm.nih.gov/fhir/res/ValueSet/$expand?url=http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1010&manifest=http://cts.nlm.nih.gov/fhir/Library/eCQM%20Update%202023-05-04&_format=json
```

This formulation should result in the same expansion as specifying the parameters directly in the $expand.

### ClaimsData Testing

To support investigation of the use of Administrative/Claims Data for use in quality reporting, we have a real-world certified to be HIPAA compliant anonymized data set of claims data from a national payer. The data set has about 740 patients, conforming to the [CARIN BlueButton IG](https://hl7.org/fhir/us/carin-bb/)

* [Patient Export (2022)](input/tests/claims/ClaimsData/patient_export_2022.ndjson)
* [Coverage Export (2022)](input/tests/claims/ClaimsData/coverage_export_2022.ndjson)
* [Explanation of Benefits Export (2022)](input/tests/claims/ClaimsData/professional_eob_export_2022.ndjson)

There are at least two potential areas of investigation:

1. Make use of the data here directly from CQL
2. Create synthetic clinical data derived from the information in the claims data

### Artifact Manifest Testing

### Measure Narrative Review

## Authoring

To author content in this implementation guide, you can use the VS Code CQL Plugin. This plugin will enable you to author, validate, and execute FHIR-based eCQM content.

For instructions on setting up your environment to use the VS Code Plugin, see the [VS Code CQL Support Readme](https://github.com/cqframework/vscode-cql/blob/master/README.md)

Github Codespaces can also be used in this repository.

## Content Indexes

* [Libraries](https://build.fhir.org/ig/cqframework/ecqm-content-qicore-2025/libraries.html)
* [Measures](https://build.fhir.org/ig/cqframework/ecqm-content-qicore-2025/measures.html)
* [Artifact Summary](https://build.fhir.org/ig/cqframework/ecqm-content-qicore-2025/artifacts.html)

## Repository Structure

This repository is setup like any HL7 FHIR IG project but also includes the CQL files and test data which means the file structure will be as follows:

```
   |-- _genonce.bat
   |-- _genonce.sh
   |-- _refresh.bat
   |-- _refresh.sh
   |-- _updatePublisher.bat
   |-- _updatePublisher.sh
   |-- _updateCQFTooling.bat
   |-- _updateCQFTooling.sh
   |-- ig.ini
   |-- bundles
       |-- MAT
           |-- <bundle files>
       |-- measure
           |-- <bundles>
   |-- input
       |-- ecqm-content-qicore-2025.xml
       |-- cql
           |-- <library name>.cql
       |-- pagecontent
       |-- resources
           |-- library
               |-- <library name>.json
           |-- measure
               |-- <measure name>.json
       |-- tests
           |-- measure
               |-- <measure name>
                   |-- <test case patient id>
                       |-- <test case resource files>
                   |-- ...
       |-- vocabulary
           |-- valueset
```

## Extracting MAT Packages

The CQF Tooling provides support for extracting a MAT exported package into the
directories of this repository so that the measure is included in the published
implementation guide. To do this, place the MAT export files (unzipped) in a
directory in the `bundles\mat` directory, and then run the following tooling
command:

```
[tooling-jar] -ExtractMatBundle bundles\mat\[bundle-directory]\[bundle-file]
```

For example:

```
input-cache\tooling-cli-3.8.0.jar -ExtractMATBundle bundles\mat\CLONE124_v6_03-Artifacts\measure-json-bundle.json
```

## Refresh IG Processing

The CQF Tooling provides "refresh" tooling that performs the following functions:

* Translates and validates all CQL source files
* Packages CQL and ELM content in the corresponding FHIR resources
* Refreshes generated content for each knowledge artifact (Library, Measure, PlanDefinition, ActivityDefinition) including parameters, dependencies, and effective data requirements

Whenever changes are made to the CQL, Library, or Measure resources, run the `_refresh` command to refresh the implementation guide content with the new content, and then run `_genonce` to run the publication tooling on the implementation guide (the same process that the continuous integration build uses to publish the implementation guide when commits are made to this repository).


## Measure Package Prep Process

1. Download Measure Zip folder to `bundles\mat` directory.
2. Unzip the folder, then unzip the MeasureExport and TestCaseExport folders within it.
3. Run `_updateCQFTooling.sh` script to ensure CQF tooling jar is present.
4. Update `_extractMATBundle.sh` so that `mat_bundle` points to the JSON file within the MeasureExport directory.
5. Run `_extractMATBundle.sh` to load Measure Resources.
6. Create a directory under `input\tests\measure` with the Measure ID.
7. Copy all files from the TestCaseExport directory to this newly created directory.
8. Update `_extractBundleResources.sh` so that `mat_bundle` points to this newly created directory.
9. Run `_extractBundleResources.sh` to populate test case resources.
10. Run `_refresh.sh` to refresh IG content.
