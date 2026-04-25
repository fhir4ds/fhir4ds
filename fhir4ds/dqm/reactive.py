"""
fhir4ds.dqm.reactive
====================
Incremental measure re-evaluation for source adapters that support delta
tracking via :meth:`~fhir4ds.sources.base.SourceAdapter.get_changed_patients`.

.. warning::
    Read the :class:`ReactiveEvaluator` limitations before use.  Using
    this class with unsupported measure types will produce silently
    incorrect results.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fhir4ds.sources.base import SourceAdapter


class ReactiveEvaluator:
    """
    Coordinates incremental measure re-evaluation for source adapters that
    support delta tracking.

    When patient data changes, :class:`ReactiveEvaluator` identifies the
    affected patients via
    :meth:`~fhir4ds.sources.base.SourceAdapter.get_changed_patients`,
    re-evaluates only those patients, and returns a delta result that can
    be merged into the existing population report.

    .. warning:: **Critical Limitations — READ BEFORE USE**

        1. **Patient-level measures only.**  This class is only correct for
           measures where each patient's result is independent of other
           patients.  Measures that derive weights or statistics from the
           full population (e.g. RAU risk adjustment measures) **cannot** be
           correctly updated incrementally — a partial re-evaluation changes
           weights for the evaluated patients without updating weights for
           the rest of the population.  Using :class:`ReactiveEvaluator`
           with such measures will produce silently incorrect results.

        2. **Deletion detection depends on adapter implementation.**  Adapters
           that cannot detect hard deletes will silently leave deleted
           patients in measure results.  Check
           ``adapter.supports_incremental()`` and review the adapter's
           :meth:`~fhir4ds.sources.base.SourceAdapter.get_changed_patients`
           documentation.

        3. **No concurrency protection.**  Concurrent writes during delta
           evaluation may produce inconsistent results.  Callers are
           responsible for serialising access if the source is written to
           concurrently.

    Args:
        con: Active DuckDB connection with a registered SourceAdapter.
        measure: Measure identifier or path.
        adapter: The :class:`~fhir4ds.sources.base.SourceAdapter` powering
            the connection's ``resources`` view.  Must return ``True`` from
            :meth:`~fhir4ds.sources.base.SourceAdapter.supports_incremental`.

    Raises:
        ValueError: If ``adapter.supports_incremental()`` returns ``False``.
    """

    def __init__(
        self,
        con: Any,
        measure: str,
        adapter: Any,
    ) -> None:
        # Check supports_incremental if the method exists; otherwise reject.
        if not (hasattr(adapter, "supports_incremental") and adapter.supports_incremental()):
            raise ValueError(
                f"{type(adapter).__name__} does not support incremental updates. "
                f"Use fhir4ds.dqm.evaluate() for a full population evaluation instead."
            )
        self._con = con
        self._measure = measure
        self._adapter = adapter
        self._last_sync: Optional[datetime] = None

    def update(self, as_of: Optional[datetime] = None) -> Optional[dict]:
        """
        Identifies changed patients since the last sync, re-evaluates them,
        and returns a delta result that can be merged into the population
        report.

        On first call (or if :attr:`last_sync` has not been set), uses
        ``datetime.min`` as the lower bound so all patients are considered
        changed.

        Args:
            as_of: Treat this as the current time for change detection.
                Defaults to ``datetime.utcnow()``.

        Returns:
            A delta result dict containing updated population assignments for
            changed patients, or ``None`` if no patients have changed since
            the last sync.
        """
        from fhir4ds import dqm

        as_of = as_of or datetime.utcnow()
        since = self._last_sync if self._last_sync is not None else datetime.min

        dirty_ids = self._adapter.get_changed_patients(since)
        if not dirty_ids:
            self._last_sync = as_of
            return None

        delta = dqm.MeasureEvaluator(self._con, self._measure).evaluate(
            patient_ids=dirty_ids,
        )

        self._last_sync = as_of
        return delta

    @property
    def last_sync(self) -> Optional[datetime]:
        """The timestamp of the last successful :meth:`update` call."""
        return self._last_sync
