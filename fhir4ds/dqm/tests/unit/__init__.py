"""DQM unit tests (a package, so same-basename modules can coexist).

Without this file pytest's default (prepend) import mode derives a module name
from the file BASENAME alone, so `unit/test_x.py` and a sibling directory's
`test_x.py` become the same module and collection fails with "import file
mismatch". That is what happened when FHIR4-110 added
`test_content_digest_fhir4_110.py` here and in `unit/`: 14,193 tests collected
with one hard error, which fails `python -m pytest` and therefore CI.

Being a package gives every module a unique dotted name. `conformance/` already
is one; this makes the two siblings consistent with it.
"""
