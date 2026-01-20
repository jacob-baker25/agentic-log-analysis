# Grounding Rules for Incident Report Generation

This document defines the grounding and safety rules that govern how
LogLint AI generates incident reports.

The purpose of these rules is to ensure that all reports are:
- factually grounded in computed metrics
- consistent across repeated runs
- auditable and defensible
- free from hallucinated or speculative data

These rules apply to **all LLM-based report generation and refinement steps**.

---

## 1. Source of Truth

The **only authoritative source of factual information** for an incident
report is the computed metrics output (e.g., `metrics.json`).

This includes, but is not limited to:
- timestamps
- request counts
- error counts
- error rates
- endpoint names
- client IPs

The LLM is not permitted to infer, estimate, or invent facts beyond what
is explicitly present in the metrics.

---

## 2. Numerical Grounding Rules

1. All numerical values mentioned in the report MUST appear in the metrics.
2. Numerical values MUST match the metrics exactly (up to formatting/rounding).
3. Percentages MUST be derived directly from reported counts or rates.
4. If a numerical value is not present in the metrics, it MUST NOT be included.

If a required number is missing, the report MUST explicitly state that
the information is unavailable.

---

## 3. Temporal Grounding Rules

1. All referenced time windows MUST match the computed window boundaries.
2. Start and end times MUST be expressed in UTC and match the metrics exactly.
3. The report MUST NOT describe events outside the observed log time range.
4. Relative language (e.g., "earlier", "later") must be consistent with timestamps.

---

## 4. Endpoint and Entity Grounding Rules

1. Any endpoint mentioned in the report MUST appear in the metrics output.
2. Any endpoint described as a "hotspot" MUST appear in the top failing endpoints.
3. Client IPs MUST appear in the metrics if referenced.
4. The report MUST NOT introduce new endpoints, services, or components.

---

## 5. Causal Language Constraints

The report MUST use **non-authoritative, probabilistic language** when
discussing causes or explanations.

Allowed phrasing includes:
- "suggests"
- "is consistent with"
- "may indicate"
- "likely reflects"

Disallowed phrasing includes:
- "this was caused by"
- "the root cause is"
- "this definitively indicates"

The system does not have sufficient information to assert root cause
and must not present speculation as fact.

---

## 6. Scope and Assumption Rules

1. The report MUST NOT assume:
   - deployment events
   - configuration changes
   - infrastructure failures
   - external dependencies
   unless such information is explicitly present in the metrics.

2. The report MUST remain scoped to observable behavior in the logs.

3. The report MUST distinguish clearly between:
   - observed facts
   - interpretations
   - suggested next investigative steps

---

## 7. Handling Missing or Ambiguous Data

If the metrics do not provide sufficient information to address a required
section of the report:

- The section MUST still be included.
- The report MUST explicitly state that the information is unavailable or
  inconclusive.
- The report MUST NOT attempt to fill gaps with speculation.

Example:
> "Latency metrics were not available in the provided data."

---

## 8. Determinism and Consistency Expectations

When run multiple times on the same input data:
- All factual statements MUST remain identical.
- Section structure and ordering MUST remain unchanged.
- Differences should be limited to superficial phrasing only.

Violations of these expectations should be treated as system errors
and flagged by evaluation tooling.

---

## 9. Enforcement

These grounding rules are enforced through:
- prompt constraints
- structured output requirements
- post-generation validation checks
- stability and consistency evaluations

Any report that violates these rules is considered **invalid**.
