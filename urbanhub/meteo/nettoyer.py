"""Partie 1 - etape 2 : nettoyage des fichiers NOAA (bronze -> silver).

Les fichiers NOAA sont codes. Exemple de colonne TMP : "+0123,1"
  -> 0123 = temperature en dixiemes de degre, donc 12.3 degres
  -> 1    = code qualite de la mesure
  -> +9999 veut dire "valeur manquante"

Nettoyages faits ici
- decodage des colonnes et conversion des unites (dixiemes -> vraies unites, m -> km, m/s -> km/h)
- valeurs manquantes (9999, 99999...) remplacees par du vide
- mesures marquees "douteuses" ou "fausses" par la NOAA supprimees
- valeurs impossibles supprimees (ex : 70 degres)
- timestamp converti en date UTC et arrondi a l'heure (une ligne par station et par heure)
- petits trous (3 h max) combles par interpolation pour la temperature et la pression

Lancer : python -m urbanhub.meteo.nettoyer
"""
import argparse
import io
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from tqdm import tqdm

from urbanhub import datalake
from urbanhub.villes import ville_proche

COLONNES = ["STATION", "DATE", "LATITUDE", "LONGITUDE", "NAME", "WND", "TMP", "SLP", "VIS", "AA1"]
QUALITE_MAUVAISE = {"2", "3", "6", "7"}  # codes NOAA : douteux / faux

# bornes physiques acceptees
BORNES = {
    "temperature": (-40, 50),       # degres C
    "wind_speed": (0, 75),          # m/s
    "pressure": (900, 1080),        # hPa
    "visibility": (0, 100),         # km
    "precipitation": (0, 100),      # mm par heure
}


def champ(serie, i):
    return serie.astype("string").str.split(",").str[i]


def valeur(serie, i_val, i_qual, manquant, echelle):
    """Extrait une valeur numerique d'une colonne codee NOAA."""
    v = pd.to_numeric(champ(serie, i_val), errors="coerce")
    q = champ(serie, i_qual)
    v = v.where((v != manquant) & ~q.isin(QUALITE_MAUVAISE))
    return v / echelle


def nettoyer_fichier(contenu):
    df = pd.read_csv(io.BytesIO(contenu), dtype=str, usecols=lambda c: c in COLONNES)
    df = df.reindex(columns=COLONNES)
    if df.empty:
        return None

    # precipitations : AA1 = "periode_en_heures,hauteur_en_dixiemes_mm,condition,qualite"
    periode = pd.to_numeric(champ(df["AA1"], 0), errors="coerce")
    hauteur = valeur(df["AA1"], 1, 3, 9999, 10)
    precip = (hauteur / periode.where((periode > 0) & (periode < 99)))  # ramene en mm par heure

    out = pd.DataFrame({
        "station_id": df["STATION"].str.zfill(11),
        "timestamp": pd.to_datetime(df["DATE"], utc=True, errors="coerce").dt.floor("h"),
        "temperature": valeur(df["TMP"], 0, 1, 9999, 10),
        "wind_direction": valeur(df["WND"], 0, 1, 999, 1),
        "wind_speed": valeur(df["WND"], 3, 4, 9999, 10),
        "pressure": valeur(df["SLP"], 0, 1, 99999, 10),
        "visibility": valeur(df["VIS"], 0, 1, 999999, 1000),
        "precipitation": precip,
    })
    out = out.dropna(subset=["timestamp"])
    for col, (bas, haut) in BORNES.items():
        out[col] = out[col].where(out[col].between(bas, haut))

    # plusieurs releves dans la meme heure -> une seule ligne (moyenne)
    agg = {c: "mean" for c in BORNES}
    agg["wind_direction"] = "first"  # on ne fait pas la moyenne d'un angle
    out = out.groupby(["station_id", "timestamp"], as_index=False).agg(agg)
    if out.empty:
        return None

    # grille horaire complete, puis on comble les trous de 3 h maximum
    out = out.set_index("timestamp").sort_index()
    station = out["station_id"].iloc[0]
    out = out.drop(columns="station_id").asfreq("h")
    for col in ["temperature", "pressure"]:
        out[col] = out[col].interpolate(method="time", limit=3, limit_area="inside")
    out = out.dropna(how="all", subset=list(BORNES)).reset_index()

    out["wind_speed_kmh"] = out["wind_speed"] * 3.6
    out["station_id"] = station
    out["station_name"] = df["NAME"].dropna().iloc[0] if df["NAME"].notna().any() else None
    lat = pd.to_numeric(df["LATITUDE"], errors="coerce").median()
    lon = pd.to_numeric(df["LONGITUDE"], errors="coerce").median()
    out["latitude"], out["longitude"] = lat, lon
    out["city"] = ville_proche(lat, lon)

    for col in list(BORNES) + ["wind_direction", "wind_speed_kmh"]:
        out[col] = out[col].astype("float32")
    colonnes = ["station_id", "station_name", "city", "latitude", "longitude", "timestamp",
                "temperature", "wind_speed", "wind_speed_kmh", "wind_direction",
                "pressure", "precipitation", "visibility"]
    return out[colonnes]


def traiter(key):
    try:
        return nettoyer_fichier(datalake.get_bytes("bronze", key))
    except Exception as e:  # un fichier abime ne doit pas bloquer toute l'annee
        print(f"  fichier ignore {key} : {e}")
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workers", type=int, default=8)
    args = p.parse_args()

    annees = sorted({k.split("year=")[1].split("/")[0] for k in datalake.lister("bronze", "meteo/noaa/")})
    if not annees:
        print("Rien dans bronze/meteo/noaa. Lancer d'abord : python -m urbanhub.meteo.telecharger")
        return

    stations = []
    for annee in annees:
        keys = list(datalake.lister("bronze", f"meteo/noaa/year={annee}/"))
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            morceaux = list(tqdm(pool.map(traiter, keys), total=len(keys), desc=f"Nettoyage {annee}"))
        morceaux = [m for m in morceaux if m is not None and not m.empty]
        if not morceaux:
            continue
        df = pd.concat(morceaux, ignore_index=True)
        datalake.put_parquet("silver", f"meteo/year={annee}/meteo.parquet", df)
        stations.append(df[["station_id", "station_name", "city", "latitude", "longitude"]].drop_duplicates("station_id"))
        print(f"  {annee} : {len(df):,} lignes horaires, {df['station_id'].nunique()} stations")

    ref = pd.concat(stations).drop_duplicates("station_id")
    datalake.put_parquet("silver", "meteo/stations.parquet", ref)
    print(f"Silver pret. {len(ref)} stations, dont {ref['city'].notna().sum()} rattachees a une grande ville.")


if __name__ == "__main__":
    main()
