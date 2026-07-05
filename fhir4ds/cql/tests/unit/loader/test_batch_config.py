"""Step 1 — config knob tests for AutoCoderConfig / NotesPipelineConfig.

Verifies the FDD §"Step 1" invariants:
- Defaults preserve current behavior (``batch_size=1, workers=1``)
- ``parallel_threshold`` defaults to 200 on NotesPipelineConfig
- Both dataclasses remain ``frozen=True``
- All 9 cross-config combinations construct cleanly
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from fhir4ds.cql.loader.auto_coder import AutoCoderConfig
from fhir4ds.cql.loader.notes_pipeline import NotesPipelineConfig


def test_auto_coder_defaults_preserve_behavior():
    cfg = AutoCoderConfig()
    assert cfg.batch_size == 1
    assert cfg.workers == 1


def test_notes_pipeline_defaults_preserve_behavior():
    cfg = NotesPipelineConfig()
    assert cfg.batch_size == 1
    assert cfg.workers == 1
    assert cfg.parallel_threshold == 200


def test_auto_coder_config_remains_frozen():
    cfg = AutoCoderConfig()
    with pytest.raises(FrozenInstanceError):
        cfg.batch_size = 10  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        cfg.workers = 4  # type: ignore[misc]


def test_notes_pipeline_config_remains_frozen():
    cfg = NotesPipelineConfig()
    with pytest.raises(FrozenInstanceError):
        cfg.batch_size = 10  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        cfg.workers = 4  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        cfg.parallel_threshold = 50  # type: ignore[misc]


def test_auto_coder_replace_works():
    cfg = AutoCoderConfig()
    cfg2 = replace(cfg, batch_size=500, workers=4)
    assert cfg2.batch_size == 500
    assert cfg2.workers == 4
    # Original untouched
    assert cfg.batch_size == 1
    assert cfg.workers == 1


def test_notes_pipeline_replace_works():
    cfg = NotesPipelineConfig()
    cfg2 = replace(cfg, batch_size=10, workers=2, parallel_threshold=50)
    assert cfg2.batch_size == 10
    assert cfg2.workers == 2
    assert cfg2.parallel_threshold == 50


@pytest.mark.parametrize("batch_size", [1, 10, 500])
@pytest.mark.parametrize("workers", [1, 2, 4])
def test_auto_coder_cross_config_matrix(batch_size, workers):
    """All 9 combinations of (batch_size, workers) construct cleanly."""
    cfg = AutoCoderConfig(batch_size=batch_size, workers=workers)
    assert cfg.batch_size == batch_size
    assert cfg.workers == workers


@pytest.mark.parametrize("batch_size", [1, 10, 500])
@pytest.mark.parametrize("workers", [1, 2, 4])
def test_notes_pipeline_cross_config_matrix(batch_size, workers):
    """All 9 combinations of (batch_size, workers) construct cleanly."""
    cfg = NotesPipelineConfig(
        batch_size=batch_size, workers=workers, parallel_threshold=10
    )
    assert cfg.batch_size == batch_size
    assert cfg.workers == workers
    assert cfg.parallel_threshold == 10


def test_parallel_threshold_zero_is_valid():
    """Users with pre-warmed medspaCy may set threshold to 0."""
    cfg = NotesPipelineConfig(parallel_threshold=0)
    assert cfg.parallel_threshold == 0
