"""Desktop side of the QA it4 live-parity harness.

Reads one JSON payload on stdin ({libraries, main, dataset, parameters,
output_columns}) and prints the evaluate_library envelope normalized for
parity comparison (timing dropped, rows sorted by patient_id).
"""
import json
import sys

sys.path.insert(0, "/home/jmontavon/src/fhir4ds")

import duckdb
import fhir4ds
from fhir4ds.operations.capabilities.evaluate import evaluate_library
from fhir4ds.operations.envelopes import DatasetSpec, LibraryText


def main() -> None:
    payload = json.loads(sys.stdin.read())
    conn = duckdb.connect(config={"allow_unsigned_extensions": True})
    fhir4ds.register(conn)
    result = evaluate_library(
        [LibraryText(**lib) for lib in payload.get("libraries", [])],
        LibraryText(**payload["main"]),
        DatasetSpec(**payload["dataset"]) if payload.get("dataset") else None,
        conn,
        parameters=payload.get("parameters"),
        output_columns=payload.get("output_columns"),
    )
    env = {
        "ok": result.ok,
        "patient_count": result.patient_count,
        "columns": list(result.columns or []),
        "rows": sorted(result.rows or [], key=lambda r: str(r.get("patient_id"))),
        "diagnostics": [d.message if hasattr(d, "message") else str(d)
                        for d in (result.diagnostics or [])],
    }
    json.dump(env, sys.stdout, default=str)


if __name__ == "__main__":
    main()
