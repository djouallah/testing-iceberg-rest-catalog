# IRC — Iceberg REST catalogs + DuckDB

Connect [DuckDB](https://duckdb.org/) to multiple Iceberg REST catalogs and write a demo table
to each. **OneLake** (Microsoft Fabric) authenticates via **OIDC federation** — no client secret
in the repo. The other catalogs read their credentials from GitHub Actions secrets.

| Catalog | DuckDB | Auth |
| --- | --- | --- |
| `onelake` | **1.4.5** (1.5.4 has a OneLake bug) | OIDC federation (`azure/login`) |
| `r2` | 1.5.4 | `ENDPOINT_R2` / `TOKEN_R2` / `R2_WAREHOUSE` |
| `s3_table` | 1.5.4 | `S3_KEY` / `S3_SECRET` / `TABLEBUCKETARN` |
| `unity` | 1.5.4 | `UC_ENDPOINT` / `UC_TOKEN` (vended credentials) |

OneLake warehouse: `1c52481c-0523-4a5a-bbde-fdc932bd77c2/ac303243-4441-4885-9e7d-f4f5e7af194c`

## Layout

| File | Purpose |
| --- | --- |
| `catalogs.py` | `connect_catalog(cat)` — attaches catalog `cat` as `cat_db` |
| `main.py` | Writes `demo.simple` to each catalog in `CATALOGS` env var; prints a status table |
| `.github/workflows/catalogs.yml` | Two jobs: `onelake` (1.4.5, OIDC) and `catalogs` (1.5.4, r2/s3/unity) |
| `requirements-onelake.txt` | `duckdb==1.4.5`, `azure-identity` |
| `requirements.txt` | `duckdb==1.5.4` |

> The reference Colab notebook stays local and is **gitignored**.

## Running

Verification happens on **GitHub Actions CI**, not locally. Trigger the `catalogs` workflow
(`workflow_dispatch`). `CATALOGS` (comma-separated) selects which catalogs a run writes to.

To run one locally, set its env vars (and `az login` for OneLake) then:

```bash
CATALOGS=onelake python main.py
```

## Prerequisites (one-time setup)

**OneLake OIDC** — an Azure app registration that trusts this repo:
1. **App registration** — note its **client id**. Add a **federated credential**:
   - Issuer: `https://token.actions.githubusercontent.com`
   - Subject: `repo:djouallah@12554469/IRC@1304884474:ref:refs/heads/main`
     (GitHub's immutable default for this repo — includes owner/repo IDs)
   - Audience: `api://AzureADTokenExchange`
2. **Grant OneLake access** — read/write on the Fabric workspace/warehouse `1c52481c-...`.
3. **GitHub secrets** — `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`.

**Other catalogs** — add the secrets listed in the table above (already configured).

## Adding more catalogs later

`polaris` and `horizon` are stubbed in `catalogs.py`. Add a `case`, supply the secret, and add
the catalog name to the `catalogs` job's `CATALOGS` list.

## DuckDB 1.4.5 / OneLake gotchas

Three things differ from the 1.5.x notebook and are needed for the OneLake write to succeed:

1. **ATTACH option name.** 1.4.5's iceberg extension uses `SUPPORT_STAGE_CREATE false`, not
   `STAGE_CREATE_TABLES` / `SKIP_CREATE_TABLE_METADATA_UPDATES` (those are 1.5.x).
2. **Separate storage credential.** The ATTACH `TOKEN` only authenticates the Iceberg REST
   catalog API. Writing the parquet data files to `onelake.dfs.fabric.microsoft.com` needs its
   own `TYPE azure, PROVIDER access_token` secret (created from the same OIDC token in `catalogs.py`).
3. **CA bundle path.** The azure extension looks for `/etc/pki/tls/certs/ca-bundle.crt` (RHEL);
   the workflow symlinks Ubuntu's `ca-certificates.crt` there so SSL to OneLake works.
