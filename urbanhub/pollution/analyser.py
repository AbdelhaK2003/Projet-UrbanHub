"""Partie 3 - etape 3 : analyses de la pollution (silver -> gold).

Les concentrations des differents polluants ne se comparent pas directement
(30 de NO2 n'est pas aussi grave que 30 de PM2.5). On les compare donc aux
valeurs guides de l'OMS (2021) : un rapport de 2 veut dire "2 fois la valeur conseillee".

Q1 Zones les plus polluees
Q2 Variation de la pollution dans la journee
Q3 Polluants dominants par ville
Q4 Episodes de pollution anormale

Chaque resultat est un tableau range dans gold/pollution/ puis affiche par l'interface.

Lancer : python -m urbanhub.pollution.analyser
"""
import pandas as pd

from urbanhub import datalake
from urbanhub.gold import sauver_table, titre

P = "pollution"
# valeurs guides OMS 2021 en microgrammes par m3 (moyenne sur 24 h, 8 h pour l'ozone)
OMS = {"pm25": 15, "pm10": 45, "no2": 25, "o3": 100, "co": 4000}
FENETRE_H = {"pm25": 24, "pm10": 24, "no2": 24, "o3": 8, "co": 24}
NOMS = {"pm25": "PM2.5", "pm10": "PM10", "no2": "NO2", "o3": "O3", "co": "CO"}


def charger():
    df = datalake.lire_parquets("silver", "pollution/")
    for c in ["city", "pollutant", "location_name"]:
        df[c] = df[c].astype("category")
    df["heure_locale"] = df["timestamp"].dt.tz_convert("Europe/Paris")
    df["date"] = df["heure_locale"].dt.tz_localize(None).dt.normalize()
    df["ratio_oms"] = df["value"] / df["pollutant"].map(OMS).astype(float)
    return df


def series_journalieres(df):
    """Moyenne par ville, polluant et jour : sert aux courbes de tendance et aux jours de depassement."""
    j = df.groupby(["city", "pollutant", "date"], observed=True)["value"].mean().rename("valeur").reset_index()
    j["depasse_oms"] = j["valeur"] > j["pollutant"].map(OMS).astype(float)
    sauver_table(j, P, "pollution_journaliere")
    dep = j.groupby(["city", "pollutant", j["date"].dt.year.rename("annee")], observed=True).agg(
        nb_jours=("valeur", "count"), jours_depassement=("depasse_oms", "sum")).reset_index()
    dep["part_jours_depassement"] = dep["jours_depassement"] / dep["nb_jours"]
    sauver_table(dep, P, "jours_depassement_oms")


def q1_zones(df):
    titre("Q1 - Zones les plus polluees")
    zones = df.groupby(["city", "location_id", "pollutant"], observed=True).agg(
        location_name=("location_name", "first"), latitude=("latitude", "median"),
        longitude=("longitude", "median"), moyenne=("value", "mean"), ratio_oms=("ratio_oms", "mean"),
        nb_heures=("value", "count")).reset_index()
    zones = zones[zones["nb_heures"] >= 24 * 30]  # au moins un mois de mesures
    sauver_table(zones, P, "q1_niveaux_par_zone")
    for pol in ["pm25", "no2"]:
        top = zones[zones["pollutant"] == pol].nlargest(3, "moyenne")
        print(f"{NOMS[pol]} - stations les plus polluees :",
              "; ".join(f"{r.location_name} ({r.city}) {r.moyenne:.1f}" for r in top.itertuples()))


def q2_journee(df):
    titre("Q2 - Variation dans la journee")
    df = df.assign(heure=df["heure_locale"].dt.hour, weekend=df["heure_locale"].dt.day_of_week >= 5)
    profil = df.groupby(["pollutant", "heure"], observed=True)["value"].mean().rename("valeur").reset_index()
    profil["indice"] = profil["valeur"] / profil.groupby("pollutant", observed=True)["valeur"].transform("mean") * 100
    profil["polluant"] = profil["pollutant"].map(NOMS)
    sauver_table(profil, P, "q2_profil_horaire")
    amplitude = profil.groupby("polluant")["indice"].agg(lambda s: s.max() - s.min()).round(0)
    heure_max = profil.loc[profil.groupby("polluant")["indice"].idxmax()].set_index("polluant")["heure"]
    print("Amplitude dans la journee (en % de la moyenne) :", amplitude.to_dict())
    print("Heure du maximum :", heure_max.to_dict())

    sem = df[df["pollutant"] == "no2"].groupby(["weekend", "heure"])["value"].mean().rename("no2").reset_index()
    sem["jour"] = sem.pop("weekend").map({False: "semaine", True: "week-end"})
    sauver_table(sem, P, "q2_no2_semaine_weekend")


def q3_dominants(df):
    titre("Q3 - Polluants dominants")
    ratio = df.groupby(["city", "pollutant"], observed=True)["ratio_oms"].mean().rename("ratio_oms").reset_index()
    ratio["polluant"] = ratio["pollutant"].map(NOMS)
    sauver_table(ratio, P, "q3_ratio_oms_par_ville")
    dominant = ratio.loc[ratio.groupby("city", observed=True)["ratio_oms"].idxmax()]
    dominant = dominant.rename(columns={"polluant": "polluant_dominant"})[["city", "polluant_dominant", "ratio_oms"]]
    sauver_table(dominant, P, "q3_polluants_dominants")
    print(dominant.to_string(index=False))


def q4_episodes(df):
    titre("Q4 - Episodes de pollution anormale")
    ville_heure = df.groupby(["city", "pollutant", "timestamp"], observed=True)["value"].mean()
    episodes = []
    for (ville, pol), s in ville_heure.groupby(level=["city", "pollutant"], observed=True):
        s = s.droplevel([0, 1]).asfreq("h")
        moy = s.rolling(FENETRE_H[pol], min_periods=int(FENETRE_H[pol] * 0.75)).mean()
        # episode = moyenne glissante au-dessus de la valeur guide OMS OU valeur exceptionnelle pour cette ville
        anormal = (moy > OMS[pol]) | (s > s.quantile(0.99))
        groupes = (anormal != anormal.shift()).cumsum()
        for _, bloc in anormal[anormal].groupby(groupes[anormal]):
            if len(bloc) >= 6:  # au moins 6 heures d'affilee
                vals = s.loc[bloc.index[0]:bloc.index[-1]]
                episodes.append({"city": ville, "pollutant": NOMS[pol], "debut": bloc.index[0], "fin": bloc.index[-1],
                                 "duree_h": len(bloc), "pic": vals.max(), "pic_vs_oms": vals.max() / OMS[pol]})
    ep = pd.DataFrame(episodes)
    if ep.empty:
        print("Aucun episode detecte sur la periode")
        return
    ep = ep.sort_values("debut", ascending=False)
    sauver_table(ep, P, "q4_episodes")
    par_mois = ep.groupby([ep["debut"].dt.tz_convert("Europe/Paris").dt.tz_localize(None).dt.to_period("M")
                           .dt.to_timestamp().rename("mois"), "pollutant"]).size().rename("nb_episodes")
    sauver_table(par_mois.reset_index(), P, "q4_episodes_par_mois")
    print(f"{len(ep)} episodes detectes")
    print(ep.groupby(["city", "pollutant"]).size().unstack(fill_value=0).to_string())


def main():
    titre("Chargement des donnees pollution (silver)")
    df = charger()
    if df.empty:
        print("Pas de donnees. Lancer la collecte puis le nettoyage.")
        return
    print(f"{len(df):,} mesures, {df['sensor_id'].nunique()} capteurs, {df['city'].nunique()} villes, "
          f"du {df['timestamp'].min():%Y-%m-%d} au {df['timestamp'].max():%Y-%m-%d}")
    series_journalieres(df)
    q1_zones(df)
    q2_journee(df)
    q3_dominants(df)
    q4_episodes(df)
    print("\nPartie 3 terminee : indicateurs dans gold/pollution/")


if __name__ == "__main__":
    main()
