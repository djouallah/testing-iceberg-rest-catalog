# Iceberg REST catalog write support (DuckDB)

| Catalog | Status | Notes |
| --- | :---: | --- |
| Microsoft OneLake | ✅ | private preview |
| Cloudflare R2 | ✅ | |
| AWS S3 Tables | ✅ | |
| Databricks Unity (external storage) | ✅ | |
| Snowflake Horizon (managed storage) | ✅ | |
| Databricks Unity (managed storage) | ❌ | by design — no credential vending |
| Google Lakehouse | ❓ | configuration not documented / not sure |
| AWS Glue (SageMaker Lakehouse) | ✅ | needs `ENDPOINT_TYPE 'glue'`, `PURGE_REQUESTED false`, and an explicit table location — a generic `ENDPOINT` attach silently loses every commit (Glue 2xx-drops the unsupported `/transactions/commit` route) |
