"""Partie 3 - etape 2 : nettoyage des mesures de pollution (bronze -> silver).

- regroupe l'historique et le flux dans un seul tableau
- variables : sensor_id, pollutant, value, unit, latitude, longitude, timestamp (+ city, location_name)
- met tout dans la meme unite (microgrammes par m3), certains capteurs donnent des ppm ou ppb
- enleve les valeurs negatives ou impossibles et les doublons

Lancer : python -m urbanhub.pollution.nettoyer
"""
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from urbanhub import datalake

# masse molaire (g/mol) pour convertir ppm -> microgrammes par m3 (a 25 C)
MASSE_MOLAIRE = {"o3": 48.00, "no2": 46.01, "co": 28.01}
MAXI = {"pm25": 1000, "pm10": 2000, "o3": 1000, "no2": 1000, "co": 50000}  # microgrammes par m3


def lire_historique(key):
    d = datalake.get_json("bronze", key)
    c = d["sensor"]
    return [{**c, "value": m.get("value"),
             "timestamp": ((m.get("period") or {}).get("datetimeFrom") or {}).get("utc")} for m in d["results"]]


def lire_flux(key, capteurs):
    d = datalake.get_json("bronze", key)
    collecte = pd.Timestamp(d["collected_at"])
    lignes = []
    for m in d["results"]:
        meta = capteurs.get(m.get("sensorsId"))
        quand = (m.get("datetime") or {}).get("utc")
        # un capteur en panne renvoie sa "derniere" mesure, parfois vieille de plusieurs annees : on l'ignore
        if meta and quand and collecte - pd.Timestamp(quand) < pd.Timedelta(days=2):
            lignes.append({**meta, "value": m.get("value"), "timestamp": quand})
    return lignes


def vers_ugm3(df):
    """Convertit ppm et ppb en microgrammes par m3."""
    unite = df["unit"].fillna("").str.lower()
    mm = df["pollutant"].map(MASSE_MOLAIRE)
    facteur = pd.Series(1.0, index=df.index)
    facteur[unite == "ppm"] = mm * 1000 / 24.45
    facteur[unite == "ppb"] = mm / 24.45
    inconnu = ~unite.isin(["ppm", "ppb", "µg/m³", "ug/m3", "µg/m3"])
    df["value"] = df["value"] * facteur
    df.loc[inconnu, "value"] = None
    df["unit"] = "µg/m³"
    return df


def main():
    try:
        capteurs = {c["sensor_id"]: c for c in datalake.get_json("bronze", "pollution/openaq/reference/capteurs.json")}
    except Exception:
        print("Pas de capteurs dans bronze. Lancer d'abord : python -m urbanhub.pollution.collecter --historique 60")
        return

    cles_histo = list(datalake.lister("bronze", "pollution/openaq/historique/"))
    cles_flux = list(datalake.lister("bronze", "pollution/openaq/flux/"))
    with ThreadPoolExecutor(max_workers=16) as pool:
        lignes = [l for m in pool.map(lire_historique, cles_histo) for l in m]
        lignes += [l for m in pool.map(lambda k: lire_flux(k, capteurs), cles_flux) for l in m]
    print(f"{len(cles_histo)} fichiers historiques, {len(cles_flux)} collectes du flux, {len(lignes):,} mesures brutes")

    df = pd.DataFrame(lignes)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dt.floor("h")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["timestamp", "value"])
    df = vers_ugm3(df)
    df = df[(df["value"] >= 0) & (df["value"] <= df["pollutant"].map(MAXI))]
    df = df.drop_duplicates(["sensor_id", "timestamp"], keep="last")

    colonnes = ["sensor_id", "location_id", "location_name", "city", "pollutant", "value", "unit",
                "latitude", "longitude", "timestamp"]
    df = df[colonnes].sort_values(["sensor_id", "timestamp"])
    datalake.put_parquet("silver", "pollution/pollution.parquet", df)
    print(f"Silver pret : {len(df):,} mesures horaires, {df['sensor_id'].nunique()} capteurs, "
          f"du {df['timestamp'].min():%Y-%m-%d} au {df['timestamp'].max():%Y-%m-%d}")
    print(df.groupby(["city", "pollutant"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
