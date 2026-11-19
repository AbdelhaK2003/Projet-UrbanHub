"""Partie 2 - etape 1 : collecte automatique des stations de velos (flux streaming).

Toutes les 2 min 30 (reglable), le script interroge l'API CityBikes pour les
reseaux des grandes villes francaises (Velib Paris, Velo'v Lyon, ...) et depose
une "photo" de toutes les stations dans bronze :

  bronze/velos/citybikes/year=2026/month=11/day=19/snapshot_20261119T143000.json

Lancer : python -m urbanhub.velos.collecter
Options : --intervalle 150 (secondes)  --une-fois (une seule collecte)  --toutes-villes

Laisser tourner le script en fond le plus longtemps possible : l'API ne donne
que l'etat actuel, l'historique se construit donc au fil de la collecte.
"""
import argparse
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from urbanhub import config, datalake
from urbanhub.villes import VILLES

API = "https://api.citybik.es/v2/networks"
HEADERS = {"User-Agent": config.USER_AGENT}


def simplifier(texte):
    """'Velo'v Lyon' -> 'velo'v lyon' sans accents, pour comparer les noms de villes."""
    texte = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    return texte.lower()


def reseaux_france(toutes_villes=False):
    r = requests.get(API, params={"fields": "id,name,location"}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    reseaux = []
    for n in r.json()["networks"]:
        loc = n.get("location", {})
        if loc.get("country") != "FR":
            continue
        ville_api = simplifier(loc.get("city"))
        ville = next((v for v in VILLES if simplifier(v) in ville_api), None)
        if ville or toutes_villes:
            reseaux.append({"id": n["id"], "name": n["name"], "city": ville or loc.get("city")})
    return reseaux


def stations_du_reseau(reseau):
    r = requests.get(f"{API}/{reseau['id']}", params={"fields": "stations"}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return {**reseau, "stations": r.json()["network"]["stations"]}


def collecter(reseaux):
    """Une collecte : tous les reseaux interroges en parallele, un seul fichier dans bronze."""
    maintenant = datetime.now(timezone.utc)
    resultats, erreurs = [], []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futurs = {pool.submit(stations_du_reseau, n): n for n in reseaux}
        for f, n in futurs.items():
            try:
                resultats.append(f.result())
            except requests.RequestException as e:
                erreurs.append(f"{n['id']}: {e}")

    key = maintenant.strftime("velos/citybikes/year=%Y/month=%m/day=%d/snapshot_%Y%m%dT%H%M%S.json")
    datalake.put_json("bronze", key, {"collected_at": maintenant.isoformat(), "networks": resultats})
    nb = sum(len(r["stations"]) for r in resultats)
    print(f"{maintenant:%H:%M:%S} UTC  {len(resultats)} reseaux, {nb} stations"
          + (f"  ({len(erreurs)} erreurs)" if erreurs else ""))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--intervalle", type=int, default=150, help="secondes entre deux collectes (120 a 180)")
    p.add_argument("--une-fois", action="store_true")
    p.add_argument("--toutes-villes", action="store_true", help="tous les reseaux francais, pas seulement les grandes villes")
    args = p.parse_args()

    datalake.init_buckets()
    reseaux, maj_reseaux = [], 0
    while True:
        debut = time.time()
        try:
            if time.time() - maj_reseaux > 3600:  # la liste des reseaux est rafraichie chaque heure
                reseaux = reseaux_france(args.toutes_villes)
                maj_reseaux = time.time()
                print("Reseaux suivis :", ", ".join(f"{n['city']} ({n['id']})" for n in reseaux))
            collecter(reseaux)
        except Exception as e:  # une panne reseau ne doit pas arreter la collecte
            print("Erreur, nouvelle tentative au prochain tour :", e)
        if args.une_fois:
            break
        time.sleep(max(0, args.intervalle - (time.time() - debut)))


if __name__ == "__main__":
    main()
