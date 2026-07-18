# IRC — Iceberg REST catalog support (DuckDB)

| Catalog | Status | Notes |
| --- | :---: | --- |
| onelake | ✅ | on 1.4.5 — 1.5.4 bug, fix ongoing |
| r2 | ✅ | |
| s3_table | ✅ | |
| unity external storage | ✅ | |
| unity managed storage | ❌ | by design — no credential vending |
| Snowflake Open Catalog (external storage) | ✅ | managed Apache Polaris |
| Snowflake Horizon (managed storage) | ✅ | needs the DB set to `CATALOG=SNOWFLAKE` + `EXTERNAL_VOLUME=SNOWFLAKE_MANAGED`, the schema pre-created, and `CREATE ICEBERG TABLE` granted to the role |
