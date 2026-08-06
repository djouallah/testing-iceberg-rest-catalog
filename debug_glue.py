"""Temporary: does the Glue commit land on the nightly (main) iceberg build?

Usage: python debug_glue.py [stable|nightly]. Delete once solved.
"""

import sys

import duckdb

from catalogs import connect_catalog, table_clause

channel = sys.argv[1] if len(sys.argv) > 1 else "stable"
tbl = f"probe_{channel}"

if channel == "nightly":
    duckdb.connect().sql("FORCE INSTALL iceberg FROM core_nightly;")

con = connect_catalog("glue")
print("duckdb        :", duckdb.__version__, flush=True)
print("iceberg ext   :", con.sql(
    "SELECT extension_version FROM duckdb_extensions() WHERE extension_name='iceberg'"
).fetchone()[0], flush=True)

con.sql("USE cat_db.demo;")
con.sql(f"DROP TABLE IF EXISTS {tbl};")
con.sql(f"CREATE TABLE {tbl} (a INTEGER) {table_clause('glue', tbl)};")
con.sql(f"INSERT INTO {tbl} VALUES (1),(2),(3);")
print("count in-session:", con.sql(f"SELECT count(*) FROM {tbl}").fetchone()[0], flush=True)
con.close()

con2 = connect_catalog("glue")
print("count on reattach:", con2.sql(f"SELECT count(*) FROM cat_db.demo.{tbl}").fetchone()[0], flush=True)
