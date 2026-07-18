# IRC — OneLake Iceberg REST + DuckDB

Connect [DuckDB](https://duckdb.org/) 1.4.5 to a Microsoft Fabric **OneLake** Iceberg REST
catalog and write a demo table. Authentication uses **OIDC federation** (workload identity),
so no client secret lives in the repo.

Warehouse: `1c52481c-0523-4a5a-bbde-fdc932bd77c2/ac303243-4441-4885-9e7d-f4f5e7af194c`
Endpoint: `https://onelake.table.fabric.microsoft.com/iceberg`

## Layout

| File | Purpose |
| --- | --- |
| `catalogs.py` | `connect_catalog("onelake")` — attaches the warehouse, token via OIDC federation |
| `main.py` | Creates schema `demo` and writes table `simple` from a CSV |
| `.github/workflows/onelake.yml` | Runs `main.py` on GitHub Actions with `azure/login@v2` OIDC |
| `requirements.txt` | `duckdb==1.4.5`, `azure-identity`, `pandas` |

> The reference Colab notebook stays local and is **gitignored**.

## Running

Verification happens on **GitHub Actions CI**, not locally. Trigger the `onelake-irc`
workflow (`workflow_dispatch`) once the prerequisites below are set.

To run locally instead, `az login` first (DefaultAzureCredential picks up the CLI session):

```bash
pip install -r requirements.txt
python main.py
```

## Prerequisites (one-time Azure + GitHub setup)

OIDC federation needs an Azure app registration that trusts this repo. Done manually:

1. **App registration** — note its **client id**. Add a **federated credential**:
   - Issuer: `https://token.actions.githubusercontent.com`
   - Subject: `repo:djouallah/IRC:ref:refs/heads/main`
   - Audience: `api://AzureADTokenExchange`
2. **Grant OneLake access** — give that service principal read/write on the Fabric
   workspace/warehouse `1c52481c-...`. Without it, the `simple` write fails.
3. **GitHub repo secrets** — add `AZURE_CLIENT_ID` and `AZURE_TENANT_ID`.

## Adding more catalogs later

Other catalogs (R2, S3 Tables, Polaris, Unity, Horizon) are stubbed out in `catalogs.py`.
Add a `case` there and supply the secret manually (GitHub secret or `.env`, both gitignored).

## DuckDB 1.4.5 / OneLake gotchas

Three things differ from the 1.5.x notebook and are needed for the write to succeed:

1. **ATTACH option name.** 1.4.5's iceberg extension uses `SUPPORT_STAGE_CREATE false`, not
   `STAGE_CREATE_TABLES` / `SKIP_CREATE_TABLE_METADATA_UPDATES` (those are 1.5.x).
2. **Separate storage credential.** The ATTACH `TOKEN` only authenticates the Iceberg REST
   catalog API. Writing the parquet data files to `onelake.dfs.fabric.microsoft.com` needs its
   own `TYPE azure, PROVIDER access_token` secret (created from the same OIDC token in `catalogs.py`).
3. **CA bundle path.** The azure extension looks for `/etc/pki/tls/certs/ca-bundle.crt` (RHEL);
   the workflow symlinks Ubuntu's `ca-certificates.crt` there so SSL to OneLake works.
