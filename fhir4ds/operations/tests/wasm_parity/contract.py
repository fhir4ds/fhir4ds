"""Step 0 contract gates T1-T7 (plan section 4.3).

The contract is computed from the LIVE desktop catalog after ``register()``,
never from source text, and it iterates desktop macros only -- internal shadow
functions (``__fhir4ds_py_*``) need no exclusion list.

"Natively provided" (T5) is inferred from the shipped x86 bundles in Tier A and
made exact against the ``.wasm`` binaries in Tier B.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .ledger import Entry, Violation, proposal, reconcile
from .reference_bundle import ReferenceBundle, app_macro_files
from .surfaces import (
    browser_sim_connection,
    builtin_names,
    catalog,
    macro_definitions,
    signatures,
    simulator_fidelity,
)

MACRO_TYPES = ("macro", "table_macro")
# Names exported by the reference module but deliberately not registered by it.
REFERENCE_UNREGISTERED = frozenset({"resolve"})


@dataclass(frozen=True)
class Contract:
    """Everything the two surfaces differ on, at name and file level."""

    reference_statement_count: int
    reference_registration_mismatch: tuple[str, ...]  # T1: names vs REGISTERED_MACRO_NAMES
    desktop_names: frozenset[str]  # every name in the desktop catalog
    browser_names: frozenset[str]  # every name in the simulated browser catalog
    wasm_only_macros: tuple[str, ...]  # T3
    body_drift: dict[str, tuple[str, str]]  # T4: name -> (browser body, desktop body)
    desktop_only_uncovered: tuple[str, ...]  # T5
    signature_drift: dict[str, tuple[tuple, tuple]]  # name -> (desktop, browser) signatures
    macro_vs_native: tuple[str, ...]  # desktop macro; the browser runs a native namesake
    app_copies: tuple[tuple[str, str], ...]  # T6: (repo-relative path, status)
    # Tier B fills this in: x86-bundle functions the SHIPPED wasm bundles lack. Until then
    # "natively provided" is the x86 proxy.
    stale_wasm_functions: tuple[str, ...] = ()

    def flagged_names(self) -> frozenset[str]:
        """Names known to differ between desktop and the browser contract."""
        return frozenset(
            name.lower()
            for name in (
                *self.wasm_only_macros,
                *self.body_drift,
                *self.desktop_only_uncovered,
                *self.signature_drift,
                *self.macro_vs_native,
                *self.stale_wasm_functions,
            )
        )


def compute(desktop, reference: ReferenceBundle) -> Contract:
    """Compute the contract between the desktop connection and the simulation."""
    sim = browser_sim_connection(reference)
    try:
        desktop_cat = catalog(desktop)
        browser_cat = catalog(sim)
        desktop_bodies = macro_definitions(desktop)
        browser_bodies = macro_definitions(sim)
        desktop_sigs = signatures(desktop)
        browser_sigs = signatures(sim)
    finally:
        sim.close()

    builtin_macros = builtin_names("macro") | builtin_names("table_macro")
    builtin_all = builtin_names()
    ts_names = reference.lower_names
    desktop_macros = {n: b for n, b in desktop_bodies.items() if n not in builtin_macros}
    desktop_name_set = frozenset(desktop_cat)
    browser_name_set = frozenset(browser_cat)
    # Builtins + the bundled C++ functions: everything the simulation has that
    # did not come from the reference statements.
    native_names = browser_name_set - ts_names

    wasm_only = tuple(sorted(ts_names - frozenset(desktop_macros)))
    body_drift = {
        name: (browser_bodies[name], desktop_macros[name])
        for name in sorted(ts_names & frozenset(desktop_macros))
        if name in browser_bodies and browser_bodies[name] != desktop_macros[name]
    }
    desktop_only = sorted(frozenset(desktop_macros) - ts_names)
    signature_drift = {
        name: (desktop_sigs[name], browser_sigs[name])
        for name in sorted((desktop_name_set & browser_name_set) - builtin_all)
        if desktop_sigs.get(name)
        and browser_sigs.get(name)
        and desktop_sigs[name] != browser_sigs[name]
    }
    registered = {name.lower() for name in reference.registered_names}
    registered_mismatch = tuple(
        sorted((registered - ts_names) - {n.lower() for n in REFERENCE_UNREGISTERED})
    ) + tuple(sorted(ts_names - registered))
    return Contract(
        reference_statement_count=len(reference.statements),
        reference_registration_mismatch=registered_mismatch,
        desktop_names=desktop_name_set,
        browser_names=browser_name_set,
        wasm_only_macros=wasm_only,
        body_drift=body_drift,
        desktop_only_uncovered=tuple(n for n in desktop_only if n not in native_names),
        signature_drift=signature_drift,
        macro_vs_native=tuple(n for n in desktop_only if n in native_names),
        app_copies=tuple(
            (path.relative_to(reference.path.parents[4]).as_posix(), status)
            for path, status in app_macro_files(reference.path)
        ),
    )


def check_reference(contract: Contract) -> list[Violation]:
    """T1: the reference statements and the module's own name export agree."""
    if not contract.reference_registration_mismatch:
        return []
    return [
        Violation(
            "T1",
            "REFERENCE_EXPORT_DRIFT",
            "CQL_MACRO_SQL names and REGISTERED_MACRO_NAMES disagree: "
            f"{list(contract.reference_registration_mismatch)}",
        )
    ]


def check_simulator(reference: ReferenceBundle) -> list[Violation]:
    """T2: the simulation is exactly bare + bundles + reference statements."""
    fidelity = simulator_fidelity(reference)
    return [
        Violation("T2", "SIMULATOR_UNFAITHFUL", f"{label}: {list(names)}")
        for label, names in fidelity.problems().items()
        if names
    ]


def evaluate(
    contract: Contract,
    entries: list[Entry],
    *,
    today: date,
    extra_observed: dict[str, list[str]] | None = None,
) -> list[Violation]:
    """T3-T6 against the ledger. ``extra_observed`` maps a file-level kind to
    its observed targets (T7 and Tier B supply theirs this way)."""
    observed_sets: dict[str, tuple[str, ...]] = {
        "WASM_ONLY_MACRO": contract.wasm_only_macros,
        "TS_BODY_DRIFT": tuple(contract.body_drift),
        "MISSING_IN_BROWSER": contract.desktop_only_uncovered,
        "SIGNATURE_DIFF": tuple(contract.signature_drift),
        "BUNDLE_DRIFT": tuple(p for p, status in contract.app_copies if status == "differs"),
        # MACRO_VS_NATIVE is reported, not required (plan T5: natively provided is OK);
        # a registration is still checked for staleness and expiry.
        "MACRO_VS_NATIVE": contract.macro_vs_native,
    }
    required = {"MACRO_VS_NATIVE": False}
    for kind, targets in (extra_observed or {}).items():
        observed_sets[kind] = tuple(targets)
    violations: list[Violation] = []
    for kind, observed in observed_sets.items():
        rec = reconcile([e for e in entries if e.kind == kind], observed, today=today)
        violations.extend(
            Violation("T3-T7", code, message, proposal=prop)
            for code, message, prop in _violation_parts(
                kind, observed, rec, required.get(kind, True)
            )
        )
    return violations


FILE_LEVEL_KINDS = ("STALE_WASM_BUNDLE", "WASM_COPY_DRIFT", "PROVENANCE_UNKNOWN")


def evaluate_files(entries: list[Entry], observed: dict[str, list[str]], *, today: date) -> list[Violation]:
    """T7: file-level gap kinds (shipped bundles) against the ledger.

    ``observed`` maps a kind in ``FILE_LEVEL_KINDS`` to the targets seen right
    now (``shipped_bundles.observe``). Every observed gap must be registered.
    """
    violations: list[Violation] = []
    for kind in FILE_LEVEL_KINDS:
        if kind not in observed:
            continue
        targets = observed[kind]
        rec = reconcile([e for e in entries if e.kind == kind], targets, today=today)
        violations.extend(
            Violation("T7", code, message, proposal=prop)
            for code, message, prop in _violation_parts(kind, targets, rec, True)
        )
    return violations


def _violation_parts(kind, observed, rec, is_required: bool):
    for item, entry_id in sorted(rec.expired.items()):
        yield (
            "EXPIRED_REGISTRATION",
            f"{kind}: entry {entry_id!r} expired but still covers {item!r}; fix the gap or re-register with a reason",
            None,
        )
    if rec.stale:
        yield (
            "STALE_REGISTRATION",
            f"{kind}: registered gaps no longer reproduce — remove them from known_gaps.json: {rec.stale}",
            None,
        )
    if is_required and rec.unregistered:
        yield (
            "UNREGISTERED_GAP",
            f"{kind}: {len(rec.unregistered)} unregistered gap(s): {rec.unregistered}",
            proposal(kind, rec.unregistered if len(rec.unregistered) > 1 else rec.unregistered[0]),
        )
