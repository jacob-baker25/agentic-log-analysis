# Incident Report Evaluation Criteria

This document defines how LogLint AI incident reports are evaluated for
correctness, consistency, and reliability.

A report that does not meet these criteria is considered invalid and should
be regenerated or flagged for review.

---

## 1. Structural Criteria

A valid report MUST:

- Include all required sections defined in `report_schema.md`
- Present sections in the correct order
- Use clear section headers
- Contain no additional sections outside the schema

Failure to meet any structural requirement constitutes a validation failure.

---

## 2. Grounding Criteria

A valid report MUST satisfy all grounding rules:

- All numerical values must match values in `metrics.json`
- All referenced time windows must match computed boundaries exactly
- All endpoints mentioned must appear in the metrics output
- No new entities, services, or facts may be introduced

If any factual statement cannot be traced back to the metrics, the report is
considered invalid.

---

## 3. Incident Window Validation

The following fields must be present and correct if an incident window exists:

- Window start time
- Window end time
- Total request count
- 5xx count
- 5xx failure rate

These values must match the peak incident window detected by the metrics
pipeline.

---

## 4. Severity and Impact Assessment

Severity descriptions must be:

- Consistent with computed failure rates
- Qualitative (e.g., low / moderate / high)
- Grounded in observed impact rather than speculation

Reports must not overstate confidence or assert root cause.

---

## 5. Language and Causality Constraints

A valid report MUST:

- Use probabilistic, non-authoritative language
- Avoid definitive root-cause claims
- Clearly distinguish between observed facts and interpretation

Disallowed language includes absolute claims such as “this outage was caused by.”

---

## 6. Stability and Consistency Criteria

When the report generation pipeline is run multiple times on the same input:

- Section headers must remain identical
- Section ordering must remain unchanged
- All factual statements must remain identical
- Any variation must be limited to minor phrasing differences

Significant variation across runs indicates insufficient prompt or grounding
control and should be treated as a system failure.

---

## 7. Handling Missing Data

If required information is not present in the metrics:

- The report must still include the relevant section
- The report must explicitly state that the information is unavailable
- The report must not attempt to infer or invent missing data

---

## 8. Evaluation Outcome

A report is considered **valid** only if it satisfies:

- All structural criteria
- All grounding criteria
- All stability expectations

Reports that fail evaluation should be regenerated with stricter constraints
or flagged for manual inspection.
