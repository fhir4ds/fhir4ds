"""Regression tests for iteration-7 Domain-9 (audit) fixes.

Covers:
- QA-016: `audit_mode='full'` SQL emission must not emit unbound `p` alias
  (partial fix: ast_helpers.py/cte_manager.py now use `_pt`), AND the
  remaining DuckDB ``struct_pack`` binder error on CMS71/CMS996/CMS135 is
  resolved at the source by ensuring every struct_pack argument is named.
- QA-017: When a patient is in denominator_exclusion, the numerator criteria
  are not evaluated for that patient, so any numerator evidence emitted by
  the audit SQL must be pruned to avoid misleading narratives (causal
  correctness per CMS eCQM Logic and Implementation Guidance).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, "/mnt/d/fhir4ds")

from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.parser.ast_nodes import Definition
from fhir4ds.dqm.artifacts import FileArtifactResolver
from fhir4ds.dqm.evaluator import MeasureEvaluator
from fhir4ds.dqm.models import MeasureResult
from fhir4ds.dqm.tests.conformance.config import (
    SUPPLEMENTAL_VALUESET_DIR,
    VALIDATOR_VALUESET_DIR,
    MeasureConfig,
    get_suite_paths,
)
from fhir4ds.dqm.tests.conformance.database import BenchmarkDatabase
from fhir4ds.dqm.tests.conformance.loader import load_test_suite
from fhir4ds.dqm.tests.conformance.runner import (
    _normalize_population_definitions,
    _translate_measure,
)
from fhir4ds.dqm.types import (
    AuditPersona,
    GroupMap,
    PopulationEntry,
    PopulationMap,
)

SUITE = get_suite_paths("2025")


def _make_exclusion_pop_map() -> PopulationMap:
    """Build a minimal PopulationMap for audit-pruning tests."""
    return PopulationMap(
        measure_id="test-measure",
        cql_library_ref="http://example.com/Library/Test",
        groups=[
            GroupMap(
                group_id="group-0",
                population_basis="boolean",
                populations=[
                    PopulationEntry(
                        "initial-population", "group-0", "Initial Population",
                        AuditPersona.INCLUSION,
                    ),
                    PopulationEntry(
                        "denominator", "group-0", "Denominator",
                        AuditPersona.INCLUSION,
                    ),
                    PopulationEntry(
                        "denominator-exclusion", "group-0", "Denominator Exclusion",
                        AuditPersona.EXCLUSION,
                    ),
                    PopulationEntry(
                        "denominator-exception", "group-0", "Denominator Exception",
                        AuditPersona.EXCLUSION,
                    ),
                    PopulationEntry(
                        "numerator", "group-0", "Numerator",
                        AuditPersona.NUMERATOR,
                    ),
                    PopulationEntry(
                        "numerator-exclusion", "group-0", "Numerator Exclusion",
                        AuditPersona.EXCLUSION,
                    ),
                ],
            )
        ],
    )


def _make_measure_config(cms_id: str, cql_filename: str) -> MeasureConfig:
    cql_path = SUITE["cql_dir"] / cql_filename
    test_dir = SUITE["bundle_dir"] / cql_filename.stem / f"{cql_filename.stem}-files"
    return MeasureConfig(
        id=cms_id,
        name=cql_filename.stem,
        cql_path=cql_path,
        test_dir=test_dir,
        include_paths=[SUITE["cql_dir"]],
        valueset_paths=[SUITE["valueset_dir"]],
        population_definitions=[
            "Initial Population",
            "Denominator",
            "Denominator Exclusions",
            "Denominator Exceptions",
            "Numerator",
            "Numerator Exclusions",
            "Measure Population",
            "Measure Population Exclusions",
            "Measure Observations",
        ],
    )


class TestQA016UnboundAliasFix:
    """QA-016: ast_helpers.py/cte_manager.py used unbound `p` alias in audit SQL.

    The fix replaces `p.patient_id` with `_pt.patient_id` (the actual outer
    patient alias). After the fix:
    - The emitted SQL must NOT contain unbound `p.patient_id` references in
      the audit subqueries emitted by ``_inject_audit_evidence`` or by the
      audit CTE pre-compute lookup in cte_manager.py.
    - CMS165v11 FULL audit must execute (was previously crashing with
      BinderException "Referenced table p not found").
    """

    def test_full_audit_sql_has_no_unbound_p_alias(self) -> None:
        """The audit SQL emitted for a measure must not contain `= p.patient_id`
        references that would be unbound at the outer patient FROM clause
        (which uses alias ``_pt``).
        """
        db = BenchmarkDatabase()
        db.load_all_valuesets(
            [SUITE["valueset_dir"], VALIDATOR_VALUESET_DIR, SUPPLEMENTAL_VALUESET_DIR]
        )
        cql_filename = SUITE["cql_dir"] / "CMS165FHIRControllingHighBloodPressure.cql"
        if not cql_filename.exists():
            import pytest

            pytest.skip(f"CMS165 fixture not found at {cql_filename}")
        mc = _make_measure_config("CMS165", cql_filename)
        db.load_all_test_data([mc])
        db.unscope_resources()

        library = parse_cql(cql_filename.read_text())
        actual_defs = {
            stmt.name for stmt in library.statements if isinstance(stmt, Definition)
        }
        normalized_pop_defs, _ = _normalize_population_definitions(
            mc.population_definitions, actual_defs
        )
        output_columns = {name: name for name in normalized_pop_defs}
        test_suite = load_test_suite(mc)
        mp_params = {"Measurement Period": test_suite.measurement_period}
        patient_ids = [tc.patient_id for tc in test_suite.test_cases]

        sql, _, _ = _translate_measure(
            db.conn,
            library,
            mc,
            output_columns,
            mp_params,
            patient_ids,
            audit_mode=True,
            audit_expressions=True,
        )

        # The outer FROM aliases the patient table as `_pt`, never `p`.
        # Audit subqueries emitted by _inject_audit_evidence and the
        # cte_manager pre-compute lookup must use `_pt.patient_id`.
        import re

        audit_subquery_patterns = [
            r"AS _sub WHERE _sub\.patient_id = p\.patient_id",
            r"AS __cmp_\d+ WHERE __cmp_\d+\.patient_id = p\.patient_id",
            r"AS __bev_\d+ WHERE __bev_\d+\.patient_id = p\.patient_id",
            r"AS __pre WHERE __pre\.patient_id = p\.patient_id",
        ]
        for pat in audit_subquery_patterns:
            matches = re.findall(pat, sql)
            assert matches == [], (
                f"Unbound `p.patient_id` reference found in audit SQL "
                f"(pattern {pat!r}): {matches[:3]}"
            )

    def test_cms165_full_audit_executes(self) -> None:
        """CMS165 was failing FULL audit with BinderException 'Referenced
        table p not found'. After the QA-016 fix, FULL audit must execute.
        """
        import pytest

        cql_filename = SUITE["cql_dir"] / "CMS165FHIRControllingHighBloodPressure.cql"
        if not cql_filename.exists():
            pytest.skip(f"CMS165 fixture not found at {cql_filename}")

        db = BenchmarkDatabase()
        db.load_all_valuesets(
            [SUITE["valueset_dir"], VALIDATOR_VALUESET_DIR, SUPPLEMENTAL_VALUESET_DIR]
        )
        mc = _make_measure_config("CMS165", cql_filename)
        db.load_all_test_data([mc])
        db.unscope_resources()

        library = parse_cql(cql_filename.read_text())
        actual_defs = {
            stmt.name for stmt in library.statements if isinstance(stmt, Definition)
        }
        normalized_pop_defs, _ = _normalize_population_definitions(
            mc.population_definitions, actual_defs
        )
        output_columns = {name: name for name in normalized_pop_defs}
        test_suite = load_test_suite(mc)
        mp_params = {"Measurement Period": test_suite.measurement_period}
        patient_ids = [tc.patient_id for tc in test_suite.test_cases]

        sql, _, _ = _translate_measure(
            db.conn,
            library,
            mc,
            output_columns,
            mp_params,
            patient_ids,
            audit_mode=True,
            audit_expressions=True,
        )

        db.conn.execute("SET max_expression_depth TO 10000")
        # Must not raise BinderException.
        db.conn.execute(sql).df()


class TestQA017NumeratorPrunedWhenExcluded:
    """QA-017: when a patient is in denominator_exclusion, the numerator
    cell must have its evidence pruned (replaced with empty) so that
    downstream narratives do not cite denominator-criteria evidence as if
    it were numerator evidence.

    Per CMS eCQM Logic and Implementation Guidance, denominator exclusions
    REMOVE the patient from denominator AND numerator. The audit trail for
    an excluded patient's numerator cell must NOT retain denominator-criteria
    evidence; doing so misleads clinicians into thinking the numerator
    criteria were evaluated.
    """

    def test_excluded_patient_numerator_evidence_pruned(self) -> None:
        """Patient in denominator_exclusion has numerator evidence pruned."""
        evaluator = MeasureEvaluator(None)
        pop_map = _make_exclusion_pop_map()
        df = pd.DataFrame({
            "patient_id": ["p1"],
            "initial_population": [{"result": True, "evidence": []}],
            "denominator": [{"result": True, "evidence": []}],
            "denominator_exclusion": [{
                "result": True,
                "evidence": [{"operator": "exists", "target": "Procedure/lvad"}],
            }],
            "denominator_exception": [{"result": False, "evidence": []}],
            # NOTE: numerator cell contains denominator-criteria evidence
            # (the LVSD encounter) — this is the QA-017 bug shape.
            "numerator": [{
                "result": False,
                "evidence": [{
                    "operator": "exists",
                    "target": "Encounter/lvsd-encounter",
                    "threshold": "AHA.Heart Failure Outpatient Encounter",
                }],
            }],
            "numerator_exclusion": [{"result": False, "evidence": []}],
        })

        pruned = evaluator._prune_population_evidence(df, pop_map)
        numerator_cell = pruned.loc[0, "numerator"]

        # The numerator evidence must be empty (pruned) because the patient
        # is excluded from denominator.
        assert numerator_cell["evidence"] == [], (
            f"Expected numerator evidence to be pruned for excluded patient, "
            f"got: {numerator_cell['evidence']}"
        )
        # effective_result must be False (numerator not evaluated)
        assert numerator_cell.get("effective_result") is False

    def test_non_excluded_patient_numerator_evidence_preserved(self) -> None:
        """Patient NOT in denominator_exclusion keeps numerator evidence."""
        evaluator = MeasureEvaluator(None)
        pop_map = _make_exclusion_pop_map()
        df = pd.DataFrame({
            "patient_id": ["p2"],
            "initial_population": [{"result": True, "evidence": []}],
            "denominator": [{"result": True, "evidence": []}],
            "denominator_exclusion": [{"result": False, "evidence": []}],
            "denominator_exception": [{"result": False, "evidence": []}],
            "numerator": [{
                "result": False,
                "evidence": [{
                    "operator": "exists",
                    "target": "MedicationRequest/acei",
                    "threshold": "ACE Inhibitor",
                }],
            }],
            "numerator_exclusion": [{"result": False, "evidence": []}],
        })

        pruned = evaluator._prune_population_evidence(df, pop_map)
        numerator_cell = pruned.loc[0, "numerator"]

        # Evidence must be preserved (patient is not excluded). The audit
        # engine reshapes the evidence into the standard form with
        # `findings` containing the original target.
        assert len(numerator_cell["evidence"]) == 1
        ev = numerator_cell["evidence"][0]
        # The target may be carried in `findings` after pruning.
        findings_targets = [
            (f.get("target") if isinstance(f, dict) else None)
            for f in ev.get("findings", [])
        ]
        assert "MedicationRequest/acei" in findings_targets or ev.get("target") == "MedicationRequest/acei"


class TestQA016FullAuditPublicAPI:
    """QA-016 public-API regression: ``MeasureEvaluator.evaluate`` boundary.

    The existing ``test_cms165_full_audit_executes`` exercises the audit SQL
    through ``_translate_measure`` (the conformance runner helper). These tests
    exercise the public ``MeasureEvaluator.evaluate(audit_mode='full')`` API
    directly against the canonical CMS measure bundles so that the FULL-audit
    path works on every CMS measure used in iteration-7 probing (CMS71, CMS996,
    CMS135, CMS165). The struct_pack binder error previously seen on
    CMS71/CMS996/CMS135 is resolved at the SQL emission source by ensuring
    every struct_pack argument carries a name.
    """

    @staticmethod
    def _bundle_path(bundle_stem: str) -> Path:
        """Return the canonical CMS measure bundle JSON path from the suite."""
        return SUITE["bundle_dir"] / bundle_stem / f"{bundle_stem}-bundle.json"

    @staticmethod
    def _make_resolver_for_loaded_db(cql_dir: Path) -> FileArtifactResolver:
        """Build a resolver that skips on-disk valueset resolution.

        ``BenchmarkDatabase.load_all_valuesets`` already loads ValueSet JSON
        into the connection's terminology UDF. The default FileArtifactResolver
        re-reads them from disk (and may hit ambiguous-version errors when the
        suite ships duplicate files). We only need it for include/library
        resolution, so override ``resolve_valuesets_for_cql`` to return empty.
        """

        class _NoDiskValueSetResolver(FileArtifactResolver):
            def resolve_valuesets_for_cql(self, cql_text: str) -> list[dict]:  # noqa: ARG002
                return []

            def resolve_valueset(self, ref) -> dict:  # noqa: ARG002
                return {}

        return _NoDiskValueSetResolver(
            include_paths=[str(cql_dir)],
            valueset_paths=None,
        )

    def test_cms165_full_audit_via_public_evaluate(self) -> None:
        """CMS165 FULL audit must succeed through the public evaluate() API.

        This locks in the partial fix (unbound ``p`` -> ``_pt``) at the
        boundary callers actually use. Was previously crashing with
        ``BinderException: Referenced table "p" not found``.
        """
        import pytest

        cql_filename = SUITE["cql_dir"] / "CMS165FHIRControllingHighBloodPressure.cql"
        bundle_path = self._bundle_path("CMS165FHIRControllingHighBloodPressure")
        if not cql_filename.exists() or not bundle_path.exists():
            pytest.skip(
                f"CMS165 fixture not found (cql={cql_filename.exists()}, "
                f"bundle={bundle_path.exists()})"
            )

        db = BenchmarkDatabase()
        db.load_all_valuesets(
            [SUITE["valueset_dir"], VALIDATOR_VALUESET_DIR, SUPPLEMENTAL_VALUESET_DIR]
        )
        mc = _make_measure_config("CMS165", cql_filename)
        db.load_all_test_data([mc])
        db.unscope_resources()

        test_suite = load_test_suite(mc)
        mp_params = {"Measurement Period": test_suite.measurement_period}
        patient_ids = [tc.patient_id for tc in test_suite.test_cases]

        evaluator = MeasureEvaluator(db.conn)
        resolver = self._make_resolver_for_loaded_db(SUITE["cql_dir"])
        result = evaluator.evaluate(
            measure_bundle=str(bundle_path),
            cql_library_path=str(cql_filename),
            parameters=mp_params,
            audit_mode="full",
            patient_ids=patient_ids,
            include_paths=[str(SUITE["cql_dir"])],
            artifact_resolver=resolver,
        )
        # Assert no DQMError (would have raised above) and valid MeasureResult.
        assert isinstance(result, MeasureResult)
        assert result.dataframe is not None
        assert "patient_id" in result.dataframe.columns

    def test_cms71_full_audit_via_public_evaluate(self) -> None:
        """CMS71 FULL audit must succeed through the public evaluate() API.

        Per QA-016: the DuckDB binder error ``Need named argument for struct
        pack`` was previously raised on this measure's audit tree. The fix
        ensures every struct_pack argument in the emitted audit SQL carries
        an explicit name, so the binder no longer fails.
        """
        cql_filename = SUITE["cql_dir"] / "CMS71FHIRSTKAnticoagAFFlutter.cql"
        bundle_path = self._bundle_path("CMS71FHIRSTKAnticoagAFFlutter")
        if not cql_filename.exists() or not bundle_path.exists():
            pytest.skip(
                f"CMS71 fixture not found (cql={cql_filename.exists()}, "
                f"bundle={bundle_path.exists()})"
            )

        db = BenchmarkDatabase()
        db.load_all_valuesets(
            [SUITE["valueset_dir"], VALIDATOR_VALUESET_DIR, SUPPLEMENTAL_VALUESET_DIR]
        )
        mc = _make_measure_config("CMS71", cql_filename)
        db.load_all_test_data([mc])
        db.unscope_resources()

        test_suite = load_test_suite(mc)
        mp_params = {"Measurement Period": test_suite.measurement_period}
        patient_ids = [tc.patient_id for tc in test_suite.test_cases]

        evaluator = MeasureEvaluator(db.conn)
        resolver = self._make_resolver_for_loaded_db(SUITE["cql_dir"])
        result = evaluator.evaluate(
            measure_bundle=str(bundle_path),
            cql_library_path=str(cql_filename),
            parameters=mp_params,
            audit_mode="full",
            patient_ids=patient_ids,
            include_paths=[str(SUITE["cql_dir"])],
            artifact_resolver=resolver,
        )
        assert isinstance(result, MeasureResult)
        assert result.dataframe is not None
        assert "patient_id" in result.dataframe.columns

    def test_cms996_full_audit_via_public_evaluate(self) -> None:
        """CMS996 FULL audit must succeed through the public evaluate() API.

        Per QA-016: same root cause as CMS71 — struct_pack binder error
        triggered by an unnamed argument in the audit tree. The fix at the
        SQL emission source resolves this measure as well.
        """
        cql_filename = SUITE["cql_dir"] / "CMS996FHIRAptTxforSTEMI.cql"
        bundle_path = self._bundle_path("CMS996FHIRAptTxforSTEMI")
        if not cql_filename.exists() or not bundle_path.exists():
            pytest.skip(
                f"CMS996 fixture not found (cql={cql_filename.exists()}, "
                f"bundle={bundle_path.exists()})"
            )

        db = BenchmarkDatabase()
        db.load_all_valuesets(
            [SUITE["valueset_dir"], VALIDATOR_VALUESET_DIR, SUPPLEMENTAL_VALUESET_DIR]
        )
        mc = _make_measure_config("CMS996", cql_filename)
        db.load_all_test_data([mc])
        db.unscope_resources()

        test_suite = load_test_suite(mc)
        mp_params = {"Measurement Period": test_suite.measurement_period}
        patient_ids = [tc.patient_id for tc in test_suite.test_cases]

        evaluator = MeasureEvaluator(db.conn)
        resolver = self._make_resolver_for_loaded_db(SUITE["cql_dir"])
        result = evaluator.evaluate(
            measure_bundle=str(bundle_path),
            cql_library_path=str(cql_filename),
            parameters=mp_params,
            audit_mode="full",
            patient_ids=patient_ids,
            include_paths=[str(SUITE["cql_dir"])],
            artifact_resolver=resolver,
        )
        assert isinstance(result, MeasureResult)
        assert result.dataframe is not None
        assert "patient_id" in result.dataframe.columns

    def test_cms135_full_audit_via_public_evaluate(self) -> None:
        """CMS135 FULL audit must succeed through the public evaluate() API.

        Per QA-016: same root cause as CMS71 — struct_pack binder error
        triggered by an unnamed argument in the audit tree. The fix at the
        SQL emission source resolves this measure as well.
        """
        import pytest

        cql_filename = SUITE["cql_dir"] / "CMS135FHIRHFACEIorARBorARNIforLVSD.cql"
        bundle_path = self._bundle_path("CMS135FHIRHFACEIorARBorARNIforLVSD")
        if not cql_filename.exists() or not bundle_path.exists():
            pytest.skip(
                f"CMS135 fixture not found (cql={cql_filename.exists()}, "
                f"bundle={bundle_path.exists()})"
            )

        db = BenchmarkDatabase()
        db.load_all_valuesets(
            [SUITE["valueset_dir"], VALIDATOR_VALUESET_DIR, SUPPLEMENTAL_VALUESET_DIR]
        )
        mc = _make_measure_config("CMS135", cql_filename)
        db.load_all_test_data([mc])
        db.unscope_resources()

        test_suite = load_test_suite(mc)
        mp_params = {"Measurement Period": test_suite.measurement_period}
        patient_ids = [tc.patient_id for tc in test_suite.test_cases]

        evaluator = MeasureEvaluator(db.conn)
        resolver = self._make_resolver_for_loaded_db(SUITE["cql_dir"])
        result = evaluator.evaluate(
            measure_bundle=str(bundle_path),
            cql_library_path=str(cql_filename),
            parameters=mp_params,
            audit_mode="full",
            patient_ids=patient_ids,
            include_paths=[str(SUITE["cql_dir"])],
            artifact_resolver=resolver,
        )
        assert isinstance(result, MeasureResult)
        assert result.dataframe is not None
        assert "patient_id" in result.dataframe.columns

    def test_population_audit_works_for_cms71(self) -> None:
        """CMS71 POPULATION audit must succeed — the recommended workaround.

        This is the user-facing escape hatch documented in the hint. POPULATION
        audit mode is unaffected by the DuckDB binder quirk and works for all
        measures, so it must succeed where FULL audit fails.
        """
        import pytest

        cql_filename = SUITE["cql_dir"] / "CMS71FHIRSTKAnticoagAFFlutter.cql"
        bundle_path = self._bundle_path("CMS71FHIRSTKAnticoagAFFlutter")
        if not cql_filename.exists() or not bundle_path.exists():
            pytest.skip(
                f"CMS71 fixture not found (cql={cql_filename.exists()}, "
                f"bundle={bundle_path.exists()})"
            )

        db = BenchmarkDatabase()
        db.load_all_valuesets(
            [SUITE["valueset_dir"], VALIDATOR_VALUESET_DIR, SUPPLEMENTAL_VALUESET_DIR]
        )
        mc = _make_measure_config("CMS71", cql_filename)
        db.load_all_test_data([mc])
        db.unscope_resources()

        test_suite = load_test_suite(mc)
        mp_params = {"Measurement Period": test_suite.measurement_period}
        patient_ids = [tc.patient_id for tc in test_suite.test_cases]

        evaluator = MeasureEvaluator(db.conn)
        resolver = self._make_resolver_for_loaded_db(SUITE["cql_dir"])
        result = evaluator.evaluate(
            measure_bundle=str(bundle_path),
            cql_library_path=str(cql_filename),
            parameters=mp_params,
            audit_mode="population",
            patient_ids=patient_ids,
            include_paths=[str(SUITE["cql_dir"])],
            artifact_resolver=resolver,
        )
        assert isinstance(result, MeasureResult)
        assert result.dataframe is not None


class TestQA016SqlStructureRegression:
    """QA-016 SQL-structure regression: the emitted audit SQL for CMS71
    Numerator must not contain a deeply-nested audit_and chain inside the
    WHERE clause of a correlated EXISTS subquery.

    Before the fix, the with-such-that condition emitted
    ``struct_extract(audit_and(...), 'result')`` directly in the WHERE of
    the inner EXISTS, which triggered DuckDB's "Need named argument for
    struct pack" binder bug. The fix fully eliminates audit macros from
    such boolean contexts via ``_fully_demote_audit_to_bool`` because the
    outer per-patient audit CTE re-captures the evidence.

    This test asserts the structural shape: the emitted SQL for CMS71
    Numerator must NOT contain ``audit_and`` inside the WHERE of the
    MedicationRequest EXISTS subquery. It must also not contain the
    binder-bug-trigger pattern ``struct_extract(audit_and(`` at all.
    """

    def test_cms71_numerator_sql_has_no_binder_bug_pattern(self) -> None:
        import re

        cql_filename = SUITE["cql_dir"] / "CMS71FHIRSTKAnticoagAFFlutter.cql"
        if not cql_filename.exists():
            import pytest
            pytest.skip(f"CMS71 fixture not found at {cql_filename}")

        db = BenchmarkDatabase()
        db.load_all_valuesets(
            [SUITE["valueset_dir"], VALIDATOR_VALUESET_DIR, SUPPLEMENTAL_VALUESET_DIR]
        )
        mc = _make_measure_config("CMS71", cql_filename)
        db.load_all_test_data([mc])
        db.unscope_resources()

        library = parse_cql(cql_filename.read_text())
        actual_defs = {
            stmt.name for stmt in library.statements if isinstance(stmt, Definition)
        }
        normalized_pop_defs, _ = _normalize_population_definitions(
            mc.population_definitions, actual_defs
        )
        output_columns = {name: name for name in normalized_pop_defs}
        test_suite = load_test_suite(mc)
        mp_params = {"Measurement Period": test_suite.measurement_period}
        patient_ids = [tc.patient_id for tc in test_suite.test_cases]

        sql, _, _ = _translate_measure(
            db.conn,
            library,
            mc,
            output_columns,
            mp_params,
            patient_ids,
            audit_mode=True,
            audit_expressions=True,
        )

        # Extract the Numerator CTE body. Before the QA-016 fix, the body
        # contained `struct_extract(audit_and(...), 'result')` directly in
        # the WHERE clause of the MedicationRequest EXISTS subquery. The
        # fix eliminates these macros via _fully_demote_audit_to_bool.
        m = re.search(r'"Numerator" AS \((.*?)\),\n"', sql, re.DOTALL)
        assert m, "Numerator CTE not found in CMS71 audit SQL"
        numerator_body = m.group(1)

        # The binder-bug trigger pattern: audit_and/or/not/or_all macros
        # surviving inside a struct_extract(...) wrapper in the Numerator
        # CTE body. After the QA-016 fix, the with-such-that condition's
        # audit macros are fully eliminated.
        binder_bug_patterns = [
            r"struct_extract\(audit_and\(",
            r"struct_extract\(audit_or\(",
            r"struct_extract\(audit_not\(",
            r"struct_extract\(audit_or_all\(",
        ]
        for pat in binder_bug_patterns:
            matches = re.findall(pat, numerator_body)
            assert matches == [], (
                f"QA-016 binder-bug pattern {pat!r} found in CMS71 Numerator "
                f"CTE body ({len(matches)} occurrences). The fix should fully "
                f"demote audit macros via _fully_demote_audit_to_bool in the "
                f"with-such-that condition to avoid the DuckDB 'Need named "
                f"argument for struct pack' binder error."
            )

        # Sanity: the SQL must still execute cleanly.
        db.conn.execute("SET max_expression_depth TO 10000")
        db.conn.execute(sql).df()
