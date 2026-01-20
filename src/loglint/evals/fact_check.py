from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
import json
import re
from pathlib import Path


@dataclass(frozen=True)
class FactCheckResult:
    ok: bool
    errors: List[str]


def _percent_str(rate: float, decimals: int = 2) -> str:
    return f"{rate * 100:.{decimals}f}%"


def check_report_facts(report_md: str, *, metrics: Dict[str, Any]) -> FactCheckResult:
    errors: List[str] = []

    peak = metrics["errors"]["peak_5xx_window_5m"]
    if peak is None:
        return FactCheckResult(ok=False, errors=["peak_5xx_window_5m is None in metrics"])

    # Check window boundaries exactly
    for k in ["window_start", "window_end"]:
        val = peak[k]
        if val not in report_md:
            errors.append(f"Missing peak {k} in report: {val}")

    # Check 5xx_rate: accept decimal OR percent formatting
    rate = float(peak["5xx_rate"])
    rate_decimal = str(peak["5xx_rate"])  # e.g., "0.482456"
    rate_percent = _percent_str(rate, decimals=2)  # e.g., "48.25%"

    if (rate_decimal not in report_md) and (rate_percent not in report_md):
        errors.append(
            f"Missing peak 5xx_rate in report: expected {rate_decimal} or {rate_percent}"
        )

    return FactCheckResult(ok=(len(errors) == 0), errors=errors)
