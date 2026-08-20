# Iceberg REST catalog write support

Two engines write the same demo table to the same catalogs, so a failure can be attributed:
a ❌ under both is a catalog gap, a ❌ under one is a client gap.

## DuckDB

| Catalog | Status | Notes |
| --- | :---: | --- |
| Microsoft OneLake | ✅ | private preview; credential vending, no storage credential of your own — but `CREATE TABLE AS SELECT` does not work yet, create the table then insert/merge (see below) |
| Cloudflare R2 | ✅ | |
| AWS S3 Tables | ✅ | |
| Databricks Unity (external storage) | ✅ | |
| Snowflake Horizon (managed storage) | ✅ | |
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

## Spark

PySpark 4.1 + `iceberg-spark-runtime-4.1_2.13:1.11.0`, run by the
[spark-catalogs](.github/workflows/spark-catalogs.yml) workflow. Same seven catalogs, same
credentials, writing `demo.spark_simple` — a distinct table so the two workflows can never race
each other. Not 4.2, despite Spark 4.2.0 having shipped: Iceberg builds a dedicated runtime per
Spark *minor*, and 4.1 is the newest one with a runtime.

| Catalog | Status | Notes |
| --- | :---: | --- |
| Cloudflare R2 | ✅ | |
| AWS S3 Tables | ✅ | no CTAS — `CREATE TABLE` then `INSERT` (see below) |
| Databricks Unity (external storage) | ✅ | |
| Snowflake Horizon (managed storage) | ✅ | no CTAS; `credential` takes the token bare, the role rides on `scope` |
| Microsoft OneLake | ❌ | `BadRequestException` on create — the endpoint documents no metadata-write support yet |
| AWS Glue (SageMaker Lakehouse) | ❌ | `BadRequestException` — unresolved, `warehouse` format suspected |

Every ✅ writes the same 176 rows DuckDB does.

Spark has no equivalent of DuckDB's `ENDPOINT_TYPE`, so S3 Tables and Glue are reached through
their own Iceberg REST endpoints (`s3tables.<region>.amazonaws.com/iceberg`,
`glue.<region>.amazonaws.com/iceberg`) with SigV4 signing.

### Managed storage rejects a CTAS

Spark's `CREATE TABLE AS SELECT` stages the table first, and a staged create carries a location
the client picked. The managed services refuse it — they choose storage themselves. Horizon says
so outright:

```
BadRequestException: Malformed request: Setting table location is not allowed
```

and Snowflake documents both halves: *"You can't specify a base location with your CREATE TABLE
statement"* and *"CREATE TABLE AS SELECT (CTAS) from an external engine is not supported."* The
fix is a real `CREATE TABLE` with a column list, then `INSERT` — `CREATE TABLE ... AS SELECT ...
WHERE 1 = 0` does not work, because it is still a CTAS. See `CREATE_THEN_INSERT` in
[spark_main.py](spark_main.py).

This is the same boundary DuckDB hits from the other side: `CREATE_THEN_INSERT` here holds
`onelake`, `s3_table` and `horizon` — exactly the catalogs [catalogs.py](catalogs.py) gives
`STAGE_CREATE_TABLES false`. Two engines, two mechanisms, one line: managed storage will not take
a location from the client.

### The two Spark can't reach

Neither is explained away — both still fail, and the notes below are where the search stopped,
not a conclusion.

- **OneLake.** Microsoft documents that metadata write operations aren't supported by the OneLake
  table API endpoint yet. That fits the shape of the DuckDB config, which only gets through with
  `SKIP_CREATE_TABLE_METADATA_UPDATES true` — a duckdb-iceberg flag with no Spark equivalent. If
  that is the whole story, this is the sharpest result in the repo: OneLake's write support is
  currently reachable only from a client that can be told to skip the calls it doesn't implement.
- **Glue.** The Glue REST endpoint wants `warehouse` set to the AWS **account id**, or
  `accountId:catalog1/catalog2` for a nested catalog — which is not necessarily what
  `GLUE_WAREHOUSE` holds, since that secret was written for DuckDB's `ENDPOINT_TYPE 'glue'`.
  Worth checking before looking anywhere else.

## A real dbt project, verbatim

The tables above are single-table smoke tests. The stronger claim: the full
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
