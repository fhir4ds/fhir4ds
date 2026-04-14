"""Column registry for tracking precomputed columns in CTEs."""

from dataclasses import dataclass, field
from typing import Dict, Optional, Set


@dataclass
class ColumnInfo:
    """Information about a precomputed column."""
    column_name: str
    fhirpath: str
    sql_type: str
    is_choice_type: bool = False


class ColumnRegistry:
    """
    Tracks precomputed columns available in each CTE.

    Used to avoid redundant FHIRPath calls by reusing columns
    that were already computed in the CTE definition.
    """

    def __init__(self):
        self._columns: Dict[str, Dict[str, ColumnInfo]] = {}

    def register_cte(self, cte_name: str, columns: Dict[str, ColumnInfo]) -> None:
        """
        Register columns for a CTE.

        Args:
            cte_name: Name of the CTE
            columns: Dict mapping column_name -> ColumnInfo
        """
        self._columns[cte_name] = columns

    def register_union(self, union_name: str, branch_names: list) -> None:
        """
        Register a union CTE.

        Only columns present in ALL branches are available.
        """
        if not branch_names:
            self._columns[union_name] = {}
            return

        # Find columns present in all branches
        common_columns: Optional[Set[str]] = None
        for branch in branch_names:
            branch_cols = set(self._columns.get(branch, {}).keys())
            if common_columns is None:
                common_columns = branch_cols
            else:
                common_columns &= branch_cols

        # Register only common columns
        union_cols = {}
        first_branch = branch_names[0]
        for col_name in (common_columns or set()):
            if col_name in self._columns.get(first_branch, {}):
                union_cols[col_name] = self._columns[first_branch][col_name]

        self._columns[union_name] = union_cols

    def lookup(self, cte_name: str, fhirpath: str) -> Optional[str]:
        """
        Look up a precomputed column by FHIRPath expression.

        Args:
            cte_name: Name of the CTE to look in
            fhirpath: The FHIRPath expression

        Returns:
            Column name if found, None otherwise
        """
        cte_cols = self._columns.get(cte_name, {})
        for col_info in cte_cols.values():
            if col_info.fhirpath == fhirpath:
                return col_info.column_name
        return None

    def get_columns(self, cte_name: str) -> Dict[str, ColumnInfo]:
        """Get all columns for a CTE."""
        return self._columns.get(cte_name, {})

    def has_column(self, cte_name: str, column_name: str) -> bool:
        """Check if a CTE has a specific column."""
        return column_name in self._columns.get(cte_name, {})

    def clear(self) -> None:
        """Clear all registered columns."""
        self._columns.clear()
