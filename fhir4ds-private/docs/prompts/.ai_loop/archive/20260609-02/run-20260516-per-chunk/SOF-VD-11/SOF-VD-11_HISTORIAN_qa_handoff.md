# SOF-VD-11 HISTORIAN QA Handoff

Spec anchors checked:
- SQL-on-FHIR v2.1.0-pre ViewDefinition defines a tabular projection of a
  single FHIR resource type and names Patient, Observation, Patient.address
  unrolling, and filtered Observation views as representative examples.
- View Runner implementations execute ViewDefinitions and return tabular
  results; `$viewdefinition-run` transforms supplied/server FHIR resources into
  tabular output.
- Required additional View Runner FHIRPath functions include
  `getResourceKey()` and `getReferenceKey()`.

Fresh probes run independently of archived SOF-VD-11 outputs:
- Parser validation rejected missing `resource`, empty `select`, non-string
  `resource`, and mutually exclusive iterator combinations.
- Generated and executed official-example-shaped PatientDemographics,
  PatientAddresses, and UsCoreBloodPressures views against synthetic Patient
  and Observation resources.
- Compared native C++ DuckDB registration against forced Python fallback for
  returned rows and observed DuckDB result column types.

Finding:
- `QA-001` HIGH: native C++ FHIRPath did not implement the SQL-on-FHIR View
  Runner key helpers. `getResourceKey()` was reported as unknown and returned
  NULL under native registration, while forced Python fallback returned
  canonical keys such as `Patient/1`. This broke PatientDemographics-style
  tabular output and native/fallback parity.

Reproducer:
- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/sof_vd_11_historian_probe.py`
  failed before remediation with native rows containing `None` for
  `getResourceKey()`.
