"""Iceberg REST catalog connections for DuckDB.

Starts with OneLake (Microsoft Fabric), authenticated via OIDC federation
instead of a client secret. Other catalogs (R2, S3 Tables, Polaris, Unity,
Horizon) get added below once their secrets are configured manually.
"""

import duckdb
from azure.identity import DefaultAzureCredential

# --- OneLake (Microsoft Fabric) ---------------------------------------------
ONELAKE_WAREHOUSE = "1c52481c-0523-4a5a-bbde-fdc932bd77c2/ac303243-4441-4885-9e7d-f4f5e7af194c"
ONELAKE_ENDPOINT = "https://onelake.table.fabric.microsoft.com/iceberg"
STORAGE_SCOPE = "https://storage.azure.com/.default"


def _onelake_token():
    """Storage token via OIDC federation.

    DefaultAzureCredential resolves the GitHub Actions federated token in CI
    (through `azure/login` -> Azure CLI credential) or your `az login` session
    locally. No client secret lives in the repo.
    """
    return DefaultAzureCredential().get_token(STORAGE_SCOPE).token


def connect_catalog(cat):
    """Return a fresh DuckDB connection with catalog `cat` attached as `cat_db`."""
    con = duckdb.connect()  # fresh, isolated state every call
    con.sql("INSTALL iceberg; LOAD iceberg;")

    match cat:
        case "onelake":
            con.sql(f"""
                ATTACH OR REPLACE '{ONELAKE_WAREHOUSE}' AS cat_db (
                    TYPE iceberg,
                    ENDPOINT '{ONELAKE_ENDPOINT}',
                    TOKEN '{_onelake_token()}',
                    SUPPORT_STAGE_CREATE false
                );
            """)

        # Add later, once secrets are configured manually:
        #   case "r2":       ...
        #   case "s3_table": ...
        #   case "polaris":  ...
        #   case "unity":    ...
        #   case "horizon":  ...

        case _:
            con.close()
            raise ValueError(f"Unknown or not-yet-configured catalog: {cat}")

    return con
