"""Tableau de bord UrbanHub (utile pour les videos de demo).

Lancer : streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from urbanhub import config, datalake  # noqa: E402

RAPPORTS = config.FIGURES.parent

st.set_page_config(page_title="UrbanHub", layout="wide")
st.title("UrbanHub, le jumeau numerique urbain")
st.caption("Meteo (NOAA), velos en libre-service (CityBikes) et pollution (OpenAQ) des grandes villes francaises")

# Pour chaque partie : (titre de la question, nom du graphique, nom du tableau, explication)
QUESTIONS = {
    "meteo": [
        ("Q1 - Periodes meteorologiques anormales", "q1_anomalies_temperature", "q1_periodes_anormales",
         "Ecart de chaque jour a la normale de saison. Rouge = anormalement chaud, bleu = anormalement froid. "
         "Le tableau liste les periodes d'au moins 3 jours."),
        ("Q2 - Meteo et visibilite", "q2_visibilite", "q2_correlations",
         "A gauche les correlations entre variables, a droite la visibilite selon l'intensite de la pluie."),
        ("Q3 - Evolution saisonniere de la temperature", "q3_saisons", "q3_profil_saisonnier_villes",
         "Temperature moyenne mois par mois (gauche) et cycle moyen sur une annee pour chaque ville (droite)."),
        ("Q4 - Jours aux conditions extremes", "q4_extremes_par_mois", "q4_jours_extremes",
         "Nombre de stations en situation extreme par mois. Le tableau classe les 20 jours les plus extremes."),
    ],
    "velos": [
        ("Q1 - Stations les plus utilisees", "q1_top_stations", "q1_top_stations",
         "Rotations = mouvements de velos divises par la capacite de la station, par jour."),
        ("Q2 - Zones avec une offre insuffisante", "q2_carte_stations_vides", "q2_zones_insuffisantes",
         "Plus le point est rouge, plus la station est souvent vide. Le tableau liste les carres de 500 m "
         "vides plus de 25 % du temps."),
        ("Q3 - Pics d'utilisation journaliers", "q3_pics_journaliers", "q3_heure_de_pointe",
         "Part des mouvements de la journee faite a chaque heure."),
        ("Q4 - Desequilibres geographiques", "q4_desequilibres", "q4_remplissage_par_distance",
         "Taux de remplissage selon la distance au centre-ville, et comparaison matin / soir."),
        ("Q5 - Stations critiques a reequilibrer", "q5_stations_critiques", "q5_stations_critiques",
         "Rouge = a remplir (souvent vide), bleu = a vider (souvent pleine)."),
    ],
    "pollution": [
        ("Q1 - Zones les plus polluees", "q1_zones_polluees", "q1_niveaux_par_zone",
         "Moyenne par station de mesure. La ligne rouge est la valeur guide de l'OMS."),
        ("Q2 - Variation journaliere", "q2_variation_journaliere", "q2_profil_horaire",
         "100 = moyenne de la journee. Le NO2 suit le trafic, l'ozone suit le soleil."),
        ("Q3 - Polluants dominants", "q3_polluants_dominants", "q3_polluants_dominants",
         "Concentration divisee par la valeur OMS : 1 = la limite conseillee."),
        ("Q4 - Episodes de pollution anormale", "q4_episodes", "q4_episodes",
         "Au moins 6 heures au-dessus de la valeur OMS ou des 1 % de valeurs les plus hautes de la ville."),
    ],
    "croisement": [
        ("Q1 - Meteo et pollution", "q1_meteo_pollution", "q1_correlation_meteo_pollution",
         "Correlation negative = quand la variable meteo monte, la pollution baisse."),
        ("Q2 - Meteo et usage des velos", "q2_meteo_velos", "q2_correlation_meteo_velos",
         "Indice d'usage : 1 = usage habituel a cette heure-la, 1,2 = 20 % de plus."),
        ("Q3 - Conditions favorables a la mobilite douce", "q3_conditions_favorables", "q3_conditions_favorables",
         "Combinaisons temperature x pluie x vent classees par indice d'usage."),
        ("Q4 - Periodes d'interaction forte", "q4_interactions", "q4_jours_interaction_forte",
         "Jours ou velos, pollution et meteo s'ecartent tous les trois de la normale."),
    ],
}


def afficher_partie(partie):
    for titre, figure, table, explication in QUESTIONS[partie]:
        st.subheader(titre)
        st.caption(explication)
        img = config.FIGURES / f"{partie}_{figure}.png"
        csv = RAPPORTS / f"{partie}_{table}.csv"
        if img.exists():
            st.image(str(img), width="stretch")
        else:
            st.info("Pas encore de resultat pour cette question (donnees insuffisantes ou analyse non lancee).")
        if csv.exists():
            with st.expander("Voir le tableau de resultats"):
                st.dataframe(pd.read_csv(csv), width="stretch", hide_index=True)
        st.divider()


@st.cache_data(ttl=120)
def derniere_photo_velos():
    cles = sorted(datalake.lister("bronze", "velos/citybikes/"))
    if not cles:
        return pd.DataFrame(), None, 0
    snap = datalake.get_json("bronze", cles[-1])
    lignes = [{"city": r["city"], "station": s.get("name"), "lat": s.get("latitude"), "lon": s.get("longitude"),
               "velos": s.get("free_bikes"), "places": s.get("empty_slots")}
              for r in snap["networks"] for s in r["stations"]]
    return pd.DataFrame(lignes), snap["collected_at"], len(cles)


@st.cache_data(ttl=300)
def contenu_datalake():
    lignes = []
    s3 = datalake.client()
    for bucket in datalake.BUCKETS:
        pages = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket)
        for page in pages:
            for o in page.get("Contents", []):
                parties = o["Key"].split("/")
                lignes.append({"bucket": bucket, "dossier": "/".join(parties[:2]), "taille": o["Size"]})
    df = pd.DataFrame(lignes)
    if df.empty:
        return df
    res = df.groupby(["bucket", "dossier"]).agg(fichiers=("taille", "size"), taille_mo=("taille", "sum")).reset_index()
    res["taille_mo"] = (res["taille_mo"] / 1e6).round(1)
    return res


onglets = st.tabs(["Temps reel", "1 Meteo", "2 Velos", "3 Pollution", "4 Croisement", "Data Lake"])

with onglets[0]:
    try:
        velos, quand, nb = derniere_photo_velos()
    except Exception as e:
        st.error(f"MinIO inaccessible : {e}")
        velos, quand, nb = pd.DataFrame(), None, 0
    if velos.empty:
        st.info("Aucune collecte velos pour l'instant.")
    else:
        st.write(f"Derniere collecte : {quand} (UTC). {nb} collectes enregistrees depuis le debut.")
        villes = sorted(velos.loc[velos["velos"].fillna(0) > 0, "city"].unique())
        ville = st.selectbox("Ville", villes, index=villes.index("Paris") if "Paris" in villes else 0)
        v = velos[velos["city"] == ville].dropna(subset=["lat", "lon"])
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Stations", len(v))
        c2.metric("Velos disponibles", int(v["velos"].sum()))
        c3.metric("Stations vides", int((v["velos"] == 0).sum()))
        c4.metric("Stations pleines", int((v["places"] == 0).sum()))
        v = v.assign(couleur=v["velos"].apply(lambda n: "#d62728" if n == 0 else "#2ca02c"))
        st.map(v, latitude="lat", longitude="lon", color="couleur", size=30)
        st.caption("Vert = velos disponibles, rouge = station vide.")
        st.dataframe(v.sort_values("velos")[["station", "velos", "places"]], width="stretch", hide_index=True)

for onglet, partie in zip(onglets[1:5], ["meteo", "velos", "pollution", "croisement"]):
    with onglet:
        afficher_partie(partie)

with onglets[5]:
    st.write("Contenu des trois couches du Data Lake (MinIO). Console complete : http://localhost:9011")
    try:
        dl = contenu_datalake()
        for bucket, explication in [("bronze", "donnees brutes, telles que recues"),
                                    ("silver", "donnees nettoyees au format Parquet"),
                                    ("gold", "indicateurs et graphiques")]:
            st.subheader(f"{bucket} : {explication}")
            st.dataframe(dl[dl["bucket"] == bucket].drop(columns="bucket"), width="stretch", hide_index=True)
    except Exception as e:
        st.error(f"MinIO inaccessible : {e}")
