# 🛠️ PROCEDURE: CONFORMANCE VALIDATION & BASELINES

This procedure defines the authoritative method for executing the `fhir4ds-v2` conformance suite. It establishes the "Release Gate" baselines and defines which test failures are "Expected Upstream Issues" versus "Regressions."

**Never hardcode these commands or baselines in your primary role prompt. Always refer to this file as the source of truth.**

## 1. 📊 CURRENT CONFORMANCE BASELINE
*(As of 2026-08-16 — refreshed by FP-01 SKEPTIC iter 1 after the committed
ViewDefinition suite grew from 134 to 144 tests; 2832/2832 verified
empirically that day. Historical 2026-04-24 baseline was 2822/2822 with
ViewDefinition 134/134.)*

The following table represents the live baseline for the `fhir4ds-v2` package.
**A run is considered a REGRESSION (and a blocker) if ANY suite falls below these pass rates.**

| Suite | Status | Passed / Total | Pass Rate | Known Failures |
| :--- | :--- | :--- | :--- | :--- |
| **ViewDefinition (v2)** | ✅ PASS | 144 / 144 | 100.0% | None |
| **FHIRPath (R4)** | ✅ PASS | 935 / 935 | 100.0% | None |
| **CQL** | ✅ PASS | 1706 / 1706 | 100.0% | None |
| **DQM (QI Core 2025)** | ✅ PASS | 47 / 47 | 100% | None |
| **OVERALL** | ✅ PASS | 2832 / 2832 | 100% | None |

---

## 2. 🛑 KNOWN UPSTREAM DATA ISSUES

The following four (4) measures have confirmed upstream test-data issues in
their official fixture bundles. The current FHIR4DS conformance suite still
passes all 47 measures; these notes explain historical accuracy gaps and
measure-report discrepancies, not current failing suite entries.

**DO NOT attempt to "fix" these measures unless explicitly directed.**

| Measure | Accuracy | Classification |
| :--- | :--- | :--- |
| **CMS1017** | 92.9% | Upstream test-data issue — expected |
| **CMS135** | 91.4% | Upstream test-data issue — expected |
| **CMS145** | 96.1% | Upstream test-data issue — expected |
| **CMS157** | 70.0% | Upstream test-data issue — expected |

*Note: If testing touches these measures and observes these fixture-level
accuracy figures during raw comparison analysis, treat them as upstream data
context rather than product bugs. Any conformance-suite regression below 47/47
is still a blocker.*

---

## 3. 🧪 EXECUTION PROTOCOL (Context-Efficient)

**CONTEXT PROTECTION MANDATE**: You must prevent raw test output from bloating your history. This is the #1 cause of "instruction drift."

### 3.1. Delegation (Preferred When Available)
If your environment supports delegated tasks, child agents, or isolated background jobs, use that capability for validation.
*   **Task**: "Run the validation commands from `PROC_VALIDATION.md`. Return ONLY a summary of pass/fail and accuracy diffs."

### 3.2. Summary Piping (Fallback)
If delegation is unavailable, use shell-based filtering or the platform's equivalent output-limiting capability to ensure no more than 100 lines of raw output enter your history. Use the following patterns:

#### Full Conformance Suite (Master Gate)
```bash
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > validation_summary.log && cat validation_summary.log
```
#### Unit Tests
```bash
python3 -m pytest fhir4ds/ -x --tb=short | tail -n 50
```
#### Benchmark Accuracy
```bash
python3 -m benchmarking.runner --all | grep -E "Regression|accuracy|Failed|Summary" | tail -n 50
```

---

## 4. 📝 EVALUATION MATRIX

Interpret the results from your validation summary log as follows:

| Result | Release / Fix Impact | Action |
| :--- | :--- | :--- |
| **ViewDefinition** = 134/134 | ✅ PASS | Continue. |
| **ViewDefinition** < 134/134 | 🚫 BLOCKER (Regression) | Investigate & Revert. |
| **FHIRPath** = 935/935 | ✅ PASS | Continue. |
| **FHIRPath** < 935/935 | 🚫 BLOCKER (Regression) | Investigate & Revert. |
| **CQL** = 1706/1706 | ✅ PASS | Continue. |
| **CQL** < 1706/1706 | 🚫 BLOCKER (Regression) | Investigate & Revert. |
| **DQM** = 47/47 | ✅ PASS | Continue. |
| **DQM** < 47/47 | 🚫 BLOCKER (Regression) | Investigate & Revert. |
| Known DQM fixture accuracy **worse** | 🚫 BLOCKER (Regression) | Investigate & Revert. |
| Known DQM fixture accuracy **improves** | ✅ OBSERVATION | Log it. Flag for human review. Do not treat as new baseline yet. |
| **Overall** = 2822/2822 | ✅ PASS | Continue. |
| **Overall** < 2822/2822 | 🚫 BLOCKER (Regression) | Investigate & Revert. |
