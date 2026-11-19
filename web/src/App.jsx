import { useEffect, useState } from "react";
import { Icones, useApi, dateHeure } from "./outils.jsx";
import Accueil from "./pages/Accueil.jsx";
import Meteo from "./pages/Meteo.jsx";
import Mobilite from "./pages/Mobilite.jsx";
import Air from "./pages/Air.jsx";
import Croisement from "./pages/Croisement.jsx";
import DataLake from "./pages/DataLake.jsx";

const PAGES = [
  ["accueil", "Vue d'ensemble", Icones.accueil, Accueil],
  ["meteo", "Météo", Icones.meteo, Meteo],
  ["mobilite", "Mobilité vélo", Icones.velo, Mobilite],
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
      <aside className="sidebar">
        <div className="logo">
          <div className="logo-mark">U</div>
          <div className="logo-text">Urban<span>Hub</span></div>
        </div>
        <nav className="nav">
          {PAGES.map(([id, nom, icone]) => (
            <button key={id} className={page === id ? "actif" : ""} onClick={() => setPage(id)}>
              {icone} {nom}
            </button>
          ))}
        </nav>
        <div className="sidebar-bas">
          Jumeau numérique des grandes villes françaises
          {etat?.velos && <div style={{ marginTop: 8 }}>Dernière collecte vélos : {dateHeure(etat.velos.derniere)}</div>}
        </div>
      </aside>
      <main className="main">
        <Page aller={setPage} />
      </main>
    </div>
  );
}
