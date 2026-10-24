# MADiE Measure-Package ZIP Layout

This document specifies the on-the-wire layout of a **MADiE-style measure
package zip** — the import/export interchange format for the CQL Cleanroom.
It is the format produced by MADiE's packaging utility, by the repo's
workspace autozip (`scripts/gen_example_workspaces.py --zip`), and by the
devserver's closure export (`fhir4ds/devserver/madie_export_closure.py`);
it is consumed by the standalone/web loader
(`web/cql-cleanroom/src/lib/madiePackage.ts::importMadiePackage`) and the
devserver MADiE import (`fhir4ds/devserver/madie_import.py`).

> The zip is the **wire format only**. The devserver's on-disk workspace
> convention (Library/, ValueSet/, Measure/, MeasureReport/, Patient/<case>/,
> ViewDefinition/) is documented separately — see "Devserver workspace
> layout" at the bottom. MADiE's shape is the interchange boundary; the
> workspace stores each artifact once, under its FHIR type folder.

## Layout

```
<measure>-package.zip
├── cql/
│   ├── <LibraryName>-<version>.cql            # plain CQL text, one per library
│   │                                          # (e.g. CMS125FHIRBreastCancerScreening-0.4.000.cql)
│   │                                          # PRIMARY library first (Measure.library[0] tail match;
│   │                                          # loader falls back to alphabetical)
│   └── ...
├── resources/
│   ├── measure-<MeasureName>-<version>.json   # FHIR Measure resource
│   │                                          # MUST carry library[0] = primary library canonical
│   │                                          # (or name-resolvable tail) — the loader's main-first key
│   ├── library-<LibraryName>-<version>.json   # FHIR Library resource per cql/ file
│   │                                          # content[0]: { contentType: "text/cql", data: <base64 CQL> }
│   │                                          # (backfill only — cql/ twin wins when present)
│   ├── valueset-<ValueSetId>.json             # FHIR ValueSet resources (autozip extension; MADiE's
│   │                                          # own packages may omit these — loader treats as additive)
│   └── extras/                                # Cleanroom round-trip extension (optional)
│       ├── view-<name>.json                   # ViewDefinition resources
│       ├── expected-measurereport-<pid>.json  # expected MeasureReports (app-saved expected results)
│       └── parameters.json                    # Parameters resource (runtime parameter defaults)
└── tests/
    └── <caseId>/
        ├── Patient-<id>.json                  # one folder per test case; all FHIR resources
        ├── Encounter-<id>.json                # for that patient (any resourceType, one file each,
        ├── ...                                # named <ResourceType>-<id>.json)
        └── MeasureReport-<id>.json            # OPTIONAL trailing entry: the case's EXPECTED
                                               # MeasureReport (MADiE convention; the standalone
                                               # loader groups resources per case and reads the
                                               # MeasureReport as the expected result)
```

## Rules

1. **cql/ is the source of truth** for library text. `resources/library-*`
   backfills any library lacking a cql/ twin; when both exist the cql/ file
   wins. Every file must open with a parseable `library <Name> version '…'`
   declaration — files without one are skipped with a warning.
2. **Primary library resolution**: `Measure.library[0]` canonical tail →
   matching library tab; miss → warning + first cql/ file. Exporters MUST
   emit `library[0]` (the autozip synthesizes it when a MAT Measure lacks
   it).
3. **tests/<caseId>/** folders group each case's resources; the standalone
   loader loads them as the in-browser dataset grouped per patient.
4. **Expected results** may travel either as the per-case trailing
   `MeasureReport-*.json` inside `tests/<caseId>/` (MADiE convention) or as
   `resources/extras/expected-measurereport-*.json` (app-save convention);
   the standalone loader honors both.
5. **ValueSets** (`resources/valueset-*.json`) and `resources/extras/` are
   Cleanroom extensions — MADiE's own packages remain valid without them.
6. Packages are read-only imports: nothing in the zip is executed;
   terminology membership is resolved from packaged expansions.

## Devserver workspace layout (on-disk, NOT the zip)

For reference, the connected-mode convention a zip imports into / exports
from (`fhir4ds dev <dir>`):

```
<workspace>/
├── Library/            # *.cql (name from the library declaration)
├── ValueSet/           # *.json (id-keyed; expansions used as-is)
├── Measure/            # <Measure>.json resources
├── MeasureReport/      # <Measure>/<caseId>.json — EXPECTED MeasureReports
│                       # (one per test case; the expected-store convention)
├── Patient/            # <caseId>/<ResourceType>-<id>.json — one folder per
│                       # test case; also accepts loose data files + a
│                       # Parameters-*.json for CQL parameter defaults
├── ViewDefinition/     # *.json ViewDefinitions
└── cql/ valuesets/ measures/ data/ views/    # legacy spellings still searched
```
