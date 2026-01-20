"""
generate_report.py

Command-line entry point for generating a grounded incident report.

This script ties together the metrics pipeline and the LLM reporting layer.
It reads the computed metrics artifact (metrics.json), invokes the draft
report generator, and writes a structured Markdown incident report to disk.

The generated report:
- strictly follows the predefined report schema
- is grounded only in values present in metrics.json
- is intended to be validated by downstream structure and fact checks

This script provides a single, repeatable command for producing an
incident-style report from log-derived metrics.
"""

import json
from pathlib import Path

from loglint.agents.draft_report import DraftReportConfig, generate_draft_report

METRICS_PATH = Path("artifacts/metrics.json")
OUT_PATH = Path("artifacts/draft_report.md")


def main() -> None:
    if not METRICS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {METRICS_PATH}. Run metrics generation first (scripts/validate_metrics.py)."
        )

    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))

    cfg = DraftReportConfig(
        # Pick a default model that is cheap + solid for structured writing.
        model="gpt-4o-mini",
        temperature=0.2,
        max_output_tokens=900,
    )

    report_md = generate_draft_report(metrics, config=cfg)

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(report_md + "\n", encoding="utf-8")

    peak = metrics.get("errors", {}).get("peak_5xx_window_5m", None)
    print(f"Wrote {OUT_PATH}")
    if peak:
        print("Peak window:", peak.get("window_start"), "->", peak.get("window_end"))
        print("5xx_rate:", peak.get("5xx_rate"), "5xx_count:", peak.get("5xx_count"))
    else:
        print("No peak 5xx window detected (peak_5xx_window_5m is None).")


if __name__ == "__main__":
    main()
