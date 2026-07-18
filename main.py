"""Attach the OneLake Iceberg REST catalog and write a demo table."""

from catalogs import connect_catalog

DB = "demo"
TBL = "simple"
URL = "https://data.wa.aemo.com.au/datafiles/post-facilities/facilities.csv"


def main():
    con = connect_catalog("onelake")
    con.sql(f"""
        CREATE SCHEMA IF NOT EXISTS cat_db.{DB};
        USE cat_db.{DB};
        DROP TABLE IF EXISTS {TBL};
        CREATE TABLE {TBL} AS
            SELECT * FROM read_csv_auto('{URL}', normalize_names=true);
    """)
    print(con.sql(f"SELECT count(*) AS rows FROM cat_db.{DB}.{TBL}").df())
    con.close()


if __name__ == "__main__":
    main()
