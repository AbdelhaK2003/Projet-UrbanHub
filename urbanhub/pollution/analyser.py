"""Partie 3 - etape 3 : analyses de la pollution (silver -> gold).

Les concentrations des differents polluants ne se comparent pas directement
(30 de NO2 n'est pas aussi grave que 30 de PM2.5). On les compare donc aux
valeurs guides de l'OMS (2021) : un rapport de 2 veut dire "2 fois la valeur conseillee".

Q1 Zones les plus polluees
Q2 Variation de la pollution dans la journee
Q3 Polluants dominants par ville
Q4 Episodes de pollution anormale

Lancer : python -m urbanhub.pollution.analyser
"""
import pandas as pd
import matplotlib.pyplot as plt

from urbanhub import datalake
from urbanhub.rapport import sauver_figure, sauver_table, titre

P = "pollution"
# valeurs guides OMS 2021 en microgrammes par m3 (moyenne sur 24 h, 8 h pour l'ozone)
OMS = {"pm25": 15, "pm10": 45, "no2": 25, "o3": 100, "co": 4000}
FENETRE_H = {"pm25": 24, "pm10": 24, "no2": 24, "o3": 8, "co": 24}
NOMS = {"pm25": "PM2.5", "pm10": "PM10", "no2": "NO2", "o3": "O3", "co": "CO"}


def charger():
    df = datalake.get_parquet("silver", "pollution/pollution.parquet")
    df["heure_locale"] = df["timestamp"].dt.tz_convert("Europe/Paris")
    df["ratio_oms"] = df["value"] / df["pollutant"].map(OMS)
    return df


def q1_zones(df):
    titre("Q1 - Zones les plus polluees")
    zones = df.groupby(["city", "location_name", "pollutant"])["value"].mean().unstack("pollutant").round(1)
    sauver_table(zones.reset_index(), P, "q1_niveaux_par_zone")

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    for ax, pol in zip(axes, ["pm25", "no2"]):
        if pol not in zones:
            continue
        top = zones[pol].dropna().sort_values(ascending=False).head(15)
        etiquettes = [f"{loc[:28]} ({ville})" for ville, loc in top.index]
        ax.barh(etiquettes[::-1], top.values[::-1], color="tab:brown")
        ax.axvline(OMS[pol], color="red", ls="--", label="valeur guide OMS 24 h")
        ax.set_title(f"{NOMS[pol]} : 15 stations les plus polluees (moyenne)")
        ax.set_xlabel("microgrammes par m3")
        ax.legend()
        print(f"{NOMS[pol]} - zone la plus polluee : {top.index[0][1]} ({top.index[0][0]}) {top.iloc[0]}")
    sauver_figure(fig, P, "q1_zones_polluees")


def q2_journee(df):
    titre("Q2 - Variation dans la journee")
    df = df.assign(heure=df["heure_locale"].dt.hour)
    profil = df.groupby(["pollutant", "heure"])["value"].mean().unstack(0)
    relatif = profil / profil.mean() * 100  # 100 = moyenne de la journee
    sauver_table(profil.round(2).reset_index(), P, "q2_profil_horaire")
    amplitude = (relatif.max() - relatif.min()).round(0)
    print("Amplitude dans la journee (en % de la moyenne) :", amplitude.to_dict())
    print("Heure du maximum :", relatif.idxmax().to_dict())

    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    relatif.rename(columns=NOMS).plot(ax=axes[0], marker=".")
    axes[0].axhline(100, color="black", lw=0.8)
    axes[0].set_title("Profil horaire moyen (100 = moyenne de la journee)")
    axes[0].set_xticks(range(24))
    jour = df.assign(we=df["heure_locale"].dt.day_of_week >= 5)
    no2 = jour[jour["pollutant"] == "no2"].groupby(["we", "heure"])["value"].mean().unstack(0)
    if not no2.empty:
        no2.columns = ["semaine" if not c else "week-end" for c in no2.columns]
        no2.plot(ax=axes[1], marker=".")
    axes[1].set_title("NO2 (trafic routier) : semaine contre week-end")
    axes[1].set_xticks(range(24))
    sauver_figure(fig, P, "q2_variation_journaliere")


def q3_dominants(df):
    titre("Q3 - Polluants dominants")
    ratio = df.groupby(["city", "pollutant"])["ratio_oms"].mean().unstack(1)
    ratio["polluant_dominant"] = ratio.apply(lambda r: NOMS[r.idxmax()] if r.notna().any() else None, axis=1)
    sauver_table(ratio.round(2).reset_index(), P, "q3_polluants_dominants")
    print(ratio.round(2).to_string())

    fig, ax = plt.subplots()
    ratio.drop(columns="polluant_dominant").rename(columns=NOMS).plot.bar(ax=ax)
    ax.axhline(1, color="red", ls="--", label="valeur guide OMS")
    ax.set_title("Concentration moyenne rapportee a la valeur guide OMS (1 = la limite)")
    ax.set_xlabel("")
    ax.legend(ncol=6)
    sauver_figure(fig, P, "q3_polluants_dominants")


def q4_episodes(df):
    titre("Q4 - Episodes de pollution anormale")
    ville_heure = df.groupby(["city", "pollutant", "timestamp"])["value"].mean()
    episodes = []
    series = {}
    for (ville, pol), s in ville_heure.groupby(level=["city", "pollutant"]):
        s = s.droplevel([0, 1]).asfreq("h")
        moy = s.rolling(FENETRE_H[pol], min_periods=int(FENETRE_H[pol] * 0.75)).mean()
        # episode = depassement de la valeur guide OMS OU valeur exceptionnelle pour cette ville
        seuil_stat = s.quantile(0.99)
        anormal = (moy > OMS[pol]) | (s > seuil_stat)
        groupes = (anormal != anormal.shift()).cumsum()
        for _, bloc in anormal[anormal].groupby(groupes[anormal]):
            if len(bloc) >= 6:  # au moins 6 heures d'affilee
                vals = s.loc[bloc.index[0]:bloc.index[-1]]
                episodes.append({"city": ville, "pollutant": NOMS[pol], "debut": bloc.index[0], "fin": bloc.index[-1],
                                 "duree_h": len(bloc), "pic": round(vals.max(), 1),
                                 "pic_vs_oms": round(vals.max() / OMS[pol], 2)})
        series[(ville, pol)] = (s, moy)
    ep = pd.DataFrame(episodes)
    if ep.empty:
        print("Aucun episode detecte sur la periode")
        return
    ep = ep.sort_values("pic_vs_oms", ascending=False)
    sauver_table(ep, P, "q4_episodes")
    print(f"{len(ep)} episodes detectes")
    print(ep.groupby(["city", "pollutant"]).size().unstack(fill_value=0).to_string())

    ville = ep["city"].value_counts().index[0]
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
    for ax, pol in zip(axes, ["pm25", "no2"]):
        if (ville, pol) not in series:
            continue
        s, moy = series[(ville, pol)]
        ax.plot(s.index, s, lw=0.6, color="gray", label="horaire")
        ax.plot(moy.index, moy, color="tab:purple", label=f"moyenne {FENETRE_H[pol]} h")
        ax.axhline(OMS[pol], color="red", ls="--", label="OMS")
        for _, e in ep[(ep["city"] == ville) & (ep["pollutant"] == NOMS[pol])].iterrows():
            ax.axvspan(e["debut"], e["fin"], color="orange", alpha=0.3)
        ax.set_title(f"{ville} - {NOMS[pol]} (zones orange = episodes)")
        ax.legend(fontsize=8)
    sauver_figure(fig, P, "q4_episodes")


def main():
    titre("Chargement des donnees pollution (silver)")
    df = charger()
    print(f"{len(df):,} mesures, {df['sensor_id'].nunique()} capteurs, {df['city'].nunique()} villes")
    q1_zones(df)
    q2_journee(df)
    q3_dominants(df)
    q4_episodes(df)
    print("\nPartie 3 terminee. Graphiques dans rapports/figures")


if __name__ == "__main__":
    main()
