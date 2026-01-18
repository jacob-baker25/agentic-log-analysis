"""
This script is a quick sanity check for the NGINX log parser.

It loads a sample NGINX access log, runs it through the parser,
and prints basic information about the resulting DataFrame.

The goal is to verify that:
- log lines are being parsed correctly
- timestamps and numeric fields have the expected types
- the dataset looks reasonable before building metrics or AI logic

This script is for local development and debugging only and is not
part of the main AI pipeline.
"""


from loglint.ingest.nginx_parser import parse_nginx_log

df = parse_nginx_log("examples/sample_nginx.log")
print(df.head(10))
print(df.dtypes)
print("Rows:", len(df))
print("Time range:", df["timestamp"].min(), "->", df["timestamp"].max())
print("5xx count:", df["is_5xx"].sum())
