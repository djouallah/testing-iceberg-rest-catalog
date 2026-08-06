"""Temporary: verify the two candidate fixes for the silent Glue commit loss. Delete once solved.

Root cause: with the generic ENDPOINT attach, duckdb-iceberg assumes the catalog
supports POST /v1/{prefix}/transactions/commit and sends snapshot commits there.
Glue does not implement that route and answers with a 2xx it never applies, so
the table stays at metadata version 00000 with zero snapshots. Both variants
below force per-table UpdateTable commits, which Glue does support.

Usage: python debug_glue.py [a|b]
  a = ENDPOINT_TYPE 'glue' (docs-blessed convenience form)
  b = explicit ENDPOINT + DISABLE_MULTI_TABLE_COMMIT true
"""

import os
import sys

import boto3
import duckdb


def attach(variant):
    con = duckdb.connect()
    region = os.environ["GLUE_REGION"]
    con.sql(f"""
        CREATE OR REPLACE SECRET glue_secret (
            TYPE S3,
            KEY_ID '{os.environ["S3_KEY"]}',
            SECRET '{os.environ["S3_SECRET"]}',
            REGION '{region}'
        );
    """)
    if variant == "a":
        con.sql(f"""
            ATTACH OR REPLACE '{os.environ["GLUE_WAREHOUSE"]}' AS cat_db (
                TYPE iceberg,
                ENDPOINT_TYPE 'glue',
                SECRET glue_secret
            );
        """)
    else:
        con.sql(f"""
            ATTACH OR REPLACE '{os.environ["GLUE_WAREHOUSE"]}' AS cat_db (
                TYPE iceberg,
                ENDPOINT 'https://glue.{region}.amazonaws.com/iceberg',
                AUTHORIZATION_TYPE 'sigv4',
                STAGE_CREATE_TABLES false,
                DISABLE_MULTI_TABLE_COMMIT true,
                SECRET glue_secret
            );
        """)
    return con


variant = sys.argv[1] if len(sys.argv) > 1 else "a"
tbl = f"probe_fix_{variant}"
location = f"{os.environ['GLUE_LOCATION'].rstrip('/')}/{tbl}"

con = attach(variant)
print("duckdb        :", duckdb.__version__, flush=True)
print("iceberg ext   :", con.sql(
    "SELECT extension_version FROM duckdb_extensions() WHERE extension_name='iceberg'"
).fetchone()[0], flush=True)

con.sql(f"DROP TABLE IF EXISTS cat_db.demo.{tbl};")
con.sql(f"CREATE TABLE cat_db.demo.{tbl} (a INTEGER) WITH ('location' = '{location}');")
con.sql(f"INSERT INTO cat_db.demo.{tbl} VALUES (1),(2),(3);")
print("count in-session:", con.sql(f"SELECT count(*) FROM cat_db.demo.{tbl}").fetchone()[0], flush=True)
con.close()

con2 = attach(variant)
print("count on reattach:", con2.sql(f"SELECT count(*) FROM cat_db.demo.{tbl}").fetchone()[0], flush=True)
con2.close()

# The commit landed iff Glue's pointer moved past version 00000.
glue = boto3.client(
    "glue",
    region_name=os.environ["GLUE_REGION"],
    aws_access_key_id=os.environ["S3_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET"],
)
meta = glue.get_table(DatabaseName="demo", Name=tbl)["Table"]["Parameters"].get("metadata_location", "")
print("metadata_location file:", meta.rsplit("/", 1)[-1], flush=True)
