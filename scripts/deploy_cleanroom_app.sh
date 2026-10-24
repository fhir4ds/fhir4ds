#!/usr/bin/env bash
# Deploy the built CQL Cleanroom SPA to the two static targets.
#
# WHY A FULL MIRROR: the app is a Vite build with CONTENT-HASHED chunks
# (App-*, main-*, monaco-setup-*, cleanroom.worker-*, editor.worker-*,
# duckdb-*). Copying a fixed filename list leaves stale/missing chunks:
# 0.0.18 shipped an App that referenced cleanroom.worker-CuBqLwW-.js while
# the targets still had the old worker (standalone 404), and the wheel the
# worker loads is resolved RELATIVE TO THE WORKER BUNDLE
# (<base>/assets/<wheel>) — so the wheel must exist at BOTH the target
# root and target/assets/.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== build =="
(cd web/cql-cleanroom && npm run build)

WHEEL=$(basename "$(ls web/cql-cleanroom/dist/fhir4ds_v2-*.whl | head -1)")
echo "== deploy $WHEEL =="
for T in fhir4ds/devserver/static-cleanroom web/website/static/cql-cleanroom; do
  rm -rf "$T"
  mkdir -p "$T"
  cp -a web/cql-cleanroom/dist/. "$T"/
  echo "   $T <- dist/"

  # --- verify ---------------------------------------------------------
  test -f "$T/index.html"
  test -f "$T/assets/$WHEEL"          || { echo "MISSING wheel in $T/assets"; exit 1; }
  test -f "$T/$WHEEL"                 || { echo "MISSING wheel at $T root"; exit 1; }
  WORKER=$(ls "$T"/assets/cleanroom.worker-*.js | head -1)
  grep -q "$WHEEL" "$WORKER"          || { echo "WORKER does not reference $WHEEL"; exit 1; }
  APP=$(ls "$T"/assets/App-*.js | head -1)
  REF=$(grep -o 'cleanroom\.worker-[A-Za-z0-9_-]*\.js' "$APP" | head -1)
  test -n "$REF" && test -f "$T/assets/$REF" || { echo "APP references missing worker $REF"; exit 1; }
  echo "   verified: $REF + $WHEEL (root+assets)"
done

echo "== md5 parity =="
md5sum web/cql-cleanroom/dist/fhir4ds_v2-*.whl \
       fhir4ds/devserver/static-cleanroom/assets/fhir4ds_v2-*.whl \
       web/website/static/cql-cleanroom/assets/fhir4ds_v2-*.whl
echo "OK"
