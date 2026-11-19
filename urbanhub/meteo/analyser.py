"""Partie 1 - etape 3 : analyses meteo (silver -> gold) et reponses aux questions metier.

Q1 Periodes meteorologiques anormales
Q2 Correlation entre conditions meteo et visibilite
Q3 Evolution saisonniere de la temperature (France et grandes villes)
Q4 Jours aux conditions extremes

Chaque resultat est un tableau range dans gold/meteo/ puis affiche par l'interface.

Lancer : python -m urbanhub.meteo.analyser
"""
import pandas as pd

from urbanhub import datalake
from urbanhub.gold import sauver_table, titre

P = "meteo"
VARIABLES = ["temperature", "humidity", "wind_speed", "pressure", "precipitation", "cloud_cover", "visibility"]


def charger():
    """Silver horaire + un tableau journalier par ville (heure de Paris)."""
    h = datalake.lire_parquets("silver", "meteo/")
    h["date"] = h["timestamp"].dt.tz_convert("Europe/Paris").dt.tz_localize(None).dt.normalize()
    h["brouillard"] = h["visibility"] < 1
    j = h.groupby(["city", "date"]).agg(
        n_heures=("temperature", "count"),
        temp_mean=("temperature", "mean"), temp_min=("temperature", "min"), temp_max=("temperature", "max"),
        humidity=("humidity", "mean"), precip_mm=("precipitation", "sum"),
        wind_mean=("wind_speed", "mean"), gusts_max=("wind_gusts", "max"),
        pressure=("pressure", "mean"), visibility_mean=("visibility", "mean"),
        heures_brouillard=("brouillard", "sum"),
    ).reset_index()
    j = j[j["n_heures"] >= 20]  # jour incomplet (debut / fin de periode) : ignore
    return h, j


def periodes(masque):
    """Transforme une serie de jours vrai/faux en periodes consecutives (debut, fin, duree)."""
    groupes = (masque != masque.shift()).cumsum()
    return [(b.index[0], b.index[-1], len(b)) for _, b in masque.groupby(groupes) if b.iloc[0]]


def q1_anomalies(jour):
    titre("Q1 - Periodes meteorologiques anormales")
    france = jour.groupby("date").agg(temperature=("temp_mean", "mean"), pluie=("precip_mm", "mean")).asfreq("D")

    # "normale" de saison = moyenne du meme jour de l'annee sur les 5 ans, lissee sur 15 jours
    jdo = france.index.day_of_year
    normale = france["temperature"].groupby(jdo).mean()
    normale = pd.concat([normale.iloc[-7:], normale, normale.iloc[:7]]).rolling(15, center=True).mean().iloc[7:-7]
    france["normale"] = normale.reindex(jdo).values
    france["anomalie"] = france["temperature"] - france["normale"]
    france["z"] = france["anomalie"] / france["anomalie"].std()
    # pluie : cumul sur 30 jours compare a la moyenne
    cumul = france["pluie"].rolling(30, min_periods=20).sum()
    france["z_pluie_30j"] = (cumul - cumul.mean()) / cumul.std()
    sauver_table(france.reset_index(), P, "q1_anomalies_journalieres")

    lignes = []
    for nom, masque in [("vague de chaleur", france["z"] > 1.5), ("vague de froid", france["z"] < -1.5),
                        ("periode tres seche", france["z_pluie_30j"] < -1.5),
                        ("periode tres humide", france["z_pluie_30j"] > 1.5)]:
        for debut, fin, duree in periodes(masque.fillna(False)):
            if duree >= 3:
                bloc = france.loc[debut:fin]
                lignes.append({"type": nom, "debut": debut, "fin": fin, "duree_jours": duree,
                               "ecart_temp_moyen": round(bloc["anomalie"].mean(), 1)})
    res = pd.DataFrame(lignes).sort_values("debut")
    sauver_table(res, P, "q1_periodes_anormales")
    print(res.groupby("type")["duree_jours"].agg(nb_periodes="count", nb_jours="sum").to_string())


def q2_visibilite(h):
    titre("Q2 - Meteo et visibilite")
    corr = h[VARIABLES].corr(method="spearman")["visibility"].drop("visibility")
    res = corr.rename_axis("variable").reset_index(name="correlation")
    sauver_table(res, P, "q2_correlations")
    print(corr.round(2).to_string())

    classes = {
        "pluie (mm/h)": pd.cut(h["precipitation"], [-0.01, 0, 1, 4, 200], labels=["0", "0-1", "1-4", "> 4"]),
        "humidite (%)": pd.cut(h["humidity"], [0, 60, 75, 90, 100], labels=["< 60", "60-75", "75-90", "> 90"]),
        "nuages (%)": pd.cut(h["cloud_cover"], [-1, 25, 50, 75, 100], labels=["< 25", "25-50", "50-75", "> 75"]),
    }
    lignes = []
    for facteur, cl in classes.items():
        g = h.groupby(cl, observed=True)["visibility"]
        for ordre, (classe, med) in enumerate(g.median().items()):
            lignes.append({"facteur": facteur, "classe": str(classe), "ordre": ordre,
                           "visibilite_mediane_km": round(med, 1),
                           "part_visibilite_reduite": (g.get_group(classe) < 10).mean(),  # sous 10 km
                           "part_brouillard": (g.get_group(classe) < 1).mean()})
    sauver_table(pd.DataFrame(lignes), P, "q2_visibilite_par_condition")


def q3_saisons(jour):
    titre("Q3 - Evolution saisonniere de la temperature")
    j = jour.assign(mois=jour["date"].dt.to_period("M").dt.to_timestamp())
    mensuel = j.groupby(["city", "mois"])["temp_mean"].mean().round(2).rename("temperature").reset_index()
    france = j.groupby("mois")["temp_mean"].mean().round(2).rename("temperature").reset_index().assign(city="France")
    sauver_table(pd.concat([mensuel, france]), P, "q3_temperature_mensuelle")

    profil = j.groupby(["city", j["date"].dt.month])["temp_mean"].mean().round(2)
    profil = profil.rename("temperature").reset_index().rename(columns={"date": "mois_calendaire"})
    sauver_table(profil, P, "q3_profil_saisonnier")

    p = profil.pivot(index="mois_calendaire", columns="city", values="temperature")
    ecart = pd.DataFrame({"ete": p.loc[[7, 8]].mean(), "hiver": p.loc[[12, 1]].mean()})
    ecart["ecart"] = ecart["ete"] - ecart["hiver"]
    ecart = ecart.round(1).sort_values("ecart", ascending=False).reset_index()
    sauver_table(ecart, P, "q3_ecart_ete_hiver")
    print(ecart.to_string(index=False))


def q4_extremes(jour):
    titre("Q4 - Jours aux conditions extremes")
    regles = {
        "chaleur (max >= 35 C)": jour["temp_max"] >= 35,
        "gel (min <= -5 C)": jour["temp_min"] <= -5,
        "tempete (rafales >= 80 km/h)": jour["gusts_max"] >= 80,
        "pluie forte (>= 30 mm)": jour["precip_mm"] >= 30,
        "brouillard (>= 6 h sous 1 km)": jour["heures_brouillard"] >= 6,
    }
    j = jour.assign(**regles)
    j["extreme"] = j[list(regles)].any(axis=1)

    par_jour = j.groupby("date").agg(villes_mesurees=("city", "nunique"), villes_en_extreme=("extreme", "sum"),
                                     **{r: (r, "sum") for r in regles})
    par_jour["part_villes"] = par_jour["villes_en_extreme"] / par_jour["villes_mesurees"]
    top = par_jour[par_jour["villes_en_extreme"] > 0].sort_values(["part_villes", "villes_en_extreme"],
                                                                  ascending=False).head(25).reset_index()
    top["type_principal"] = top[list(regles)].idxmax(axis=1)
    villes = j[j["extreme"]].groupby("date")["city"].agg(lambda s: ", ".join(sorted(s)))
    top["villes"] = top["date"].map(villes)
    sauver_table(top[["date", "type_principal", "villes_en_extreme", "villes_mesurees", "part_villes", "villes"]]
                 , P, "q4_jours_extremes")
    print(top[["date", "type_principal", "villes_en_extreme"]].head(10).to_string(index=False))

    long = j.melt(id_vars=["city", "date"], value_vars=list(regles), var_name="type", value_name="oui")
    long = long[long["oui"]]
    par_mois = long.groupby([long["date"].dt.to_period("M").dt.to_timestamp(), "type"]).size()
    sauver_table(par_mois.rename("nb_jours_ville").reset_index().rename(columns={"date": "mois"}), P,
                 "q4_extremes_par_mois")
    par_ville = long.groupby(["city", "type"]).size().rename("nb_jours").reset_index()
    sauver_table(par_ville, P, "q4_extremes_par_ville")
    print(long.groupby("type").size().rename("jours-ville sur 5 ans").to_string())


def main():
    titre("Chargement des donnees meteo (silver)")
    h, jour = charger()
    if jour.empty:
        print("Pas de donnees. Lancer d'abord le telechargement puis le nettoyage.")
        return
    print(f"{len(h):,} heures, {jour['city'].nunique()} villes, du {jour['date'].min():%Y-%m-%d} "
          f"au {jour['date'].max():%Y-%m-%d}")
    sauver_table(jour.drop(columns="n_heures"), P, "meteo_journaliere")
    q1_anomalies(jour)
    q2_visibilite(h)
    q3_saisons(jour)
    q4_extremes(jour)
    print("\nPartie 1 terminee : indicateurs dans gold/meteo/")


if __name__ == "__main__":
    main()
