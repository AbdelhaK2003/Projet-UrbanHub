"""Partie 3 - etape 2 : nettoyage des mesures de pollution (bronze -> silver).

- regroupe l'historique (3 ans) et le flux temps reel dans un seul tableau
- variables : sensor_id, pollutant, value, unit, latitude, longitude, timestamp (+ city, location_name)
- l'heure d'une mesure = le debut de l'heure mesuree (l'archive donne la fin : on retire 1 h)
- met tout dans la meme unite (microgrammes par m3), certains capteurs donnent des ppm ou ppb
- enleve les valeurs negatives ou impossibles et les doublons

Resultat, un fichier Parquet par annee :
  silver/pollution/year=2025/pollution.parquet

Lancer : python -m urbanhub.pollution.nettoyer
"""
import gzip
import io
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from urbanhub import datalake

POLLUANTS = ["pm25", "pm10", "o3", "no2", "co"]
# masse molaire (g/mol) pour convertir ppm -> microgrammes par m3 (a 25 C)
MASSE_MOLAIRE = {"o3": 48.00, "no2": 46.01, "co": 28.01}
MAXI = {"pm25": 1000, "pm10": 2000, "o3": 1000, "no2": 1000, "co": 50000}  # microgrammes par m3
COLONNES = ["sensor_id", "location_id", "location_name", "city", "pollutant", "value", "unit",
            "latitude", "longitude", "timestamp"]


def lire_historique(key, villes):
    """Un fichier mois du depot OpenAQ -> lignes au format commun."""
    brut = gzip.decompress(datalake.get_bytes("bronze", key))
    try:
        texte = brut.decode("utf-8")
    except UnicodeDecodeError:  # les fichiers de l'archive sont souvent en latin-1 (le "µ" de µg/m³)
        texte = brut.decode("latin-1")
    df = pd.read_csv(io.StringIO(texte), dtype=str)
    # un fichier mois = des fichiers jour mis bout a bout : chaque jour repete la ligne d'en-tete
    df = df[(df["location_id"] != "location_id") & df["parameter"].isin(POLLUANTS)].copy()
    for c in ["location_id", "sensors_id", "lat", "lon", "value"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.rename(columns={"sensors_id": "sensor_id", "location": "location_name", "parameter": "pollutant",
                            "units": "unit", "lat": "latitude", "lon": "longitude"})
    df["location_name"] = df["location_name"].str.replace(r"-\d+$", "", regex=True)
    df["city"] = df["location_id"].map(villes)
    # l'archive date la FIN de l'heure mesuree, l'API son DEBUT : on aligne sur le debut
    df["timestamp"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce", format="ISO8601") - pd.Timedelta(hours=1)
    return df.drop(columns="datetime")


def lignes_flux(snapshot, capteurs):
    """Une collecte du flux (reponse de l'API /latest) -> lignes au format commun."""
    collecte = pd.Timestamp(snapshot["collected_at"])
    lignes = []
    for m in snapshot["results"]:
        meta = capteurs.get(m.get("sensorsId"))
        quand = (m.get("datetime") or {}).get("utc")
        # un capteur en panne renvoie sa "derniere" mesure, parfois vieille de plusieurs annees : on l'ignore
        if meta and quand and collecte - pd.Timestamp(quand) < pd.Timedelta(days=2):
            lignes.append({**meta, "value": m.get("value"), "timestamp": quand})
    return pd.DataFrame(lignes)


def vers_ugm3(df):
    """Convertit ppm et ppb en microgrammes par m3."""
    unite = df["unit"].fillna("").str.lower()
    mm = df["pollutant"].map(MASSE_MOLAIRE).astype("float64")
    facteur = pd.Series(1.0, index=df.index)
    facteur[unite == "ppm"] = mm * 1000 / 24.45
    facteur[unite == "ppb"] = mm / 24.45
    inconnu = ~unite.isin(["ppm", "ppb", "µg/m³", "ug/m3", "µg/m3"])
    df["value"] = df["value"] * facteur
    df.loc[inconnu, "value"] = None
    df["unit"] = "µg/m³"
    return df


def nettoyer_mesures(df):
    """Regles de nettoyage communes a l'historique et au flux."""
    if df.empty:
        return df
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dt.floor("h")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["timestamp", "value", "city"])
    df = vers_ugm3(df)
    df = df[(df["value"] >= 0) & (df["value"] <= df["pollutant"].map(MAXI).astype("float64"))]
    df = df.drop_duplicates(["sensor_id", "timestamp"], keep="last")
    df["location_name"] = df["location_name"].fillna("").astype(str)
    df["timestamp"] = df["timestamp"].astype("datetime64[ns, UTC]")
    return df[COLONNES].sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)


def main():
    try:
        capteurs = {c["sensor_id"]: c for c in datalake.get_json("bronze", "pollution/openaq/reference/capteurs.json")}
    except Exception:
        print("Pas de capteurs dans bronze. Lancer d'abord : python -m urbanhub.pollution.collecter --historique 3")
        return
    villes = {c["location_id"]: c["city"] for c in capteurs.values()}

    cles_histo = list(datalake.lister("bronze", "pollution/openaq/historique/"))
    cles_flux = list(datalake.lister("bronze", "pollution/openaq/flux/"))
    print(f"{len(cles_histo)} fichiers historiques, {len(cles_flux)} collectes du flux")
    with ThreadPoolExecutor(max_workers=16) as pool:
        flux = list(pool.map(lambda k: lignes_flux(datalake.get_json("bronze", k), capteurs), cles_flux))

    # on traite annee par annee pour ne pas saturer la memoire
    annees = sorted({k.split("year=")[1][:4] for k in cles_histo} | {k.split("year=")[1][:4] for k in cles_flux})
    total = 0
    for annee in annees:
        cles = [k for k in cles_histo if f"/year={annee}/" in k]
        with ThreadPoolExecutor(max_workers=16) as pool:
            morceaux = list(pool.map(lambda k: lire_historique(k, villes), cles))
        morceaux += [f[pd.to_datetime(f["timestamp"], utc=True).dt.year == int(annee)] for f in flux if not f.empty]
        df = nettoyer_mesures(pd.concat(morceaux, ignore_index=True)) if morceaux else pd.DataFrame()
        if df.empty:
            continue
        datalake.put_parquet("silver", f"pollution/year={annee}/pollution.parquet", df)
        total += len(df)
        print(f"  {annee} : {len(df):,} mesures horaires, {df['sensor_id'].nunique()} capteurs, "
              f"du {df['timestamp'].min():%Y-%m-%d} au {df['timestamp'].max():%Y-%m-%d %H:%M}")
    print(f"Silver pret : {total:,} mesures")


if __name__ == "__main__":
    main()
