"""Partie 2 - etape 2 : nettoyage des donnees velos (bronze -> silver).

Deux sources arrivent dans bronze :
- les photos du collecteur (toutes les 3 min, depuis son lancement)
- l'historique CityBikes (un changement d'etat par ligne, depuis novembre 2024)

On produit deux tables dans silver :

1. silver/velos/date=2026-11-19/velos.parquet
   les photos du collecteur, une ligne par station et par collecte
   (station_id, station_name, latitude, longitude, collected_at, bikes_available,
   free_slots, capacity, fill_rate, city, network_id). Sert au temps reel.

2. silver/velos_horaire/month=2025-03/network=velib.parquet
   une ligne par station et par heure, historique et collecte reunis :
   velos et places moyens, taux de remplissage, part du temps ou la station est
   vide ou pleine, et "mouvements" (velos pris ou rendus pendant l'heure).
   C'est la table utilisee par les analyses.

Lancer : python -m urbanhub.velos.nettoyer
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import numpy as np
import pandas as pd

from urbanhub import datalake
from urbanhub.velos.historique import RESEAUX

PREFIXE = "velos/citybikes/"
PREFIXE_HISTO = "velos/citybikes_historique/"


# ---------- photos du collecteur ----------

def lignes_snapshot(snap):
    """Une photo (reponse brute de l'API) -> une ligne par station."""
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
                "bikes_available": s.get("free_bikes"),
                "free_slots": s.get("empty_slots"),
            })
    return lignes


def nettoyer_snapshots(snaps):
    """Regles de nettoyage, utilisees par le nettoyage du jour ET par le collecteur (temps reel)."""
    df = pd.DataFrame([l for snap in snaps for l in lignes_snapshot(snap)])
    if df.empty:
        return df

    df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True).dt.floor("min")
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


def nettoyer_jour(prefixe_jour):
    keys = [k for k in datalake.lister("bronze", prefixe_jour) if k.endswith(".json")]
    with ThreadPoolExecutor(max_workers=16) as pool:
        return nettoyer_snapshots(list(pool.map(lambda k: datalake.get_json("bronze", k), keys)))


def photos_vers_silver():
    """Photos du collecteur -> silver/velos/date=.../ . Seuls les jours nouveaux, hier et
    aujourd'hui sont retraites (les jours plus anciens ne changent plus)."""
    jours = sorted({k.rsplit("/", 1)[0] + "/" for k in datalake.lister("bronze", PREFIXE)})
    deja = {k.split("date=")[1][:10] for k in datalake.lister("silver", "velos/date=")}
    recents = {(date.today() - timedelta(days=i)).isoformat() for i in range(2)}
    faits = []
    for prefixe_jour in jours:
        a, m, j = (prefixe_jour.split(x)[1][:n] for x, n in (("year=", 4), ("month=", 2), ("day=", 2)))
        jour = f"{a}-{m}-{j}"
        if jour in deja and jour not in recents:
            continue
        df = nettoyer_jour(prefixe_jour)
        if df.empty:
            continue
        datalake.put_parquet("silver", f"velos/date={jour}/velos.parquet", df)
        faits.append(jour)
        print(f"  photos {jour} : {df['collected_at'].nunique()} collectes, {df['station_id'].nunique()} stations")
    return faits


# ---------- table station x heure ----------

def vers_horaire(ev, city, network):
    """Etats successifs des stations -> une ligne par station et par heure.

    ev : station_id, station_name, latitude, longitude, timestamp, bikes, free
    (un changement d'etat de l'historique, ou une photo du collecteur).
    On reconstitue l'etat de chaque station tous les quarts d'heure (dernier etat connu),
    puis on fait la moyenne par heure. Les mouvements sont les variations du nombre de velos.
    Calcul en tableaux numpy (temps x stations) pour aller vite sur des millions de lignes.
    """
    ev = ev.dropna(subset=["station_id", "timestamp", "bikes"])
    if ev.empty:
        return pd.DataFrame()
    codes, ids = pd.factorize(ev["station_id"])
    ev = ev.assign(sid=codes).sort_values(["sid", "timestamp"])
    sid = ev["sid"].to_numpy()
    velos_ev = ev["bikes"].to_numpy(dtype="float64")
    places_ev = ev["free"].to_numpy(dtype="float64")

    # mouvements : variation du nombre de velos entre deux etats d'une meme station
    mouv = np.abs(np.diff(velos_ev, prepend=np.nan))
    mouv[np.r_[True, sid[1:] != sid[:-1]]] = np.nan
    heure_ev = ev["timestamp"].dt.floor("h")
    mouvements = pd.Series(mouv).groupby([heure_ev.to_numpy(), sid]).sum()

    # etat de chaque station a la fin de chaque quart d'heure
    q = ev["timestamp"].dt.floor("15min")
    q0, pas = q.min(), pd.Timedelta(minutes=15)
    iq = ((q - q0) // pas).to_numpy()
    garder = np.r_[(iq[1:] != iq[:-1]) | (sid[1:] != sid[:-1]), True]  # dernier etat du quart
    nq, ns = iq.max() + 1, len(ids)
    quarts = pd.date_range(q0, periods=nq, freq="15min")

    def matrice(valeurs):
        m = np.full((nq, ns), np.nan)
        m[iq[garder], sid[garder]] = valeurs[garder]
        return pd.DataFrame(m, index=quarts).ffill()

    velos, places = matrice(velos_ev), matrice(places_ev)
    capacite = velos + places
    heures = quarts.floor("h")

    def par_heure(x):
        return x.groupby(heures).mean().stack()

    h = pd.DataFrame({
        "velos": par_heure(velos),
        "places": par_heure(places),
        "capacite": par_heure(capacite),
        "remplissage": par_heure(velos / capacite.where(capacite > 0)),
        "part_vide": par_heure((velos == 0).astype("float64").where(velos.notna())),
        "part_plein": par_heure((places == 0).astype("float64").where(places.notna())),
    })
    h.index.names = ["heure", "sid"]
    mouvements.index.names = ["heure", "sid"]
    h = h.join(mouvements.rename("mouvements")).reset_index()
    h["mouvements"] = h["mouvements"].fillna(0)

    meta = ev.groupby("sid")[["station_name", "latitude", "longitude"]].last()
    h = h.join(meta, on="sid")
    h.insert(0, "station_id", ids[h.pop("sid").to_numpy()].astype(str))
    h.insert(0, "network_id", network)
    h.insert(0, "city", city)
    for c in ["velos", "places", "capacite", "mouvements", "remplissage", "part_vide", "part_plein"]:
        h[c] = h[c].astype("float32")
    return h


def lire_historique(key):
    d = datalake.get_parquet("bronze", key, columns=["id", "name", "latitude", "longitude", "bikes", "free", "timestamp"])
    d = d.rename(columns={"id": "station_id", "name": "station_name"})
    ts = pd.to_datetime(d["timestamp"])
    d["timestamp"] = ts.dt.tz_localize("UTC") if ts.dt.tz is None else ts.dt.tz_convert("UTC")
    d.loc[d["bikes"] < 0, "bikes"] = np.nan
    d.loc[d["free"] < 0, "free"] = np.nan
    return d


def cle_horaire(mois, reseau):
    return f"velos_horaire/month={mois}/network={reseau}.parquet"


def historique_vers_horaire():
    """Historique CityBikes -> table horaire. Un mois deja traite n'est pas refait (l'archive ne change plus)."""
    faits = set()
    for key in sorted(datalake.lister("bronze", PREFIXE_HISTO)):
        reseau = key.split("network=")[1].split("/")[0]
        mois = f"{key.split('year=')[1][:4]}-{key.split('month=')[1][:2]}"
        faits.add((mois, reseau))
        if datalake.existe("silver", cle_horaire(mois, reseau)):
            continue
        h = vers_horaire(lire_historique(key), RESEAUX.get(reseau, reseau), reseau)
        if h.empty:
            continue
        datalake.put_parquet("silver", cle_horaire(mois, reseau), h)
        print(f"  historique {reseau} {mois} : {h['station_id'].nunique()} stations, {len(h):,} lignes station-heure")
    return faits


def photos_vers_horaire(deja_dans_historique, jours_modifies):
    """Photos du collecteur -> table horaire, pour les mois que l'historique ne couvre pas encore."""
    jours = sorted(k.split("date=")[1][:10] for k in datalake.lister("silver", "velos/date="))
    mois_a_faire = {j[:7] for j in jours_modifies}
    for mois in sorted({j[:7] for j in jours}):
        cles_existantes = list(datalake.lister("silver", f"velos_horaire/month={mois}/"))
        if mois not in mois_a_faire and cles_existantes:
            continue
        d = pd.concat([datalake.get_parquet("silver", f"velos/date={j}/velos.parquet") for j in jours if j.startswith(mois)])
        d = d.rename(columns={"collected_at": "timestamp", "bikes_available": "bikes", "free_slots": "free"})
        for c in ["bikes", "free"]:
            d[c] = d[c].astype("float64")
        for reseau, morceau in d.groupby("network_id"):
            if (mois, reseau) in deja_dans_historique:
                continue  # l'archive officielle est prioritaire
            h = vers_horaire(morceau, morceau["city"].iloc[0], reseau)
            if not h.empty:
                datalake.put_parquet("silver", cle_horaire(mois, reseau), h)
        print(f"  collecte {mois} : table horaire mise a jour")


def main():
    print("Photos du collecteur")
    jours_modifies = photos_vers_silver()
    print("Historique CityBikes")
    faits = historique_vers_horaire()
    print("Table horaire de la collecte")
    photos_vers_horaire(faits, jours_modifies)


if __name__ == "__main__":
    main()
