"""Write a demo table (demo.simple) to each catalog named in the CATALOGS env var.

CATALOGS is a comma-separated list (default: onelake). Prints a per-catalog
ok/ERROR line and exits non-zero if a catalog that isn't an expected failure
fails. Error details are intentionally not printed (avoid leaking secrets).
"""

import os

from catalogs import connect_catalog

DB = "demo"
TBL = "simple"
URL = "https://data.wa.aemo.com.au/datafiles/post-facilities/facilities.csv"

# Known-broken catalogs: reported ERROR but don't fail the CI job.
EXPECTED_FAILURES = {"unity_managed"}


def write_demo(cat):
    con = connect_catalog(cat)
    con.sql(f"""
        CREATE SCHEMA IF NOT EXISTS cat_db.{DB};
        USE cat_db.{DB};
        DROP TABLE IF EXISTS {TBL};
        CREATE TABLE {TBL} AS
            SELECT * FROM read_csv_auto('{URL}', normalize_names=true);
    """)
    n = con.sql(f"SELECT count(*) FROM cat_db.{DB}.{TBL}").fetchone()[0]
    con.close()
    return n


def main():
    cats = [c.strip() for c in os.environ.get("CATALOGS", "onelake").split(",") if c.strip()]
    results = []
    for cat in cats:
        try:
            n = write_demo(cat)
            results.append((cat, "ok", f"{n} rows"))
        except Exception:
            # Errors intentionally not printed — they can carry vended tokens / URLs.
            results.append((cat, "ERROR", ""))

    width = max(len(c) for c, _, _ in results)
    print()
    for cat, status, detail in results:
        print(f"{cat.ljust(width)}  {status:6}  {detail}".rstrip())

    unexpected = [c for c, status, _ in results if status == "ERROR" and c not in EXPECTED_FAILURES]
    if unexpected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
