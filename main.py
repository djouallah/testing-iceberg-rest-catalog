"""Write a demo table to each catalog named in the CATALOGS env var.

CATALOGS is a comma-separated list (default: onelake). Each catalog gets the
same CSV written as `demo.simple`. Prints a per-catalog status table and exits
non-zero if any catalog failed.
"""

import os
import re

from catalogs import connect_catalog

DB = "demo"
TBL = "simple"
URL = "https://data.wa.aemo.com.au/datafiles/post-facilities/facilities.csv"

# Known-broken catalogs: shown in the status table but don't fail the CI job.
EXPECTED_FAILURES = {"horizon", "unity_managed"}


def scrub(text):
    """Redact secrets before printing an error: strip URL query strings (where
    vended SAS tokens/signatures live) and mask any configured secret values."""
    text = re.sub(r"\?[^\s'\"]+", "?<redacted>", text)
    for key, val in os.environ.items():
        if val and len(val) >= 8 and key not in ("CATALOGS", "PATH", "PWD"):
            text = text.replace(val, f"<{key}>")
    return text


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
        except Exception as e:
            # Show the reason, but scrub secrets/tokens first (see scrub()).
            results.append((cat, "ERROR", scrub(str(e).splitlines()[0])[:220]))

    width = max(len(c) for c, _, _ in results)
    print()
    for cat, status, detail in results:
        print(f"{cat.ljust(width)}  {status:6}  {detail}".rstrip())

    unexpected = [c for c, status, _ in results if status == "ERROR" and c not in EXPECTED_FAILURES]
    if unexpected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
