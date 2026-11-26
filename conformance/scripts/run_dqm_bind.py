#!/usr/bin/env python3
"""Bind-only gate for one DQM content suite (FHIR4-64).

Translates every measure of ``--suite`` with ``all_columns=True`` and runs
``EXPLAIN`` on a STRICT connection — parser, binder and optimizer over the
whole statement, with no rows scanned and no valueset scoring. Nothing is
written to ``conformance/reports/``: this is a GATE, not an evaluation, so the
master runner invokes it for exit status only.

Why it exists: DuckDB binds only the reachable plan, and ``run_dqm.py``
projects population columns only, so CMS986 reported qi-core 47/47 and
us-core 73/73 for months while its all-columns SQL could not bind at all
(``Binder Error: No function matches ... 'fhirpath_text(JSON[],
STRING_LITERAL)'``). A whole measure can be silently unbuildable and the
measure suite still prints PASS.

Usage:
    python3 conformance/scripts/run_dqm_bind.py --suite qi-core-2025
    python3 conformance/scripts/run_dqm_bind.py --suite us-core-2025

Exit codes are the CLI's: 0 all measures bind, 1 a measure failed to
translate/bind (printed with its id and error), 2 the check could not run
honestly (e.g. a masked connection that would weaken the check).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main(argv: list[str] | None = None) -> int:
    from fhir4ds.dqm.tests.conformance.cli import main as cli_main

    args = list(sys.argv[1:] if argv is None else argv)
    if "--bind-check" not in args:
        args.append("--bind-check")
    # cli.main() reads sys.argv itself (it owns the full option surface, so
    # this wrapper forwards rather than duplicating the parser).
    sys.argv = [sys.argv[0], *args]
    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
