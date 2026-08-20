# Iceberg REST catalog write support (DuckDB)

| Catalog | Status | Notes |
| --- | :---: | --- |
| Microsoft OneLake | ✅ | private preview; credential vending, no storage credential of your own — but `CREATE TABLE AS SELECT` does not work yet, create the table then insert/merge (see below) |
| Cloudflare R2 | ✅ | |
| AWS S3 Tables | ✅ | |
| Databricks Unity (external storage) | ✅ | |
| Snowflake Horizon (managed storage) | ✅ | |
| Databricks Unity (managed storage) | ❌ | by design — no credential vending |
| Google Lakehouse | ❓ | configuration not documented / not sure |
| AWS Glue (SageMaker Lakehouse) | ✅ | needs `ENDPOINT_TYPE 'glue'`, `PURGE_REQUESTED false`, and an explicit table location — a generic `ENDPOINT` attach silently loses every commit (Glue 2xx-drops the unsupported `/transactions/commit` route) |

### OneLake credential vending: everything except CTAS

OneLake vends a per-table Azure SAS like the other managed services, so it attaches with no
storage credential of your own — no `ACCESS_DELEGATION_MODE` at all, since vended credentials is
the default. Your token authenticates the catalog API; the vended SAS covers the data files.

Two caveats:

- **Needs [duckdb-iceberg#1331](https://github.com/duckdb/duckdb-iceberg/pull/1331)**, merged into
  `v1.5-variegata` on 2026-08-19. Before it, the connection string built from the vended
  `adls.sas-token.*` key carried no `EndpointSuffix`, so the Azure SDK fell back to
  `core.windows.net` and resolved OneLake tables to `onelake.dfs.core.windows.net` — every vended
  access failed. The fix is not in the `core` extension repo yet (newest core build is v1.5.5,
  released a month before the merge), so [catalogs.py](catalogs.py) does
  `FORCE INSTALL iceberg FROM core_nightly`.
- **`CREATE TABLE AS SELECT` does not work.** OneLake vends nothing on `createTable`, so the CTAS
  writes its parquet unauthenticated and fails `Unauthorized` on
  `.../Tables/demo/simple/data/<uuid>.parquet`. `loadTable` *does* vend a writable SAS, so the
  workaround is to create the table first and then `INSERT` / `MERGE` into it — see
  `CREATE_THEN_INSERT` in [main.py](main.py). OneLake is fixing the vend on `createTable`; drop the
  workaround once it lands.

The dbt target in [dbt/profiles.yml](dbt/profiles.yml) is the exception: dbt-duckdb materializes
tables with a CTAS and offers no hook to split it, so that target stays on
`ACCESS_DELEGATION_MODE 'none'` plus an `onelake_storage` access-token secret until the vend on
`createTable` lands.

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
