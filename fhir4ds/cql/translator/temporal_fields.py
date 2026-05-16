"""Temporal field metadata used by CQL SQL optimization."""

TEMPORAL_FHIR_TYPES = frozenset({"Period", "dateTime", "date", "instant"})

TEMPORAL_CHOICE_PATHS = frozenset(
    {
        "abatement",
        "effective",
        "occurrence",
        "onset",
        "performed",
    }
)

TEMPORAL_CHOICE_SUFFIXES = ("Period", "DateTime", "Date", "Instant")

TEMPORAL_BOUND_COLUMN_NAMES = frozenset(
    {
        "abatement",
        "authored_date",
        "authored_on",
        "billable_period",
        "effective",
        "issued",
        "occurrence",
        "onset",
        "period",
        "performed",
        "recorded_date",
        "sent",
        "when_handed_over",
    }
)
