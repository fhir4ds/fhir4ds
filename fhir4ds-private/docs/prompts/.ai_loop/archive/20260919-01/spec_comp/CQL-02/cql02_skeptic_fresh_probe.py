"""CQL-02 SKEPTIC fresh launch probe (2026-08-19): CQL 1.5 clinical types.

Spec grounding: cql-master 09-b-cqlreference.md
- Code structured type { code, display, system, version }
- Concept { codes List, display }
- Equal (Code/Concept): TUPLE equality semantics; null or different components -> null
- Equivalent (Code): code+system equivalent (string equivalence => case-insensitive),
  version/display ignored, ALWAYS true/false even with nulls
- Equivalent (Concept): non-empty code intersection using Code equivalence; display ignored
- ToConcept(Code): display propagates; ToConcept(List<Code>): no display; null -> null
- ToString: no Code/Concept overload -> null
"""

from __future__ import annotations

import json
import sys

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.translator import translate_cql

CQL = """library ClinicalProbe version '1.0.0'
using FHIR version '4.0.1'
valueset "Example VS": 'http://example.org/fhir/ValueSet/example'
codesystem LOINC: 'http://loinc.org'
code "Systolic": '8480-6' from LOINC display 'Systolic blood pressure'
context Patient

// H1: Code tuple accessors
define CodeAccessorCode: (Code '8480-6' from LOINC).code
define CodeAccessorSystem: (Code '8480-6' from LOINC).system
define CodeAccessorDisplay: (Code '8480-6' from LOINC).display
define LiteralCodeAccessorCode: (Code { code: 'c1', system: 's1', display: 'd1' }).code
define LiteralCodeAccessorVersion: (Code { code: 'c1', system: 's1', version: 'v1' }).version

// H2: Concept literal + accessors
define ConceptLiteralDisplay: (Concept { codes: { Code { code: 'c1', system: 's1' }, Code { code: 'c2', system: 's1' } }, display: 'The Concept' }).display
define ConceptLiteralCodes: (Concept { codes: { Code { code: 'c1', system: 's1' } } }).codes

// H3: Code equality (tuple semantics)
define CodeEqIdentical: Code { code: '8480-6', system: 'http://loinc.org', display: 'Systolic blood pressure' } = Code { code: '8480-6', system: 'http://loinc.org', display: 'Systolic blood pressure' }
define CodeEqDisplayDiffers: Code { code: '8480-6', system: 'http://loinc.org', display: 'A' } = Code { code: '8480-6', system: 'http://loinc.org', display: 'B' }
define CodeEqVersionDiffers: Code { code: '8480-6', system: 'http://loinc.org', version: '1' } = Code { code: '8480-6', system: 'http://loinc.org', version: '2' }
define CodeEqDiffComponents: Code { code: 'x', system: 's' } = Code { code: 'x', system: 's', display: 'd' }
define CodeEqNull: Code { code: 'x' } = null
define ConceptEqDisplayDiffers: Concept { codes: { Code { code: 'c', system: 's' } }, display: 'A' } = Concept { codes: { Code { code: 'c', system: 's' } }, display: 'B' }

// H4: equivalence is case-insensitive on code+system (string equivalence), ignores display/version
define CodeEquivCaseInsensitiveCode: Code { code: 'ABC', system: 'http://s.org' } ~ Code { code: 'abc', system: 'http://s.org' }
define CodeEquivCaseInsensitiveSystem: Code { code: 'abc', system: 'http://S.ORG' } ~ Code { code: 'abc', system: 'http://s.org' }
define CodeEquivDisplayIgnored: Code { code: 'abc', system: 's', display: 'X' } ~ Code { code: 'abc', system: 's', display: 'Y' }
define CodeEquivVersionIgnored: Code { code: 'abc', system: 's', version: '1' } ~ Code { code: 'abc', system: 's', version: '2' }
define CodeEquivSystemDiffers: Code { code: 'abc', system: 's1' } ~ Code { code: 'abc', system: 's2' }

// H5: equivalence totality (always true/false, even nulls)
define CodeEquivBothNullCodes: Code { code: null, system: null } ~ Code { code: 'x', system: 'y' }
define CodeEquivNullLiteralLeft: null ~ Code { code: 'x', system: 'y' }
define CodeEquivBothNullLiterals: null as Code ~ null as Code
define ConceptEquivEmptyCodes: Concept { codes: { } } ~ Concept { codes: { Code { code: 'x', system: 'y' } } }
define ConceptEquivNullConcept: null as Concept ~ Concept { codes: { Code { code: 'x', system: 'y' } } }

// H6: ToConcept overloads
define ToConceptNullCode: ToConcept(null as Code)
define ToConceptDisplayPropagates: ToConcept(Code '8480-6' from LOINC).display
define ToConceptListOfCodesNoDisplay: ToConcept({ Code '8480-6' from LOINC, Code '8462-4' from LOINC }).display
define ToConceptListOfCodesCount: Count(ToConcept({ Code '8480-6' from LOINC }).codes)
define ToConceptEmptyList: ToConcept({ })

// H7: ToString boundaries (no Code/Concept overload)
define ToStringCode: ToString(Code '8480-6' from LOINC)
define ToStringConcept: ToString(ToConcept(Code '8480-6' from LOINC))

// H8: membership in codesystem
define NamedCodeInCodeSystem: "Systolic" in LOINC
define OtherCodeInCodeSystem: Code '9999-9' from LOINC in LOINC
define NullCodeInCodeSystem: null in LOINC

// H9: cross-type equivalence Code ~ Concept (mixed signatures)
define CodeEquivConceptContaining: Code { code: 'c', system: 's' } ~ Concept { codes: { Code { code: 'c', system: 's' } } }
define CodeEquivConceptDisjoint: Code { code: 'z', system: 's' } ~ Concept { codes: { Code { code: 'c', system: 's' } } }
"""


def py_con():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=False)
    return con


def cpp_con():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=False)
    return con


def main() -> int:
    translated = translate_cql(CQL)
    py, cpp = py_con(), cpp_con()
    failures = 0
    try:
        for name in translated.keys() if hasattr(translated, "keys") else translated:
            sql = f"SELECT {translated[name].to_sql()}"
            try:
                a = py.execute(sql).fetchone()[0]
            except Exception as e:  # noqa: BLE001
                a = f"PY-ERR:{type(e).__name__}:{str(e)[:120]}"
            try:
                b = cpp.execute(sql).fetchone()[0]
            except Exception as e:  # noqa: BLE001
                b = f"CPP-ERR:{type(e).__name__}:{str(e)[:120]}"
            parity = "OK " if a == b else "DIFF"
            print(f"{parity} {name}: py={a!r} cpp={b!r}")
    finally:
        py.close()
        cpp.close()
    return failures


if __name__ == "__main__":
    sys.exit(main())
