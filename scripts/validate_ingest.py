"""
validate_ingest.py

Simple script to check that log parsing and normalization are working correctly.

This script loads a sample NGINX access log, runs it through the parser and
normalization steps, and prints out basic information about the results
(e.g., number of rows, time range, status code counts).

It is meant to be run by a developer to quickly confirm that the ingested
data looks reasonable before moving on to metric computation or AI analysis.

This is not a test suite and does not use assertions.
"""

from loglint.ingest.nginx_parser import parse_nginx_log
from loglint.ingest.normalize import normalize_events

df_raw = parse_nginx_log("examples/sample_nginx_with_incident.log")
df, rep = normalize_events(df_raw, assume_tz="UTC")

print("=== Normalize Report ===")
print(rep)

print("\n=== Head ===")
print(df.head())

print("\n=== Dtypes ===")
print(df.dtypes)

print("\n=== Basic Sanity ===")
print("rows:", len(df))
print("time range:", df["timestamp"].min(), "->", df["timestamp"].max())
print("unique IPs:", df["ip"].nunique())
print("status counts:\n", df["status_class"].value_counts().sort_index())
print("5xx:", int(df["is_5xx"].sum()), "4xx:", int(df["is_4xx"].sum()))
