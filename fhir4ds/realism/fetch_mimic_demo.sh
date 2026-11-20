#!/usr/bin/env bash
# Fetch the MIMIC-IV-FHIR demo corpus (PhysioNet).
#
# The 2.1.0 demo zip is DIRECTLY downloadable (no credentialed login
# needed as of 2026-11-20):
#   https://physionet.org/content/mimic-iv-fhir-demo/get-zip/2.1.0/
#
# The full (non-demo) MIMIC-IV-FHIR release IS restricted: you must
# create a PhysioNet account, sign the DUA, and complete credentialed
# training before those links respond. This script NEVER embeds
# credentials; for the restricted release use:
#     wget --user YOU@example.org --ask-password <url>     # basic auth
#   or a logged-in browser cookie jar:
#     wget --load-cookies cookies.txt <url>
#
# Data lands in tests/data/mimic-iv-fhir-demo/ (GITIGNORED — never
# commit MIMIC data). After the fetch, smoke the harness:
#   python3 -m fhir4ds.realism.benchmark \
#     --corpus tests/data/mimic-iv-fhir-demo/mimic-iv-clinical-database-demo-on-fhir-2.1.0/fhir \
#     --output-dir /tmp/realism-mimic --realistic-names --rebase-dobs \
#     --patient-limit 5 --num-dup-patients 3

set -euo pipefail

URL="https://physionet.org/content/mimic-iv-fhir-demo/get-zip/2.1.0/"
DEST="$(cd "$(dirname "$0")/../.." && pwd)/tests/data/mimic-iv-fhir-demo"
mkdir -p "${DEST}"

if [[ -d "${DEST}/mimic-iv-clinical-database-demo-on-fhir-2.1.0/fhir" ]]; then
  echo "already fetched: ${DEST}/mimic-iv-clinical-database-demo-on-fhir-2.1.0/fhir"
  exit 0
fi

ZIP="${DEST}/mimic-iv-fhir-demo-2.1.0.zip"
echo "downloading ${URL} ..."
wget --continue --content-disposition "${URL}" -O "${ZIP}"

echo "unzipping ..."
unzip -o -q "${ZIP}" -d "${DEST}"

echo "Done. Corpus at: ${DEST}/mimic-iv-clinical-database-demo-on-fhir-2.1.0/fhir"
echo "Run the smoke command from this script's header."
