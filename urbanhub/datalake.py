"""Acces au Data Lake MinIO (meme principe que les TP : boto3 + bronze / silver / gold).

bronze : donnees brutes, telles que recues des sources
silver : donnees nettoyees au format Parquet
gold   : indicateurs prets pour les decideurs (tableaux et graphiques)
"""
import io
import json
from functools import lru_cache

import boto3
import pandas as pd
from botocore.client import Config
from botocore.exceptions import ClientError

from urbanhub import config

BUCKETS = ["bronze", "silver", "gold"]


@lru_cache(maxsize=1)
def client():
    return boto3.client(
        "s3",
        endpoint_url=config.MINIO_URL,
        aws_access_key_id=config.MINIO_USER,
        aws_secret_access_key=config.MINIO_PASSWORD,
        # retries : si la connexion est coupee (frequent avec Docker Desktop sous Windows
        # quand il y a beaucoup d'envois en parallele), boto3 reessaie tout seul
        config=Config(signature_version="s3v4", max_pool_connections=50,
                      retries={"max_attempts": 10, "mode": "standard"}),
        region_name="us-east-1",
    )


def init_buckets():
    """Cree les 3 buckets s'ils n'existent pas et active le versioning sur bronze."""
    s3 = client()
    existants = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
    for b in BUCKETS:
        if b not in existants:
            s3.create_bucket(Bucket=b)
    s3.put_bucket_versioning(Bucket="bronze", VersioningConfiguration={"Status": "Enabled"})


# ---------- ecriture ----------

def put_bytes(bucket, key, data, content_type="application/octet-stream"):
    client().put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


def put_json(bucket, key, obj):
    data = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
    put_bytes(bucket, key, data, "application/json")


def put_parquet(bucket, key, df):
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    put_bytes(bucket, key, buf.getvalue(), "application/vnd.apache.parquet")


# ---------- lecture ----------

def get_bytes(bucket, key):
    return client().get_object(Bucket=bucket, Key=key)["Body"].read()


def get_json(bucket, key):
    return json.loads(get_bytes(bucket, key))


def get_parquet(bucket, key, columns=None):
    return pd.read_parquet(io.BytesIO(get_bytes(bucket, key)), columns=columns)


def existe(bucket, key):
    try:
        client().head_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


def lister(bucket, prefix=""):
    """Liste toutes les cles d'un dossier (gere la pagination de S3)."""
    pages = client().get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
    for page in pages:
        for obj in page.get("Contents", []):
            yield obj["Key"]


def lire_parquets(bucket, prefix, columns=None):
    """Lit et concatene tous les fichiers Parquet d'un dossier."""
    morceaux = [get_parquet(bucket, k, columns) for k in lister(bucket, prefix) if k.endswith(".parquet")]
    if not morceaux:
        return pd.DataFrame(columns=columns)
    return pd.concat(morceaux, ignore_index=True)
