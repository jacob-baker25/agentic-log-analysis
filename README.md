# LogLint AI

LogLint AI is a Python system that analyzes NGINX access logs, computes deterministic incident metrics, and generates a structured incident report using an LLM.

The core goal is **reliability**. Reports are grounded strictly in computed metrics rather than raw log inference and are automatically validated for structure and factual consistency. A stability evaluator reruns generation multiple times to verify repeatability.

---

## What It Does

Given an NGINX access log, LogLint AI produces:

- `artifacts/metrics.json`  
  Deterministic computed facts including traffic volume, error rates, peak incident window, and endpoint hotspots.

- `artifacts/draft_report.md`  
  A structured incident-style report generated exclusively from computed metrics.

- Automated validation ensuring the report:
  - Follows the required schema
  - Does not contradict computed metrics

---

## Quickstart

### 1. Set Up Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set your LLM API key (example):

```bash
export OPENAI_API_KEY="..."
```
### 2. Run the Full Pipeline (Recommended)
```bash
python scripts/validate_all.py
```
This runs the complete system:
- Log ingestion and normalization validation
- Metrics computation and incident detection
- Report generation
- Report validation (structure and facts)
- Stability evaluation across repeated generations

### Example: Detected Incident Window
Using the included sample dataset:
`examples/sample_nginx_with_incident.log`
The pipeline detects a localized server error incident:
- Peak window:
`2015-05-20T12:05:00+00:00 → 2015-05-20T12:10:00+00:00`
- Peak 5xx rate:
`0.482456` (55 failures/114 requests)
- Domain hotspot:
`/api/login `

### Project Layout

src/loglint/
├── ingest/
│   Parses and normalizes NGINX logs into structured events.
│
├── tools/
│   Computes deterministic metrics and incident summaries.
│
├── agents/
│   Generates reports from metrics.json using strict schema rules.
│
├── evals/
│   Validates report structure and facts; evaluates stability.
│
docs/report/
├── report_schema.md
├── grounding_rules.md
├── example_report.md
└── evaluation_criteria.md

### How Grounding Works (Important)
The LLM never analyzes raw logs directly. It only receives:
- `artifacts/metrics.json`
  Computed facts only
-  `docs/report/report_schema.md`
  Required report structure and section ordering
- `docs/report/grounding_rules.md`
  Anti-hallucination and fact-use rules
If a number, timestamp, or endpoint is not present in `metrics.json`, the report is not allowed to include it.

### Validation and Stability
- `scripts/validate_report.py` checks:
  - Required sections exist and are correctly ordered
  - Peak incident window timestamps match exactly
  - Peak 5xx rate is present (decimal or equivalent percentage)
- `scripts/eval_stability.py`
  - Reruns report generation multiple times on identical inputs
  - Reports pass rates for key invariants such as structure and facts

### Data Notes
The sample incident log is produced by injecting a controlled 5xx spike into a normal access log:
-  `scripts/inject_incident.py`
- `examples/sample_nginx_with_incident.log`
This provides a fully reproducible scenario for testing and demonstration.

### Future Work (Not Implemented in v1)
- Support for additional log formats (JSON app logs, auth logs)
- Richer numeric fact validation
- Optional API server (FastAPI)
- Iterative report refinement loop

### Project Highlights
- Deterministic metrics layer (no LLM math)
- LLM grounded strictly on computed facts
- Schema enforcement with automated validation
- Stability evaluation across repeated generations
























