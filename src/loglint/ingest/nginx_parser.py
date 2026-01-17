import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd


# Matches NGINX "combined" access log lines.
# Captures:
#  - ip
#  - time
#  - request (method path protocol)
#  - status
#  - bytes_sent
LOG_RE = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<request>[^"]*)"\s+(?P<status>\d{3})\s+(?P<bytes>\S+)'
)


@dataclass(frozen=True)
class ParsedLine:
    ip: str
    timestamp: datetime
    method: str
    path: str
    status: int
    bytes_sent: int


def _parse_time_nginx(time_str: str) -> datetime:
    """
    Parse NGINX time_local like: 17/Jan/2026:13:42:10 -0500
    Returns timezone-aware datetime.
    """
    return datetime.strptime(time_str, "%d/%b/%Y:%H:%M:%S %z")


def _parse_request(request: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse request like: 'GET /api/login HTTP/1.1'
    Returns (method, path). If malformed, returns (None, None).
    """
    parts = request.split()
    if len(parts) < 2:
        return None, None
    return parts[0], parts[1]


def parse_nginx_log(path: str, *, max_bad_lines: int = 200) -> pd.DataFrame:
    """
    Parse an NGINX access log file into a pandas DataFrame.

    Columns:
      - timestamp (datetime64[ns, tz])
      - ip (string)
      - method (string)
      - path (string)
      - status (int)
      - bytes_sent (int)

    Behavior:
      - Skips malformed lines, counts them, and raises if too many.
    """
    rows: List[Dict[str, Any]] = []
    bad_lines = 0

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            m = LOG_RE.match(line)
            if not m:
                bad_lines += 1
                if bad_lines > max_bad_lines:
                    raise ValueError(
                        f"Too many malformed lines (> {max_bad_lines}). "
                        f"Last failure at line {line_no}: {line[:120]}"
                    )
                continue

            gd = m.groupdict()
            try:
                ts = _parse_time_nginx(gd["time"])
                method, path_ = _parse_request(gd["request"])
                if method is None or path_ is None:
                    bad_lines += 1
                    continue

                status = int(gd["status"])

                # bytes may be '-' sometimes
                bytes_raw = gd["bytes"]
                bytes_sent = int(bytes_raw) if bytes_raw.isdigit() else 0

                rows.append(
                    {
                        "timestamp": ts,
                        "ip": gd["ip"],
                        "method": method,
                        "path": path_,
                        "status": status,
                        "bytes_sent": bytes_sent,
                    }
                )
            except Exception:
                bad_lines += 1
                if bad_lines > max_bad_lines:
                    raise ValueError(
                        f"Too many malformed lines (> {max_bad_lines}). "
                        f"Last parse exception at line {line_no}: {line[:120]}"
                    )
                continue

    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError(f"No parseable log lines found in {path}")

    # Normalize types
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False)
    df["status"] = df["status"].astype(int)
    df["bytes_sent"] = df["bytes_sent"].astype(int)

    # Sort (critical for time-series)
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Optional: add helpful derived fields
    df["is_4xx"] = (df["status"] >= 400) & (df["status"] < 500)
    df["is_5xx"] = (df["status"] >= 500) & (df["status"] < 600)

    return df
