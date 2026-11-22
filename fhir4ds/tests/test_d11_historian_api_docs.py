"""QA-D11H-001..003 (v0.0.26 Domain 11 HISTORIAN) — docstring-body contract.

The Domain 11 HISTORIAN docstring walk found that documentation which
EXISTS but is not ATTACHED is invisible to help()/pydoc/IDE consumers:

* QA-D11H-001: ``FHIRDataLoader.load_valuesets`` had its (accurate)
  docstring placed AFTER executable statements, so the string was a
  no-op expression and ``__doc__`` was ``None``.
* QA-D11H-002: ``evaluate_measure_legacy`` gained a ``strict_profiles``
  parameter (strict-profile campaign) without documenting it.
* QA-D11H-003: ``piqi.run_terminology_sam`` documented
  ``patient_id / source_table`` jointly as "the usual scoping knobs"
  with no defaults.
"""
import inspect

from fhir4ds.cql.loader import FHIRDataLoader
from fhir4ds.piqi import run_terminology_sam


def test_load_valuesets_docstring_is_attached_and_documents_contract():
    doc = FHIRDataLoader.load_valuesets.__doc__
    assert doc, "load_valuesets docstring must be attached (was a dangling string)"
    assert "Args:" in doc
    assert "valuesets" in doc and "table_name" in doc
    # defaults and the additive-reload contract are part of the documented API
    assert '"valueset_codes"' in doc
    assert "ADDITIVE" in doc or "additive" in doc


def test_every_public_fhir_loader_method_has_attached_docstring():
    loader_docless = [
        name
        for name in dir(FHIRDataLoader)
        if not name.startswith("_")
        and callable(getattr(FHIRDataLoader, name, None))
        and not (inspect.getdoc(getattr(FHIRDataLoader, name)) or "").strip()
    ]
    assert not loader_docless, f"public FHIRDataLoader methods without docstrings: {loader_docless}"


def test_evaluate_measure_legacy_documents_strict_profiles():
    from fhir4ds.cql import evaluate_measure_legacy

    doc = inspect.getdoc(evaluate_measure_legacy) or ""
    assert "strict_profiles" in doc, (
        "strict_profiles (default True) is a public kwarg of "
        "evaluate_measure_legacy and must be documented"
    )


def test_run_terminology_sam_documents_scoping_defaults():
    doc = inspect.getdoc(run_terminology_sam) or ""
    assert "patient_id" in doc and "source_table" in doc
    assert "None" in doc.split("patient_id")[1][:200], (
        "patient_id default None must be documented"
    )
    assert '"resources"' in doc, "source_table default must be documented"
