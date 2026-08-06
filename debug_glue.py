"""Temporary: work out why a Glue write leaves an empty table. Delete once solved."""

import os

from catalogs import connect_catalog, table_clause

URL = "https://data.wa.aemo.com.au/datafiles/post-facilities/facilities.csv"
LOC = os.environ["GLUE_LOCATION"].rstrip("/")


def step(label, fn):
    try:
        print(f"{label}: {fn()}")
    except Exception as e:
        print(f"{label}: FAILED -> {str(e)[:400]}")


con = connect_catalog("glue")
con.sql("USE cat_db.demo;")
step("drop", lambda: con.sql("DROP TABLE IF EXISTS simple;") or "ok")

# 1. CTAS — the path main.py takes.
step("ctas", lambda: con.sql(f"""
    CREATE TABLE simple {table_clause("glue", "simple")} AS
        SELECT * FROM read_csv_auto('{URL}', normalize_names=true);
""") or "ok")
step("count after ctas", lambda: con.sql("SELECT count(*) FROM simple").fetchone()[0])

# 2. Did the parquet actually reach S3? Distinguishes a failed write from a
#    failed metadata commit.
step("parquet files in S3", lambda: con.sql(
    f"SELECT count(*) FROM glob('{LOC}/simple/**/*.parquet')").fetchone()[0])
step("rows in those parquet", lambda: con.sql(
    f"SELECT count(*) FROM read_parquet('{LOC}/simple/**/*.parquet')").fetchone()[0])
step("metadata files in S3", lambda: con.sql(
    f"SELECT count(*) FROM glob('{LOC}/simple/**/*.json')").fetchone()[0])

# 3. Does an explicit INSERT commit where CTAS didn't?
step("insert", lambda: con.sql(
    f"INSERT INTO simple SELECT * FROM read_csv_auto('{URL}', normalize_names=true);") or "ok")
step("count after insert", lambda: con.sql("SELECT count(*) FROM simple").fetchone()[0])

# 4. Fresh connection — rules out stale in-session catalog state.
con.close()
con2 = connect_catalog("glue")
step("count on fresh attach", lambda: con2.sql("SELECT count(*) FROM cat_db.demo.simple").fetchone()[0])
