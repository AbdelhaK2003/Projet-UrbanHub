"""Partie 2 - etape 1 : collecte automatique des stations de velos (flux streaming).

Toutes les 3 minutes (reglable), le script interroge l'API CityBikes pour les
reseaux des grandes villes francaises (Velib Paris, Velo'v Lyon, ...) et depose
une "photo" de toutes les stations dans bronze :

  bronze/velos/citybikes/year=2026/month=11/day=19/snapshot_20261119T143000.json

Lancer : python -m urbanhub.velos.collecter
Options : --intervalle 180 (secondes)  --une-fois (une seule collecte)  --toutes-villes

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
# CityBikes autorise 300 requetes par heure. On garde une marge pour la liste des reseaux.
LIMITE_PAR_HEURE = 280


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


class TropDeRequetes(Exception):
    """L'API a repondu 429 : on a depasse la limite et il faut attendre."""

    def __init__(self, attente):
        super().__init__(f"limite de l'API atteinte, attendre {attente} s")
        self.attente = attente


def stations_du_reseau(reseau):
    r = requests.get(f"{API}/{reseau['id']}", params={"fields": "stations"}, headers=HEADERS, timeout=30)
    if r.status_code == 429:
        raise TropDeRequetes(int(r.headers.get("retry-after", 600)))
    r.raise_for_status()
    return {**reseau, "stations": r.json()["network"]["stations"]}


def collecter(reseaux):
    """Une collecte : tous les reseaux interroges en parallele, un seul fichier dans bronze.
    Renvoie le nombre de secondes a attendre si l'API nous a bloques (0 sinon)."""
    maintenant = datetime.now(timezone.utc)
    resultats, erreurs, attente = [], [], 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futurs = {pool.submit(stations_du_reseau, n): n for n in reseaux}
        for f, n in futurs.items():
            try:
                resultats.append(f.result())
            except TropDeRequetes as e:
                attente = max(attente, e.attente)
                erreurs.append(f"{n['id']}: {e}")
            except Exception as e:
                erreurs.append(f"{n['id']}: {e}")

    if resultats:  # on n'enregistre pas une photo vide
        key = maintenant.strftime("velos/citybikes/year=%Y/month=%m/day=%d/snapshot_%Y%m%dT%H%M%S.json")
        datalake.put_json("bronze", key, {"collected_at": maintenant.isoformat(), "networks": resultats})
    nb = sum(len(r["stations"]) for r in resultats)
    print(f"{maintenant:%H:%M:%S} UTC  {len(resultats)} reseaux, {nb} stations"
          + (f"  ({len(erreurs)} erreurs, ex : {erreurs[0]})" if erreurs else ""))
    return attente


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--intervalle", type=int, default=180, help="secondes entre deux collectes (120 a 180)")
    p.add_argument("--une-fois", action="store_true")
    p.add_argument("--toutes-villes", action="store_true", help="tous les reseaux francais, pas seulement les grandes villes")
    args = p.parse_args()

    datalake.init_buckets()
    reseaux, maj_reseaux, intervalle = [], 0, args.intervalle
    while True:
        debut, attente = time.time(), 0
        try:
            if time.time() - maj_reseaux > 3600:  # la liste des reseaux est rafraichie chaque heure
                reseaux = reseaux_france(args.toutes_villes)
                maj_reseaux = time.time()
                print("Reseaux suivis :", ", ".join(f"{n['city']} ({n['id']})" for n in reseaux))
                # une requete par reseau a chaque collecte : on reste sous la limite de l'API
                intervalle = max(args.intervalle, len(reseaux) * 3600 / LIMITE_PAR_HEURE)
                if intervalle > args.intervalle:
                    print(f"Intervalle porte a {intervalle:.0f} s pour respecter la limite de l'API")
            attente = collecter(reseaux)
        except Exception as e:  # une panne reseau ne doit pas arreter la collecte
            print("Erreur, nouvelle tentative au prochain tour :", e)
        if args.une_fois:
            break
        if attente:
            print(f"API saturee : pause de {attente} s")
        time.sleep(max(attente, intervalle - (time.time() - debut)))


if __name__ == "__main__":
    main()
