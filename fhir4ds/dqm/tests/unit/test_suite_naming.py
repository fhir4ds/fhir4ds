"""Suite naming: canonical names with legacy aliases (2026-11-12).

The DQM conformance suites were renamed to describe WHAT they are rather than
the content-package year:

    qi-core-2025 <- "2025"    (ecqm-content-qicore-2025)
    us-core-2025 <- "cms2025" (dqm-content-cms-2025, the CMS US Core measures)
    qi-core-2026 <- "2026"    (dqm-content-qicore-2026)

Names carry the release year on purpose: more content releases are expected, so
a bare "qi-core" would silently mean a different suite next year.

Old spellings stay accepted because they appear throughout CI jobs, docs and
muscle memory. These tests pin BOTH directions so a future rename cannot
silently break an existing invocation.
"""

from __future__ import annotations

import pytest

from fhir4ds.dqm.tests.conformance.config import (
    CANONICAL_SUITES,
    SUITE_QI_CORE_2025,
    SUITE_QI_CORE_2026,
    SUITE_US_CORE_2025,
    get_suite_paths,
    normalize_suite,
)


class TestSuiteAliases:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("qi-core-2025", SUITE_QI_CORE_2025),
            ("2025", SUITE_QI_CORE_2025),
            ("us-core-2025", SUITE_US_CORE_2025),
            ("cms2025", SUITE_US_CORE_2025),
            ("qi-core-2026", SUITE_QI_CORE_2026),
            ("2026", SUITE_QI_CORE_2026),
            # unversioned names mean the 2025 release and are not a "latest"
            ("qi-core", SUITE_QI_CORE_2025),
            ("us-core", SUITE_US_CORE_2025),
            ("  US-CORE-2025  ", SUITE_US_CORE_2025),  # case/space insensitive
        ],
    )
    def test_legacy_and_canonical_names_normalise(self, given, expected):
        assert normalize_suite(given) == expected

    def test_none_defaults_to_qi_core(self):
        assert normalize_suite(None) == SUITE_QI_CORE_2025

    def test_unknown_name_is_a_clear_error(self):
        with pytest.raises(ValueError) as excinfo:
            normalize_suite("cms-2024")
        assert "Unknown suite" in str(excinfo.value)
        # the message must tell the caller what IS valid
        assert SUITE_US_CORE_2025 in str(excinfo.value)

    @pytest.mark.parametrize("suite", CANONICAL_SUITES)
    def test_every_canonical_suite_resolves_to_a_directory(self, suite):
        paths = get_suite_paths(suite)
        assert paths["suite_dir"].name
        assert paths["cql_dir"].parent.parent == paths["suite_dir"]

    def test_alias_and_canonical_resolve_to_the_same_paths(self):
        for alias, canonical in (
            ("2025", "qi-core-2025"),
            ("cms2025", "us-core-2025"),
            ("qi-core", "qi-core-2025"),
            ("us-core", "us-core-2025"),
        ):
            assert get_suite_paths(alias) == get_suite_paths(canonical)
