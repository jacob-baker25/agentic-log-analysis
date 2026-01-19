"""
inject_incident.py

Injects a controlled "incident" into an NGINX access log for testing and demos.

This script rewrites a bounded time window in an existing NGINX access log to create
a realistic server-error event. Within the chosen window, it can:
- concentrate requests onto a small set of endpoints (e.g., /api/login, /api/checkout)
- flip a configurable fraction of requests to HTTP 500 (to simulate an outage)
- optionally duplicate some in-window requests to simulate a traffic surge

The output is a new log file that preserves the original log format but contains a
localized 5xx incident. This makes it easier to test metrics extraction and
incident-style reporting without needing private or production data.

Example:
  python scripts/inject_incident.py \
    --in examples/sample_nginx.log \
    --out examples/sample_nginx_with_incident.log \
    --start "2015-05-20T12:05:00+00:00" \
    --minutes 10 \
    --error-rate 0.4 \
    --endpoints "/api/login,/api/checkout,/downloads/product_1" \
    --rewrite-path \
    --surge-multiplier 1.2 \
    --seed 42
"""

from __future__ import annotations

import argparse
import random
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple


# Extract timestamp inside [ ... ] from typical NGINX access logs.
# Example: [17/May/2015:08:05:32 +0000]
TIME_RE = re.compile(r"\[(?P<time>[^\]]+)\]")


def parse_nginx_time(time_str: str) -> datetime:
    """
    Parse NGINX time_local format: '17/May/2015:08:05:32 +0000'
    Returns a timezone-aware datetime.
    """
    return datetime.strptime(time_str, "%d/%b/%Y:%H:%M:%S %z")


def extract_timestamp(line: str) -> Optional[datetime]:
    """Return the parsed timestamp for a log line, or None if not found/parseable."""
    m = TIME_RE.search(line)
    if not m:
        return None
    try:
        return parse_nginx_time(m.group("time"))
    except Exception:
        return None


def replace_path_in_request(line: str, new_path: str) -> str:
    """
    Replace the path inside the quoted request: "METHOD /path HTTP/1.1"
    Keeps the existing method and protocol if present.
    """
    # Match: "GET /something HTTP/1.1"
    req_re = re.compile(r'"(?P<method>[A-Z]+)\s+(?P<path>\S+)(\s+(?P<proto>HTTP/[^"]+))?"')
    m = req_re.search(line)
    if not m:
        return line  # no change if request is missing/malformed

    method = m.group("method")
    proto = m.group("proto") or "HTTP/1.1"
    new_req = f'"{method} {new_path} {proto}"'
    return req_re.sub(new_req, line, count=1)


def replace_status_code(line: str, new_status: int) -> str:
    """
    Replace the HTTP status code in a common access log line.
    This assumes the status appears immediately after the quoted request.
    """
    # After request quotes: "..." <status> <bytes>
    status_re = re.compile(r'(".*?")\s+(?P<status>\d{3})\s+')
    return status_re.sub(rf'\1 {new_status} ', line, count=1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help="Input NGINX log file")
    ap.add_argument("--out", dest="out_path", required=True, help="Output log file")
    ap.add_argument(
        "--start",
        required=True,
        help="Incident start time in ISO format (e.g., 2015-05-20T12:05:00+00:00)",
    )
    ap.add_argument(
        "--minutes",
        type=int,
        default=10,
        help="Incident duration in minutes (default: 10)",
    )
    ap.add_argument(
        "--error-rate",
        type=float,
        default=0.4,
        help="Fraction of in-window requests to flip to 500 (default: 0.4)",
    )
    ap.add_argument(
        "--endpoints",
        default="/api/login,/api/checkout,/downloads/product_1",
        help="Comma-separated incident endpoints",
    )
    ap.add_argument(
        "--rewrite-path",
        action="store_true",
        help="If set, rewrite in-window requests to incident endpoints to concentrate failures",
    )
    ap.add_argument(
        "--surge-multiplier",
        type=float,
        default=1.0,
        help="If > 1.0, duplicate some in-window requests to simulate a traffic surge (default: 1.0)",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible incident injection (default: 42)",
    )

    args = ap.parse_args()

    if not (0.0 <= args.error_rate <= 1.0):
        raise ValueError("--error-rate must be between 0 and 1")

    endpoints: List[str] = [e.strip() for e in args.endpoints.split(",") if e.strip()]
    if not endpoints:
        raise ValueError("No endpoints provided")

    random.seed(args.seed)

    incident_start = datetime.fromisoformat(args.start)
    if incident_start.tzinfo is None:
        # default to UTC if user forgot tz
        incident_start = incident_start.replace(tzinfo=timezone.utc)

    incident_end = incident_start + timedelta(minutes=args.minutes)

    # Weighted endpoints (more realistic: one primary endpoint fails most often)
    # You can tune weights later; this gives a nice default distribution.
    weighted_endpoints = [endpoints[0]] * 6 + endpoints[1:]  # endpoint[0] favored

    injected_500 = 0
    rewritten_paths = 0
    surged_lines = 0
    total_in_window = 0
    total_lines = 0

    with open(args.in_path, "r", encoding="utf-8", errors="replace") as fin, open(
        args.out_path, "w", encoding="utf-8"
    ) as fout:
        for line in fin:
            total_lines += 1
            ts = extract_timestamp(line)

            in_window = False
            if ts is not None:
                in_window = (ts >= incident_start) and (ts < incident_end)

            if not in_window:
                fout.write(line)
                continue

            total_in_window += 1
            out_line = line

            # Optionally concentrate traffic onto a small set of endpoints
            if args.rewrite_path:
                chosen_path = random.choice(weighted_endpoints)
                new_line = replace_path_in_request(out_line, chosen_path)
                if new_line != out_line:
                    rewritten_paths += 1
                out_line = new_line

            # Flip some requests to 500
            if random.random() < args.error_rate:
                new_line = replace_status_code(out_line, 500)
                if new_line != out_line:
                    injected_500 += 1
                out_line = new_line

            fout.write(out_line)

            # Optional traffic surge: probabilistically duplicate some in-window requests
            if args.surge_multiplier > 1.0:
                # Example: multiplier 1.2 => duplicate ~20% of in-window lines
                extra_prob = min(args.surge_multiplier - 1.0, 1.0)
                if random.random() < extra_prob:
                    fout.write(out_line)
                    surged_lines += 1

    print("=== Incident Injection Summary ===")
    print("Input lines:", total_lines)
    print("Window:", incident_start.isoformat(), "->", incident_end.isoformat())
    print("In-window lines:", total_in_window)
    print("Rewritten paths:", rewritten_paths)
    print("Injected 500s:", injected_500)
    print("Surge duplicated lines:", surged_lines)
    print("Output file:", args.out_path)


if __name__ == "__main__":
    main()
