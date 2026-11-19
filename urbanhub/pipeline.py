"""Lance toute la chaine de traitement dans l'ordre, une fois ou en boucle.

  bronze -> silver (nettoyage) -> gold (indicateurs) -> ClickHouse -> interface

Etapes :
  1. meteo     : mise a jour Open-Meteo jusqu'a aujourd'hui, nettoyage, analyses
  2. velos     : nouveaux mois de l'historique CityBikes, nettoyage, analyses
  3. pollution : nettoyage (historique + flux), analyses
  4. croisement
  5. chargement de silver et gold dans ClickHouse

Les collecteurs (velos et pollution) tournent a part, en continu, et alimentent
deja ClickHouse en direct. Ce script, lui, rafraichit les indicateurs gold.

Lancer :
  python -m urbanhub.pipeline                 (une fois)
  python -m urbanhub.pipeline --boucle 3600   (toutes les heures)
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime

ETAPES = [
    "urbanhub.meteo.telecharger",
    "urbanhub.meteo.nettoyer",
    "urbanhub.meteo.analyser",
    "urbanhub.velos.historique",
    "urbanhub.velos.nettoyer",
    "urbanhub.velos.analyser",
    "urbanhub.pollution.nettoyer",
    "urbanhub.pollution.analyser",
    "urbanhub.croisement.analyser",
    "urbanhub.charger_clickhouse",
]


def executer(etapes):
    debut = time.time()
    for module in etapes:
        print(f"\n===== {datetime.now():%H:%M:%S}  python -m {module}", flush=True)
        r = subprocess.run([sys.executable, "-m", module])
        if r.returncode != 0:
            print(f"!!! {module} a echoue (code {r.returncode}), on continue avec la suite", flush=True)
    print(f"\nPipeline termine en {(time.time() - debut) / 60:.1f} min", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--boucle", type=int, metavar="SECONDES", help="relancer la chaine toutes les N secondes")
    p.add_argument("--sans-meteo", action="store_true", help="ne pas retelecharger la meteo")
    args = p.parse_args()
    etapes = [e for e in ETAPES if not (args.sans_meteo and e == "urbanhub.meteo.telecharger")]
    while True:
        debut = time.time()
        executer(etapes)
        if not args.boucle:
            break
        time.sleep(max(0, args.boucle - (time.time() - debut)))


if __name__ == "__main__":
    main()
