"""
validate_report.py

Validation entry point for generated incident reports.

This script performs automated checks to ensure that the report:
- follows the required report schema (structure validation)
- is grounded in computed metrics (fact validation)

It is intended to be run after generating artifacts/draft_report.md and will
exit with a non-zero status code if validation fails.
"""

import json
from pathlib import Path
from loglint.evals.fact_check import check_report_facts

from loglint.evals.structure_check import check_report_structure

METRICS_PATH = Path("artifacts/metrics.json")
REPORT_PATH = Path("artifacts/draft_report.md")

report_md = REPORT_PATH.read_text(encoding="utf-8")
metrics = json.loads(Path("artifacts/metrics.json").read_text())
fres = check_report_facts(report_md, metrics=metrics)


def main() -> None:
    if not METRICS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {METRICS_PATH}. Run metrics generation first (scripts/validate_metrics.py)."
        )
    if not REPORT_PATH.exists():
        raise FileNotFoundError(
            f"Missing {REPORT_PATH}. Run report generation first (scripts/generate_report.py)."
        )

    metrics = json.loads(Path("artifacts/metrics.json").read_text())
    report_md = REPORT_PATH.read_text(encoding="utf-8")

    # 1) Structure validation
    sres = check_report_structure(report_md)
    if not sres.ok:
        print("STRUCTURE CHECK FAILED:")
        for e in sres.errors:
            print("-", e)
        raise SystemExit(1)

    # 2) Fact / grounding validation
    fres = check_report_facts(report_md, metrics=metrics)
    if not fres.ok:
        print("FACT CHECK FAILED:")
        for e in fres.errors:
            print("-", e)
        raise SystemExit(1)

    print("Report validation passed ✅ (structure + facts)")


if __name__ == "__main__":
    main()
