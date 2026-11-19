"""Charge le Data Lake (silver + gold) dans ClickHouse, la base qui alimente l'interface.

ClickHouse lit directement les fichiers Parquet dans MinIO avec la fonction s3().

- silver/meteo, silver/velos, silver/pollution  -> tables urbanhub.meteo / velos / pollution
- chaque tableau de gold (gold/<partie>/<nom>.parquet) -> table urbanhub.gold_<partie>_<nom>
  ex : gold/meteo/q1_periodes_anormales.parquet -> urbanhub.gold_meteo_q1_periodes_anormales

Lancer : python -m urbanhub.charger_clickhouse
"""
from urbanhub import config, datalake, olap

# depuis le conteneur ClickHouse, MinIO s'appelle "minio" (reseau Docker)
S3 = "http://minio:9000"

SILVER = {
    "meteo": "silver/meteo/year=*/meteo.parquet",
    "velos": "silver/velos/date=*/velos.parquet",
    "pollution": "silver/pollution/year=*/pollution.parquet",
}


def source(chemin):
    return f"s3('{S3}/{chemin}', '{config.MINIO_USER}', '{config.MINIO_PASSWORD}', 'Parquet')"


def charger_silver(ch):
    for table, chemin in SILVER.items():
        schema, ordre = olap.SCHEMAS[table]
        cols = ", ".join(olap.colonnes(table))
        ch.command(f"DROP TABLE IF EXISTS {olap.BASE}.{table}")
        ch.command(f"CREATE TABLE {olap.BASE}.{table} ({schema}) ENGINE = ReplacingMergeTree ORDER BY {ordre}")
        try:
            ch.command(f"INSERT INTO {olap.BASE}.{table} ({cols}) SELECT {cols} FROM {source(chemin)}")
        except Exception as e:
            raison = "pas encore de fichier dans silver" if "404" in str(e) or "not found" in str(e).lower() else str(e)[:200]
            print(f"  {table} : vide ({raison})")
            continue
        print(f"  {table} : {ch.command(f'SELECT count() FROM {olap.BASE}.{table}'):,} lignes")


def charger_gold(ch):
    cles = [k for k in datalake.lister("gold") if k.endswith(".parquet")]
    attendues = set()
    for k in cles:
        table = "gold_" + k[:-len(".parquet")].replace("/", "_")
        attendues.add(table)
        ch.command(f"CREATE OR REPLACE TABLE {olap.BASE}.{table} ENGINE = MergeTree ORDER BY tuple() "
                   f"AS SELECT * FROM {source('gold/' + k)}")
        print(f"  {table} : {ch.command(f'SELECT count() FROM {olap.BASE}.{table}'):,} lignes")
    # un indicateur qui n'existe plus dans gold disparait aussi de ClickHouse
    for (table,) in ch.query(f"SELECT name FROM system.tables WHERE database = '{olap.BASE}' "
                             "AND name LIKE 'gold_%'").result_rows:
        if table not in attendues:
            ch.command(f"DROP TABLE {olap.BASE}.{table}")


def main(silver=True, gold=True):
    ch = olap.client()
    if silver:
        print("Tables detaillees (silver)")
        charger_silver(ch)
    if gold:
        print("Indicateurs (gold)")
        charger_gold(ch)


if __name__ == "__main__":
    main()
