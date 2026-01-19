"""
normalize.py

Cleans and standardizes parsed NGINX access log data.

This module takes the raw DataFrame produced by the NGINX log parser and
converts it into a clean, consistent format that is safe to use for analysis.
It ensures that timestamps, status codes, and other fields have the correct
types, removes malformed rows, and adds a few helpful derived columns used
throughout the project.

After this step, the log data can be reliably used to compute metrics and
generate AI-driven summaries without worrying about missing fields, bad
timestamps, or inconsistent formats.

This module contains no AI logic and is intentionally deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Optional

import pandas as pd


REQUIRED_COLUMNS = ["timestamp", "ip", "method", "path", "status", "bytes_sent"]


@dataclass(frozen=True)
class NormalizeReport:
    input_rows: int
    output_rows: int
    dropped_rows: int
    dropped_reasons: Dict[str, int]


def _ensure_columns(df: pd.DataFrame, required: List[str]) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Found: {list(df.columns)}")


def normalize_events(
    df: pd.DataFrame,
    *,
    assume_tz: str = "UTC",
    drop_private_ips: bool = False,
) -> tuple[pd.DataFrame, NormalizeReport]:
    """
    Normalize a parsed NGINX log DataFrame into a canonical event table.
    - Enforces schema + types
    - Drops malformed rows
    - Adds derived fields useful for metrics

    Returns: (normalized_df, report)
    """
    _ensure_columns(df, REQUIRED_COLUMNS)

    input_rows = len(df)
    dropped: Dict[str, int] = {}

    out = df.copy()

    # --- Type conversions ---
    # timestamp -> tz-aware datetime
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    # If timestamps are naive, localize them, if tz-aware, keep them.
    if out["timestamp"].dt.tz is None:
        out["timestamp"] = out["timestamp"].dt.tz_localize(assume_tz)

    # status -> int (coerce invalid to NaN then drop)
    out["status"] = pd.to_numeric(out["status"], errors="coerce")
    out["bytes_sent"] = pd.to_numeric(out["bytes_sent"], errors="coerce").fillna(0)

    # strings: make sure they're strings and strip
    for c in ["ip", "method", "path"]:
        out[c] = out[c].astype(str).str.strip()

    # --- Drop malformed rows ---
    # invalid timestamp
    mask_bad_time = out["timestamp"].isna()
    if mask_bad_time.any():
        dropped["bad_timestamp"] = int(mask_bad_time.sum())
        out = out[~mask_bad_time]

    # invalid status
    mask_bad_status = out["status"].isna()
    if mask_bad_status.any():
        dropped["bad_status"] = int(mask_bad_status.sum())
        out = out[~mask_bad_status]

    # empty path or method
    mask_bad_req = (out["method"] == "") | (out["path"] == "") | (out["path"] == "None")
    if mask_bad_req.any():
        dropped["bad_request"] = int(mask_bad_req.sum())
        out = out[~mask_bad_req]

    # coerce numeric types after dropping
    out["status"] = out["status"].astype(int)
    out["bytes_sent"] = out["bytes_sent"].astype(int)

    # Optional: drop private IPs (not necessary for MVP)
    if drop_private_ips:
        # Simple heuristic: 10.*, 192.168.*, 172.16-31.*
        private = (
            out["ip"].str.startswith("10.")
            | out["ip"].str.startswith("192.168.")
            | out["ip"].str.match(r"^172\.(1[6-9]|2\d|3[0-1])\.")
        )
        if private.any():
            dropped["private_ip"] = int(private.sum())
            out = out[~private]

    # --- Deduplicate (optional but helpful) ---
    # Not strictly required, kept simple:
    before = len(out)
    out = out.drop_duplicates(subset=["timestamp", "ip", "method", "path", "status", "bytes_sent"])
    dupes_dropped = before - len(out)
    if dupes_dropped:
         dropped["duplicates"] = dupes_dropped
    # --- Derived columns for metrics ---
    out["status_class"] = (out["status"] // 100) * 100  # 200, 300, 400, 500
    out["is_4xx"] = (out["status"] >= 400) & (out["status"] < 500)
    out["is_5xx"] = (out["status"] >= 500) & (out["status"] < 600)
    out["minute"] = out["timestamp"].dt.floor("min")  # time bucketing

    # Sort for time-series work
    out = out.sort_values("timestamp").reset_index(drop=True)

    report = NormalizeReport(
        input_rows=input_rows,
        output_rows=len(out),
        dropped_rows=input_rows - len(out),
        dropped_reasons=dropped,
    )
    return out, report
