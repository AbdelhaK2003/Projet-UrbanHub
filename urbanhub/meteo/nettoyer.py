"""Partie 1 - etape 2 : nettoyage de la meteo (bronze -> silver).

Pour chaque fichier JSON de bronze (une ville x une annee) :
- on remet les colonnes de l'API sous des noms simples
  (station_id, timestamp, temperature, wind_speed, wind_direction, pressure,
  precipitation, visibility, + humidity, wind_gusts, cloud_cover)
- visibilite en km (l'API donne des metres)
- on enleve les valeurs impossibles (ex : temperature a 70 C)
- on bouche les petits trous (3 heures maximum) par interpolation
- on enleve les heures futures et les doublons

Resultat, un fichier Parquet par annee :
  silver/meteo/year=2024/meteo.parquet

Lancer : python -m urbanhub.meteo.nettoyer
"""
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from urbanhub import datalake
from urbanhub.villes import VILLES

COLONNES = {
    "temperature_2m": "temperature",
    "relative_humidity_2m": "humidity",
    "precipitation": "precipitation",
    "wind_speed_10m": "wind_speed",
    "wind_direction_10m": "wind_direction",
    "wind_gusts_10m": "wind_gusts",
    "pressure_msl": "pressure",
    "cloud_cover": "cloud_cover",
}
# valeurs possibles en France (en dehors : erreur)
BORNES = {
    "temperature": (-40, 50), "humidity": (0, 100), "precipitation": (0, 200),
    "wind_speed": (0, 250), "wind_gusts": (0, 300), "pressure": (900, 1100),
    "cloud_cover": (0, 100), "visibility": (0, 100),
}


def lire(key):
    brut = datalake.get_json("bronze", key)
    ville = brut["ville"]
    a = pd.DataFrame(brut["archive"]["hourly"]).rename(columns=COLONNES)
    v = pd.DataFrame(brut["visibilite"]["hourly"])
    df = a.merge(v, on="time", how="left")
    df["timestamp"] = pd.to_datetime(df.pop("time"), utc=True)
    df["visibility"] = df["visibility"] / 1000  # metres -> km
    df.insert(0, "city", ville)
    df.insert(0, "station_id", "openmeteo-" + ville.lower())
    df["latitude"], df["longitude"] = VILLES[ville]
    return df


def nettoyer(df):
    maintenant = pd.Timestamp.now(tz="UTC")
    df = df[df["timestamp"] <= maintenant].copy()  # pas de prevision dans l'historique
    for col, (mini, maxi) in BORNES.items():
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
        df.loc[(df[col] < mini) | (df[col] > maxi), col] = None
    df = df.drop_duplicates(["station_id", "timestamp"]).sort_values(["station_id", "timestamp"])
    continues = ["temperature", "humidity", "pressure", "wind_speed", "visibility"]
    df[continues] = df.groupby("station_id")[continues].transform(lambda s: s.interpolate(limit=3))
    return df.reset_index(drop=True)


def main():
    cles = [k for k in datalake.lister("bronze", "meteo/openmeteo/") if k.endswith(".json")]
    if not cles:
        print("Rien dans bronze. Lancer d'abord : python -m urbanhub.meteo.telecharger")
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        df = pd.concat(pool.map(lire, cles), ignore_index=True)
    df = nettoyer(df)
    for annee, morceau in df.groupby(df["timestamp"].dt.year):
        datalake.put_parquet("silver", f"meteo/year={annee}/meteo.parquet", morceau)
        print(f"  {annee} : {len(morceau):,} heures, {morceau['city'].nunique()} villes")
    manquants = df[["temperature", "visibility"]].isna().mean().round(4).to_dict()
    print(f"Silver pret : {len(df):,} lignes du {df['timestamp'].min():%Y-%m-%d} au "
          f"{df['timestamp'].max():%Y-%m-%d %H:%M}. Part de valeurs manquantes : {manquants}")


if __name__ == "__main__":
    main()
