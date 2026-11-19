"""Partie 1 - etape 1 : telechargement parallele de la meteo historique (Open-Meteo).

Source : Open-Meteo (gratuit, sans cle). On recupere, pour chaque grande ville,
la meteo heure par heure des 5 dernieres annees jusqu'a aujourd'hui :

- API "archive" (reanalyse ERA5) : temperature, humidite, pluie, vent, rafales,
  pression, couverture nuageuse
- API "historical forecast" : la visibilite (absente de l'archive)

Une requete = une ville x une annee. Les requetes partent en parallele
(ThreadPoolExecutor) et chaque reponse est deposee telle quelle dans bronze :

  bronze/meteo/openmeteo/ville=Paris/year=2024.json

Les annees passees deja telechargees ne sont pas reprises. L'annee en cours est
toujours retelechargee pour aller jusqu'a aujourd'hui.

Lancer : python -m urbanhub.meteo.telecharger
Options : --annees 5  --workers 4
"""
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import requests

from urbanhub import config, datalake
from urbanhub.villes import VILLES

API_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
API_VISIBILITE = "https://historical-forecast-api.open-meteo.com/v1/forecast"
VARIABLES = ("temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_direction_10m,"
             "wind_gusts_10m,pressure_msl,cloud_cover")


def appel(url, params):
    """Requete avec nouvelles tentatives (limite de debit ou coupure reseau)."""
    for essai in range(6):
        try:
            r = requests.get(url, params=params, headers={"User-Agent": config.USER_AGENT}, timeout=120)
            if r.status_code == 429:
                time.sleep(30 * (essai + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            time.sleep(5 * (essai + 1))
    raise RuntimeError(f"echec apres plusieurs essais : {url}")


def cle(ville, annee):
    return f"meteo/openmeteo/ville={ville}/year={annee}.json"


def telecharger_un(ville, annee, debut, fin):
    lat, lon = VILLES[ville]
    commun = {"latitude": lat, "longitude": lon, "start_date": debut.isoformat(),
              "end_date": fin.isoformat(), "timezone": "UTC"}
    brut = {
        "ville": ville,
        "archive": appel(API_ARCHIVE, {**commun, "hourly": VARIABLES}),
        "visibilite": appel(API_VISIBILITE, {**commun, "hourly": "visibility"}),
    }
    datalake.put_json("bronze", cle(ville, annee), brut)
    return len(brut["archive"]["hourly"]["time"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--annees", type=int, default=5, help="nombre d'annees d'historique")
    p.add_argument("--workers", type=int, default=4, help="telechargements en parallele")
    args = p.parse_args()

    datalake.init_buckets()
    aujourdhui = date.today()
    depart = aujourdhui.replace(year=aujourdhui.year - args.annees)

    taches = []
    for annee in range(depart.year, aujourdhui.year + 1):
        debut = max(date(annee, 1, 1), depart)
        fin = min(date(annee, 12, 31), aujourdhui)
        for ville in VILLES:
            if annee < aujourdhui.year and datalake.existe("bronze", cle(ville, annee)):
                continue  # annee passee deja recuperee
            taches.append((ville, annee, debut, fin))
    print(f"Periode : du {depart} au {aujourdhui}. {len(taches)} fichiers a telecharger "
          f"({len(VILLES)} villes), {args.workers} en parallele")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futurs = {pool.submit(telecharger_un, *t): t for t in taches}
        for f in as_completed(futurs):
            ville, annee = futurs[f][:2]
            try:
                print(f"  {ville} {annee} : {f.result():,} heures")
            except Exception as e:
                print(f"  {ville} {annee} : ERREUR {e}")
    print("Bronze pret. Etape suivante : python -m urbanhub.meteo.nettoyer")


if __name__ == "__main__":
    main()
