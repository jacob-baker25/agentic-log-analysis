import json
from pathlib import Path

from loglint.ingest.nginx_parser import parse_nginx_log
from loglint.ingest.normalize import normalize_events
from loglint.tools.metrics import compute_metrics

LOG_PATH = "examples/sample_nginx_with_incident.log"

df_raw = parse_nginx_log(LOG_PATH)
df, rep = normalize_events(df_raw, assume_tz="UTC")

metrics = compute_metrics(df)

print("baseline_5m:", metrics["traffic"]["baseline_5m"])
peak = metrics["errors"]["peak_5xx_window_5m"]
if peak:
    print("peak_total_requests:", peak.get("total_requests"))
    print("typical_requests_5m:", peak.get("typical_requests_5m"))
    print("traffic_multiplier_vs_typical:", peak.get("traffic_multiplier_vs_typical"))

out_path = Path("artifacts")
out_path.mkdir(exist_ok=True)
with open(out_path / "metrics.json", "w", encoding="utf-8") as f:
    json.dump(metrics, f, indent=2)

print("Wrote artifacts/metrics.json")
print("5xx_count:", metrics["errors"]["overall"]["5xx_count"])
print("peak_5xx_window_5m:", metrics["errors"]["peak_5xx_window_5m"])
print("top_5xx_paths:", metrics["errors"]["top_5xx_paths"][:3])

peak = metrics["errors"]["peak_5xx_window_5m"]
peak = metrics["errors"]["peak_5xx_window_5m"]
if peak is None:
    print("No 5xx detected; peak_5xx_window_5m is None")
else:
    print("peak window:", peak["window_start"], "->", peak["window_end"])
    print("peak totals:", peak["total_requests"], "req,", peak["5xx_count"], "5xx")
    print("peak 5xx rate:", peak["5xx_rate"])
    print("peak top paths:", peak["top_5xx_paths"][:3])
