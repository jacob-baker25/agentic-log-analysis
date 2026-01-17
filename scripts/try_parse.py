from loglint.ingest.nginx_parser import parse_nginx_log

df = parse_nginx_log("examples/sample_nginx.log")
print(df.head(10))
print(df.dtypes)
print("Rows:", len(df))
print("Time range:", df["timestamp"].min(), "->", df["timestamp"].max())
print("5xx count:", df["is_5xx"].sum())
