"""D8 HISTORIAN v0.0.26 — serve error-contract regressions (QA-D8H-003).

``serve.create_app(<str>/<dict>)`` leaked a raw ``AttributeError: 'str'
object has no attribute 'database'`` far from the call site; now a typed
TypeError naming the expected ServeConfig.
"""

from __future__ import annotations

import pytest


class TestServeCreateAppConfigTypeError:
    def test_str_config_raises_type_error(self):
        from fhir4ds.serve.app import create_app

        with pytest.raises(TypeError, match="ServeConfig"):
            create_app("/nonexistent/dataset")

    def test_dict_config_raises_type_error(self):
        from fhir4ds.serve.app import create_app

        with pytest.raises(TypeError, match="ServeConfig"):
            create_app({"path": "/tmp"})
