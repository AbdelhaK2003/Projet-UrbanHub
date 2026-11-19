"""API de l'interface UrbanHub : lit ClickHouse et renvoie du JSON a l'application React.

Lancer : uvicorn api.main:app --port 8000
(si l'interface a ete construite avec "npm run build", elle est aussi servie sur http://localhost:8000)

Routes :
  /api/kpis                      les indicateurs cles de la page d'accueil
  /api/gold/<nom>                une table gold (ex : /api/gold/meteo_q1_periodes_anormales)
  /api/velos/live                etat actuel des velos par ville (derniere collecte)
  /api/velos/evolution?city=     velos disponibles a chaque collecte des dernieres 24 h
  /api/velos/stations?city=      position et etat de chaque station (carte)
  /api/pollution/live            pollution des dernieres 24 h par ville et polluant
  /api/pollution/serie?pollutant= moyenne horaire par ville sur 7 jours
  /api/meteo/live                derniere heure meteo connue par ville
  /api/datalake                  contenu des buckets MinIO
  /api/etat                      fraicheur des donnees (derniere collecte de chaque source)
"""
import re
import time
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from urbanhub import datalake, olap
from urbanhub.pollution.analyser import OMS

app = FastAPI(title="UrbanHub API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
B = olap.BASE


def requete(sql, **params):
    """Execute une requete SQL et renvoie un DataFrame (vide si la table n'existe pas encore)."""
    try:
        df = olap.client().query_df(sql, parameters=params)
    except Exception as e:
        if "UNKNOWN_TABLE" in str(e) or "doesn't exist" in str(e):
            return pd.DataFrame()
        raise
    # ClickHouse renvoie les heures UTC sans fuseau : on le precise pour que le navigateur affiche l'heure de Paris
    for c in df.columns:
        if str(df[c].dtype).startswith("datetime64") and df[c].dt.tz is None:
            df[c] = df[c].dt.tz_localize("UTC")
    return df


def json(df):
    return Response(df.to_json(orient="records", date_format="iso", force_ascii=False),
                    media_type="application/json")


def valeur(sql, **params):
    df = requete(sql, **params)
    return None if df.empty else df.iloc[0, 0]


def nombre(x, chiffres=1):
    try:
        return None if x is None or x != x else round(float(x), chiffres)
    except (TypeError, ValueError):
        return None


# ---------- vue d'ensemble ----------

SQL_VELOS_LIVE = f"""
    SELECT city, max(collected_at) AS heure_collecte, count() AS stations,
           sum(bikes_available) AS velos, sum(free_slots) AS places, sum(capacity) AS capacite,
           avg(fill_rate) AS remplissage, countIf(bikes_available = 0) AS stations_vides,
           countIf(free_slots = 0) AS stations_pleines
    FROM {B}.velos FINAL
    WHERE (city, collected_at) IN (SELECT city, max(collected_at) FROM {B}.velos GROUP BY city)
    GROUP BY city
    HAVING velos > 0
    ORDER BY velos DESC"""

SQL_POLLUTION_LIVE = f"""
    SELECT city, pollutant, avg(value) AS valeur, max(timestamp) AS derniere_mesure, uniqExact(sensor_id) AS capteurs
    FROM {B}.pollution FINAL
    WHERE timestamp >= (SELECT max(timestamp) FROM {B}.pollution) - INTERVAL 24 HOUR
    GROUP BY city, pollutant
    ORDER BY city, pollutant"""


@app.get("/api/kpis")
def kpis():
    velos = requete(SQL_VELOS_LIVE)
    pol = requete(SQL_POLLUTION_LIVE)
    if not pol.empty:
        pol["ratio_oms"] = pol["valeur"] / pol["pollutant"].map(OMS)
    meteo = requete(f"""SELECT avg(temperature) AS t, max(timestamp) AS quand FROM {B}.meteo
                        WHERE timestamp = (SELECT max(timestamp) FROM {B}.meteo)""")

    def moyenne_polluant(p):
        d = pol[pol["pollutant"] == p] if not pol.empty else pol
        return nombre(d["valeur"].mean()) if not d.empty else None

    pm25 = pol[pol["pollutant"] == "pm25"] if not pol.empty else pol
    corr = requete(f"SELECT meteo, pollutant, correlation FROM {B}.gold_croisement_q1_correlation_meteo_pollution")
    c = {(r.meteo, r.pollutant): r.correlation for r in corr.itertuples()} if not corr.empty else {}

    return {
        "velos": {
            "disponibles": int(velos["velos"].sum()) if not velos.empty else None,
            "places_libres": int(velos["places"].sum()) if not velos.empty else None,
            "stations": int(velos["stations"].sum()) if not velos.empty else None,
            "stations_vides": int(velos["stations_vides"].sum()) if not velos.empty else None,
            "remplissage": nombre((velos["velos"].sum() / velos["capacite"].sum()) * 100) if not velos.empty else None,
            "villes": int(len(velos)),
            "derniere_collecte": velos["heure_collecte"].max().isoformat() if not velos.empty else None,
        },
        "pollution": {
            "pm25": moyenne_polluant("pm25"), "no2": moyenne_polluant("no2"),
            "o3": moyenne_polluant("o3"), "pm10": moyenne_polluant("pm10"),
            "villes_pm25_au_dessus_oms": int((pm25["ratio_oms"] > 1).sum()) if not pm25.empty else None,
            "villes_mesurees": int(pm25["city"].nunique()) if not pm25.empty else None,
            "episodes_30j": nombre(valeur(f"""SELECT count() FROM {B}.gold_pollution_q4_episodes
                WHERE debut >= (SELECT max(debut) FROM {B}.gold_pollution_q4_episodes) - INTERVAL 30 DAY"""), 0),
            "derniere_mesure": pol["derniere_mesure"].max().isoformat() if not pol.empty else None,
        },
        "meteo": {
            "temperature": nombre(meteo["t"].iloc[0]) if not meteo.empty else None,
            "derniere_heure": meteo["quand"].iloc[0].isoformat() if not meteo.empty and meteo["quand"].iloc[0] else None,
            "vagues_chaleur": nombre(valeur(f"SELECT count() FROM {B}.gold_meteo_q1_periodes_anormales "
                                            "WHERE type = 'vague de chaleur'"), 0),
            "vagues_froid": nombre(valeur(f"SELECT count() FROM {B}.gold_meteo_q1_periodes_anormales "
                                          "WHERE type = 'vague de froid'"), 0),
            "jours_extremes": nombre(valeur(f"SELECT sum(nb_jours) FROM {B}.gold_meteo_q4_extremes_par_ville"), 0),
            "jours_chaleur": nombre(valeur(f"SELECT sum(nb_jours) FROM {B}.gold_meteo_q4_extremes_par_ville "
                                           "WHERE type LIKE 'chaleur%'"), 0),
        },
        "croisement": {
            "vent_no2": nombre(c.get(("wind_speed", "no2")), 2),
            "temperature_o3": nombre(c.get(("temperature", "o3")), 2),
            "humidite_pm25": nombre(c.get(("humidity", "pm25")), 2),
        },
    }


# ---------- tables gold ----------

@app.get("/api/gold/{nom}")
def gold(nom: str, city: str | None = None, limit: int = 50000):
    if not re.fullmatch(r"[a-z0-9_]+", nom):
        raise HTTPException(400, "nom invalide")
    filtre = " WHERE city = {city:String}" if city else ""
    try:
        return json(requete(f"SELECT * FROM {B}.gold_{nom}{filtre} LIMIT {int(limit)}", city=city))
    except Exception as e:
        if "Missing columns" in str(e) or "UNKNOWN_IDENTIFIER" in str(e):  # table sans colonne city
            return json(requete(f"SELECT * FROM {B}.gold_{nom} LIMIT {int(limit)}"))
        raise


# ---------- temps reel ----------

@app.get("/api/velos/live")
def velos_live():
    return json(requete(SQL_VELOS_LIVE))


@app.get("/api/velos/evolution")
def velos_evolution(city: str | None = None, heures: int = 24):
    filtre = "AND city = {city:String}" if city else ""
    return json(requete(f"""
        SELECT collected_at, sum(bikes_available) AS velos, avg(fill_rate) AS remplissage,
               countIf(bikes_available = 0) AS stations_vides
        FROM {B}.velos FINAL
        WHERE collected_at >= (SELECT max(collected_at) FROM {B}.velos) - INTERVAL {int(heures)} HOUR {filtre}
          AND city IN (SELECT city FROM {B}.velos GROUP BY city HAVING max(bikes_available) > 0)
        GROUP BY collected_at ORDER BY collected_at""", city=city))


@app.get("/api/velos/stations")
def velos_stations(city: str = "Paris"):
    return json(requete(f"""
        SELECT station_name, latitude, longitude, bikes_available, free_slots, capacity, fill_rate, collected_at
        FROM {B}.velos FINAL
        WHERE city = {{city:String}}
          AND collected_at = (SELECT max(collected_at) FROM {B}.velos WHERE city = {{city:String}})""", city=city))


@app.get("/api/pollution/live")
def pollution_live():
    df = requete(SQL_POLLUTION_LIVE)
    if not df.empty:
        df["ratio_oms"] = df["valeur"] / df["pollutant"].map(OMS)
    return json(df)


@app.get("/api/pollution/serie")
def pollution_serie(pollutant: str = "no2", jours: int = 7):
    return json(requete(f"""
        SELECT timestamp, city, avg(value) AS valeur FROM {B}.pollution FINAL
        WHERE pollutant = {{p:String}}
          AND timestamp >= (SELECT max(timestamp) FROM {B}.pollution) - INTERVAL {int(jours)} DAY
        GROUP BY timestamp, city ORDER BY timestamp""", p=pollutant))


@app.get("/api/meteo/live")
def meteo_live():
    return json(requete(f"""
        SELECT city, timestamp, temperature, humidity, wind_speed, precipitation, visibility, cloud_cover
        FROM {B}.meteo
        WHERE (city, timestamp) IN (SELECT city, max(timestamp) FROM {B}.meteo GROUP BY city)
        ORDER BY city"""))


@app.get("/api/etat")
def etat():
    sources = {"meteo": "timestamp", "velos": "collected_at", "pollution": "timestamp"}
    res = {}
    for table, col in sources.items():
        df = requete(f"SELECT count() AS lignes, max({col}) AS derniere FROM {B}.{table}")
        res[table] = None if df.empty else {"lignes": int(df["lignes"].iloc[0]),
                                            "derniere": df["derniere"].iloc[0].isoformat()}
    res["tables_gold"] = int(valeur(f"SELECT count() FROM system.tables WHERE database = '{B}' "
                                    "AND name LIKE 'gold_%'") or 0)
    return res


# ---------- data lake ----------

_cache_lake = {"t": 0, "data": None}


@app.get("/api/datalake")
def data_lake():
    if time.time() - _cache_lake["t"] > 60:  # lister des milliers de fichiers prend du temps : cache 1 min
        lignes = []
        for bucket in datalake.BUCKETS:
            dossiers = {}
            for page in datalake.client().get_paginator("list_objects_v2").paginate(Bucket=bucket):
                for o in page.get("Contents", []):
                    parties = o["Key"].split("/")
                    dossier = "/".join(parties[:2]) if len(parties) > 2 else parties[0]
                    d = dossiers.setdefault(dossier, {"fichiers": 0, "taille_mo": 0.0})
                    d["fichiers"] += 1
                    d["taille_mo"] += o["Size"] / 1e6
            lignes += [{"bucket": bucket, "dossier": k, "fichiers": v["fichiers"], "taille_mo": round(v["taille_mo"], 1)}
                       for k, v in sorted(dossiers.items())]
        _cache_lake.update(t=time.time(), data=lignes)
    return _cache_lake["data"]


# l'interface construite (npm run build) est servie a la racine
DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
