# Iceberg REST catalog write support (DuckDB)

| Catalog | Status | Notes |
| --- | :---: | --- |
| Microsoft OneLake | ✅ | private preview |
| Cloudflare R2 | ✅ | |
| AWS S3 Tables | ✅ | |
| Databricks Unity (external storage) | ✅ | |
| Snowflake Horizon (managed storage) | ✅ | |
| Databricks Unity (managed storage) | ❌ | by design — no credential vending |
| Google Lakehouse | ❓ | configuration not documented / not sure |
| AWS Glue (SageMaker Lakehouse) | ✅ | needs `ENDPOINT_TYPE 'glue'`, `PURGE_REQUESTED false`, and an explicit table location — a generic `ENDPOINT` attach silently loses every commit (Glue 2xx-drops the unsupported `/transactions/commit` route) |

## A real dbt project, verbatim

The table above is a single-table smoke test. The stronger claim: the full
[fabric-dbt-benchmark](https://github.com/djouallah/fabric-dbt-benchmark) dbt project —
staging, dimensions, incremental fact merges, data tests — runs **unchanged** against each
catalog. Nothing is forked or patched: the [dbt-catalogs](.github/workflows/dbt-catalogs.yml)
workflow clones the project, points dbt at the local [dbt/profiles.yml](dbt/profiles.yml), and
runs `dbt build --target <catalog>`. Switching catalogs is a profile switch.

| Target | dbt build | Notes |
| --- | :---: | --- |
| `onelake` | ✅ | ~1 min |
| `r2` | ✅ | ~1 min |
| `s3_table` | ✅ | ~1 min |
| `unity-external-storage` | ✅ | ~1 min |
| `horizon` | ✅ | ~1 min |
| `glue` | ❌ | Glue demands an explicit location on every `CREATE TABLE` and dbt-duckdb has no way to send one — [duckdb-iceberg#1299](https://github.com/duckdb/duckdb-iceberg/issues/1299) |

Runs are isolated in `dbt_landing` / `dbt_mart` (`DBT_SCHEMA=dbt`), so catalogs that also
hold production data are never touched.
