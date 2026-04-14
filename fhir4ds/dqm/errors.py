"""Error classes for dqm-py."""


class DQMError(Exception):
    """Base exception for dqm-py errors."""

    pass


class MeasureParseError(DQMError):
    """Raised when a FHIR Measure resource cannot be parsed."""

    pass
