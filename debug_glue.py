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

step("namespaces", lambda: con.sql(
    "SELECT schema_name FROM information_schema.schemata WHERE catalog_name='cat_db'").fetchall())

con.sql("USE cat_db.demo;")
step("drop", lambda: con.sql("DROP TABLE IF EXISTS simple;") or "ok")
step("ctas", lambda: con.sql(f"""
    CREATE TABLE simple {table_clause("glue", "simple")} AS
        SELECT * FROM read_csv_auto('{URL}', normalize_names=true);
""") or "ok")
step("count after ctas", lambda: con.sql("SELECT count(*) FROM simple").fetchone()[0])

# Where did the files actually go, and did the metadata get a snapshot?
step("all files under table dir", lambda: con.sql(
    f"SELECT file FROM glob('{LOC}/simple/**') ORDER BY file").fetchall())
step("snapshots in metadata json", lambda: con.sql(f"""
    SELECT regexp_extract(filename, '[^/]+$') AS f,
           len(COALESCE(snapshots, [])) AS n_snapshots,
           "current-snapshot-id", location
    FROM read_json('{LOC}/simple/metadata/*.json', filename=true, union_by_name=true)
    ORDER BY f
""").fetchall())
