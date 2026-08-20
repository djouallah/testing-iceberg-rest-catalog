"""Write a demo table (demo.spark_simple) to each catalog named in CATALOGS, via Spark.

The Spark twin of main.py: same comma-separated CATALOGS env var (default:
onelake), same per-catalog ok/ERROR report, same non-zero exit unless every
failure was expected. Error details are hidden unless DEBUG=1 (avoid leaking
secrets).

The table name differs from main.py's demo.simple on purpose: both engines write
to the same live catalogs, and a distinct table means the two workflows can never
race each other's DROP/CREATE.
"""

import os
import re
import tempfile
import urllib.request

from spark_catalogs import catalog_name, location_clause, spark_session

DB = "demo"
TBL = "spark_simple"
URL = "https://data.wa.aemo.com.au/datafiles/post-facilities/facilities.csv"

# Known-broken catalogs: reported ERROR but don't fail the CI job.
EXPECTED_FAILURES = {"unity_managed"}

# Catalogs that cannot take a CTAS. Carried over from main.py as a hypothesis to
# test, not an established fact: OneLake vends no credentials on createTable for
# DuckDB, and if Spark hits the same wall the gap is catalog-side. If a plain
# CTAS works here, drop onelake from this set and revisit the README claim.
CREATE_THEN_INSERT = {"onelake"}


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
        # Empty CREATE, then INSERT: createTable vends nothing, loadTable does.
        spark.sql(f"CREATE TABLE {where} {loc} AS SELECT * FROM src WHERE 1 = 0")
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
            results.append((cat, "ERROR", ""))
    spark.stop()

    width = max(len(c) for c, _, _ in results)
    print()
    for cat, status, detail in results:
        print(f"{cat.ljust(width)}  {status:6}  {detail}".rstrip())

    unexpected = [c for c, status, _ in results if status == "ERROR" and c not in EXPECTED_FAILURES]
    if unexpected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
