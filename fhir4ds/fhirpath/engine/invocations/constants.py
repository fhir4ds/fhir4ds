from datetime import datetime, timezone


class SystemTime:
    """
    System date/time should not change during an evaluation of a FHIRPath
    expression. It remains the same for the entire expression evaluation.

    Pinned to UTC to match the native C++ extension, which uses ``gmtime_r``
    to break down ``time_t`` into UTC components. Using host-local time would
    cause native↔fallback divergence on non-UTC hosts (FHIRPath §5.9.2 allows
    either, but the two backends must agree).
    """

    def __init__(self) -> None:
        self.expressionExecutionDateTime = datetime.now(timezone.utc)

    def now(self):
        return self.expressionExecutionDateTime

    def reset(self):
        self.expressionExecutionDateTime = datetime.now(timezone.utc)


class Constants:
    """
    These are values that should not change during an evaluation of a FHIRPath
    expression (e.g. the return value of today(), per the spec.)  They are
    constant during at least one evaluation.
    """

    def __init__(self):
        self.today = None
        self.now = None
        self.timeOfDay = None
        self.localTimezoneOffset = None
        self.systemtime = SystemTime()

    def reset(self):
        self.today = None
        self.now = None
        self.timeOfDay = None
        self.localTimezoneOffset = None
        self.systemtime.reset()
