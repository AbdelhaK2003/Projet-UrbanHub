"""Charge les donnees silver du Data Lake dans ClickHouse (base OLAP).

ClickHouse lit directement les fichiers Parquet dans MinIO avec la fonction s3().
Ensuite on peut faire du SQL rapide sur des millions de lignes (voir sql/requetes.sql).

Lancer : python -m urbanhub.charger_clickhouse
"""
import clickhouse_connect

from urbanhub import config

# depuis le conteneur ClickHouse, MinIO s'appelle "minio" (reseau Docker)
S3 = "http://minio:9000"

TABLES = {
    "meteo": ("silver/meteo/year=*/meteo.parquet", "(station_id, timestamp)"),
    "velos": ("silver/velos/date=*/velos.parquet", "(station_id, collected_at)"),
    "pollution": ("silver/pollution/pollution.parquet", "(sensor_id, timestamp)"),
}


def main():
    ch = clickhouse_connect.get_client(host=config.CLICKHOUSE_HOST, port=8123,
                                       username=config.CLICKHOUSE_USER, password=config.CLICKHOUSE_PASSWORD)
    ch.command("CREATE DATABASE IF NOT EXISTS urbanhub")
    for table, (chemin, ordre) in TABLES.items():
        source = f"s3('{S3}/{chemin}', '{config.MINIO_USER}', '{config.MINIO_PASSWORD}', 'Parquet')"
        try:
            ch.command(f"DROP TABLE IF EXISTS urbanhub.{table}")
            ch.command(f"CREATE TABLE urbanhub.{table} ENGINE = MergeTree ORDER BY {ordre} "
                       f"SETTINGS allow_nullable_key = 1 AS SELECT * FROM {source}")
            n = ch.command(f"SELECT count() FROM urbanhub.{table}")
            print(f"  {table} : {n:,} lignes")
        except Exception as e:
            raison = "pas encore de fichier dans silver" if "404" in str(e) else str(e)[:200]
            print(f"  {table} : pas chargee ({raison})")


if __name__ == "__main__":
    main()
