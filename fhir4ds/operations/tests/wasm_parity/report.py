"""Gap reports under ``tests/output/wasm-parity/`` (gitignored) and the triage CLI.

Every gate run writes ``<name>.json`` and ``<name>.md``: size by class and
owner, each ledger entry with its reason and expiry, and the unregistered
proposals. This is the artefact that answers "what are the gaps".

CLI (triage): ``python -m fhir4ds.operations.tests.wasm_parity.report``.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

from . import shipped_bundles
from .contract import FILE_LEVEL_KINDS, Contract
from .evaluators import SuiteResult
from .ledger import Entry, Violation
from .reference_bundle import REPO_ROOT, EnvironmentInputMissing, load_reference_bundle
from .surfaces import SimulatorFidelity

OUTPUT_DIR = REPO_ROOT / "tests" / "output" / "wasm-parity"
MAX_CASES_IN_MARKDOWN = 400


def _write(stem: str, payload: dict, markdown: str, today: date) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{stem}.json").write_text(
        json.dumps({"generated": today.isoformat(), **payload}, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    path = OUTPUT_DIR / f"{stem}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def _entry_rows(entries: list[Entry], today: date) -> list[str]:
    rows = []
    for entry in entries:
        days = (entry.expires - today).days
        state = "EXPIRED" if days < 0 else ("expiring soon" if days <= 14 else "live")
        targets = (
            entry.items
            if len(entry.items) <= 6
            else entry.items[:6] + (f"... +{len(entry.items) - 6}",)
        )
        rows.append(
            f"| `{entry.id}` | {entry.kind}{(' / ' + entry.suite) if entry.suite else ''} | "
            f"{len(entry.items)} | {entry.owner} | {entry.expires} ({days} d, {state}) | "
            f"{targets} | {entry.reason} |"
        )
    return rows


def _entry_header() -> list[str]:
    return [
        "",
        "| Entry | Kind | Size | Owner | Expires | Targets | Reason |",
        "|---|---|---|---|---|---|---|",
    ]


def _violation_lines(violations: list[Violation]) -> list[str]:
    lines: list[str] = []
    for violation in violations:
        lines.append(f"- **[{violation.gate} {violation.code}]** {violation.message}")
        if violation.proposal is not None:
            lines.append("  proposal:")
            lines.append("  ```json")
            lines.append("  " + json.dumps(violation.proposal, indent=2).replace("\n", "\n  "))
            lines.append("  ```")
    return lines


def failure_text(title: str, violations: list[Violation]) -> str:
    lines = [f"{title}: {len(violations)} problem(s). Details in {OUTPUT_DIR}/"]
    lines.extend(_violation_lines(violations))
    return "\n".join(lines)


def write_contract(
    contract: Contract,
    fidelity: SimulatorFidelity,
    violations: list[Violation],
    entries: list[Entry],
    *,
    today: date,
) -> Path:
    counts = {
        "reference_statements": contract.reference_statement_count,
        "wasm_only_macros": len(contract.wasm_only_macros),
        "body_drift": len(contract.body_drift),
        "desktop_only_uncovered": len(contract.desktop_only_uncovered),
        "macro_vs_native": len(contract.macro_vs_native),
        "signature_drift": len(contract.signature_drift),
        "app_copies_differing": sum(1 for _, status in contract.app_copies if status == "differs"),
        "violations": len(violations),
    }
    md = [
        "# WASM parity - Step 0: browser contract vs desktop",
        "",
        f"Generated {today.isoformat()}. Ledger: {len(entries)} entries.",
        "",
        "| Measure | Value |",
        "|---|---|",
        *[f"| {name} | {value} |" for name, value in counts.items()],
        "",
        "Reference bundle: `web/cql-cleanroom/src/lib/cql-macros.ts`.",
        "",
        "## T2 simulator fidelity",
        "",
        "OK"
        if fidelity.ok
        else "\n".join(f"- {k}: {list(v)}" for k, v in fidelity.problems().items() if v),
        "",
        "## T3 wasm-only macros (the principle)",
        "",
        *([f"- `{n}`" for n in contract.wasm_only_macros] or ["none"]),
        "",
        "## T4 same-name macros with a different body",
        "",
        *(
            [
                f"- `{n}`: browser `{b[:110]}` | desktop `{d[:110]}`"
                for n, (b, d) in contract.body_drift.items()
            ]
            or ["none"]
        ),
        "",
        "## T5 desktop macros with no browser counterpart",
        "",
        *([f"- `{n}`" for n in contract.desktop_only_uncovered] or ["none"]),
        "",
        "## Desktop macros the browser replaces with a native namesake (reported, not required)",
        "",
        *([f"- `{n}`" for n in contract.macro_vs_native] or ["none"]),
        "",
        "## Same-name functions with different overload signatures",
        "",
        *(
            [
                f"- `{n}`: desktop {d} | browser {b}"
                for n, (d, b) in contract.signature_drift.items()
            ]
            or ["none"]
        ),
        "",
        "## T6 app bundles",
        "",
        *[f"- `{p}`: {s}" for p, s in contract.app_copies],
        *_entry_header(),
        *_entry_rows(entries, today),
        "",
        "## Violations",
        "",
        *(_violation_lines(violations) or ["none"]),
        "",
    ]
    payload = {
        **counts,
        "wasm_only_macro_names": contract.wasm_only_macros,
        "body_drift": contract.body_drift,
        "desktop_only_uncovered": contract.desktop_only_uncovered,
        "macro_vs_native": contract.macro_vs_native,
        "signature_drift": contract.signature_drift,
        "app_copies": contract.app_copies,
        "simulator_fidelity": fidelity.problems(),
        "violations": [v.__dict__ for v in violations],
        "entries": [
            {
                **e.__dict__,
                "target": e.items,
                "since": e.since.isoformat(),
                "expires": e.expires.isoformat(),
            }
            for e in entries
        ],
    }
    return _write("step0", payload, "\n".join(md), today)


def write_suite(
    result: SuiteResult,
    violations: list[Violation],
    entries: list[Entry],
    *,
    today: date,
    stem: str | None = None,
) -> Path:
    counts = result.counts()
    in_scope = [e for e in entries if e.suite in (None, result.suite)]
    md = [
        f"# WASM parity - {'Tier B' if stem else 'Tier A'}: {result.suite} "
        f"(browser surface: {result.surface})",
        "",
        f"Generated {today.isoformat()}. {len(result.cases)} cases in {result.elapsed:.1f} s; "
        f"{result.gated} held back"
        + (f" ({'; '.join(f'{n} {why}' for why, n in sorted(result.gated_reasons.items()))})." if result.gated_reasons else " by the official runner's own gating."),
        "",
        "| Outcome | Cases | Meaning |",
        "|---|---|---|",
        "| GREEN | counts[GREEN] | expected matched on both; value and type identical |",
        "| PARITY_GAP | counts[PARITY_GAP] | desktop matches the official expectation, browser contract does not |",
        "| ENGINE_DIFF | counts[ENGINE_DIFF] | both match, but raw value or declared type differs |",
        "| BROWSER_ONLY_PASS | counts[BROWSER_ONLY_PASS] | browser contract matches, desktop does not |",
        "| BOTH_FAIL | counts[BOTH_FAIL] | desktop defect: neither surface matches |",
        "| TRANSLATE_DIFF | counts[TRANSLATE_DIFF] | SQL text depends on the translation connection (must be zero) |",
        "| TRANSLATE_ERROR | counts[TRANSLATE_ERROR] | translation-layer, engine-independent (reported only) |",
        "",
    ]
    md = [
        line.replace(f"counts[{key}]", str(counts[key])) if f"counts[{key}]" in line else line
        for line in md
        for key in [k for k in counts if f"counts[{k}]" in line]
    ]
    md += [
        "## Gaps by missing browser name (cases the browser contract cannot run)",
        "",
    ]
    missing_counter: Counter[str] = Counter(
        name for case in result.cases for name in case.missing if not case.green
    )
    md += [f"| `{name}` | {n} |" for name, n in missing_counter.most_common()] or ["none"]
    md += [
        "",
        f"## Ledger entries in scope ({result.suite} and name-level)",
        *_entry_header(),
        *_entry_rows(in_scope, today),
        "",
        "## Violations (fix, or register with a reason and an owner)",
        "",
        *(_violation_lines(violations) or ["none"]),
        "",
        "## Non-green cases",
        "",
        "| Case | Outcome | Desktop | Browser | Detail | Suspects |",
        "|---|---|---|---|---|---|",
    ]
    non_green = [c for c in result.cases if not c.green and c.outcome != "TRANSLATE_ERROR"]
    for case in non_green[:MAX_CASES_IN_MARKDOWN]:
        md.append(
            f"| `{case.case_id}` | {case.outcome} | {case.desktop[:90]} | {case.browser[:90]} | "
            f"{case.detail[:120]} | {', '.join(case.suspects)} |"
        )
    if len(non_green) > MAX_CASES_IN_MARKDOWN:
        md.append(f"| ... {len(non_green) - MAX_CASES_IN_MARKDOWN} more in the JSON |")
    payload = {
        "suite": result.suite,
        "surface": result.surface,
        "elapsed_seconds": round(result.elapsed, 1),
        "gated": result.gated,
        "gated_reasons": dict(result.gated_reasons),
        "counts": counts,
        "missing_name_counts": dict(missing_counter.most_common()),
        "violations": [v.__dict__ for v in violations],
        "entries": [
            {
                **e.__dict__,
                "target": e.items,
                "since": e.since.isoformat(),
                "expires": e.expires.isoformat(),
            }
            for e in in_scope
        ],
        "cases": [
            c.__dict__ for c in result.cases if not c.green or c.outcome == "TRANSLATE_ERROR"
        ],
    }
    return _write((stem or result.suite), payload, "\n".join(md) + "\n", today)


def write_files(
    observed: dict[str, list[str]],
    violations: list[Violation],
    entries: list[Entry],
    *,
    today: date,
) -> Path:
    """Report for T7: the shipped WASM extension bundles."""
    md = [
        "# WASM parity - Step 0, T7: shipped WASM extension bundles",
        "",
        f"Generated {today.isoformat()}. Source of truth: `fhir4ds/wasm_extension_bundles.json`.",
        "",
        "| Kind | Target |",
        "|---|---|",
        *[f"| {kind} | `{target}` |" for kind, targets in observed.items() for target in targets],
    ] or ["none observed"]
    md += [
        "",
        "## Ledger entries (file-level)",
        *_entry_header(),
        *_entry_rows([e for e in entries if e.kind in FILE_LEVEL_KINDS], today),
        "",
        "## Violations (fix, or register with a reason and an owner)",
        "",
        *(_violation_lines(violations) or ["none"]),
        "",
    ]
    payload = {
        "observed": observed,
        "violations": [v.__dict__ for v in violations],
        "entries": [
            {**e.__dict__, "target": e.items, "since": e.since.isoformat(), "expires": e.expires.isoformat()}
            for e in entries
            if e.kind in FILE_LEVEL_KINDS
        ],
    }
    return _write("shipped", payload, "\n".join(md) + "\n", today)


def _summary_line(name: str, violations: list[Violation]) -> str:
    kinds = Counter(v.code for v in violations)
    return f"{name}: {len(violations)} violation(s) {dict(kinds)}" if violations else f"{name}: OK"


def cli(argv: list[str] | None = None) -> int:
    """Run Step 0 and Tier A, write the reports, print the summary and proposals."""
    import argparse

    from . import contract as contract_mod
    from . import evaluators, ledger, surfaces

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", action="append", help="run only this suite (repeatable)")
    parser.add_argument(
        "--tier-b",
        action="store_true",
        help="also run the Tier B real-browser audit (needs web/cql-cleanroom/node_modules; "
        "cannot run under a virtual-memory cap)",
    )
    args = parser.parse_args(argv)
    today = date.today()
    entries = ledger.load()
    reference = load_reference_bundle()
    desktop = surfaces.desktop_connection()
    browser = surfaces.browser_sim_connection(reference)
    try:
        computed = contract_mod.compute(desktop, reference)
        violations = contract_mod.check_reference(computed) + contract_mod.check_simulator(reference)
        violations += contract_mod.evaluate(computed, entries, today=today)
        write_contract(
            computed, surfaces.simulator_fidelity(reference), violations, entries, today=today
        )
        print(_summary_line("step0", violations))
        for violation in violations:
            print(f"  [{violation.code}] {violation.message[:600]}")
            if violation.proposal is not None:
                print("  proposal:", json.dumps(violation.proposal))
        observed = shipped_bundles.observe(shipped_bundles.load_manifest())
        file_violations = contract_mod.evaluate_files(entries, observed, today=today)
        write_files(observed, file_violations, entries, today=today)
        print(_summary_line("shipped", file_violations), observed)
        for violation in file_violations:
            print(f"  [{violation.code}] {violation.message[:600]}")
            if violation.proposal is not None:
                print("  proposal:", json.dumps(violation.proposal))
        from . import macro_bundle

        generated_problems = list(macro_bundle.problems())
        stale_catalog = macro_bundle.browser_catalog_stale()
        if stale_catalog:
            generated_problems.append(stale_catalog)
        print(
            _summary_line(
                "generated",
                [
                    ledger.Violation("generated", "GENERATED_BUNDLE", text)
                    for text in generated_problems
                ],
            )
        )
        for text in generated_problems:
            print(f"  [GENERATED_BUNDLE] {text[:600]}")
        for name, module in _evaluators().items():
            if args.suite and name not in args.suite:
                continue
            result = module.run(desktop, browser, computed)
            suite_violations = evaluators.judge(result, entries, today=today)
            write_suite(result, suite_violations, entries, today=today)
            print(_summary_line(name, suite_violations), result.counts())
            for violation in suite_violations:
                print(f"  [{violation.code}] {violation.message[:600]}")
                if violation.proposal is not None:
                    print("  proposal:", json.dumps(violation.proposal))
        if args.tier_b:
            violations_b = tier_b_audit(reference, desktop, browser, computed, entries, today)
            print(_summary_line("real", violations_b))
            for violation in violations_b:
                print(f"  [{violation.code}] {violation.message[:600]}")
                if violation.proposal is not None:
                    print("  proposal:", json.dumps(violation.proposal))
        return 0
    finally:
        browser.close()
        desktop.close()


def tier_b_audit(reference, desktop, browser, computed, entries, today: date) -> list[Violation]:
    """B1-B4 on the real engine; writes tests/output/wasm-parity/real.{json,md}."""
    import dataclasses

    from . import evaluators, ledger, real_engine, tier_b
    from .ledger import Violation

    violations: list[Violation] = []
    with real_engine.real_engine() as real:
        real.use_reference(reference)
        parity = tier_b.macro_parity(real, browser)
        if any(parity.values()):
            violations.append(
                Violation(
                    "TIER_B",
                    "SIMULATION_DRIFT",
                    f"the real macro catalog differs from the simulation: {parity}",
                )
            )
        x86_only, wasm_only = tier_b.staleness(real, browser)
        print(f"  staleness: x86-only {sorted(x86_only)}; wasm-only {sorted(wasm_only)}")
        stale = ledger.reconcile(
            [e for e in entries if e.kind == tier_b.STALE_KIND], x86_only, today=today
        )
        for target in stale.unregistered:
            violations.append(
                Violation(
                    "TIER_B",
                    "UNREGISTERED_GAP",
                    f"the real engine lacks {target!r}: register it as {tier_b.STALE_KIND} "
                    "or rebuild the wasm bundles",
                    proposal=ledger.proposal(tier_b.STALE_KIND, target),
                )
            )
        for target, entry_id in sorted(stale.expired.items()):
            violations.append(
                Violation(
                    "TIER_B",
                    "EXPIRED_REGISTRATION",
                    f"{target!r} is still missing from the wasm bundles but registration "
                    f"{entry_id!r} expired: rebuild, or re-register with a reason",
                )
            )
        if stale.stale:
            violations.append(
                Violation(
                    "TIER_B",
                    "STALE_REGISTRATION",
                    f"functions registered as missing now exist in the wasm bundles — remove "
                    f"them from known_gaps.json: {stale.stale}",
                )
            )
        result = tier_b.run(
            desktop,
            real,
            dataclasses.replace(computed, stale_wasm_functions=tuple(sorted(x86_only))),
        )
        violations += evaluators.judge(result, entries, today=today, gate="TIER_B")
        write_suite(result, violations, entries, today=today, stem="real")
        return violations


def _evaluators() -> dict:
    from .evaluators import cql, fhirpath, omop, viewdef

    return {
        cql.SUITE: cql,
        fhirpath.SUITE: fhirpath,
        viewdef.SUITE: viewdef,
        omop.SUITE: omop,
    }


if __name__ == "__main__":
    try:
        raise SystemExit(cli())
    except EnvironmentInputMissing as exc:  # environment input, not a parity finding
        raise SystemExit(str(exc)) from exc
