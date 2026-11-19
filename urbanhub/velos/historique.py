"""Partie 2 - historique des stations de velos (archive publique CityBikes).

L'API CityBikes ne donne que l'etat actuel des stations. Mais CityBikes publie a
part un historique sur https://data.citybik.es : un fichier Parquet par reseau et
par mois, ou chaque ligne est un changement d'etat d'une station (velos, places libres).
L'archive commence en novembre 2024.

Ce script telecharge en parallele les mois des 3 dernieres annees (dans la limite
de ce qui existe) pour les reseaux suivis par le collecteur, et les depose dans bronze :

  bronze/velos/citybikes_historique/network=velib/year=2025/month=03.parquet

Les mois deja recuperes ne sont pas repris. Licence ODbL : "Bike-share data by
CityBikes contributors and available from https://data.citybik.es".

Lancer : python -m urbanhub.velos.historique
"""
import argparse
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import requests

from urbanhub import config, datalake

ARCHIVE = "https://data.citybik.es/dumps/by-network"
HEADERS = {"User-Agent": config.USER_AGENT, "Accept": "application/json"}

# reseaux suivis (memes identifiants que le collecteur) -> ville
RESEAUX = {
    "velib": "Paris", "velov": "Lyon", "le-velo": "Marseille", "velo": "Toulouse", "pony-nice": "Nice",
    "bicloo": "Nantes", "chantrerie-captainbike": "Nantes", "velhop": "Strasbourg", "velomagg": "Montpellier",
    "v3-bordeaux": "Bordeaux", "vlille": "Lille", "le-velo-star": "Rennes",
}


def cle(reseau, annee, mois):
    return f"velos/citybikes_historique/network={reseau}/year={annee}/month={mois}.parquet"


def fichiers_disponibles(depuis):
    """Liste des fichiers de l'archive pour nos reseaux, a partir du mois 'depuis' (AAAAMM)."""
    res = []
    for annee in range(int(depuis[:4]), date.today().year + 1):
        r = requests.get(f"{ARCHIVE}/{annee}/", headers=HEADERS, timeout=60)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        for f in r.json():
            m = re.match(r"(\d{4})(\d{2})-(.+)-stats\.parquet$", f["name"])
            if m and m.group(3) in RESEAUX and m.group(1) + m.group(2) >= depuis:
                res.append({"url": f"{ARCHIVE}/{annee}/{f['name']}", "reseau": m.group(3),
                            "annee": m.group(1), "mois": m.group(2), "taille": f.get("size", 0)})
    return res


def telecharger(f):
    r = requests.get(f["url"], headers={"User-Agent": config.USER_AGENT}, timeout=600)
    r.raise_for_status()
    datalake.put_bytes("bronze", cle(f["reseau"], f["annee"], f["mois"]), r.content, "application/vnd.apache.parquet")
    return len(r.content)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--annees", type=int, default=3)
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()

    datalake.init_buckets()
    aujourdhui = date.today()
    depuis = f"{aujourdhui.year - args.annees}{aujourdhui.month:02d}"
    fichiers = [f for f in fichiers_disponibles(depuis)
                if not datalake.existe("bronze", cle(f["reseau"], f["annee"], f["mois"]))]
    total = sum(f["taille"] for f in fichiers) / 1e6
    print(f"{len(fichiers)} fichiers mensuels a telecharger ({total:,.0f} Mo), {args.workers} en parallele")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futurs = {pool.submit(telecharger, f): f for f in fichiers}
        for fut in as_completed(futurs):
            f = futurs[fut]
            try:
                print(f"  {f['reseau']} {f['annee']}-{f['mois']} : {fut.result() / 1e6:.1f} Mo")
            except Exception as e:
                print(f"  {f['reseau']} {f['annee']}-{f['mois']} : ERREUR {e}")
    print("Historique dans bronze. Etape suivante : python -m urbanhub.velos.nettoyer")


if __name__ == "__main__":
    main()
