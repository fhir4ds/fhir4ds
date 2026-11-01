# 🛠️ PROCEDURE: DEEP RESEARCH & CONTEXT ESCALATION

This procedure dictates how to perform exhaustive research when a fix attempt fails, or when the root cause of an issue is ambiguous. 

**This is a mandatory gate.** No issue may be reclassified as `NEEDS_CONTEXT` (given up to human review) without first completing this protocol and producing a `deep_research_findings.md` report.

---

## 1. 🚦 WHEN TO TRIGGER THIS PROCEDURE

You MUST execute this Deep Research procedure under any of the following conditions:
*   **The "First-Fail" Rule**: You applied a fix, ran validation, and it caused a new regression or failed to resolve the issue. (Do not guess on your second attempt).
*   **Diagnostic Ambiguity**: You are in the "Remediation Plan" phase, but you cannot pinpoint the exact line of code or cite the specific spec section governing the behavior.
*   **Escalation Intent**: You believe the issue cannot be resolved without developer-only knowledge and want to reclassify it as `NEEDS_CONTEXT`.

---

## 2. 🔍 THE DEEP RESEARCH PROTOCOL

**CONTEXT PROTECTION MANDATE**: Research involves high-volume data (specs, code, web pages). You must prevent this data from polluting the primary loop.

### 2.1. Delegation (Preferred When Available)
If available, delegate the research to a child agent, isolated task, or equivalent background context.
*   **Task**: "Execute the Deep Research Protocol from `PROC_DEEP_RESEARCH.md`. Research [Issue ID]. Return ONLY the structured `deep_research_findings.md` report."

### 2.2. Selective Reading (Fallback)
If delegation is unavailable, use targeted reads:
*   Use the platform's file search, `rg`, `grep`, or equivalent capability to find relevant lines first.
*   Use targeted file reads with line ranges, editor range selection, or equivalent capabilities for surgical reads.
*   Summarize findings internally and **discard** raw spec text once analyzed.

---

## 3. 📄 THE DEEP RESEARCH REPORT

Once research is complete, you must write a structured report to `.ai_loop/state/deep_research_findings.md` (or append to it if it exists).

**Format Requirements:**
```markdown
### Deep Research: [Issue ID]

**1. Spec Determination:** 
[Exact citation and quote of the normative rule. Or explicit confirmation that the spec is silent.]

**2. Prior Art:**
[How other engines handle this. Any relevant HL7 Jira tickets.]

**3. Approaches Attempted:**
[What you already tried that failed, and specifically WHY it failed validation.]

**4. Blast Radius:**
[List of other modules/tests that rely on the currently failing logic.]

**5. Recommended Path:**
[Either 1: A newly formulated Fix Strategy based on research.]
[Or 2: Escalation to NEEDS_CONTEXT, with the SPECIFIC question only a human can answer.]
```

---

## 4. 🔙 RETURN TO EXECUTION LOOP

After writing the report, read it back into your context and resume your primary Execution Loop:
*   If you found a new approach, proceed to implement it.
*   If your recommendation was escalation, you are now authorized to reclassify the issue as `NEEDS_CONTEXT`.
