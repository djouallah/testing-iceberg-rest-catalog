"""Temporary: is the Glue commit just eventually consistent? Delete once solved."""

import time

from catalogs import connect_catalog, table_clause

URL = "https://data.wa.aemo.com.au/datafiles/post-facilities/facilities.csv"


def step(label, fn):
    try:
        print(f"{label}: {fn()}", flush=True)
    except Exception as e:
        print(f"{label}: FAILED -> {str(e)[:300]}", flush=True)


def count(con, tbl):
    return con.sql(f"SELECT count(*) FROM cat_db.demo.{tbl}").fetchone()[0]


# 1. How do tables written by EARLIER runs read now, minutes later?
con = connect_catalog("glue")
for t in ("simple", "probe_ins", "probe_ctas"):
    step(f"pre-existing demo.{t}", lambda t=t: count(con, t))

# 2. Fresh write, then poll a fresh attach.
con.sql("USE cat_db.demo;")
step("drop", lambda: con.sql("DROP TABLE IF EXISTS probe_lag;") or "ok")
step("ctas", lambda: con.sql(f"""
    CREATE TABLE probe_lag {table_clause("glue", "probe_lag")} AS
        SELECT * FROM read_csv_auto('{URL}', normalize_names=true);
""") or "ok")
step("count immediately, same connection", lambda: count(con, "probe_lag"))
con.close()

for wait in (5, 10, 15, 30):
    time.sleep(wait)
    c = connect_catalog("glue")
    step(f"count on fresh attach, +{wait}s", lambda: count(c, "probe_lag"))
    c.close()
