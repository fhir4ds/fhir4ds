"""Unit tests for DQM batch helpers."""

import json

import duckdb
import pytest

from fhir4ds.dqm.batch import _load_valuesets
from fhir4ds.dqm.config import DQMConfigError


def test_load_valuesets_rejects_non_object_json(tmp_path):
    valueset_file = tmp_path / "valuesets.json"
    valueset_file.write_text(json.dumps([]))

    con = duckdb.connect(":memory:")
    try:
        with pytest.raises(DQMConfigError, match="object resource or Bundle.*list"):
            _load_valuesets(con, [valueset_file])
    finally:
        con.close()
