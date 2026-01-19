"""
metrics.py

Computes deterministic, fact-based metrics from normalized NGINX access log events.

This module takes the canonical event table produced by the ingestion + normalization
pipeline (one row per request) and computes the key statistics needed to understand
traffic patterns and error behavior.

These metrics are the "ground truth" for the rest of the project:
- they are produced by code (not an LLM)
- they are deterministic and repeatable
- they are designed to be easy to export to JSON

The AI summarization layer will use these metrics to write an incident-style report
without guessing or inventing numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


def _iso(ts: pd.Timestamp) -> str:
    """Convert a pandas Timestamp to an ISO 8601 string."""
    # ISO string is JSON friendly (pandas.Timestamp can't go into JSON)
    # Ensure timezone-aware output
    if getattr(ts, "tzinfo", None) is None:
        ts = ts.tz_localize("UTC")
    return ts.isoformat()


def _safe_div(n: int, d: int) -> float:
    """Prevents divide by zero.
       Used for error rates (ex. 4xx_count / total)
       If total is 0, returns 0.0 instead of crashing
    """
    return float(n) / float(d) if d else 0.0


def _top_n(df: pd.DataFrame, col: str, n: int = 10) -> List[Dict[str, Any]]:
    """Return top N values for a column as [{'value': ..., 'count': ...}, ...]."""
    vc = df[col].value_counts().head(n)
    return [{"value": idx, "count": int(cnt)} for idx, cnt in vc.items()]


def _top_n_filtered(
    df: pd.DataFrame, filter_mask: pd.Series, col: str, n: int = 10
) -> List[Dict[str, Any]]:
    """
    Same as _top_n but only for rows matching a condition (like only 5xx rows)
    Allows you to compute things like "top ips tha produced 4xx"
    """
    sub = df[filter_mask]
    if sub.empty:
        return []
    return _top_n(sub, col, n=n)

# The next two are time series metrics
# They answer "How did things change over time?"

def requests_per_minute(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Return a time series of request counts per minute:
    [{'minute': '...', 'requests': 123}, ...]
    """
    counts = df.groupby("minute").size().sort_index()
    return [{"minute": _iso(idx), "requests": int(val)} for idx, val in counts.items()]


def errors_per_minute(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Return a time series per minute with 4xx/5xx counts:
    [{'minute': '...', '4xx': 10, '5xx': 2, 'total': 120}, ...]
    """
    g = df.groupby("minute").agg(
        total=("status", "size"),
        c4xx=("is_4xx", "sum"),
        c5xx=("is_5xx", "sum"),
    ).sort_index()

    out: List[Dict[str, Any]] = []
    for idx, row in g.iterrows():
        out.append(
            {
                "minute": _iso(idx),
                "total": int(row["total"]),
                "4xx": int(row["c4xx"]),
                "5xx": int(row["c5xx"]),
            }
        )
    return out


def overall_error_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Computes the headline numbers:
	- total requests
	- total 4xx count + rate
	- total 5xx count + rate
    So the summar can immediately start with:
	"Overall 5xx rate was X%"
    """
    total = int(len(df))
    c4 = int(df["is_4xx"].sum())
    c5 = int(df["is_5xx"].sum())
    return {
        "total_requests": total,
        "4xx_count": c4,
        "5xx_count": c5,
        "4xx_rate": round(_safe_div(c4, total), 6),
        "5xx_rate": round(_safe_div(c5, total), 6),
    }

# top endpoints by total traffic (regardless of status)
def top_paths_by_volume(df: pd.DataFrame, n: int = 10) -> List[Dict[str, Any]]:
    return _top_n(df, "path", n=n)

# top endpoints that generate server errors
def top_5xx_paths(df: pd.DataFrame, n: int = 10) -> List[Dict[str, Any]]:
    return _top_n_filtered(df, df["is_5xx"], "path", n=n)

# top clients by request count
def top_ips_by_requests(df: pd.DataFrame, n: int = 10) -> List[Dict[str, Any]]:
    return _top_n(df, "ip", n=n)


def top_ips_by_5xx(df: pd.DataFrame, n: int = 10, min_requests: int = 20) -> List[Dict[str, Any]]:
    """
    Return IPs that generate the most 5xx responses.
    We also apply a minimum request threshold to avoid one-off noise.
    """
    # total requests per ip
    totals = df.groupby("ip").size()
    eligible = totals[totals >= min_requests].index
    sub = df[df["ip"].isin(eligible) & (df["is_5xx"])]
    if sub.empty:
        return []
    return _top_n(sub, "ip", n=n)


def top_ips_by_4xx(df: pd.DataFrame, n: int = 10, min_requests: int = 20) -> List[Dict[str, Any]]:
    totals = df.groupby("ip").size()
    eligible = totals[totals >= min_requests].index
    sub = df[df["ip"].isin(eligible) & (df["is_4xx"])]
    if sub.empty:
        return []
    return _top_n(sub, "ip", n=n)

# "Incident Detector"
def peak_5xx_window_5m(df: pd.DataFrame, top_k_paths: int = 5) -> Optional[Dict[str, Any]]:
    """
    Find the 5-minute time window with the highest number of 5xx responses.
    Returns window timing, totals, and top failing endpoints, or None if no 5xx exist.
    """
    if int(df["is_5xx"].sum()) == 0:
        return None

    df2 = df.copy()
    df2["window_5m"] = df2["timestamp"].dt.floor("5min")

    # Count 5xx per window, choose the worst
    g5 = df2.groupby("window_5m")["is_5xx"].sum().sort_values(ascending=False)
    peak_start = g5.index[0]
    peak_5xx = int(g5.iloc[0])

    # Restrict to the peak window (all requests, not just 5xx)
    in_window = df2["window_5m"] == peak_start
    window_df = df2[in_window]

    total = int(len(window_df))
    c4 = int(window_df["is_4xx"].sum())
    c5 = int(window_df["is_5xx"].sum())

    # Top paths among the 5xx in this window
    top_paths = []
    failing = window_df[window_df["is_5xx"]]
    if not failing.empty:
        vc = failing["path"].value_counts().head(top_k_paths)
        top_paths = [{"value": idx, "count": int(cnt)} for idx, cnt in vc.items()]

    return {
        "window_start": _iso(peak_start),
        "window_end": _iso(peak_start + pd.Timedelta(minutes=5)),
        "total_requests": total,
        "4xx_count": c4,
        "5xx_count": c5,  # should equal peak_5xx
        "5xx_rate": round(_safe_div(c5, total), 6),
        "top_5xx_paths": top_paths,
    }


def compute_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Compute the full v1 metrics bundle from a normalized event table.
    The returned dict is JSON-ready.
    """
    if df.empty:
        raise ValueError("compute_metrics() received an empty DataFrame")

    start = df["timestamp"].min()
    end = df["timestamp"].max()

    metrics: Dict[str, Any] = {
        "meta": {
            "start_time": _iso(start),
            "end_time": _iso(end),
            "total_requests": int(len(df)),
            "unique_ips": int(df["ip"].nunique()),
            "unique_paths": int(df["path"].nunique()),
        },
        "traffic": {
            "requests_per_minute": requests_per_minute(df),
            "top_paths_by_volume": top_paths_by_volume(df, n=10),
        },
        "errors": {
            "overall": overall_error_stats(df),
            "errors_per_minute": errors_per_minute(df),
            "top_5xx_paths": top_5xx_paths(df, n=10),
            "peak_5xx_window_5m": peak_5xx_window_5m(df, top_k_paths=5),
        },
        "clients": {
            "top_ips_by_requests": top_ips_by_requests(df, n=10),
            "top_ips_by_5xx": top_ips_by_5xx(df, n=10, min_requests=20),
            "top_ips_by_4xx": top_ips_by_4xx(df, n=10, min_requests=20),
        },
    }

    return metrics
