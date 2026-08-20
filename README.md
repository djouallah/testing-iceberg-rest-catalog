# Iceberg REST catalog write support (DuckDB)

| Catalog | Status | Notes |
| --- | :---: | --- |
| Microsoft OneLake | ✅ | private preview; needs `ACCESS_DELEGATION_MODE 'none'` and your own storage token — the vended SAS reads but does not write (see below) |
| Cloudflare R2 | ✅ | |
| AWS S3 Tables | ✅ | |
| Databricks Unity (external storage) | ✅ | |
| Snowflake Horizon (managed storage) | ✅ | |
| Databricks Unity (managed storage) | ❌ | by design — no credential vending |
| Google Lakehouse | ❓ | configuration not documented / not sure |
| AWS Glue (SageMaker Lakehouse) | ✅ | needs `ENDPOINT_TYPE 'glue'`, `PURGE_REQUESTED false`, and an explicit table location — a generic `ENDPOINT` attach silently loses every commit (Glue 2xx-drops the unsupported `/transactions/commit` route) |

### OneLake credential vending: reads yes, writes no

OneLake vends a per-table Azure SAS like the other managed services, so in principle it should
attach with `ACCESS_DELEGATION_MODE 'vended_credentials'` and no storage credential of your own.
Two things were in the way, and only one is fixed:

- **Fixed.** duckdb-iceberg built the connection string from the vended `adls.sas-token.*` key
  without an `EndpointSuffix`, so the Azure SDK fell back to `core.windows.net` and resolved
  OneLake tables to `onelake.dfs.core.windows.net`. Every vended access failed.
  [duckdb-iceberg#1331](https://github.com/duckdb/duckdb-iceberg/pull/1331), merged into
  `v1.5-variegata` on 2026-08-19, takes the suffix from the same key. Reads then work.
- **Not fixed.** The vended SAS still will not write. Tried on 2026-08-20: `CREATE TABLE` fails
  `Unauthorized` opening `.../Tables/demo/simple/data/<uuid>.parquet`, with the host and the path
  both correct — so this is OneLake declining the write, not a client-side URL problem.

Hence `ACCESS_DELEGATION_MODE 'none'` plus an `onelake_storage` access-token secret. Since this
table is a **write**-support matrix, that is the configuration it reports on. Flip the mode back
to `'vended_credentials'` to retest once OneLake vends a writable SAS.

## A real dbt project, verbatim

The table above is a single-table smoke test. The stronger claim: the full
[fabric-dbt-benchmark](https://github.com/djouallah/fabric-dbt-benchmark) dbt project —
staging, dimensions, incremental fact merges, data tests — runs **unchanged** against each
managed IRC service (the catalog provides the storage too). Nothing is forked or patched:
the [dbt-catalogs](.github/workflows/dbt-catalogs.yml) workflow clones the project, points
dbt at the local [dbt/profiles.yml](dbt/profiles.yml), and runs `dbt build --target
<catalog>`. Switching catalogs is a profile switch.

| Target | dbt build | Notes |
| --- | :---: | --- |
| `onelake` | ✅ | ~1 min |
| `r2` | ✅ | ~1 min |
| `s3_table` | ✅ | ~1 min |
| `horizon` | ✅ | ~1 min |

Bring-your-own-bucket catalogs are out of scope here: Unity external storage by design,
Glue because it demands an explicit location on every `CREATE TABLE` and dbt-duckdb has no
way to send one — [duckdb-iceberg#1299](https://github.com/duckdb/duckdb-iceberg/issues/1299).

Runs are isolated in `dbt_landing` / `dbt_mart` (`DBT_SCHEMA=dbt`), so catalogs that also
hold production data are never touched.
