"""
eval_stability.py

Stability evaluation for the LLM-driven incident report generator.

This script runs report generation multiple times on the same input metrics and
checks whether key invariants remain consistent across runs. The purpose is to
verify that the reporting layer is repeatable and does not drift in structure or
core facts when the input does not change.

It is intentionally simple and auditable:
- generate N reports with identical metrics.json
- assert required sections are present each time (structure invariants)
- assert peak incident window timestamps appear each time (fact invariants)
- track whether the dominant failing endpoint appears each time
- print a stability summary (rates and any failures)

This script is CI-friendly: it exits non-zero if any required invariant fails.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ARTIFACTS_DIR = Path("artifacts")
METRICS_PATH = ARTIFACTS_DIR / "metrics.json"
REPORT_PATH = ARTIFACTS_DIR / "draft_report.md"


# --- Helpers ---------------------------------------------------------------

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(cmd: List[str]) -> None:
    """Run a command and raise if it fails."""
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n\nSTDOUT:\n{res.stdout}\n\nSTDERR:\n{res.stderr}"
        )


def _extract_required_headings_from_schema(schema_text: str) -> List[str]:
    """
    Extract required section titles from report_schema.md.

    Supports headings like:
      ## 1. Executive Summary
      ## Executive Summary
    and returns normalized titles without numbering, e.g.:
      "Executive Summary"
    """
    headings: List[str] = []
    for line in schema_text.splitlines():
        line = line.strip()
        if line.startswith("## "):
            title = line.replace("## ", "").strip()
            # Strip leading numbering like "1. " or "1) "
            title = re.sub(r"^\d+\s*[\.\)]\s*", "", title).strip()
            headings.append(title)

    # If schema has a top title like "# ...", ignore it by only using ## headings.
    # Also avoid including a schema header if you have one.
    return [h for h in headings if h.lower() not in {"report schema", "incident report schema"}]


def _heading_present(report_md: str, title: str) -> bool:
    """
    Check whether a heading appears in the report.

    Accepts either:
      ## Title
      ## 1. Title
      ## 1) Title
    """
    pattern = rf"^##\s+(?:\d+\s*[\.\)]\s+)?{re.escape(title)}\s*$"
    return re.search(pattern, report_md, flags=re.MULTILINE) is not None


def _contains_exact(report_md: str, needle: str) -> bool:
    return needle in report_md


def _contains_percent_equivalent(report_md: str, rate_decimal: float) -> bool:
    """
    Accept either:
      - the raw decimal (e.g., 0.482456)
      - a percent with rounding (e.g., 48.25%)
    """
    # Raw decimal check (allow a few decimal representations)
    dec_str = f"{rate_decimal:.6f}".rstrip("0").rstrip(".")
    if dec_str and dec_str in report_md:
        return True

    pct = rate_decimal * 100.0
    # Accept common rounding levels: 0, 1, 2 decimal places
    for dp in (0, 1, 2):
        pct_str = f"{pct:.{dp}f}%"
        if pct_str in report_md:
            return True
    return False


@dataclass
class RunResult:
    ok: bool
    structure_ok: bool
    facts_ok: bool
    hotspot_ok: bool
    errors: List[str]


# --- Core evaluation -------------------------------------------------------

def evaluate_once(
    *,
    schema_path: Path,
    generator_cmd: List[str],
    peak_window_start: str,
    peak_window_end: str,
    peak_5xx_rate: float,
    hotspot_path: Optional[str],
) -> RunResult:
    errors: List[str] = []

    # Generate report (writes artifacts/draft_report.md)
    try:
        _run(generator_cmd)
    except Exception as e:
        return RunResult(ok=False, structure_ok=False, facts_ok=False, hotspot_ok=False, errors=[str(e)])

    if not REPORT_PATH.exists():
        return RunResult(
            ok=False, structure_ok=False, facts_ok=False, hotspot_ok=False,
            errors=[f"Missing report artifact: {REPORT_PATH}"]
        )

    report_md = _read_text(REPORT_PATH)
    schema_text = _read_text(schema_path)

    # Structure invariants
    required_headings = _extract_required_headings_from_schema(schema_text)
    missing = [h for h in required_headings if not _heading_present(report_md, h)]
    structure_ok = len(missing) == 0
    if not structure_ok:
        errors.append(f"Missing required headings: {missing}")

    # Fact invariants: exact peak window timestamps + 5xx rate presence
    facts_ok = True
    if not _contains_exact(report_md, peak_window_start):
        facts_ok = False
        errors.append(f"Report missing exact peak window start: {peak_window_start}")
    if not _contains_exact(report_md, peak_window_end):
        facts_ok = False
        errors.append(f"Report missing exact peak window end: {peak_window_end}")
    if not _contains_percent_equivalent(report_md, peak_5xx_rate):
        facts_ok = False
        errors.append("Report missing peak 5xx rate (decimal or percent equivalent)")

    # Hotspot invariant: mention dominant failing endpoint (if available)
    hotspot_ok = True
    if hotspot_path:
        if hotspot_path not in report_md:
            hotspot_ok = False
            errors.append(f"Report missing hotspot endpoint mention: {hotspot_path}")

    ok = structure_ok and facts_ok and hotspot_ok
    return RunResult(ok=ok, structure_ok=structure_ok, facts_ok=facts_ok, hotspot_ok=hotspot_ok, errors=errors)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5, help="Number of repeated generations.")
    parser.add_argument(
        "--schema",
        type=str,
        default="docs/report/report_schema.md",
        help="Path to report schema markdown."
    )
    parser.add_argument(
        "--generator-cmd",
        type=str,
        default="python scripts/generate_report.py",
        help="Command to generate the report (writes artifacts/draft_report.md)."
    )
    args = parser.parse_args()

    if not METRICS_PATH.exists():
        print(f"ERROR: missing {METRICS_PATH}. Run metrics generation first.", file=sys.stderr)
        return 2

    schema_path = Path(args.schema)
    if not schema_path.exists():
        print(f"ERROR: missing schema file {schema_path}", file=sys.stderr)
        return 2

    metrics = _read_json(METRICS_PATH)
    peak = metrics["errors"]["peak_5xx_window_5m"]
    if not peak:
        print("ERROR: metrics has no peak_5xx_window_5m (no 5xx incident?)", file=sys.stderr)
        return 2

    peak_start = peak["window_start"]
    peak_end = peak["window_end"]
    peak_rate = float(peak.get("5xx_rate", 0.0))

    hotspot_path: Optional[str] = None
    top_paths = peak.get("top_5xx_paths") or metrics["errors"].get("top_5xx_paths") or []
    if top_paths:
        # list entries are usually {"value": "/api/login", "count": 42}
        hotspot_path = top_paths[0].get("value")

    generator_cmd = args.generator_cmd.split()

    results: List[RunResult] = []
    for i in range(args.runs):
        r = evaluate_once(
            schema_path=schema_path,
            generator_cmd=generator_cmd,
            peak_window_start=peak_start,
            peak_window_end=peak_end,
            peak_5xx_rate=peak_rate,
            hotspot_path=hotspot_path,
        )
        results.append(r)
        status = "OK" if r.ok else "FAIL"
        print(f"[run {i+1}/{args.runs}] {status}")

        if not r.ok:
            for e in r.errors:
                print(f"  - {e}")

    # Summary
    total = len(results)
    structure_rate = sum(1 for r in results if r.structure_ok) / total
    facts_rate = sum(1 for r in results if r.facts_ok) / total
    hotspot_rate = sum(1 for r in results if r.hotspot_ok) / total
    ok_rate = sum(1 for r in results if r.ok) / total

    print("\n=== Stability Summary ===")
    print(f"runs: {total}")
    print(f"overall_pass_rate: {ok_rate:.2f}")
    print(f"structure_pass_rate: {structure_rate:.2f}")
    print(f"fact_pass_rate: {facts_rate:.2f}")
    print(f"hotspot_mention_rate: {hotspot_rate:.2f}")
    if hotspot_path:
        print(f"expected_hotspot: {hotspot_path}")
    print(f"expected_peak_window: {peak_start} -> {peak_end}")
    print(f"expected_peak_5xx_rate: {peak_rate:.6f}")

    # CI behavior: fail if any run violates required invariants
    # (structure + facts) — hotspot is also treated as required here.
    # If you want hotspot to be "best effort", remove it from the fail condition.
    any_fail = any(not r.ok for r in results)
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
