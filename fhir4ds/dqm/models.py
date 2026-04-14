"""Result models for dqm-py."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from .types import PopulationMap


@dataclass
class MeasureResult:
    """Result of a measure evaluation."""

    dataframe: pd.DataFrame
    populations: dict[str, Any]
    parameters: dict[str, Any]
    measure_url: str | None = None
    # Internal: full population map for export methods
    pop_map: PopulationMap | None = field(default=None, repr=False)
