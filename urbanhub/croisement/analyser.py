"""Partie 4 : analyse croisee meteo x pollution x velos.

On construit une table "une ligne = une ville x une heure" qui rassemble :
- la meteo de la ville (Open-Meteo, silver/meteo)
- la pollution (moyenne des capteurs OpenAQ de la ville, silver/pollution)
- l'usage des velos (mouvements par station, silver/velos_ville_heure)

Pour comparer l'usage des velos d'une heure a l'autre, on enleve l'effet de
l'heure de la journee : un "indice d'usage" de 1.2 veut dire "20 % de plus que
d'habitude a cette heure-la, ce jour-la de la semaine, dans cette ville".

Q1 Meteo et pollution
Q2 Meteo et usage des velos
Q3 Conditions meteo favorables a la mobilite douce
Q4 Periodes ou mobilite, pollution et meteo interagissent fortement

Chaque resultat est un tableau range dans gold/croisement/ puis affiche par l'interface.

Lancer : python -m urbanhub.croisement.analyser
"""
import numpy as np
import pandas as pd

from urbanhub import datalake
from urbanhub.gold import sauver_table, titre

P = "croisement"
METEO = ["temperature", "humidity", "wind_speed", "precipitation", "pressure", "visibility"]
POLLUANTS = ["pm25", "pm10", "no2", "o3", "co"]
NOMS = {"pm25": "PM2.5", "pm10": "PM10", "no2": "NO2", "o3": "O3", "co": "CO"}


def meme_format(d):
    """Les 3 sources doivent avoir exactement le meme type de cle pour etre jointes."""
    if not d.empty:
        d["timestamp"] = d["timestamp"].astype("datetime64[ns, UTC]")
        d["city"] = d["city"].astype(str)
    return d


def meteo_horaire():
    return meme_format(datalake.lire_parquets("silver", "meteo/", columns=["city", "timestamp"] + METEO))


def pollution_horaire():
    d = datalake.lire_parquets("silver", "pollution/", columns=["city", "timestamp", "pollutant", "value"])
    if d.empty:
        return d
    return meme_format(d.groupby(["city", "timestamp", "pollutant"])["value"].mean().unstack("pollutant").reset_index())


def velos_horaire():
    """Usage des velos par ville et par heure (table preparee par l'analyse velos)."""
    if not datalake.existe("silver", "velos_ville_heure/velos_ville_heure.parquet"):
        return pd.DataFrame()
    h = datalake.get_parquet("silver", "velos_ville_heure/velos_ville_heure.parquet").rename(columns={"heure": "timestamp"})
    h["mouv_par_station"] = h["mouvements"] / h["stations"].where(h["stations"] > 0)
    local = h["timestamp"].dt.tz_convert("Europe/Paris")
    h["h_locale"], h["we"] = local.dt.hour, local.dt.day_of_week >= 5
    # on enleve l'effet de l'heure de la journee et du week-end : 1 = usage habituel
    habituel = h.groupby(["city", "h_locale", "we"])["mouv_par_station"].transform("mean")
    h["indice_usage"] = h["mouv_par_station"] / habituel.where(habituel > 0)
    return meme_format(h[["city", "timestamp", "mouv_par_station", "indice_usage", "remplissage"]])


def construire_table():
    pol, vel = pollution_horaire(), velos_horaire()
    debuts = [t["timestamp"].min() for t in (pol, vel) if not t.empty]
    if not debuts:
        return pd.DataFrame()
    met = meteo_horaire()
    table = met[met["timestamp"] >= min(debuts)]
    for autre in (pol, vel):
        if not autre.empty:
            table = table.merge(autre, on=["city", "timestamp"], how="outer")
    return table.sort_values(["city", "timestamp"]).reset_index(drop=True)


def q1_meteo_pollution(t):
    titre("Q1 - Meteo et pollution")
    pols = [p for p in POLLUANTS if p in t]
    d = t.dropna(subset=["temperature"])
    corr = d[METEO + pols].corr(method="spearman").loc[METEO, pols]
    print(corr.round(2).to_string())
    long = corr.stack().rename("correlation").reset_index()
    long.columns = ["meteo", "pollutant", "correlation"]
    long["polluant"] = long["pollutant"].map(NOMS)
    sauver_table(long, P, "q1_correlation_meteo_pollution")

    vent = pd.cut(d["wind_speed"], [0, 10, 20, 30, 200], labels=["< 10", "10-20", "20-30", "> 30"], include_lowest=True)
    par_vent = d.groupby(vent.rename("vent_kmh"), observed=True)[pols].mean().reset_index()
    sauver_table(par_vent, P, "q1_pollution_selon_vent")
    temp = pd.cut(d["temperature"], [-30, 0, 5, 10, 15, 20, 25, 30, 50],
                  labels=["< 0", "0-5", "5-10", "10-15", "15-20", "20-25", "25-30", "> 30"])
    par_temp = d.groupby(temp.rename("temperature_c"), observed=True)[pols].mean().reset_index()
    sauver_table(par_temp, P, "q1_pollution_selon_temperature")


def classes_meteo(d):
    d = d.copy()
    d["classe_temp"] = pd.cut(d["temperature"], [-30, 5, 10, 15, 20, 25, 50],
                              labels=["< 5", "5-10", "10-15", "15-20", "20-25", "> 25"]).astype(str)
    d["pluie"] = np.where(d["precipitation"].fillna(0) > 0.2, "pluie", "sec")
    d["classe_vent"] = pd.cut(d["wind_speed"], [0, 15, 30, 200], labels=["calme", "modere", "fort"],
                              include_lowest=True).astype(str)
    return d


def q2_meteo_velos(t):
    titre("Q2 - Meteo et usage des velos")
    d = classes_meteo(t.dropna(subset=["indice_usage", "temperature"]))
    corr = d[METEO + ["indice_usage"]].corr(method="spearman")["indice_usage"].drop("indice_usage")
    print("Correlation avec l'indice d'usage :", corr.round(2).to_dict())
    sauver_table(corr.rename_axis("meteo").reset_index(name="correlation"), P, "q2_correlation_meteo_velos")
    lignes = []
    ordres = {"classe_temp": ["< 5", "5-10", "10-15", "15-20", "20-25", "> 25"], "pluie": ["sec", "pluie"],
              "classe_vent": ["calme", "modere", "fort"]}
    for col, facteur in [("classe_temp", "temperature (C)"), ("pluie", "pluie"), ("classe_vent", "vent")]:
        g = d.groupby(col)["indice_usage"].agg(["mean", "count"])
        for classe, r in g.iterrows():
            ordre = ordres[col].index(classe) if classe in ordres[col] else 99
            lignes.append({"facteur": facteur, "classe": classe, "ordre": ordre,
                           "indice_usage": r["mean"], "nb_heures": r["count"]})
    sauver_table(pd.DataFrame(lignes), P, "q2_usage_selon_meteo")
    return d


def q3_favorables(d):
    titre("Q3 - Conditions favorables a la mobilite douce")
    combos = d.groupby(["classe_temp", "pluie", "classe_vent"])["indice_usage"].agg(["mean", "count"])
    combos = combos[combos["count"] >= 10].sort_values("mean", ascending=False).reset_index()
    combos = combos.rename(columns={"mean": "indice_usage_moyen", "count": "nb_heures"})
    sauver_table(combos, P, "q3_conditions_favorables")
    print(combos.head(5).to_string(index=False))


def q4_interactions(t):
    titre("Q4 - Periodes d'interaction forte")
    pol = "no2" if "no2" in t else "pm25"
    t = t.assign(date=t["timestamp"].dt.tz_convert("Europe/Paris").dt.tz_localize(None).dt.normalize())
    jour = t.groupby(["city", "date"]).agg(usage=("indice_usage", "mean"), heures_velos=("indice_usage", "count"),
                                           pollution=(pol, "mean"), temperature=("temperature", "mean"),
                                           pluie=("precipitation", "sum"), vent=("wind_speed", "mean")).dropna()
    jour = jour[jour.pop("heures_velos") >= 20]  # journee incomplete (ex : aujourd'hui) : ignoree
    if len(jour) < 5:
        print("Pas assez de jours en commun pour l'instant (laisser tourner la collecte)")
        return
    z = jour.groupby(level="city").transform(lambda s: (s - s.mean()) / s.std())
    z["meteo"] = z[["temperature", "pluie", "vent"]].abs().max(axis=1)
    sauver_table(z.reset_index(), P, "q4_ecarts_journaliers")
    forts = z[(z["usage"].abs() > 1) & (z["pollution"].abs() > 1) & (z["meteo"] > 1)]
    res = jour.loc[forts.index].join(forts[["usage", "pollution", "meteo"]].add_suffix("_z")).reset_index()
    sauver_table(res, P, "q4_jours_interaction_forte")
    print(f"{len(res)} jours ou les trois s'ecartent fortement de la normale en meme temps (polluant : {pol})")


def main():
    titre("Construction de la table croisee ville x heure")
    t = construire_table()
    if t.empty:
        print("Pas encore de donnees velos ou pollution. Lancer d'abord les parties 2 et 3.")
        return
    datalake.put_parquet("silver", "croisement/table_ville_heure.parquet", t)
    print(f"{len(t):,} lignes, du {t['timestamp'].min():%Y-%m-%d} au {t['timestamp'].max():%Y-%m-%d}")
    q1_meteo_pollution(t)

    # Q2 a Q4 ont besoin des velos : au moins 24 heures de collecte, sinon les resultats ne veulent rien dire
    heures_velos = t.loc[t["indice_usage"].notna(), "timestamp"].nunique() if "indice_usage" in t else 0
    if heures_velos < 24:
        print(f"\nQ2, Q3 et Q4 : seulement {heures_velos} heures de collecte velos, il en faut au moins 24 "
              "(idealement une semaine). Laisser tourner : python -m urbanhub.velos.collecter")
    else:
        d = q2_meteo_velos(t)
        q3_favorables(d)
        q4_interactions(t)
    print("\nPartie 4 terminee : indicateurs dans gold/croisement/")


if __name__ == "__main__":
    main()
