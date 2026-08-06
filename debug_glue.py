"""Temporary: work out why a Glue write leaves an empty table. Delete once solved."""

import os

from catalogs import connect_catalog, table_clause

LOC = os.environ["GLUE_LOCATION"].rstrip("/")


def step(label, fn):
    try:
        print(f"{label}: {fn()}")
    except Exception as e:
        print(f"{label}: FAILED -> {str(e)[:300]}")


def versions(tbl):
    """Metadata versions committed for `tbl`, with their snapshot counts."""
    return con.sql(f"""
        SELECT regexp_extract(filename, '[^/]+$')[1:5] AS v,
               len(COALESCE(snapshots, [])) AS snaps
        FROM read_json('{LOC}/{tbl}/metadata/*.json', filename=true, union_by_name=true)
        ORDER BY v
    """).fetchall()


con = connect_catalog("glue")
con.sql("USE cat_db.demo;")

# A: explicit CREATE then INSERT — the path the DuckDB 1.5 notes say works.
step("A drop", lambda: con.sql("DROP TABLE IF EXISTS probe_ins;") or "ok")
step("A create", lambda: con.sql(
    f"CREATE TABLE probe_ins (a INTEGER) {table_clause('glue', 'probe_ins')};") or "ok")
step("A versions after create", lambda: versions("probe_ins"))
step("A insert", lambda: con.sql("INSERT INTO probe_ins VALUES (1),(2),(3);") or "ok")
step("A count", lambda: con.sql("SELECT count(*) FROM probe_ins").fetchone()[0])
step("A versions after insert", lambda: versions("probe_ins"))

# B: same thing via CTAS, for comparison.
step("B drop", lambda: con.sql("DROP TABLE IF EXISTS probe_ctas;") or "ok")
step("B ctas", lambda: con.sql(
    f"CREATE TABLE probe_ctas {table_clause('glue', 'probe_ctas')} AS SELECT 1 AS a;") or "ok")
step("B count", lambda: con.sql("SELECT count(*) FROM probe_ctas").fetchone()[0])
step("B versions", lambda: versions("probe_ctas"))
