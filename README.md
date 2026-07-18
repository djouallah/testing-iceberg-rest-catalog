# IRC — Iceberg REST catalog support (DuckDB)

| Catalog | Status | Notes |
| --- | :---: | --- |
| onelake | ✅ | on 1.4.5 — 1.5.4 bug, fix ongoing |
| r2 | ✅ | |
| s3_table | ✅ | |
| unity external storage | ✅ | |
| unity managed storage | ❌ | by design — no credential vending |
| Snowflake Open Catalog (external storage) | ✅ | managed Apache Polaris |
| Snowflake Horizon (managed storage) | ❌ | 403 on create-table — namespace must be an existing Snowflake `database.schema` (REST can't create `demo`) with `CREATE ICEBERG TABLE` + external-volume `USAGE`. Snowflake-side setup, not DuckDB |
