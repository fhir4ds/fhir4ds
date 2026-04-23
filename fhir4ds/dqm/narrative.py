"""Narrative generator — produces human-readable audit explanations.

Consumes grouped evidence from ``compact_audit`` output. Each evidence
item is a *logic group* with ``trace``, ``attribute``, ``operator``,
``threshold``, and ``findings`` (list of ``{target, value}``).
"""

from __future__ import annotations

# Human-readable operator display names
_OP_DISPLAY = {
    "=": "equals",
    ">": "greater than",
    "<": "less than",
    ">=": "at least",
    "<=": "at most",
    "!=": "not equal to",
    "<>": "not equal to",
    "exists": "found",
    "absent": "not found",
}


class NarrativeGenerator:
    """Base narrative generator. Subclass for custom clinical language."""

    TEMPLATES: dict[str, str] = {
        "initial-population": "Included in Initial Population",
        "denominator": "Eligible for measure denominator",
        "denominator-exclusion": "Excluded from denominator",
        "denominator-exception": "Exception applied",
        "numerator": "Met numerator criteria",
        "numerator-exclusion": "Excluded from numerator",
    }

    FAILURE_TEMPLATES: dict[str, str] = {
        "initial-population": "Not in Initial Population",
        "denominator": "Not eligible for denominator",
        "denominator-exclusion": "Not excluded from denominator",
        "denominator-exception": "No exception applied",
        "numerator": "Failed numerator",
        "numerator-exclusion": "Not excluded from numerator",
    }

    def generate(
        self, population_code: str, evidence: list[dict], is_satisfied: bool,
        evidence_captured: bool = True,
    ) -> list[str]:
        """Generate narrative fragments for a population result.

        Returns a list of short, human-readable strings — one per logic group.

        Args:
            population_code: The population code (e.g., 'numerator').
            evidence: List of evidence dicts from audit.
            is_satisfied: Whether the population criteria were met.
            evidence_captured: Whether evidence was actively captured. False when
                audit mode doesn't capture detail (e.g., POPULATION mode).
        """
        templates = self.FAILURE_TEMPLATES if not is_satisfied else self.TEMPLATES
        header = templates.get(population_code, "Evidence")

        if not evidence:
            verb = "met" if is_satisfied else "not met"
            if not evidence_captured:
                return [f"{header}: criteria {verb} (evidence not captured in this audit mode)."]
            return [f"{header}: criteria {verb} (no detailed evidence available)."]

        fragments = [f"{header}:"]
        for group in evidence:
            frag = self._format_group(group)
            if frag:
                fragments.append(frag)
        return fragments

    def _format_group(self, group: dict) -> str | None:
        """Format a logic group into a readable fragment.

        Args:
            group: A dict with keys ``attribute``, ``operator``, ``threshold``,
                ``trace`` (list[str]), and ``findings`` (list of {target, value}).
        """
        attr = group.get("attribute")
        op = group.get("operator", "")
        threshold = group.get("threshold")
        trace = [str(v) for v in (group.get("trace") or []) if v]
        findings = group.get("findings") or []
        count = len(findings)

        op_display = _OP_DISPLAY.get(op, op)

        if op == "absent":
            resource_label = attr or self._resource_type_from_trace(trace) or "resource"
            valueset = threshold or "required criteria"
            frag = f"Logic: No {resource_label} found for {valueset}"
        elif attr and threshold:
            frag = f"Logic: {attr} {op_display} {threshold}"
        elif threshold:
            frag = f"Logic: {op_display} {threshold}"
        elif op_display:
            frag = f"Logic: {op_display}"
        else:
            return None

        if findings:
            sample = findings[0]
            rid = sample.get("target", "Resource")
            val = sample.get("value")

            if val:
                finding_str = f"Finding: {rid} value={val}"
            else:
                finding_str = f"Finding: {rid}"

            if count > 1:
                finding_str += f" (+{count - 1} more)"

            frag = f"{frag} | {finding_str}"
        elif count > 0:
            frag = f"{frag} | {count} finding(s)"

        if trace:
            frag += f" | Trace: {' > '.join(trace)}"

        return frag

    @staticmethod
    def _resource_type_from_trace(trace: list[str]) -> str | None:
        """Extract a FHIR resource type from the first trace entry if available.

        Trace entries from retrieve CTEs follow the pattern ``"Condition: ..."``
        or just ``"Encounter"``.
        """
        if not trace:
            return None
        first = trace[0]
        if ": " in first:
            return first.split(": ", 1)[0]
        return first if first[0].isupper() else None
