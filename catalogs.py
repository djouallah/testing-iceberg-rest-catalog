"""Iceberg REST catalog connections for DuckDB.

Every catalog runs on DuckDB 1.5.5, with the iceberg extension from core_nightly.
OneLake authenticates via OIDC federation; the others (R2, S3 Tables, Glue, Unity,
Horizon) read their credentials from environment variables (GitHub Actions secrets).
"""

import os
import re

# --- OneLake (Microsoft Fabric) ---------------------------------------------
ONELAKE_WAREHOUSE = "1c52481c-0523-4a5a-bbde-fdc932bd77c2/ac303243-4441-4885-9e7d-f4f5e7af194c"
ONELAKE_ENDPOINT = "https://onelake.table.fabric.microsoft.com/iceberg"
STORAGE_SCOPE = "https://storage.azure.com/.default"

# --- S3 Tables (AWS) --------------------------------------------------------
S3_TABLES_REGION = "ap-southeast-2"

# A fully-qualified Java exception class, e.g.
# org.apache.iceberg.exceptions.ForbiddenException. Matches the class name only,
# never the surrounding message.
_JAVA_EXC = re.compile(r"\b((?:[a-z]\w*\.){2,}[A-Z]\w*(?:Exception|Error))\b")


def error_label(e):
    """Name the failure without quoting it.

    These logs are public and Iceberg error messages can carry vended SAS
    tokens and presigned URLs, so the report gets a class name and nothing
    else — enough to tell a config bug from a catalog gap. Full text stays
    behind DEBUG=1. Spark buries the real failure inside a Py4JJavaError, whose
    own class name says nothing, so dig out the first Java class it names.
    """
    match = _JAVA_EXC.search(str(e))
    return match.group(1).rsplit(".", 1)[-1] if match else type(e).__name__


def onelake_token():
    """Storage token via OIDC federation. Shared with spark_catalogs.py."""
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential().get_token(STORAGE_SCOPE).token


def connect_catalog(cat):
    """Return a fresh DuckDB connection with catalog `cat` attached as `cat_db`."""
    # Imported here, not at module scope: spark_catalogs.py imports the OneLake
    # constants and onelake_token() from this module and has no duckdb.
    import duckdb

    con = duckdb.connect()  # fresh, isolated state every call
    # core_nightly, not core: OneLake's vended SAS needs duckdb-iceberg#1331.
    # curl transport: the azure extension only probes for a system CA bundle
    # inside CreateCurlTransport.
    con.sql("""
        FORCE INSTALL iceberg FROM core_nightly;
        LOAD iceberg;
        SET azure_transport_option_type = 'curl';
    """)

    match cat:
        case "onelake":  # Microsoft Fabric OneLake (managed storage, vended creds)
            token = onelake_token()  # authenticates the catalog API only
            con.sql(f"""
                ATTACH OR REPLACE '{ONELAKE_WAREHOUSE}' AS cat_db (
                    TYPE iceberg,
                    ENDPOINT '{ONELAKE_ENDPOINT}',
                    TOKEN '{token}',
                    STAGE_CREATE_TABLES false,
                    SKIP_CREATE_TABLE_METADATA_UPDATES true,
                    DEFAULT_SCHEMA dbo
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

        case "glue":  # AWS Glue Data Catalog / SageMaker Lakehouse
            region = os.environ["GLUE_REGION"]
            # The S3 secret does double duty: sigv4 signing for the catalog API
            # and the parquet writes to GLUE_LOCATION.
            con.sql(f"""
                CREATE OR REPLACE SECRET glue_secret (
                    TYPE S3,
                    KEY_ID '{os.environ["S3_KEY"]}',
                    SECRET '{os.environ["S3_SECRET"]}',
                    REGION '{region}'
                );
            """)
            # ENDPOINT_TYPE 'glue' (not a generic ENDPOINT) is load-bearing: it
            # scopes duckdb-iceberg to the REST operations Glue implements, so
            # snapshot commits go per-table via UpdateTable. A generic attach
            # assumes POST /transactions/commit support, which Glue 2xx-drops —
            # writes then silently never commit (table stuck at version 00000).
            # PURGE_REQUESTED false: ENDPOINT_TYPE glue defaults it to true, but
            # Glue 400-rejects DROP TABLE with purgeRequested=true.
            con.sql(f"""
                ATTACH OR REPLACE '{os.environ["GLUE_WAREHOUSE"]}' AS cat_db (
                    TYPE iceberg,
                    ENDPOINT_TYPE 'glue',
                    PURGE_REQUESTED false,
                    SECRET glue_secret
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


def table_clause(cat, tbl):
    """Extra CREATE TABLE clause for catalogs that don't assign a storage location.

    Glue is a plain catalog over a regular S3 bucket and does not inherit its
    database's LocationUri, so every table has to name its own path. GLUE_LOCATION
    is the database folder; the table name is appended. Everything else manages
    its own storage and gets no clause.
    """
    if cat == "glue":
        return f"WITH ('location' = '{os.environ['GLUE_LOCATION'].rstrip('/')}/{tbl}')"
    return ""
