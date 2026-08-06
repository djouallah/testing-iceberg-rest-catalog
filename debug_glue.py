"""Temporary: ask Glue itself what it thinks demo.simple is. Delete once solved."""

import json
import os

import boto3

glue = boto3.client(
    "glue",
    region_name=os.environ["GLUE_REGION"],
    aws_access_key_id=os.environ["S3_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET"],
)

db = glue.get_database(Name="demo")["Database"]
print("database demo LocationUri:", db.get("LocationUri"), flush=True)

for name in ("simple", "probe_ins", "probe_ctas", "probe_lag"):
    try:
        t = glue.get_table(DatabaseName="demo", Name=name)["Table"]
    except Exception as e:
        print(f"\n{name}: FAILED -> {str(e)[:200]}", flush=True)
        continue
    params = t.get("Parameters", {})
    sd = t.get("StorageDescriptor", {})
    print(f"\n{name}:", flush=True)
    print("  table_type        :", params.get("table_type"), flush=True)
    print("  metadata_location :", params.get("metadata_location"), flush=True)
    print("  sd.Location       :", sd.get("Location"), flush=True)
    print("  columns           :", [c["Name"] for c in sd.get("Columns", [])][:5], flush=True)
    print("  other params      :", json.dumps(
        {k: v for k, v in params.items()
         if k not in ("metadata_location", "table_type")})[:300], flush=True)
