"""
validate_all.py

One-command end-to-end validation runner for the LogLint AI pipeline.

This script executes the full workflow in a fixed order:
1) Ingest + normalization validation
2) Metrics computation validation
3) Draft report generation
4) Report validation (structure + grounding checks)
5) Stability evaluation (repeated generations + invariant checks)

It is designed to be:
- easy to run locally
- CI-friendly (exits non-zero on failure)
- readable (prints clear step-by-step output)

Usage:
  python scripts/validate_all.py
  python scripts/validate_all.py --runs 10
  python scripts/validate_all.py --skip-stability
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Step:
    name: str
    cmd: List[str]


def run_step(step: Step) -> None:
    print(f"\n=== {step.name} ===")
    print("$ " + " ".join(step.cmd))
    res = subprocess.run(step.cmd)
    if res.returncode != 0:
        raise RuntimeError(f"Step failed: {step.name} (exit code {res.returncode})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5, help="Stability evaluation runs.")
    parser.add_argument(
        "--skip-stability",
        action="store_true",
        help="Skip stability evaluation (faster local runs).",
    )
    args = parser.parse_args()

    steps: List[Step] = [
        Step("Ingest validation", ["python", "scripts/validate_ingest.py"]),
        Step("Metrics validation", ["python", "scripts/validate_metrics.py"]),
        Step("Report generation", ["python", "scripts/generate_report.py"]),
        Step("Report validation", ["python", "scripts/validate_report.py"]),
    ]

    if not args.skip_stability:
        steps.append(
            Step(
                "Stability evaluation",
                ["python", "scripts/eval_stability.py", "--runs", str(args.runs)],
            )
        )

    failures: List[str] = []

    for step in steps:
        try:
            run_step(step)
            print("✅ PASS")
        except Exception as e:
            print("❌ FAIL")
            print(str(e), file=sys.stderr)
            failures.append(step.name)
            break  # fail fast

    print("\n=== Summary ===")
    if not failures:
        print("All validations passed ✅")
        return 0

    print("Failed step(s):")
    for name in failures:
        print(f"- {name}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
