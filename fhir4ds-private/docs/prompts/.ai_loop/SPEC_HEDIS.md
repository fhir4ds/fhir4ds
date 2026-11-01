# 📋 SPEC: HEDIS CLINICAL PATTERNS

This document details the complex clinical logic patterns required to correctly evaluate HEDIS measures. It serves as the primary reference for testing and auditing CQL interval boundaries, multi-population attribution, and zero-ETL integration.

**If your QA assignment involves Domains 11–20, use this spec to formulate your "Hypothesis Attacker" predictions and construct boundary-condition synthetic data.**

---

## 1. 🛑 CONTINUOUS ENROLLMENT (Domain 11)
**Core Logic:** The "With continuous enrollment during" function gates nearly every measure. If this is wrong, all denominators are wrong.

**Test Matrix (The 3 Gap Constraints):**
*   **Gap Collapse**: Overlapping coverage records must be collapsed (e.g., Dual Medicare/Medicaid) before gaps are computed to avoid double-counting.
*   **Longest Single Gap**: Must satisfy exactly the allowed limit (e.g., 45 days). A 46-day gap should fail.
*   **Total Gap Days**: Total days across multiple small gaps must be <= threshold. One day over should fail.
*   **Gap Count**: The number of independent gaps must be <= limit.
*   **Off-By-One Risks**: Does `successor of end of interval` correctly advance by exactly one day, or does it miscalculate the days between gaps?

---

## 2. 🎂 AGE CALCULATION SEMANTICS (Domain 12)
**Core Logic:** Age boundaries determine the Initial Population.

**Test Matrix (Boundary Conditions):**
*   **CQL Definition**: Age is based on the calendar year difference, NOT duration in days.
*   **Leap Years**: Calculate `AgeInYearsAt` for someone born Feb 29th when the `asOfDate` is a non-leap year.
*   **Inclusive Boundaries**: `Patient."Aged between"(Interval[18, 64])`. A patient who is *exactly* 64 should be included. A patient who just turned 65 should not.
*   **Month Math**: Does `CalculateAgeInMonthsAt` correctly handle patients who haven't reached their birthday in the current month?

---

## 3. ⏱️ EPISODE DEDUPLICATION (Domain 13)
**Core Logic:** Prevents double-counting the same clinical event in event-based measures (e.g., AAB, PPC). Uses `."Deduplicated Episodes"(31 days)`.

**Test Matrix (Accumulator Boundaries):**
*   **Inclusive/Exclusive**: If the gap is 31 days, does an event exactly 31 days later start a new episode, or must it be 32 days?
*   **Empty Lists**: The aggregate clause must return an empty list, NOT `null` or throw an error.
*   **Sorting**: Does sorting happen *before* deduplication? (It must).
*   **Same Day**: Two events on the identical day must collapse into one episode.

---

## 4. 🔀 MULTI-SOURCE HOSPICE EXCLUSION (Domain 14)
**Core Logic:** A patient in hospice must be excluded regardless of the source table (claims, EOBs, encounters, procedures, or coverages).

**Test Matrix (OR-Semantics):**
*   **Short-Circuiting**: If `claims` is empty, does the check gracefully short-circuit, or does it crash on an empty list?
*   **Extension Sniffing**: Does coverage-based hospice detection correctly inspect the `extension.url` for the LTI (Long-Term Institution) extension?
*   **Temporal Bounding**: A patient in hospice in 2023 but NOT in 2025 should NOT be excluded from 2025 measures.

---

## 5. 🔠 FHIR CHOICE TYPE HANDLING (Domain 15)
**Core Logic:** Handling polymorphic FHIR fields (`Observation.effective[x]`, `Condition.onset[x]`) using `is/as`.

**Test Matrix (Type Coercion):**
*   **Graceful Nulls**: `obs.effective as FHIR.dateTime` MUST return `null` (not crash) if the underlying data is actually a `FHIR.Period`.
*   **Date Extraction**: `date from (obs.effective as FHIR.dateTime)` must correctly extract the date component and strip the time.
*   **System vs. FHIR Types**: Ensure `FHIR.date` (date only) is handled differently from `System.Date`.

---

## 6. 📏 INTERVAL OPERATOR BOUNDARIES (Domain 16)
**Core Logic:** HEDIS relies on precise temporal reasoning (e.g., follow-up within exactly X days).

**Test Matrix (The Boundary Cases):**
*   `overlaps`: Must return `true` if they share exactly ONE boundary point (e.g., `[1,3]` overlaps `[3,5]`).
*   `during`: Do both endpoints need to fall strictly inside, or is it sufficient to be contained?
*   `within 15 days of`: Is the absolute distance `<=` 15, or strictly `<` 15?
*   `same or after`: Must treat the identical date as satisfying the condition.
*   `starts during` / `ends during`: Must handle the first/last day of the measurement period inclusively.

---

## 7. 👥 MULTI-POPULATION STRUCTURE (Domain 17)
**Core Logic:** Measures with independent rate groups (e.g., FUA Numerator 1 / Numerator 2).

**Test Matrix (State Isolation):**
*   **Non-Bleed**: Denominator exclusions for Numerator 1 must NOT bleed into Numerator 2.
*   **Shared Initial Population**: The IPP is evaluated once. Verify that a patient qualifying for AABA but not AABB is correctly attributed to both independent tracks.

---

## 8. 🏷️ PAYER STRATIFICATION (Domain 18)
**Core Logic:** Assigning patients to reporting lines (Commercial, Medicare, Medicaid) using `Certification_Payer_Reporting.cql`.

**Test Matrix (Priority Resolution):**
*   **Dual Eligibility**: Correctly resolve patients with simultaneous Medicare and Medicaid.
*   **Mid-Year Changes**: Assign to the payer the patient was enrolled with at the anchor date.
*   **MMP / SNP Remapping**: Ensure Special Needs Plans and MMP override the initial classification.
*   **Total Validation**: The sum of all stratification counts MUST exactly equal the total Initial Population.

---

## 9. 🔗 REFERENCE RESOLUTION (Domain 19)
**Core Logic:** The `FHIR_Common.cql` pattern using `singleton from`.

**Test Matrix (Fallback Semantics):**
*   **GetId()**: Correctly extracts the ID from `"ResourceType/id"`, bare `"id"`, and URL formats.
*   **Singleton Enforcement**: MUST raise an error (or return null) if multiple resources match. Never silently pick one.
*   **Coalesce Pattern**: If primary ID match is `null`, does it correctly fallback to `identifier` matching?