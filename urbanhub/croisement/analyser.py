"""Partie 4 : analyse croisee meteo x pollution x velos.

On construit une table "une ligne = une ville x une heure" qui rassemble :
- la meteo (moyenne des stations NOAA proches de la ville)
- la pollution (moyenne des capteurs OpenAQ de la ville)
- l'usage des velos (mouvements par collecte)

Pour comparer l'usage des velos d'une heure a l'autre, on enleve l'effet de
l'heure de la journee : un "indice d'usage" de 1.2 veut dire "20 % de plus que
d'habitude a cette heure-la, ce jour-la de la semaine, dans cette ville".

Q1 Meteo et pollution
Q2 Meteo et usage des velos
Q3 Conditions meteo favorables a la mobilite douce
Q4 Periodes ou mobilite, pollution et meteo interagissent fortement

Meteo : NOAA quand elle existe, sinon Open-Meteo (python -m urbanhub.meteo.recente),
car le depot NOAA s'arrete en 2025.

Lancer : python -m urbanhub.croisement.analyser
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from urbanhub import datalake
from urbanhub.rapport import sauver_figure, sauver_table, titre
from urbanhub.velos.analyser import charger as charger_velos

P = "croisement"
METEO = ["temperature", "wind_speed_kmh", "precipitation", "pressure", "visibility"]
POLLUANTS = ["pm25", "pm10", "no2", "o3", "co"]


def meteo_horaire(debut):
    annees = range(debut.year, pd.Timestamp.now().year + 1)
    morceaux = []
    for a in annees:
        key = f"meteo/year={a}/meteo.parquet"
        if datalake.existe("silver", key):
            d = datalake.get_parquet("silver", key, columns=["city", "timestamp"] + METEO)
            morceaux.append(d[d["city"].notna() & (d["timestamp"] >= debut)])
    noaa = pd.concat(morceaux).groupby(["city", "timestamp"])[METEO].mean().reset_index() if morceaux else pd.DataFrame()
    # NOAA s'arrete en 2025 : pour la periode recente on complete avec Open-Meteo
    if datalake.existe("silver", "meteo_recente/meteo_recente.parquet"):
        recente = datalake.get_parquet("silver", "meteo_recente/meteo_recente.parquet", columns=["city", "timestamp"] + METEO)
        recente = recente[recente["timestamp"] >= debut]
        tout = [meme_format_date(x) for x in (noaa, recente) if not x.empty]
        # si les deux sources ont la meme heure, on garde NOAA (mesure reelle d'une station)
        return pd.concat(tout).drop_duplicates(["city", "timestamp"], keep="first")
    return noaa


def pollution_horaire():
    if not datalake.existe("silver", "pollution/pollution.parquet"):
        return pd.DataFrame()
    d = datalake.get_parquet("silver", "pollution/pollution.parquet")
    return d.groupby(["city", "timestamp", "pollutant"])["value"].mean().unstack("pollutant").reset_index()


def velos_horaire():
    d = charger_velos()
    if d.empty:
        return d
    d["timestamp"] = d["collected_at"].dt.floor("h")
    h = d.groupby(["city", "timestamp"], observed=True).agg(
        mouvements=("mouvements", "sum"), collectes=("collected_at", "nunique"),
        remplissage=("fill_rate", "mean")).reset_index()
    h = h[h["collectes"] >= 10]  # heure trop incomplete : ignoree
    h["mouv_par_collecte"] = h["mouvements"] / h["collectes"]
    local = h["timestamp"].dt.tz_convert("Europe/Paris")
    h["heure"], h["we"] = local.dt.hour, local.dt.day_of_week >= 5
    habituel = h.groupby(["city", "heure", "we"], observed=True)["mouv_par_collecte"].transform("mean")
    h["indice_usage"] = h["mouv_par_collecte"] / habituel.where(habituel > 0)
    h["city"] = h["city"].astype(str)
    return h[["city", "timestamp", "mouv_par_collecte", "indice_usage", "remplissage"]]


def meme_format_date(d):
    """Les 3 sources doivent avoir exactement le meme type de date pour etre jointes."""
    if not d.empty:
        d["timestamp"] = d["timestamp"].astype("datetime64[ns, UTC]")
        d["city"] = d["city"].astype(str)
    return d


def construire_table():
    pol, vel = meme_format_date(pollution_horaire()), meme_format_date(velos_horaire())
    debuts = [t["timestamp"].min() for t in (pol, vel) if not t.empty]
    if not debuts:
        return pd.DataFrame()
    met = meme_format_date(meteo_horaire(min(debuts)))
    table = met
    for autre in (pol, vel):
        if not autre.empty:
            table = table.merge(autre, on=["city", "timestamp"], how="outer") if not table.empty else autre
    return table.sort_values(["city", "timestamp"])


def heatmap(ax, corr, titre_graph):
    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(corr.shape[1]), corr.columns, rotation=45)
    ax.set_yticks(range(corr.shape[0]), corr.index)
    for i in range(corr.shape[0]):
        for k in range(corr.shape[1]):
            if pd.notna(corr.iloc[i, k]):
                ax.text(k, i, f"{corr.iloc[i, k]:.2f}", ha="center", va="center", fontsize=8)
    ax.set_title(titre_graph)
    ax.grid(False)
    return im


def q1_meteo_pollution(t):
    titre("Q1 - Meteo et pollution")
    pols = [p for p in POLLUANTS if p in t]
    d = t.dropna(subset=["temperature"])
    corr = d[METEO + pols].corr(method="spearman").loc[METEO, pols]
    sauver_table(corr.round(3).reset_index(names="meteo"), P, "q1_correlation_meteo_pollution")
    print(corr.round(2).to_string())

    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    im = heatmap(axes[0], corr, "Correlation meteo / pollution (Spearman)")
    fig.colorbar(im, ax=axes[0])
    vent = pd.cut(d["wind_speed_kmh"], [0, 10, 20, 30, 200], labels=["<10", "10-20", "20-30", ">30 km/h"], include_lowest=True)
    d.groupby(vent, observed=True)[[p for p in ["pm25", "no2"] if p in d]].mean().plot.bar(ax=axes[1])
    axes[1].set_title("Pollution moyenne selon la force du vent")
    axes[1].set_ylabel("microgrammes par m3")
    sauver_figure(fig, P, "q1_meteo_pollution")


def classes_meteo(d):
    d = d.copy()
    d["classe_temp"] = pd.cut(d["temperature"], [-30, 5, 10, 15, 20, 25, 50],
                              labels=["<5", "5-10", "10-15", "15-20", "20-25", ">25"])
    d["pluie"] = np.where(d["precipitation"].fillna(0) > 0.2, "pluie", "sec")
    d["classe_vent"] = pd.cut(d["wind_speed_kmh"], [0, 15, 30, 200], labels=["calme", "modere", "fort"], include_lowest=True)
    return d


def q2_meteo_velos(t):
    titre("Q2 - Meteo et usage des velos")
    d = classes_meteo(t.dropna(subset=["indice_usage", "temperature"]))
    if d.empty:
        print("Pas encore de periode commune meteo / velos")
        return d
    corr = d[METEO + ["indice_usage"]].corr(method="spearman")["indice_usage"].drop("indice_usage")
    print("Correlation avec l'indice d'usage :", corr.round(2).to_dict())
    sauver_table(corr.round(3).reset_index(name="correlation"), P, "q2_correlation_meteo_velos")

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    for ax, col, nom in zip(axes, ["classe_temp", "pluie", "classe_vent"], ["temperature (C)", "pluie", "vent"]):
        d.groupby(col, observed=True)["indice_usage"].mean().plot.bar(ax=ax, color="tab:green")
        ax.axhline(1, color="black", lw=0.8)
        ax.set_title(f"Usage des velos selon : {nom}")
        ax.set_xlabel("")
    axes[0].set_ylabel("indice d'usage (1 = habituel)")
    sauver_figure(fig, P, "q2_meteo_velos")
    return d


def q3_favorables(d):
    titre("Q3 - Conditions favorables a la mobilite douce")
    if d is None or d.empty:
        return
    combos = d.groupby(["classe_temp", "pluie", "classe_vent"], observed=True)["indice_usage"].agg(["mean", "count"])
    combos = combos[combos["count"] >= 10].sort_values("mean", ascending=False).reset_index()
    combos = combos.rename(columns={"mean": "indice_usage_moyen", "count": "nb_heures"})
    sauver_table(combos.round(3), P, "q3_conditions_favorables")
    print("Meilleures conditions :")
    print(combos.head(5).to_string(index=False))
    print("Pires conditions :")
    print(combos.tail(3).to_string(index=False))

    sec = d[d["pluie"] == "sec"].pivot_table(index="classe_vent", columns="classe_temp", values="indice_usage",
                                              aggfunc="mean", observed=True)
    fig, ax = plt.subplots(figsize=(9, 4))
    im = ax.imshow(sec, cmap="Greens", aspect="auto")
    ax.set_xticks(range(sec.shape[1]), sec.columns)
    ax.set_yticks(range(sec.shape[0]), sec.index)
    for i in range(sec.shape[0]):
        for k in range(sec.shape[1]):
            if pd.notna(sec.iloc[i, k]):
                ax.text(k, i, f"{sec.iloc[i, k]:.2f}", ha="center", va="center")
    ax.set_title("Indice d'usage par temps sec : temperature x vent")
    ax.set_xlabel("temperature (C)")
    ax.grid(False)
    fig.colorbar(im, ax=ax)
    sauver_figure(fig, P, "q3_conditions_favorables")


def q4_interactions(t):
    titre("Q4 - Periodes d'interaction forte")
    pol = "no2" if "no2" in t else ("pm25" if "pm25" in t else None)
    if pol is None or "indice_usage" not in t:
        print("Il faut des donnees velos et pollution sur la meme periode")
        return
    t = t.assign(date=t["timestamp"].dt.tz_convert("Europe/Paris").dt.tz_localize(None).dt.normalize())
    jour = t.groupby(["city", "date"]).agg(usage=("indice_usage", "mean"), pollution=(pol, "mean"),
                                           temperature=("temperature", "mean"), pluie=("precipitation", "sum"),
                                           vent=("wind_speed_kmh", "mean")).dropna()
    if len(jour) < 5:
        print("Pas assez de jours en commun pour l'instant (laisser tourner la collecte)")
        return
    z = jour.groupby(level="city").transform(lambda s: (s - s.mean()) / s.std())
    z["meteo"] = z[["temperature", "pluie", "vent"]].abs().max(axis=1)
    forts = z[(z["usage"].abs() > 1) & (z["pollution"].abs() > 1) & (z["meteo"] > 1)]
    res = jour.loc[forts.index].join(forts[["usage", "pollution", "meteo"]], rsuffix="_z").reset_index()
    sauver_table(res.round(2), P, "q4_jours_interaction_forte")
    print(f"{len(res)} jours ou les trois s'ecartent fortement de la normale en meme temps (polluant : {pol})")
    if not res.empty:
        print(res.head(10).round(2).to_string(index=False))

    ville = jour.index.get_level_values("city").value_counts().index[0]
    zv = z.loc[ville]
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(zv.index, zv["usage"], marker="o", label="usage velos")
    ax.plot(zv.index, zv["pollution"], marker="o", label=pol.upper())
    ax.plot(zv.index, zv["temperature"], marker="o", label="temperature")
    ax.bar(zv.index, zv["pluie"], alpha=0.3, color="tab:blue", label="pluie")
    ax.axhline(0, color="black", lw=0.8)
    for d in forts.loc[ville].index if ville in forts.index.get_level_values("city") else []:
        ax.axvspan(d - pd.Timedelta(hours=12), d + pd.Timedelta(hours=12), color="orange", alpha=0.25)
    ax.set_title(f"{ville} : ecarts a la normale (en ecarts-types). Orange = interaction forte")
    ax.legend()
    sauver_figure(fig, P, "q4_interactions")


def main():
    titre("Construction de la table croisee ville x heure")
    t = construire_table()
    if t.empty:
        print("Pas encore de donnees velos ou pollution exploitables (il faut au moins une heure complete "
              "de collecte velos, ou l'historique pollution). Lancer d'abord les parties 2 et 3.")
        return
    datalake.put_parquet("gold", f"{P}/table_ville_heure.parquet", t)
    print(f"{len(t):,} lignes, du {t['timestamp'].min():%Y-%m-%d} au {t['timestamp'].max():%Y-%m-%d}")
    for col in ["temperature", "no2", "indice_usage"]:
        if col in t:
            print(f"  heures avec {col} : {t[col].notna().sum():,}")
    if "temperature" in t:
        q1_meteo_pollution(t)
        d = q2_meteo_velos(t) if "indice_usage" in t else None
        q3_favorables(d)
    q4_interactions(t)
    print("\nPartie 4 terminee. Graphiques dans rapports/figures")


if __name__ == "__main__":
    main()
