"""
smoke_test.py

Quick sanity check for the log ingestion pipeline.

This script runs the log parser and normalization steps on a sample NGINX
access log and performs a few basic assertions to make sure the pipeline is
working as expected.

It is meant to catch obvious issues early, such as:
- parsing failures that produce empty outputs
- missing derived columns required for analysis
- invalid or unsorted timestamps
- incorrect data types for key fields

The test is lightweight and can be run locally without any external
dependencies. It helps ensure that core ingestion logic remains stable as
the project evolves.
"""


from loglint.ingest.nginx_parser import parse_nginx_log
from loglint.ingest.normalize import normalize_events

df = parse_nginx_log("examples/sample_nginx.log")
df, rep = normalize_events(df)

assert len(df) > 0
assert "minute" in df.columns
assert df["timestamp"].is_monotonic_increasing
assert df["status"].dtype.kind in ("i", "u")
