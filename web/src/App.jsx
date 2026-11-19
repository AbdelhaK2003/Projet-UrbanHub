import { useEffect, useState } from "react";
import { Icones, useApi, heure } from "./outils.jsx";
import Accueil from "./pages/Accueil.jsx";
import Meteo from "./pages/Meteo.jsx";
import Mobilite from "./pages/Mobilite.jsx";
import Air from "./pages/Air.jsx";
import Croisement from "./pages/Croisement.jsx";
import DataLake from "./pages/DataLake.jsx";

const PAGES = [
  ["accueil", "Vue d'ensemble", Icones.accueil, Accueil],
  ["meteo", "Météo", Icones.meteo, Meteo],
  ["mobilite", "Mobilité", Icones.velo, Mobilite],
  ["air", "Qualité de l'air", Icones.air, Air],
  ["croisement", "Analyse croisée", Icones.croisement, Croisement],
  ["lac", "Data Lake", Icones.lac, DataLake],
];

export default function App() {
  const [page, setPage] = useState(() => location.hash.slice(1) || "accueil");
  useEffect(() => { location.hash = page; window.scrollTo(0, 0); }, [page]);
  const { data: etat } = useApi("/api/etat", 60);
  const Page = (PAGES.find((p) => p[0] === page) || PAGES[0])[3];

  return (
    <div className="app">
      <header className="barre-haut">
        <div className="barre-interieur">
          <button className="marque" onClick={() => setPage("accueil")}>Urban<span>Hub</span></button>
          <nav className="nav">
            {PAGES.map(([id, nom, icone]) => (
              <button key={id} className={page === id ? "actif" : ""} onClick={() => setPage(id)}>
                {icone}<span>{nom}</span>
              </button>
            ))}
          </nav>
          <div className="statut">
            <span className="point" />
            {etat?.velos ? `Direct · ${heure(etat.velos.derniere)}` : "Connexion…"}
          </div>
        </div>
      </header>
      <main className="main">
        <Page aller={setPage} />
      </main>
      <footer className="pied">
        Sources : <a href="https://open-meteo.com" target="_blank" rel="noreferrer">Open-Meteo</a> ·{" "}
        <a href="https://citybik.es" target="_blank" rel="noreferrer">CityBikes</a> (bike-share data by CityBikes contributors,{" "}
        <a href="https://data.citybik.es" target="_blank" rel="noreferrer">data.citybik.es</a>, ODbL) ·{" "}
        <a href="https://openaq.org" target="_blank" rel="noreferrer">OpenAQ</a>
      </footer>
    </div>
  );
}
