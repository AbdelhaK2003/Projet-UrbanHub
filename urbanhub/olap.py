"""Acces a ClickHouse, la base OLAP qui alimente l'interface.

Deux sortes de tables dans la base "urbanhub" :

1. Les tables detaillees (copie de silver) : meteo, velos, pollution
   - remplies par le chargement (python -m urbanhub.charger_clickhouse)
   - velos et pollution recoivent AUSSI chaque nouvelle collecte en direct
     (les collecteurs y inserent leurs lignes) : c'est ce qui rend l'interface temps reel
   - moteur ReplacingMergeTree : si une meme mesure arrive deux fois
     (collecteur puis chargement), ClickHouse n'en garde qu'une

2. Les tables gold_* : une table par indicateur de la couche gold (ex : gold_meteo_q1_periodes_anormales)
"""
import threading

import clickhouse_connect

from urbanhub import config

BASE = "urbanhub"

SCHEMAS = {
    "meteo": ("""
        station_id String, city String, latitude Float64, longitude Float64,
        timestamp DateTime('UTC'), temperature Nullable(Float64), humidity Nullable(Float64),
        precipitation Nullable(Float64), wind_speed Nullable(Float64), wind_direction Nullable(Float64),
        wind_gusts Nullable(Float64), pressure Nullable(Float64), cloud_cover Nullable(Float64),
        visibility Nullable(Float64)""", "(city, timestamp)"),
    "velos": ("""
        collected_at DateTime('UTC'), city String, network_id String, station_id String,
        station_name String, latitude Float64, longitude Float64,
        bikes_available Nullable(Int32), free_slots Nullable(Int32), capacity Nullable(Int32),
        fill_rate Nullable(Float64)""", "(city, station_id, collected_at)"),
    "pollution": ("""
        sensor_id Int64, location_id Int64, location_name String, city String, pollutant String,
        value Float64, unit String, latitude Float64, longitude Float64,
        timestamp DateTime('UTC')""", "(city, pollutant, sensor_id, timestamp)"),
}


def colonnes(table):
    """Noms des colonnes d'une table, dans l'ordre du schema."""
    return [morceau.split()[0] for morceau in SCHEMAS[table][0].split(",") if morceau.strip()]


_local = threading.local()


def client():
    """Une connexion par thread : ClickHouse refuse deux requetes en meme temps sur la meme session
    (l'API repond a plusieurs pages en parallele)."""
    if not hasattr(_local, "ch"):
        _local.ch = clickhouse_connect.get_client(host=config.CLICKHOUSE_HOST, port=8123,
                                                  username=config.CLICKHOUSE_USER, password=config.CLICKHOUSE_PASSWORD,
                                                  autogenerate_session_id=False)
        _local.ch.command(f"CREATE DATABASE IF NOT EXISTS {BASE}")
    return _local.ch


def creer_tables():
    for table, (schema, ordre) in SCHEMAS.items():
        client().command(f"CREATE TABLE IF NOT EXISTS {BASE}.{table} ({schema}) "
                         f"ENGINE = ReplacingMergeTree ORDER BY {ordre}")


def inserer(table, df):
    """Ajoute des lignes (DataFrame pandas) dans une table detaillee. Ne plante jamais :
    si ClickHouse est arrete, la collecte continue (les donnees restent dans MinIO)."""
    if df is None or df.empty:
        return 0
    try:
        creer_tables()
        cols = colonnes(table)
        d = df[cols].astype(object).where(df[cols].notna(), None)  # valeur manquante -> NULL
        client().insert(f"{BASE}.{table}", d.values.tolist(), column_names=cols)
        return len(d)
    except Exception as e:
        print(f"  (ClickHouse indisponible, lignes gardees seulement dans MinIO : {str(e)[:120]})")
        return 0
