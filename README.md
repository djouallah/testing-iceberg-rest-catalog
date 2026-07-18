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

## Known issue

The original notebook's OneLake write failed with `NotFound` on the metadata folder. If CI
reproduces this, it's a warehouse/permission problem, not auth — fall back to a
connect-and-list step to confirm the OIDC token and attach work before debugging the write.
