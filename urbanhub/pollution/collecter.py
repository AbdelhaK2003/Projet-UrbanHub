"""Partie 3 - etape 1 : collecte des capteurs de pollution OpenAQ (IoT).

1. On cherche les capteurs autour de chaque grande ville (rayon 25 km)
   et on garde les 5 polluants demandes : PM2.5, PM10, O3, NO2, CO
2. Mode historique : les mesures horaires des 3 dernieres annees jusqu'a aujourd'hui.
   OpenAQ publie tout son historique dans un depot public (AWS S3, un fichier par
   station et par jour). On telecharge ces fichiers en parallele et on les regroupe
   par mois dans bronze :
     bronze/pollution/openaq/historique/location=2681/year=2024/month=05.csv.gz
3. Mode flux (par defaut) : toutes les 15 min on lit la derniere mesure de chaque
   station via l'API, comme si les capteurs nous envoyaient leurs donnees en direct.
   Chaque collecte va dans bronze ET directement dans ClickHouse (interface temps reel).

Une cle API gratuite est necessaire pour l'API (fichier .env, variable OPENAQ_API_KEY).

Lancer :
  python -m urbanhub.pollution.collecter --historique 3   (une fois, 3 dernieres annees)
  python -m urbanhub.pollution.collecter                   (flux continu)
"""
import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import boto3
import requests
from botocore import UNSIGNED
from botocore.client import Config

from urbanhub import config, datalake, olap
from urbanhub.villes import VILLES

API = "https://api.openaq.org/v3"
ARCHIVE = "openaq-data-archive"  # depot public OpenAQ sur AWS S3 (lecture libre)
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


def chercher_capteurs(jours_activite=30):
    """Liste des capteurs (sensor) utiles autour des grandes villes."""
    capteurs, brut = [], {}
    limite_activite = datetime.now(timezone.utc) - timedelta(days=jours_activite)
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


# ---------- historique (depot public OpenAQ) ----------

def depot_public():
    return boto3.client("s3", config=Config(signature_version=UNSIGNED, max_pool_connections=64),
                        region_name="us-east-1")


def cle_bronze(location_id, annee, mois):
    return f"pollution/openaq/historique/location={location_id}/year={annee}/month={mois:02d}.csv.gz"


def recuperer_mois(pub, location_id, annee, mois, debut):
    """Telecharge les fichiers jour d'une station pour un mois et les depose en un seul fichier.
    Des fichiers gzip mis bout a bout forment un gzip valide : pas besoin de decompresser."""
    prefixe = f"records/csv.gz/locationid={location_id}/year={annee}/month={mois:02d}/"
    cles = []
    for page in pub.get_paginator("list_objects_v2").paginate(Bucket=ARCHIVE, Prefix=prefixe):
        cles += [o["Key"] for o in page.get("Contents", []) if o["Key"][-15:-7] >= f"{debut:%Y%m%d}"]
    if not cles:
        return 0
    morceaux = []
    for k in sorted(cles):
        for essai in range(4):
            try:
                morceaux.append(pub.get_object(Bucket=ARCHIVE, Key=k)["Body"].read())
                break
            except Exception:
                time.sleep(2 * (essai + 1))
    datalake.put_bytes("bronze", cle_bronze(location_id, annee, mois), b"".join(morceaux), "application/gzip")
    return len(morceaux)


def collecte_historique(capteurs, annees, workers=24):
    aujourdhui = date.today()
    debut = aujourdhui.replace(year=aujourdhui.year - annees)
    lieux = sorted({c["location_id"] for c in capteurs})
    mois = []
    a, m = debut.year, debut.month
    while (a, m) <= (aujourdhui.year, aujourdhui.month):
        mois.append((a, m))
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)

    taches = []
    for loc in lieux:
        for a, m in mois:
            en_cours = (a, m) == (aujourdhui.year, aujourdhui.month)
            if not en_cours and datalake.existe("bronze", cle_bronze(loc, a, m)):
                continue  # mois termine deja recupere
            taches.append((loc, a, m))
    print(f"Historique du {debut} au {aujourdhui} : {len(lieux)} stations x {len(mois)} mois, "
          f"{len(taches)} mois a telecharger ({workers} en parallele)")

    pub = depot_public()
    fichiers, fait = 0, 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for n in pool.map(lambda t: recuperer_mois(pub, *t, debut), taches):
            fichiers += n
            fait += 1
            if fait % 200 == 0 or fait == len(taches):
                print(f"  {fait}/{len(taches)} mois traites, {fichiers:,} fichiers jour recuperes")
    print("Historique dans bronze. Etape suivante : python -m urbanhub.pollution.nettoyer")


# ---------- flux temps reel (API) ----------

def collecte_flux(capteurs):
    """Une collecte : derniere valeur de chaque station de mesure."""
    from urbanhub.pollution.nettoyer import lignes_flux, nettoyer_mesures

    maintenant = datetime.now(timezone.utc)
    lieux = sorted({c["location_id"] for c in capteurs})
    resultats = []
    for loc_id in lieux:
        try:
            resultats.extend(appel(f"/locations/{loc_id}/latest")["results"])
        except (requests.RequestException, RuntimeError) as e:
            print(f"  station {loc_id} ignoree : {e}")
    snapshot = {"collected_at": maintenant.isoformat(), "results": resultats}
    key = maintenant.strftime("pollution/openaq/flux/year=%Y/month=%m/day=%d/snapshot_%Y%m%dT%H%M%S.json")
    datalake.put_json("bronze", key, snapshot)
    # vitesse : les mesures nettoyees partent tout de suite dans ClickHouse
    n = olap.inserer("pollution", nettoyer_mesures(lignes_flux(snapshot, {c["sensor_id"]: c for c in capteurs})))
    print(f"{maintenant:%H:%M:%S} UTC  {len(resultats)} mesures recues de {len(lieux)} stations, "
          f"{n} envoyees a ClickHouse")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--historique", type=int, metavar="ANNEES", help="recuperer les N dernieres annees puis s'arreter")
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
