"""Iceberg REST catalog connections for DuckDB.

OneLake runs on DuckDB 1.4.5 (1.5.4 has a OneLake bug), authenticated via OIDC
federation. The other catalogs (R2, S3 Tables, Unity) run on DuckDB 1.5.4 and
read their credentials from environment variables (GitHub Actions secrets).
"""

import os
import duckdb

# --- OneLake (Microsoft Fabric) — DuckDB 1.4.5 ------------------------------
ONELAKE_WAREHOUSE = "1c52481c-0523-4a5a-bbde-fdc932bd77c2/ac303243-4441-4885-9e7d-f4f5e7af194c"
ONELAKE_ENDPOINT = "https://onelake.table.fabric.microsoft.com/iceberg"
STORAGE_SCOPE = "https://storage.azure.com/.default"

# --- S3 Tables (AWS) --------------------------------------------------------
S3_TABLES_REGION = "ap-southeast-2"


def _onelake_token():
    """Storage token via OIDC federation (lazy import so non-OneLake jobs,
    which don't install azure-identity, can import this module)."""
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential().get_token(STORAGE_SCOPE).token


def connect_catalog(cat):
    """Return a fresh DuckDB connection with catalog `cat` attached as `cat_db`."""
    con = duckdb.connect()  # fresh, isolated state every call
    con.sql("INSTALL iceberg; LOAD iceberg;")

    match cat:
        case "onelake":  # DuckDB 1.4.5 only
            token = _onelake_token()  # one token for both the catalog API and storage
            con.sql("INSTALL azure; LOAD azure;")
            # Storage credential so DuckDB can write the parquet data files to
            # OneLake. The ATTACH TOKEN below only authenticates the catalog API.
            con.sql(f"""
                CREATE OR REPLACE SECRET onelake_storage (
                    TYPE azure,
                    PROVIDER access_token,
                    ACCESS_TOKEN '{token}',
                    ACCOUNT_NAME 'onelake',
                    ENDPOINT 'onelake.dfs.fabric.microsoft.com'
                );
            """)
            con.sql(f"""
                ATTACH OR REPLACE '{ONELAKE_WAREHOUSE}' AS cat_db (
                    TYPE iceberg,
                    ENDPOINT '{ONELAKE_ENDPOINT}',
                    TOKEN '{token}',
                    SUPPORT_STAGE_CREATE false
                );
            """)

        case "r2":  # Cloudflare R2 Data Catalog
            wh = os.environ["R2_WAREHOUSE"]
            ep = os.environ["ENDPOINT_R2"]
            tok = os.environ["TOKEN_R2"]
            con.sql(f"""
                ATTACH OR REPLACE '{wh}' AS cat_db (
                    TYPE iceberg, ENDPOINT '{ep}', TOKEN '{tok}'
                );
            """)

        case "s3_table":  # AWS S3 Tables
            con.sql(f"""
                CREATE OR REPLACE SECRET s3_table (
                    TYPE S3,
                    KEY_ID '{os.environ["S3_KEY"]}',
                    SECRET '{os.environ["S3_SECRET"]}',
                    REGION '{S3_TABLES_REGION}'
                );
            """)
            con.sql(f"""
                ATTACH OR REPLACE '{os.environ["TABLEBUCKETARN"]}' AS cat_db (
                    TYPE iceberg, ENDPOINT_TYPE s3_tables,
                    STAGE_CREATE_TABLES false, SECRET s3_table
                );
            """)

        case "unity":  # Databricks Unity Catalog (external storage, vended creds)
            con.sql(f"""
                CREATE OR REPLACE SECRET uc_secret (
                    TYPE iceberg, TOKEN '{os.environ["UC_TOKEN"]}'
                );
            """)
            con.sql(f"""
                ATTACH OR REPLACE 'iceberg' AS cat_db (
                    TYPE iceberg, SECRET uc_secret,
                    ENDPOINT '{os.environ["UC_ENDPOINT"]}',
                    ACCESS_DELEGATION_MODE 'vended_credentials'
                );
            """)

        case "unity_managed":  # Unity Catalog managed storage (serverless)
            con.sql(f"""
                CREATE OR REPLACE SECRET uc_secret (
                    TYPE iceberg, TOKEN '{os.environ["UC_TOKEN"]}'
                );
            """)
            con.sql(f"""
                ATTACH OR REPLACE 'serverless' AS cat_db (
                    TYPE iceberg, SECRET uc_secret,
                    ENDPOINT '{os.environ["UC_ENDPOINT"]}',
                    ACCESS_DELEGATION_MODE 'vended_credentials'
                );
            """)

        case "polaris":  # Snowflake Open Catalog (Polaris)
            con.sql(f"""
                CREATE OR REPLACE SECRET pol_secret (
                    TYPE iceberg,
                    CLIENT_ID '{os.environ["POLARIS_CLIENT"]}',
                    CLIENT_SECRET '{os.environ["POLARIS_SECRET"]}',
                    OAUTH2_SERVER_URI '{os.environ["POLARIS_TOKEN_ENDPOINT"]}',
                    OAUTH2_SCOPE 'PRINCIPAL_ROLE:data_engineer'
                );
            """)
            con.sql(f"""
                ATTACH OR REPLACE 'dwh' AS cat_db (
                    TYPE iceberg, ENDPOINT '{os.environ["POLARIS_ENDPOINT"]}',
                    SECRET pol_secret, DEFAULT_REGION 'us-east-1'
                );
            """)

        case "horizon":  # Snowflake Horizon (managed storage)
            ep = os.environ["HORIZON_ENDPOINT"]
            con.sql(f"""
                CREATE OR REPLACE SECRET horizon_secret (
                    TYPE iceberg, CLIENT_ID '',
                    CLIENT_SECRET '{os.environ["HORIZON_TOKEN"]}',
                    OAUTH2_SERVER_URI '{ep}/v1/oauth/tokens',
                    OAUTH2_GRANT_TYPE 'client_credentials',
                    OAUTH2_SCOPE 'session:role:DATA_ENGINEER'
                );
            """)
            con.sql(f"""
                ATTACH OR REPLACE 'ICEBERG' AS cat_db (
                    TYPE iceberg, SECRET horizon_secret, ENDPOINT '{ep}',
                    ACCESS_DELEGATION_MODE 'vended_credentials',
                    SUPPORT_NESTED_NAMESPACES false,
                    STAGE_CREATE_TABLES false,
                    SKIP_CREATE_TABLE_METADATA_UPDATES true,
                    REMOVE_FILES_ON_DELETE false,
                    DISABLE_MULTI_TABLE_COMMIT true
                );
            """)

        case _:
            con.close()
            raise ValueError(f"Unknown or not-yet-configured catalog: {cat}")

    return con
