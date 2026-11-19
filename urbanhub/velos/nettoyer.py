"""Partie 2 - etape 2 : nettoyage des photos de stations (bronze -> silver).

Pour chaque jour collecte, on lit toutes les photos et on produit un fichier Parquet :
  silver/velos/date=2026-11-19/velos.parquet

Variables gardees : station_id, station_name, latitude, longitude, timestamp,
bikes_available, free_slots (+ city, network_id, collected_at, capacity, fill_rate)

Lancer : python -m urbanhub.velos.nettoyer
Option : --jour 2026-11-19 (un seul jour)
"""
import argparse
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from urbanhub import datalake

PREFIXE = "velos/citybikes/"


def lignes_snapshot(key):
    snap = datalake.get_json("bronze", key)
    lignes = []
    for reseau in snap["networks"]:
        for s in reseau["stations"]:
            lignes.append({
                "collected_at": snap["collected_at"],
                "city": reseau["city"],
                "network_id": reseau["id"],
                "station_id": s.get("id"),
                "station_name": s.get("name"),
                "latitude": s.get("latitude"),
                "longitude": s.get("longitude"),
                "timestamp": s.get("timestamp"),
                "bikes_available": s.get("free_bikes"),
                "free_slots": s.get("empty_slots"),
            })
    return lignes


def nettoyer_jour(prefixe_jour):
    keys = [k for k in datalake.lister("bronze", prefixe_jour) if k.endswith(".json")]
    with ThreadPoolExecutor(max_workers=16) as pool:
        lignes = [l for morceau in pool.map(lignes_snapshot, keys) for l in morceau]
    df = pd.DataFrame(lignes)
    if df.empty:
        return df

    df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True).dt.floor("min")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce", format="ISO8601")
    for c in ["latitude", "longitude", "bikes_available", "free_slots"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # lignes inutilisables : sans identifiant ou sans position
    df = df.dropna(subset=["station_id", "latitude", "longitude"])
    # valeurs negatives = erreur de l'API
    df.loc[df["bikes_available"] < 0, "bikes_available"] = None
    df.loc[df["free_slots"] < 0, "free_slots"] = None
    # une station absente du releve (free_slots vide) : on ne peut pas calculer son taux
    df["capacity"] = df["bikes_available"] + df["free_slots"]
    df["fill_rate"] = (df["bikes_available"] / df["capacity"]).where(df["capacity"] > 0)
    df = df.drop_duplicates(["station_id", "collected_at"])

    df["station_id"] = df["station_id"].astype(str)
    for c in ["bikes_available", "free_slots", "capacity"]:
        df[c] = df[c].astype("Int16")
    return df


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--jour", help="AAAA-MM-JJ, sinon tous les jours")
    args = p.parse_args()

    jours = sorted({k.rsplit("/", 1)[0] + "/" for k in datalake.lister("bronze", PREFIXE)})
    if args.jour:
        a, m, j = args.jour.split("-")
        jours = [d for d in jours if d.endswith(f"year={a}/month={m}/day={j}/")]
    if not jours:
        print("Aucune collecte trouvee. Lancer d'abord : python -m urbanhub.velos.collecter")
        return

    for prefixe_jour in jours:
        df = nettoyer_jour(prefixe_jour)
        if df.empty:
            continue
        date = df["collected_at"].dt.date.min().isoformat()
        datalake.put_parquet("silver", f"velos/date={date}/velos.parquet", df)
        print(f"  {date} : {df['collected_at'].nunique()} collectes, {df['station_id'].nunique()} stations, {len(df):,} lignes")


if __name__ == "__main__":
    main()
