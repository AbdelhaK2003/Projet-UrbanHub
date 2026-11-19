"""Partie 1 - etape 1 : telechargement PARALLELE des fichiers NOAA des stations francaises.

Principe
1. On recupere la liste officielle des stations NOAA (isd-history.csv)
2. On garde les stations dont le pays est la France (code FR) et actives sur la periode
3. On telecharge tous les fichiers (une station x une annee) en meme temps
   avec un pool de threads, et on les depose tels quels dans bronze

Lancer : python -m urbanhub.meteo.telecharger
Options utiles : --workers 16  --annees 5  --max-stations 10 (pour tester vite)
                 --grandes-villes (seulement les stations a moins de 30 km d'une grande ville)
"""
import argparse
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import requests
from tqdm import tqdm

from urbanhub import config, datalake
from urbanhub.villes import ville_proche

URL_STATIONS = "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"
# l'adresse ncei.noaa.gov/data/global-hourly/access/ redirige maintenant vers ce depot AWS
URL_FICHIER = "https://noaa-global-hourly-pds.s3.amazonaws.com/{annee}/{station}.csv"


def stations_france(annee_debut):
    """Liste des stations meteo francaises actives depuis annee_debut."""
    r = requests.get(URL_STATIONS, timeout=60, headers={"User-Agent": config.USER_AGENT})
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content), dtype=str)
    df = df[df["CTRY"] == "FR"].copy()
    df["END"] = pd.to_datetime(df["END"], format="%Y%m%d", errors="coerce")
    df = df[df["END"].dt.year >= annee_debut]
    df["station_id"] = df["USAF"] + df["WBAN"]
    df = df.rename(columns={"STATION NAME": "station_name", "LAT": "latitude", "LON": "longitude"})
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    # on ne garde que la France metropolitaine (Corse incluse)
    df = df[df["latitude"].between(41, 52) & df["longitude"].between(-5.5, 10)]
    return df[["station_id", "station_name", "latitude", "longitude"]].drop_duplicates("station_id")


def telecharger_un(annee, station):
    """Telecharge un fichier station/annee et l'envoie dans bronze. Renvoie un statut."""
    key = f"meteo/noaa/year={annee}/{station}.csv"
    # les annees passees ne changent plus : on ne les retelecharge pas
    # l'annee en cours est toujours mise a jour
    if annee < datetime.now().year and datalake.existe("bronze", key):
        return "deja la"
    url = URL_FICHIER.format(annee=annee, station=station)
    for essai in range(3):
        try:
            r = requests.get(url, timeout=120, headers={"User-Agent": config.USER_AGENT})
            if r.status_code == 404:
                return "absent"  # la station n'a pas publie de donnees cette annee-la
            r.raise_for_status()
            datalake.put_bytes("bronze", key, r.content, "text/csv")
            return "ok"
        except requests.RequestException:
            time.sleep(2 * (essai + 1))
    return "erreur"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--annees", type=int, default=5, help="nombre d'annees completes a recuperer")
    p.add_argument("--workers", type=int, default=16, help="nombre de telechargements simultanes")
    p.add_argument("--max-stations", type=int, default=None, help="limite pour un test rapide")
    p.add_argument("--grandes-villes", action="store_true", help="seulement les stations proches des grandes villes")
    args = p.parse_args()

    datalake.init_buckets()
    annee_courante = datetime.now().year
    # 5 annees completes + l'annee en cours (utile pour croiser avec les velos et la pollution)
    annees = list(range(annee_courante - args.annees, annee_courante + 1))

    stations = stations_france(annees[0])
    if args.grandes_villes:
        stations = stations[[ville_proche(la, lo) is not None for la, lo in zip(stations["latitude"], stations["longitude"])]]
    if args.max_stations:
        stations = stations.head(args.max_stations)
    datalake.put_parquet("bronze", "meteo/reference/stations_france.parquet", stations)
    print(f"{len(stations)} stations francaises, annees {annees[0]} a {annees[-1]}")

    taches = [(a, s) for a in annees for s in stations["station_id"]]
    bilan = {}
    debut = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futurs = [pool.submit(telecharger_un, a, s) for a, s in taches]
        for f in tqdm(as_completed(futurs), total=len(futurs), desc="Telechargement"):
            statut = f.result()
            bilan[statut] = bilan.get(statut, 0) + 1

    print(f"Termine en {time.time() - debut:.0f} s :", bilan)


if __name__ == "__main__":
    main()
