# Supplemental CQL for dqm-content-cms-2025 (US Core measures)

The `dqm-content-cms-2025` submodule references three shared CQL libraries
that it does not ship (IG tooling resolves them at build time from the
"Using CQL With FHIR" and "Common CQL Artifacts for FHIR (US-Based)" IGs).
They are vendored here at the exact pinned versions the measures include:

| File | Included as | Source | Tag | Commit |
|---|---|---|---|---|
| `FHIRCommon.cql` | `hl7.fhir.uv.cql.FHIRCommon version '2.0.0'` | github.com/HL7/cql-ig | `2.0.0` | `24c4c3157d33` |
| `USCoreCommon.cql` | `hl7.fhir.us.cql.USCoreCommon version '2.0.0-ballot'` | github.com/HL7/us-cql-ig | `2.0.0-ballot` | `fb23fc7bca47` |
| `USCoreElements.cql` | `hl7.fhir.us.cql.USCoreElements version '2.0.0-ballot'` | github.com/HL7/us-cql-ig | `2.0.0-ballot` | `fb23fc7bca47` |

Their only transitive dependency is `FHIRHelpers version '4.0.1'`, resolved
from the `ecqm-content-qicore-2025` submodule (added as an include path for
the `cms2025` suite, same as `2026`).

Refresh policy: re-vendor only when dqm-content-cms-2025 moves its include
pins (the repo README notes a planned upgrade from USQualityCore
0.1.0-cibuild to 0.5.0); update the table above with the new tag/commit.
