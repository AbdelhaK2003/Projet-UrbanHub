"""Tableau de bord UrbanHub (utile pour les videos de demo).

Lancer : streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from urbanhub import config, datalake  # noqa: E402

st.set_page_config(page_title="UrbanHub", layout="wide")
st.title("UrbanHub, le jumeau numerique urbain")
st.caption("Meteo (NOAA), velos en libre-service (CityBikes) et pollution (OpenAQ) des grandes villes francaises")


def figures(partie):
    images = sorted(config.FIGURES.glob(f"{partie}_*.png"))
    if not images:
        st.info("Pas encore de graphique. Lancer le script d'analyse de cette partie.")
    for img in images:
        st.image(str(img), width="stretch")


@st.cache_data(ttl=120)
def derniere_photo_velos():
    cles = sorted(datalake.lister("bronze", "velos/citybikes/"))
    if not cles:
        return pd.DataFrame(), None
    snap = datalake.get_json("bronze", cles[-1])
    lignes = [{"city": r["city"], "station": s.get("name"), "lat": s.get("latitude"), "lon": s.get("longitude"),
               "velos": s.get("free_bikes"), "places": s.get("empty_slots")}
              for r in snap["networks"] for s in r["stations"]]
    return pd.DataFrame(lignes), snap["collected_at"]


onglets = st.tabs(["Temps reel", "1 Meteo", "2 Velos", "3 Pollution", "4 Croisement"])

with onglets[0]:
    try:
        velos, quand = derniere_photo_velos()
    except Exception as e:
        st.error(f"MinIO inaccessible : {e}")
        velos, quand = pd.DataFrame(), None
    if velos.empty:
        st.info("Aucune collecte velos pour l'instant.")
    else:
        st.write(f"Derniere collecte : {quand} (UTC)")
        ville = st.selectbox("Ville", sorted(velos["city"].unique()))
        v = velos[velos["city"] == ville].dropna(subset=["lat", "lon"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Stations", len(v))
        c2.metric("Velos disponibles", int(v["velos"].sum()))
        c3.metric("Stations vides", int((v["velos"] == 0).sum()))
        v = v.assign(couleur=v["velos"].apply(lambda n: "#d62728" if n == 0 else "#2ca02c"))
        st.map(v, latitude="lat", longitude="lon", color="couleur", size=30)
        st.dataframe(v.sort_values("velos")[["station", "velos", "places"]], width="stretch")

for onglet, partie in zip(onglets[1:], ["meteo", "velos", "pollution", "croisement"]):
    with onglet:
        figures(partie)
