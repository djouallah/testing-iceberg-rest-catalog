"""Iceberg REST catalog connections for Spark — the twin of catalogs.py.

Same seven catalogs, same credentials (GitHub Actions secrets, OIDC for OneLake),
via PySpark 4.1 + iceberg-spark-runtime instead of DuckDB. The OneLake constants
and the OIDC token helper are imported from catalogs.py so the warehouse GUID
lives in exactly one place.

Structure differs from catalogs.py in one way: `spark.jars.packages` and
`spark.sql.extensions` are fixed when the SparkSession is created and a stopped
session cannot be reconfigured, so there is no "fresh connection per catalog".
Instead one session registers every requested catalog under its own name
(onelake -> cat_onelake, r2 -> cat_r2, ...), which keeps the comma-separated
CATALOGS contract working without restarting the JVM.
"""

import os

from catalogs import (
    ONELAKE_ENDPOINT,
    ONELAKE_WAREHOUSE,
    S3_TABLES_REGION,
    onelake_token,
)

# Iceberg builds one runtime per Spark *minor* (each under /spark/vX.Y, linking
# Spark internals), so these two pins move together. 4.1 is the newest Spark
# with a runtime — there is no iceberg-spark-runtime-4.2 at any version, even
# though Spark 4.2.0 is out. See requirements-spark.txt.
ICEBERG_VERSION = "1.11.0"
PACKAGES = [
    f"org.apache.iceberg:iceberg-spark-runtime-4.1_2.13:{ICEBERG_VERSION}",
    f"org.apache.iceberg:iceberg-aws-bundle:{ICEBERG_VERSION}",  # r2, s3_table, glue
    f"org.apache.iceberg:iceberg-azure-bundle:{ICEBERG_VERSION}",  # onelake, unity
]

# Resolved jars land here; the workflow caches this path so the three bundles
# are downloaded once rather than per matrix job.
IVY_DIR = os.path.expanduser("~/.ivy2")

VENDED = "vended-credentials"  # X-Iceberg-Access-Delegation header value
S3_IO = "org.apache.iceberg.aws.s3.S3FileIO"
ADLS_IO = "org.apache.iceberg.azure.adlsv2.ADLSFileIO"


def catalog_name(cat):
    """Spark catalog name for `cat` — one session holds several at once."""
    return f"cat_{cat}"


def catalog_options(cat):
    """The spark.sql.catalog.<name>.* suffixes for `cat`.

    Every catalog here is `type=rest`; what differs is how the request is
    authenticated (bearer token, OAuth2 client credentials, or SigV4) and which
    FileIO reads the vended storage credentials.
    """
    match cat:
        case "onelake":  # Microsoft Fabric OneLake (managed storage, vended creds)
            return {
                "uri": ONELAKE_ENDPOINT,
                "warehouse": ONELAKE_WAREHOUSE,
                # Authenticates the catalog API only; the vended SAS covers data.
                "token": onelake_token(),
                "header.X-Iceberg-Access-Delegation": VENDED,
                "io-impl": ADLS_IO,
            }

        case "r2":  # Cloudflare R2 Data Catalog
            return {
                "uri": os.environ["ENDPOINT_R2"],
                "warehouse": os.environ["R2_WAREHOUSE"],
                "token": os.environ["TOKEN_R2"],
                "header.X-Iceberg-Access-Delegation": VENDED,
                "io-impl": S3_IO,
                # R2 vends real S3 credentials rather than signing per request.
                "s3.remote-signing-enabled": "false",
            }

        case "s3_table":  # AWS S3 Tables
            # Spark has no ENDPOINT_TYPE equivalent: reach S3 Tables through its
            # Iceberg REST endpoint and sign with SigV4. Credentials come from
            # the default AWS chain (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY),
            # which the workflow fills from the same S3_KEY / S3_SECRET secrets.
            return {
                "uri": f"https://s3tables.{S3_TABLES_REGION}.amazonaws.com/iceberg",
                "warehouse": os.environ["TABLEBUCKETARN"],
                "rest.sigv4-enabled": "true",
                "rest.signing-name": "s3tables",
                "rest.signing-region": S3_TABLES_REGION,
                "client.region": S3_TABLES_REGION,
                "io-impl": S3_IO,
                # The AWS endpoints don't implement the scan-metrics route.
                "rest-metrics-reporting-enabled": "false",
            }

        case "glue":  # AWS Glue Data Catalog / SageMaker Lakehouse
            # The Spark counterpart of catalogs.py's ENDPOINT_TYPE 'glue': the
            # dedicated Glue REST endpoint, not a generic one. Same finding, same
            # reason — the generic route assumes /transactions/commit, which Glue
            # 2xx-drops, so commits silently never land.
            region = os.environ["GLUE_REGION"]
            return {
                "uri": f"https://glue.{region}.amazonaws.com/iceberg",
                "warehouse": os.environ["GLUE_WAREHOUSE"],
                "rest.sigv4-enabled": "true",
                "rest.signing-name": "glue",
                "rest.signing-region": region,
                "client.region": region,
                "io-impl": S3_IO,
                "rest-metrics-reporting-enabled": "false",
            }

        case "unity":  # Databricks Unity Catalog (external storage, vended creds)
            return {
                "uri": os.environ["UC_ENDPOINT"],
                "warehouse": "iceberg",
                "token": os.environ["UC_TOKEN"],
                "header.X-Iceberg-Access-Delegation": VENDED,
            }

        case "unity_managed":  # Unity Catalog managed storage (serverless)
            return {
                "uri": os.environ["UC_ENDPOINT"],
                "warehouse": "serverless",
                "token": os.environ["UC_TOKEN"],
                "header.X-Iceberg-Access-Delegation": VENDED,
            }

        case "horizon":  # Snowflake Horizon (managed storage)
            # Snowflake's own Spark example passes the token bare and lets scope
            # carry the role — no oauth2-server-uri, no client_credentials
            # exchange. The "client_id:client_secret" credential that catalogs.py
            # builds is the Open Catalog / Polaris form, not this one.
            return {
                "uri": os.environ["HORIZON_ENDPOINT"],
                "warehouse": "ICEBERG",
                "credential": os.environ["HORIZON_TOKEN"],
                "scope": "session:role:DATA_ENGINEER",
                "header.X-Iceberg-Access-Delegation": VENDED,
            }

        case _:
            raise ValueError(f"Unknown or not-yet-configured catalog: {cat}")


def spark_session(cats):
    """Return (SparkSession, errors) with every catalog in `cats` registered.

    Catalogs are registered before the session starts, so one missing secret
    would otherwise abort the whole run. Instead the failure is collected into
    `errors` (cat -> exception) for the caller to report per catalog, the way
    main.py's loop does.
    """
    from pyspark.sql import SparkSession

    builder = (
        SparkSession.builder.appName("irc-write-support")
        .master("local[2]")
        .config("spark.jars.packages", ",".join(PACKAGES))
        .config("spark.jars.ivy", IVY_DIR)
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
    )
    errors = {}
    for cat in cats:
        try:
            options = catalog_options(cat)
        except Exception as e:  # missing secret, unknown catalog
            errors[cat] = e
            continue
        name = catalog_name(cat)
        builder = builder.config(
            f"spark.sql.catalog.{name}", "org.apache.iceberg.spark.SparkCatalog"
        ).config(f"spark.sql.catalog.{name}.type", "rest")
        for key, value in options.items():
            builder = builder.config(f"spark.sql.catalog.{name}.{key}", value)

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark, errors


def location_clause(cat, tbl):
    """Extra CREATE TABLE clause for catalogs that don't assign a storage location.

    Same reason as table_clause() in catalogs.py, and the same layout —
    GLUE_LOCATION is the database folder, the table name is appended. Glue is a
    plain catalog over a regular S3 bucket and does not inherit its database's
    LocationUri. Everything else manages its own storage and gets no clause.
    """
    if cat == "glue":
        return f"LOCATION '{os.environ['GLUE_LOCATION'].rstrip('/')}/{tbl}'"
    return ""
