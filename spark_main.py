"""Write a demo table (demo.spark_simple) to each catalog named in CATALOGS, via Spark.

The Spark twin of main.py: same comma-separated CATALOGS env var (default:
onelake), same per-catalog ok/ERROR report, same non-zero exit if any catalog
fails. Error details are hidden unless DEBUG=1 (avoid leaking secrets); the
ERROR line names the exception class.

The table name differs from main.py's demo.simple on purpose: both engines write
to the same live catalogs, and a distinct table means the two workflows can never
race each other's DROP/CREATE.
"""

import os
import re
import tempfile
import urllib.request

from catalogs import error_label
from spark_catalogs import catalog_name, location_clause, spark_session

DB = "demo"
TBL = "spark_simple"
URL = "https://data.wa.aemo.com.au/datafiles/post-facilities/facilities.csv"

# Catalogs that cannot take a CTAS — exactly the managed-storage ones, which is
# also exactly the set catalogs.py gives STAGE_CREATE_TABLES false. Spark's CTAS
# stages the table first, and a staged create carries a location the catalog did
# not choose:
#   Snowflake documents both halves outright — "You can't specify a base location
#   with your CREATE TABLE statement" and "CREATE TABLE AS SELECT (CTAS) from an
#   external engine is not supported" — and Horizon rejects it with
#   BadRequestException: Malformed request: Setting table location is not allowed.
#   OneLake refuses for its own reason: it vends no credentials on createTable.
# So these get a real CREATE TABLE with a column list, then an INSERT.
CREATE_THEN_INSERT = {"onelake", "s3_table", "horizon"}


def _load_source(spark):
    """The AEMO CSV as a DataFrame, with DuckDB's normalize_names=true naming.

    Spark cannot read https:// directly (main.py leans on DuckDB's read_csv_auto),
    so download once and normalize the header the same way, keeping both engines
    on the same schema.
    """
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    urllib.request.urlretrieve(URL, path)
    df = spark.read.csv(path, header=True, inferSchema=True)
    return df.toDF(*[re.sub(r"[^0-9a-z]+", "_", c.lower()).strip("_") for c in df.columns])


def write_demo(spark, src, cat, config_errors):
    if cat in config_errors:  # never registered — missing secret, unknown catalog
        raise config_errors[cat]
    name = catalog_name(cat)
    src.createOrReplaceTempView("src")
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {name}.{DB}")
    spark.sql(f"DROP TABLE IF EXISTS {name}.{DB}.{TBL}")

    where = f"{name}.{DB}.{TBL}"
    loc = location_clause(cat, TBL)
    if cat in CREATE_THEN_INSERT:
        # A column list, not `AS SELECT ... WHERE 1 = 0` — that is still a CTAS
        # and would be refused for the same reason.
        cols = ", ".join(f"{f.name} {f.dataType.simpleString()}" for f in src.schema.fields)
        spark.sql(f"CREATE TABLE {where} ({cols}) USING iceberg {loc}")
        # BY NAME so this doesn't rely on the catalog round-tripping column order.
        spark.sql(f"INSERT INTO {where} BY NAME SELECT * FROM src")
    else:
        spark.sql(f"CREATE TABLE {where} {loc} AS SELECT * FROM src")

    n = spark.sql(f"SELECT count(*) FROM {where}").collect()[0][0]
    if not n:
        # Table created but empty — the snapshot commit didn't land. Silent data
        # loss, so treat it as a failure rather than reporting ok.
        raise RuntimeError("table is empty after write")
    return n


def main():
    cats = [c.strip() for c in os.environ.get("CATALOGS", "onelake").split(",") if c.strip()]
    # One session holds every catalog: jars and extensions are fixed at creation.
    spark, config_errors = spark_session(cats)
    src = _load_source(spark)

    results = []
    for cat in cats:
        try:
            n = write_demo(spark, src, cat, config_errors)
            results.append((cat, "ok", f"{n} rows"))
        except Exception as e:
            # Errors are hidden by default — they can carry vended tokens / URLs.
            # Set DEBUG=1 (workflow_dispatch `debug` input) to see them.
            if os.environ.get("DEBUG") == "1":
                print(f"--- {cat} ---\n{e}\n")
            results.append((cat, "ERROR", error_label(e)))
    spark.stop()

    width = max(len(c) for c, _, _ in results)
    print()
    for cat, status, detail in results:
        print(f"{cat.ljust(width)}  {status:6}  {detail}".rstrip())

    if any(status == "ERROR" for _, status, _ in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
