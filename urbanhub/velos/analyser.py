"""Partie 2 - etape 3 : analyses de la mobilite a velo (silver -> gold).

Idee centrale : entre deux photos (2-3 min d'ecart), si le nombre de velos d'une
station change, c'est que des velos ont ete pris ou deposes. On appelle ca des
"mouvements". C'est notre mesure de l'utilisation.

Q1 Stations au plus fort taux d'utilisation
Q2 Zones ou l'offre de velos est insuffisante
Q3 Pics d'utilisation dans la journee
Q4 Desequilibres geographiques (centre / peripherie, matin / soir)
Q5 Stations critiques a reequilibrer

Lancer : python -m urbanhub.velos.analyser
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from urbanhub import datalake
from urbanhub.rapport import sauver_figure, sauver_table, titre
from urbanhub.villes import VILLES, distance_km

P = "velos"
COLONNES = ["collected_at", "city", "station_id", "station_name", "latitude", "longitude",
            "bikes_available", "free_slots", "capacity", "fill_rate"]


def charger():
    df = datalake.lire_parquets("silver", "velos/", columns=COLONNES)
    if df.empty:
        return df
    for c in ["bikes_available", "free_slots", "capacity"]:
        df[c] = df[c].astype("float32")
    # certains reseaux renvoient toujours 0 velo (donnee non publiee par l'operateur) : inutilisables
    max_ville = df.groupby("city")["bikes_available"].max()
    exclues = list(max_ville[~(max_ville > 0)].index)
    if exclues:
        print("Villes ignorees (l'API ne donne pas le nombre de velos) :", ", ".join(exclues))
        df = df[~df["city"].isin(exclues)]
    df["city"] = df["city"].astype("category")
    df["city"] = df["city"].cat.remove_unused_categories()
    df = df.sort_values(["station_id", "collected_at"]).reset_index(drop=True)

    g = df.groupby("station_id", sort=False)
    delta = g["bikes_available"].diff()
    trou = g["collected_at"].diff() > pd.Timedelta(minutes=15)  # collecte interrompue : on ne compte pas
    delta[trou] = float("nan")
    df["mouvements"] = delta.abs()
    df["heure_locale"] = df["collected_at"].dt.tz_convert("Europe/Paris")
    df["heure"] = df["heure_locale"].dt.hour
    df["vide"] = df["bikes_available"] == 0
    df["plein"] = df["free_slots"] == 0
    return df


def jours_collectes(df):
    return max((df["collected_at"].max() - df["collected_at"].min()) / pd.Timedelta(days=1), 1 / 24)


def stats_stations(df):
    """Un resume par station, reutilise par plusieurs questions."""
    s = df.groupby("station_id").agg(
        city=("city", "first"), station_name=("station_name", "last"),
        latitude=("latitude", "median"), longitude=("longitude", "median"),
        capacity=("capacity", "median"), mouvements=("mouvements", "sum"),
        taux_remplissage=("fill_rate", "mean"), part_temps_vide=("vide", "mean"),
        part_temps_plein=("plein", "mean"),
    ).reset_index()
    s["rotations_par_jour"] = s["mouvements"] / s["capacity"].where(s["capacity"] > 0) / jours_collectes(df)
    s["dist_centre_km"] = [distance_km(la, lo, *VILLES[c]) if c in VILLES else None
                           for la, lo, c in zip(s["latitude"], s["longitude"], s["city"])]
    return s


def q1_utilisation(s):
    titre("Q1 - Stations les plus utilisees")
    top = s[s["capacity"] >= 5].sort_values("rotations_par_jour", ascending=False).head(20)
    sauver_table(top[["city", "station_name", "capacity", "mouvements", "rotations_par_jour"]].round(2), P, "q1_top_stations")
    print(top[["city", "station_name", "rotations_par_jour"]].head(10).round(2).to_string(index=False))

    fig, ax = plt.subplots(figsize=(11, 7))
    etiquettes = top["station_name"].str.slice(0, 35) + " (" + top["city"].astype(str) + ")"
    ax.barh(etiquettes[::-1], top["rotations_par_jour"][::-1], color="tab:green")
    ax.set_title("Top 20 stations : rotations par point d'attache et par jour")
    ax.set_xlabel("mouvements / capacite / jour")
    sauver_figure(fig, P, "q1_top_stations")


def q2_offre_insuffisante(s):
    titre("Q2 - Zones avec une offre insuffisante")
    z = s.copy()
    # decoupage en carres d'environ 500 m
    z["zone_lat"] = (z["latitude"] / 0.005).round() * 0.005
    z["zone_lon"] = (z["longitude"] / 0.005).round() * 0.005
    zones = z.groupby(["city", "zone_lat", "zone_lon"], observed=True).agg(
        nb_stations=("station_id", "count"), part_temps_vide=("part_temps_vide", "mean"),
        taux_remplissage=("taux_remplissage", "mean")).reset_index()
    insuffisantes = zones[zones["part_temps_vide"] >= 0.25].sort_values("part_temps_vide", ascending=False)
    sauver_table(insuffisantes.round(3), P, "q2_zones_insuffisantes")
    print(f"{len(insuffisantes)} zones de 500 m ou les stations sont vides plus de 25 % du temps")
    print(insuffisantes.groupby("city", observed=True).size().sort_values(ascending=False).to_string())

    villes = s["city"].value_counts().head(4).index
    fig, axes = plt.subplots(1, len(villes), figsize=(5 * len(villes), 5))
    axes = np.atleast_1d(axes)
    for ax, v in zip(axes, villes):
        d = s[s["city"] == v]
        pts = ax.scatter(d["longitude"], d["latitude"], c=d["part_temps_vide"], cmap="Reds", s=12, vmin=0, vmax=0.6)
        ax.set_title(f"{v} : part du temps sans velo")
        ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(pts, ax=axes, shrink=0.8)
    sauver_figure(fig, P, "q2_carte_stations_vides")


def q3_pics(df):
    titre("Q3 - Pics d'utilisation dans la journee")
    df = df.assign(weekend=df["heure_locale"].dt.day_of_week >= 5)
    par_heure = df.groupby(["city", "heure"], observed=True)["mouvements"].sum().unstack(0)
    part = par_heure / par_heure.sum() * 100  # en % des mouvements de la journee
    part = part.loc[:, part.notna().any()]  # villes sans aucun mouvement encore : ignorees
    pics = part.idxmax().rename("heure_de_pointe").reset_index()
    sauver_table(pics, P, "q3_heure_de_pointe")
    print(pics.to_string(index=False))

    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    part.plot(ax=axes[0], marker=".")
    axes[0].set_title("Repartition des mouvements selon l'heure (% de la journee)")
    axes[0].set_xticks(range(24))
    axes[0].legend(fontsize=7, ncol=2)
    sem = df.groupby(["weekend", "heure"])["mouvements"].sum().unstack(0)
    sem = sem / sem.sum() * 100
    sem.columns = ["semaine" if not c else "week-end" for c in sem.columns]
    sem.plot(ax=axes[1], marker=".")
    axes[1].set_title("Toutes villes : semaine contre week-end")
    axes[1].set_xticks(range(24))
    sauver_figure(fig, P, "q3_pics_journaliers")


def q4_desequilibres(df, s):
    titre("Q4 - Desequilibres geographiques")
    bandes = pd.cut(s["dist_centre_km"], [0, 2, 4, 6, 10, 50], labels=["0-2 km", "2-4", "4-6", "6-10", "+10"])
    s = s.assign(bande=bandes)
    remplissage = s.groupby(["city", "bande"], observed=True)["taux_remplissage"].mean().unstack(1)
    sauver_table(remplissage.round(3).reset_index(), P, "q4_remplissage_par_distance")
    print("Taux de remplissage moyen selon la distance au centre :")
    print(remplissage.round(2).to_string())

    # matin (7h-10h) contre soir (17h-20h) : effet des trajets domicile-travail
    df = df.assign(bande=df["station_id"].map(s.set_index("station_id")["bande"]))
    moment = pd.cut(df["heure"], [6, 10, 16, 20], labels=["matin 7-10h", "apres-midi", "soir 17-20h"])
    ms = df.groupby([moment, "bande"], observed=True)["fill_rate"].mean().unstack(0)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    remplissage.T.plot(ax=axes[0], marker="o")
    axes[0].set_title("Taux de remplissage selon la distance au centre")
    axes[0].set_ylabel("velos / places")
    axes[0].legend(fontsize=7, ncol=2)
    moments = [m for m in ["matin 7-10h", "soir 17-20h"] if m in ms.columns]  # selon les heures deja collectees
    if moments:
        ms[moments].plot.bar(ax=axes[1])
    axes[1].set_title("Matin contre soir (toutes villes)")
    axes[1].set_xlabel("distance au centre")
    sauver_figure(fig, P, "q4_desequilibres")


def q5_critiques(df, s):
    titre("Q5 - Stations critiques a reequilibrer")
    dernier = df.sort_values("collected_at").groupby("station_id").tail(1)
    etat = dernier.set_index("station_id")[["bikes_available", "free_slots", "collected_at"]]
    s = s.join(etat, on="station_id")
    s["action"] = None
    s.loc[(s["part_temps_vide"] >= 0.3) | (s["bikes_available"] <= 1), "action"] = "a remplir"
    s.loc[(s["part_temps_plein"] >= 0.3) | (s["free_slots"] <= 1), "action"] = "a vider"
    s["urgence"] = s[["part_temps_vide", "part_temps_plein"]].max(axis=1)
    crit = s[s["action"].notna() & (s["capacity"] >= 5)].sort_values("urgence", ascending=False)
    cols = ["city", "station_name", "action", "bikes_available", "free_slots", "capacity",
            "part_temps_vide", "part_temps_plein", "latitude", "longitude"]
    sauver_table(crit[cols].round(3), P, "q5_stations_critiques")
    print(crit.groupby(["city", "action"], observed=True).size().unstack(fill_value=0).to_string())

    fig, ax = plt.subplots(figsize=(8, 7))
    paris = s[s["city"] == s["city"].value_counts().index[0]]
    ax.scatter(paris["longitude"], paris["latitude"], s=6, color="lightgray", label="normale")
    for action, couleur in [("a remplir", "tab:red"), ("a vider", "tab:blue")]:
        d = paris[paris["action"] == action]
        ax.scatter(d["longitude"], d["latitude"], s=14, color=couleur, label=action)
    ax.set_title(f"{paris['city'].iloc[0]} : stations critiques")
    ax.legend()
    ax.set_xticks([]); ax.set_yticks([])
    sauver_figure(fig, P, "q5_stations_critiques")


def main():
    titre("Chargement des donnees velos (silver)")
    df = charger()
    if df.empty:
        print("Pas de donnees. Lancer la collecte puis le nettoyage.")
        return
    print(f"{df['collected_at'].nunique()} collectes sur {jours_collectes(df):.1f} jours, {df['station_id'].nunique()} stations")
    s = stats_stations(df)
    sauver_table(s.round(4), P, "stations_resume")
    q1_utilisation(s)
    q2_offre_insuffisante(s)
    q3_pics(df)
    q4_desequilibres(df, s)
    q5_critiques(df, s)
    print("\nPartie 2 terminee. Graphiques dans rapports/figures")


if __name__ == "__main__":
    main()
