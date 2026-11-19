"""Partie 1 - etape 3 : analyses meteo (silver -> gold) et reponses aux questions metier.

Q1 Periodes meteorologiques anormales
Q2 Correlation entre conditions meteo et visibilite
Q3 Evolution saisonniere de la temperature (France et grandes villes)
Q4 Jours aux conditions extremes

Lancer : python -m urbanhub.meteo.analyser
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from urbanhub import datalake
from urbanhub.rapport import sauver_figure, sauver_table, titre

P = "meteo"
VARIABLES = ["temperature", "wind_speed", "pressure", "precipitation", "visibility"]


def charger():
    """Charge silver annee par annee et fabrique :
    - un tableau journalier par station (petit, pour la plupart des analyses)
    - un echantillon horaire (10 %) pour les correlations
    """
    journaliers, echantillons = [], []
    annees = sorted({k.split("year=")[1].split("/")[0] for k in datalake.lister("silver", "meteo/year=")})
    for annee in annees:
        df = datalake.get_parquet("silver", f"meteo/year={annee}/meteo.parquet")
        df["date"] = df["timestamp"].dt.tz_convert("Europe/Paris").dt.tz_localize(None).dt.normalize()
        g = df.groupby(["station_id", "date"])
        j = g.agg(
            city=("city", "first"),
            n_obs=("temperature", "count"),
            temp_mean=("temperature", "mean"),
            temp_min=("temperature", "min"),
            temp_max=("temperature", "max"),
            wind_mean=("wind_speed", "mean"),
            wind_max=("wind_speed", "max"),
            pressure_mean=("pressure", "mean"),
            visibility_mean=("visibility", "mean"),
            precip_mm=("precipitation", "mean"),
        ).reset_index()
        j["precip_mm"] = j["precip_mm"] * 24  # moyenne horaire -> cumul du jour
        j = j[j["n_obs"] >= 12]  # un jour avec moins de 12 heures mesurees n'est pas fiable
        journaliers.append(j)
        echantillons.append(df[VARIABLES].sample(frac=0.1, random_state=0))
        print(f"  {annee} charge")
    return pd.concat(journaliers, ignore_index=True), pd.concat(echantillons, ignore_index=True)


def periodes(masque):
    """Transforme une serie de jours vrai/faux en periodes consecutives (debut, fin, duree)."""
    groupes = (masque != masque.shift()).cumsum()
    res = []
    for _, bloc in masque.groupby(groupes):
        if bloc.iloc[0]:
            res.append((bloc.index[0], bloc.index[-1], len(bloc)))
    return res


def q1_anomalies(jour):
    titre("Q1 - Periodes meteorologiques anormales")
    france = jour.groupby("date").agg(temp=("temp_mean", "mean"), pluie=("precip_mm", "mean"))
    france = france.asfreq("D")

    # "normale" de saison = moyenne du meme jour de l'annee sur toutes les annees, lissee sur 15 jours
    jdo = france.index.day_of_year
    normale = france["temp"].groupby(jdo).mean()
    normale = pd.concat([normale.iloc[-7:], normale, normale.iloc[:7]]).rolling(15, center=True).mean().iloc[7:-7]
    france["normale"] = normale.reindex(jdo).values
    france["anomalie"] = france["temp"] - france["normale"]
    france["z"] = france["anomalie"] / france["anomalie"].std()

    # pluie : cumul sur 30 jours compare a la moyenne
    cumul = france["pluie"].rolling(30, min_periods=20).sum()
    france["z_pluie_30j"] = (cumul - cumul.mean()) / cumul.std()

    lignes = []
    for nom, masque in [
        ("vague de chaleur", france["z"] > 1.5),
        ("vague de froid", france["z"] < -1.5),
        ("periode tres seche", france["z_pluie_30j"] < -1.5),
        ("periode tres humide", france["z_pluie_30j"] > 1.5),
    ]:
        for debut, fin, duree in periodes(masque.fillna(False)):
            if duree >= 3:
                bloc = france.loc[debut:fin]
                lignes.append({"type": nom, "debut": debut.date(), "fin": fin.date(), "duree_jours": duree,
                               "ecart_temp_moyen": round(bloc["anomalie"].mean(), 1)})
    res = pd.DataFrame(lignes).sort_values("debut") if lignes else pd.DataFrame(lignes)
    sauver_table(res, P, "q1_periodes_anormales")
    if not res.empty:
        print(res.groupby("type")["duree_jours"].agg(["count", "sum"]).rename(columns={"count": "nb_periodes", "sum": "nb_jours"}))

    fig, ax = plt.subplots()
    couleurs = np.where(france["z"] > 1.5, "tab:red", np.where(france["z"] < -1.5, "tab:blue", "lightgray"))
    ax.bar(france.index, france["anomalie"], color=couleurs, width=1)
    ax.set_title("Ecart de temperature a la normale de saison (France). Rouge = anormalement chaud, bleu = froid")
    ax.set_ylabel("ecart (degres C)")
    sauver_figure(fig, P, "q1_anomalies_temperature")


def q2_visibilite(echant):
    titre("Q2 - Meteo et visibilite")
    corr = echant.corr(method="spearman")
    print(corr["visibility"].drop("visibility").round(2).to_string())
    sauver_table(corr.round(3).reset_index(names="variable"), P, "q2_correlations")

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    im = axes[0].imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    axes[0].set_xticks(range(len(corr)), corr.columns, rotation=45)
    axes[0].set_yticks(range(len(corr)), corr.columns)
    for i in range(len(corr)):
        for k in range(len(corr)):
            axes[0].text(k, i, f"{corr.iloc[i, k]:.2f}", ha="center", va="center", fontsize=8)
    axes[0].set_title("Correlations (Spearman)")
    axes[0].grid(False)
    fig.colorbar(im, ax=axes[0])

    classes = pd.cut(echant["precipitation"].fillna(0), [-0.01, 0, 1, 4, 100],
                     labels=["pas de pluie", "faible", "moderee", "forte"])
    echant.groupby(classes, observed=True)["visibility"].median().plot.bar(ax=axes[1], color="tab:cyan")
    axes[1].set_title("Visibilite mediane selon la pluie")
    axes[1].set_ylabel("km")
    axes[1].set_xlabel("")
    sauver_figure(fig, P, "q2_visibilite")


def q3_saisons(jour):
    titre("Q3 - Evolution saisonniere de la temperature")
    jour = jour.copy()
    jour["mois"] = jour["date"].dt.to_period("M").dt.to_timestamp()
    villes = jour.dropna(subset=["city"])

    mensuel = villes.groupby(["city", "mois"])["temp_mean"].mean().unstack(0)
    france = jour.groupby("mois")["temp_mean"].mean()
    profil = villes.groupby(["city", villes["date"].dt.month])["temp_mean"].mean().unstack(0)
    profil.index.name = "mois_calendaire"
    sauver_table(profil.round(1).reset_index(), P, "q3_profil_saisonnier_villes")

    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    mensuel.plot(ax=axes[0], lw=1)
    france.plot(ax=axes[0], color="black", lw=2.5, label="France (moyenne)")
    axes[0].set_title("Temperature moyenne mensuelle")
    axes[0].set_ylabel("degres C")
    axes[0].legend(fontsize=7, ncol=2)
    profil.plot(ax=axes[1], marker="o")
    axes[1].set_xticks(range(1, 13))
    axes[1].set_title("Cycle saisonnier moyen par ville")
    axes[1].legend(fontsize=7, ncol=2)
    sauver_figure(fig, P, "q3_saisons")

    ete_hiver = profil.loc[[7, 8]].mean() - profil.loc[[12, 1]].mean()
    print("Ecart ete / hiver par ville (degres) :")
    print(ete_hiver.sort_values(ascending=False).round(1).to_string())


def q4_extremes(jour):
    titre("Q4 - Jours aux conditions extremes")
    j = jour.copy()
    regles = {
        "chaleur (max >= 35 C)": j["temp_max"] >= 35,
        "gel fort (min <= -10 C)": j["temp_min"] <= -10,
        "vent fort (>= 72 km/h)": j["wind_max"] >= 20,
        "pluie forte (>= 50 mm)": j["precip_mm"] >= 50,
        "brouillard (visi < 1 km)": j["visibility_mean"] < 1,
    }
    for nom, m in regles.items():
        j[nom] = m

    par_jour = j.groupby("date")[list(regles)].sum()
    par_jour["stations_mesurees"] = j.groupby("date")["station_id"].nunique()
    par_jour["stations_en_extreme"] = j.assign(x=j[list(regles)].any(axis=1)).groupby("date")["x"].sum()
    par_jour["part_stations"] = par_jour["stations_en_extreme"] / par_jour["stations_mesurees"]
    top = par_jour.sort_values("part_stations", ascending=False).head(20).reset_index()
    top["type_principal"] = top[list(regles)].idxmax(axis=1)
    top["date"] = top["date"].dt.date
    sauver_table(top[["date", "type_principal", "stations_en_extreme", "stations_mesurees", "part_stations"] + list(regles)],
                 P, "q4_jours_extremes")
    print(top[["date", "type_principal", "part_stations"]].head(10).to_string(index=False))

    fig, ax = plt.subplots()
    par_jour[list(regles)].resample("ME").sum().plot.area(ax=ax, stacked=True, alpha=0.8)
    ax.set_title("Nombre de 'station-jours' extremes par mois")
    ax.set_ylabel("station-jours")
    sauver_figure(fig, P, "q4_extremes_par_mois")


def main():
    titre("Chargement des donnees meteo (silver)")
    jour, echant = charger()
    if jour.empty:
        print("Pas de donnees. Lancer d'abord le telechargement puis le nettoyage.")
        return
    datalake.put_parquet("gold", f"{P}/meteo_journaliere.parquet", jour)
    q1_anomalies(jour)
    q2_visibilite(echant)
    q3_saisons(jour)
    q4_extremes(jour)
    print("\nPartie 1 terminee. Graphiques dans rapports/figures")


if __name__ == "__main__":
    main()
