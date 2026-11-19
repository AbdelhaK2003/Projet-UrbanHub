"""Partie 3 - etape 1 : collecte des capteurs de pollution OpenAQ (flux IoT).

1. On cherche les capteurs autour de chaque grande ville (rayon 25 km)
   et on garde les 5 polluants demandes : PM2.5, PM10, O3, NO2, CO
2. Mode flux (par defaut) : toutes les 15 min on lit la derniere mesure de chaque
   capteur, comme si les capteurs nous envoyaient leurs donnees en direct
3. Mode historique : on recupere les mesures horaires des N derniers jours
   (utile pour avoir tout de suite assez de donnees a analyser)

Une cle API gratuite est necessaire (fichier .env, variable OPENAQ_API_KEY).

Lancer :
  python -m urbanhub.pollution.collecter --historique 60   (une fois, 60 derniers jours)
  python -m urbanhub.pollution.collecter                    (flux continu)
"""
import argparse
import time
from datetime import datetime, timedelta, timezone

import requests

from urbanhub import config, datalake
from urbanhub.villes import VILLES

API = "https://api.openaq.org/v3"
POLLUANTS = {"pm25", "pm10", "o3", "no2", "co"}
_dernier_appel = [0.0]


def appel(chemin, params=None):
    """Appel a l'API avec respect de la limite (60 requetes / minute) et nouvelles tentatives."""
    if not config.OPENAQ_API_KEY:
        raise SystemExit("Cle OpenAQ manquante : la mettre dans le fichier .env (OPENAQ_API_KEY=...)")
    headers = {"X-API-Key": config.OPENAQ_API_KEY, "User-Agent": config.USER_AGENT}
    for essai in range(5):
        attente = 1.1 - (time.time() - _dernier_appel[0])
        if attente > 0:
            time.sleep(attente)
        _dernier_appel[0] = time.time()
        try:
            r = requests.get(API + chemin, params=params, headers=headers, timeout=60)
        except requests.RequestException:
            time.sleep(5 * (essai + 1))
            continue
        if r.status_code == 429:  # trop de requetes : on attend la fin de la fenetre
            time.sleep(int(r.headers.get("x-ratelimit-reset", 60)) + 1)
            continue
        if r.status_code >= 500:
            time.sleep(5 * (essai + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Echec apres plusieurs essais : {chemin}")


def chercher_capteurs():
    """Liste des capteurs (sensor) utiles autour des grandes villes."""
    capteurs, brut = [], {}
    limite_activite = datetime.now(timezone.utc) - timedelta(days=30)
    for ville, (lat, lon) in VILLES.items():
        res = appel("/locations", {"coordinates": f"{lat},{lon}", "radius": 25000, "limit": 1000})["results"]
        brut[ville] = res
        for loc in res:
            dernier = (loc.get("datetimeLast") or {}).get("utc")
            if not dernier or datetime.fromisoformat(dernier.replace("Z", "+00:00")) < limite_activite:
                continue  # station arretee
            for s in loc.get("sensors", []):
                param = s["parameter"]
                if param["name"] in POLLUANTS:
                    capteurs.append({
                        "sensor_id": s["id"], "location_id": loc["id"], "location_name": loc.get("name"),
                        "city": ville, "pollutant": param["name"], "unit": param.get("units"),
                        "latitude": loc["coordinates"]["latitude"], "longitude": loc["coordinates"]["longitude"],
                    })
        print(f"  {ville} : {sum(c['city'] == ville for c in capteurs)} capteurs actifs")
    jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    datalake.put_json("bronze", f"pollution/openaq/reference/locations_{jour}.json", brut)
    datalake.put_json("bronze", "pollution/openaq/reference/capteurs.json", capteurs)
    return capteurs


def collecte_flux(capteurs):
    """Une collecte : derniere valeur de chaque station de mesure."""
    maintenant = datetime.now(timezone.utc)
    lieux = sorted({c["location_id"] for c in capteurs})
    resultats = []
    for loc_id in lieux:
        try:
            resultats.extend(appel(f"/locations/{loc_id}/latest")["results"])
        except (requests.RequestException, RuntimeError) as e:
            print(f"  station {loc_id} ignoree : {e}")
    key = maintenant.strftime("pollution/openaq/flux/year=%Y/month=%m/day=%d/snapshot_%Y%m%dT%H%M%S.json")
    datalake.put_json("bronze", key, {"collected_at": maintenant.isoformat(), "results": resultats})
    print(f"{maintenant:%H:%M:%S} UTC  {len(resultats)} mesures recues de {len(lieux)} stations")


def collecte_historique(capteurs, jours):
    """Mesures horaires des N derniers jours pour chaque capteur."""
    fin = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    debut = fin - timedelta(days=jours)
    for i, c in enumerate(capteurs, 1):
        mesures, page = [], 1
        while True:
            res = appel(f"/sensors/{c['sensor_id']}/hours", {
                "datetime_from": debut.isoformat(), "datetime_to": fin.isoformat(),
                "limit": 1000, "page": page})["results"]
            mesures.extend(res)
            if len(res) < 1000:
                break
            page += 1
        key = f"pollution/openaq/historique/sensor={c['sensor_id']}/{debut:%Y%m%d}_{fin:%Y%m%d}.json"
        datalake.put_json("bronze", key, {"sensor": c, "results": mesures})
        print(f"  [{i}/{len(capteurs)}] {c['city']} {c['pollutant']} capteur {c['sensor_id']} : {len(mesures)} heures")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--historique", type=int, metavar="JOURS", help="recuperer les N derniers jours puis s'arreter")
    p.add_argument("--intervalle", type=int, default=900, help="secondes entre deux collectes du flux")
    p.add_argument("--une-fois", action="store_true")
    args = p.parse_args()

    datalake.init_buckets()
    print("Recherche des capteurs autour des grandes villes")
    capteurs = chercher_capteurs()
    print(f"{len(capteurs)} capteurs retenus")

    if args.historique:
        collecte_historique(capteurs, args.historique)
        return

    maj = time.time()
    while True:
        debut = time.time()
        try:
            if time.time() - maj > 86400:  # liste des capteurs rafraichie chaque jour
                capteurs, maj = chercher_capteurs(), time.time()
            collecte_flux(capteurs)
        except Exception as e:
            print("Erreur, nouvelle tentative au prochain tour :", e)
        if args.une_fois:
            break
        time.sleep(max(0, args.intervalle - (time.time() - debut)))


if __name__ == "__main__":
    main()
