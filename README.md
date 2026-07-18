# IRC — Iceberg REST catalog support (DuckDB)

| Catalog | Status | Notes |
| --- | :---: | --- |
| onelake | ✅ | on 1.4.5 — 1.5.4 bug, fix ongoing |
| r2 | ✅ | |
| s3_table | ✅ | |
| unity external storage | ✅ | |
| unity managed storage | ❌ | by design — no credential vending |
| Snowflake Open Catalog (external storage) | ✅ | managed Apache Polaris |
| Snowflake Horizon (managed storage) | ❌ | 403 on create-table — targets Snowflake DB `ICEBERG` / schema `demo`; that DB must be `CATALOG=SNOWFLAKE` + `EXTERNAL_VOLUME=SNOWFLAKE_MANAGED`, schema must exist (REST can't create it), and the role needs `CREATE ICEBERG TABLE`. Snowflake-side setup, not DuckDB |
