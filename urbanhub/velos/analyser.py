"""Partie 2 - etape 3 : analyses de la mobilite a velo (silver -> gold).

On part de la table silver/velos_horaire (une ligne par station et par heure, historique
CityBikes depuis novembre 2024 + collecte en direct). Elle fait des dizaines de millions
de lignes : on la lit fichier par fichier (un reseau x un mois) et on ne garde en memoire
que des totaux (sommes et comptes), combines a la fin.

Les "mouvements" (velos pris ou rendus) sont notre mesure de l'utilisation.

Q1 Stations au plus fort taux d'utilisation
Q2 Zones ou l'offre de velos est insuffisante
Q3 Pics d'utilisation dans la journee
Q4 Desequilibres geographiques (centre / peripherie, matin / soir)
Q5 Stations critiques a reequilibrer (sur les 30 derniers jours)

Chaque resultat est un tableau range dans gold/velos/ puis affiche par l'interface.

Lancer : python -m urbanhub.velos.analyser
"""
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from urbanhub import datalake
from urbanhub.gold import sauver_table, titre
from urbanhub.villes import VILLES, distance_km

P = "velos"
SOMMES = ["mouvements", "heures", "remplissage_somme", "remplissage_n", "vide_somme", "plein_somme"]
MOMENTS = pd.IntervalIndex.from_breaks([6, 10, 16, 20])  # 7h-10h, 11h-16h, 17h-20h
NOMS_MOMENTS = ["matin 7-10h", "apres-midi", "soir 17-20h"]


def totaux_station(h):
    g = h.groupby("station_id")
    return pd.DataFrame({
        "mouvements": g["mouvements"].sum(), "heures": g.size(),
        "remplissage_somme": g["remplissage"].sum(), "remplissage_n": g["remplissage"].count(),
        "vide_somme": g["part_vide"].sum(), "plein_somme": g["part_plein"].sum(),
    })


def accumuler():
    """Lit la table horaire fichier par fichier et cumule tout ce dont les questions ont besoin."""
    cles = sorted(k for k in datalake.lister("silver", "velos_horaire/") if k.endswith(".parquet"))
    if not cles:
        return None
    # Q5 : pour chaque reseau, les 2 derniers fichiers mensuels disponibles (l'archive a parfois des mois manquants)
    par_reseau = {}
    for k in cles:
        par_reseau.setdefault(k.split("network=")[1], []).append(k)
    recents = {k for ks in par_reseau.values() for k in ks[-2:]}
    acc = {k: [] for k in ["station", "meta", "profil", "moment", "ville_heure", "recent"]}

    def lire(k):
        return datalake.get_parquet("silver", k)

    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, h in enumerate(pool.map(lire, cles), 1):
            if h.empty:
                continue
            local = h["heure"].dt.tz_convert("Europe/Paris")
            h["h_locale"], h["weekend"] = local.dt.hour, local.dt.day_of_week >= 5
            acc["station"].append(totaux_station(h))
            acc["meta"].append(h.groupby("station_id")[["city", "station_name", "latitude", "longitude", "capacite"]]
                               .agg({"city": "last", "station_name": "last", "latitude": "median",
                                     "longitude": "median", "capacite": "median"}))
            acc["profil"].append(h.groupby(["city", "h_locale", "weekend"])["mouvements"].sum())
            moment = pd.cut(h["h_locale"], MOMENTS)
            acc["moment"].append(h.groupby(["station_id", moment], observed=True)["remplissage"].agg(["sum", "count"]))
            acc["ville_heure"].append(h.groupby(["city", "heure"]).agg(
                mouvements=("mouvements", "sum"), velos=("velos", "sum"), stations=("station_id", "size"),
                remplissage=("remplissage", "mean"), part_vide=("part_vide", "mean")))
            if cles[i - 1] in recents:
                acc["recent"].append(h[["station_id", "city", "heure", "mouvements", "remplissage", "part_vide",
                                        "part_plein", "velos", "places"]])
            if i % 40 == 0:
                print(f"  {i}/{len(cles)} fichiers lus")

    def somme(liste):
        return pd.concat(liste).groupby(level=0).sum()

    stations = somme(acc["station"]).join(pd.concat(acc["meta"]).groupby(level=0).last())
    profil = pd.concat(acc["profil"]).groupby(level=[0, 1, 2]).sum()
    moment = pd.concat(acc["moment"]).groupby(level=[0, 1], observed=True).sum()
    ville_heure = pd.concat(acc["ville_heure"]).groupby(level=[0, 1]).agg(
        {"mouvements": "sum", "velos": "sum", "stations": "sum", "remplissage": "mean", "part_vide": "mean"})

    # Q5 : etat actuel de chaque station, et les 30 derniers jours AVEC donnees de chaque ville
    r = pd.concat(acc["recent"])
    dernier = r.sort_values("heure").groupby("station_id").last()[["heure", "velos", "places"]]
    # heures ou la ville ne publie pas le nombre de velos (toutes les stations a 0) : pas un vrai etat
    vide_ville = r.groupby(["city", "heure"])["part_vide"].transform("mean")
    r = r[vide_ville < 0.95]
    jour = r["heure"].dt.floor("D")
    jours = jour.groupby(r["city"]).transform(lambda d: d.rank(method="dense", ascending=False))
    r = r[jours <= 30]
    stations30 = totaux_station(r)
    periode = r.groupby("city")["heure"].agg(["min", "max"])
    return stations, stations30, profil, moment, ville_heure, dernier, periode


def indicateurs(t):
    """Totaux -> indicateurs par station."""
    s = pd.DataFrame(index=t.index)
    s["mouvements"] = t["mouvements"]
    s["jours"] = t["heures"] / 24
    s["taux_remplissage"] = t["remplissage_somme"] / t["remplissage_n"].where(t["remplissage_n"] > 0)
    s["part_temps_vide"] = t["vide_somme"] / t["heures"]
    s["part_temps_plein"] = t["plein_somme"] / t["heures"]
    return s


def villes_sans_donnees(stations):
    """Reseaux qui ne publient pas le nombre de velos (toujours 0) : inutilisables."""
    vide = stations.groupby("city")["vide_somme"].sum() / stations.groupby("city")["heures"].sum()
    return list(vide[vide > 0.99].index)


def stats_stations(stations):
    s = indicateurs(stations).join(stations[["city", "station_name", "latitude", "longitude", "capacite"]])
    s = s.rename(columns={"capacite": "capacity"}).reset_index()
    s["rotations_par_jour"] = s["mouvements"] / s["capacity"].where(s["capacity"] > 0) / s["jours"]
    s["dist_centre_km"] = [distance_km(la, lo, *VILLES[c]) if c in VILLES else None
                           for la, lo, c in zip(s["latitude"], s["longitude"], s["city"])]
    return s


def q1_utilisation(s):
    titre("Q1 - Stations les plus utilisees")
    fiables = s[(s["capacity"] >= 5) & (s["jours"] >= 7)]
    top = fiables.sort_values("rotations_par_jour", ascending=False).head(20)
    sauver_table(top[["city", "station_name", "capacity", "mouvements", "rotations_par_jour", "latitude", "longitude"]],
                 P, "q1_top_stations")
    print(top[["city", "station_name", "rotations_par_jour"]].head(10).round(1).to_string(index=False))
    par_ville = fiables.groupby("city").agg(
        nb_stations=("station_id", "count"), capacite=("capacity", "sum"),
        rotations_par_jour=("rotations_par_jour", "median"), taux_remplissage=("taux_remplissage", "mean"),
        part_temps_vide=("part_temps_vide", "mean")).reset_index()
    sauver_table(par_ville, P, "q1_utilisation_par_ville")
    print(par_ville[["city", "rotations_par_jour", "part_temps_vide"]].round(2).to_string(index=False))


def q2_offre_insuffisante(s):
    titre("Q2 - Zones avec une offre insuffisante")
    # memes stations que Q1 ; une station vide 99 % du temps est hors service, pas un manque de velos
    s = s[(s["capacity"] >= 5) & (s["jours"] >= 7) & (s["part_temps_vide"] < 0.99)]
    z = s.assign(zone_lat=(s["latitude"] / 0.005).round() * 0.005, zone_lon=(s["longitude"] / 0.005).round() * 0.005)
    zones = z.groupby(["city", "zone_lat", "zone_lon"]).agg(
        nb_stations=("station_id", "count"), part_temps_vide=("part_temps_vide", "mean"),
        taux_remplissage=("taux_remplissage", "mean"),
        stations=("station_name", lambda n: ", ".join(sorted(map(str, n))[:3]))).reset_index()
    insuffisantes = zones[zones["part_temps_vide"] >= 0.25].sort_values("part_temps_vide", ascending=False)
    sauver_table(insuffisantes, P, "q2_zones_insuffisantes")
    print(f"{len(insuffisantes)} zones de 500 m ou les stations sont vides plus de 25 % du temps")
    print(insuffisantes.groupby("city").size().sort_values(ascending=False).to_string())


def q3_pics(profil):
    titre("Q3 - Pics d'utilisation dans la journee")
    par_heure = profil.groupby(level=["city", "h_locale"]).sum().unstack("city")
    part = par_heure / par_heure.sum() * 100
    part.index.name = "heure"
    pics = part.idxmax().rename("heure_de_pointe").reset_index()
    # deuxieme pic : le maximum en dehors de +/- 3 h du premier (matin / soir)
    pics["second_pic"] = [part[c].drop(range(p - 3, p + 4), errors="ignore").idxmax() for c, p in
                          zip(pics["city"], pics["heure_de_pointe"])]
    sauver_table(pics, P, "q3_heure_de_pointe")
    print(pics.to_string(index=False))
    sauver_table(part.stack().rename("part_mouvements").reset_index(), P, "q3_profil_horaire")
    sem = profil.groupby(level=["weekend", "h_locale"]).sum()
    sem = (sem / sem.groupby(level="weekend").transform("sum") * 100).rename("part_mouvements").reset_index()
    sem = sem.rename(columns={"h_locale": "heure"})
    sem["jour"] = sem.pop("weekend").map({False: "semaine", True: "week-end"})
    sauver_table(sem, P, "q3_semaine_weekend")


def q4_desequilibres(s, moment):
    titre("Q4 - Desequilibres geographiques")
    bandes = pd.cut(s["dist_centre_km"], [0, 2, 4, 6, 10, 50], labels=["0-2 km", "2-4", "4-6", "6-10", "+10"])
    s = s.assign(bande=bandes)
    remplissage = s.groupby(["city", "bande"], observed=True)["taux_remplissage"].mean()
    sauver_table(remplissage.rename("taux_remplissage").reset_index(), P, "q4_remplissage_par_distance")
    print(remplissage.unstack(1).round(2).to_string())

    m = moment.reset_index()
    m.columns = ["station_id", "moment", "somme", "n"]
    m["moment"] = m["moment"].map(dict(zip(MOMENTS, NOMS_MOMENTS)))
    m = m.merge(s[["station_id", "city", "bande"]], on="station_id")
    ms = m.groupby(["city", "moment", "bande"], observed=True)[["somme", "n"]].sum()
    ms["taux_remplissage"] = ms["somme"] / ms["n"]
    sauver_table(ms[["taux_remplissage"]].reset_index(), P, "q4_matin_soir")


def q5_critiques(s30, dernier, meta, periode):
    titre("Q5 - Stations critiques a reequilibrer (30 derniers jours de donnees)")
    print(periode.to_string())
    s = indicateurs(s30).join(meta[["city", "station_name", "latitude", "longitude", "capacite"]])
    s = s.join(dernier.rename(columns={"velos": "bikes_available", "places": "free_slots"})).reset_index()
    s = s.rename(columns={"capacite": "capacity"})
    # ville dont toutes les stations sont a 0 en ce moment : l'API ne publie pas les velos en direct,
    # l'etat actuel est inconnu (le diagnostic, lui, vient des jours ou la ville publiait)
    muettes = s.groupby("city")["bikes_available"].apply(lambda v: (v == 0).mean() > 0.95)
    muettes = list(muettes[muettes].index)
    if muettes:
        print("Etat actuel inconnu (nombre de velos non publie en direct) :", ", ".join(muettes))
        s.loc[s["city"].isin(muettes), ["bikes_available", "free_slots"]] = None
    s = s.join(periode.rename(columns={"min": "periode_debut", "max": "periode_fin"}), on="city")
    s["action"] = None
    s.loc[s["part_temps_vide"] >= 0.3, "action"] = "a remplir"
    s.loc[s["part_temps_plein"] >= 0.3, "action"] = "a vider"
    s["urgence"] = s[["part_temps_vide", "part_temps_plein"]].max(axis=1)
    # vide 99 % du temps ou plus : station hors service (comme en Q2), pas une station a remplir
    crit = s[s["action"].notna() & (s["capacity"] >= 5) & (s["part_temps_vide"] < 0.99)]
    crit = crit.sort_values("urgence", ascending=False)
    cols = ["city", "station_name", "action", "bikes_available", "free_slots", "capacity",
            "part_temps_vide", "part_temps_plein", "latitude", "longitude", "periode_debut", "periode_fin"]
    sauver_table(crit[cols], P, "q5_stations_critiques")
    print(crit.groupby(["city", "action"]).size().unstack(fill_value=0).to_string())


def usage_journalier(ville_heure):
    """Mouvements et velos disponibles par ville et par jour : la tendance sur toute la periode."""
    v = ville_heure.reset_index()
    v["date"] = v["heure"].dt.tz_convert("Europe/Paris").dt.tz_localize(None).dt.normalize()
    j = v.groupby(["city", "date"]).agg(mouvements=("mouvements", "sum"), velos_moyens=("velos", "mean"),
                                        heures=("heure", "size"), part_vide=("part_vide", "mean")).reset_index()
    j = j[j["heures"] >= 20].drop(columns="heures")  # jour incomplet : ignore
    # jour quasi sans mouvement (< 10 % de la mediane de la ville) : donnees figees dans l'archive, pas un vrai usage
    j = j[j["mouvements"] >= 0.1 * j.groupby("city")["mouvements"].transform("median")]
    sauver_table(j, P, "velos_journalier")


def main():
    titre("Lecture de la table horaire (silver/velos_horaire)")
    res = accumuler()
    if res is None:
        print("Pas de donnees. Lancer : python -m urbanhub.velos.historique puis python -m urbanhub.velos.nettoyer")
        return
    stations, stations30, profil, moment, ville_heure, dernier, periode = res
    exclues = villes_sans_donnees(stations)
    if exclues:
        print("Villes ignorees (l'API ne donne pas le nombre de velos) :", ", ".join(exclues))
    garder = ~stations["city"].isin(exclues)
    stations, stations30 = stations[garder], stations30[stations30.index.isin(stations.index)]
    profil = profil[~profil.index.get_level_values("city").isin(exclues)]
    ville_heure = ville_heure[~ville_heure.index.get_level_values("city").isin(exclues)]
    datalake.put_parquet("silver", "velos_ville_heure/velos_ville_heure.parquet", ville_heure.reset_index())

    debut, fin = ville_heure.index.get_level_values("heure").min(), ville_heure.index.get_level_values("heure").max()
    print(f"{len(stations):,} stations, du {debut:%Y-%m-%d} au {fin:%Y-%m-%d}")
    s = stats_stations(stations)
    sauver_table(s, P, "stations_resume")
    usage_journalier(ville_heure)
    q1_utilisation(s)
    q2_offre_insuffisante(s)
    q3_pics(profil)
    q4_desequilibres(s, moment)
    q5_critiques(stations30, dernier, stations, periode)
    print("\nPartie 2 terminee : indicateurs dans gold/velos/")


if __name__ == "__main__":
    main()
