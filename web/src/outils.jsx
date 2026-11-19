// Petits outils partages par toutes les pages : appels a l'API, formats, cartes, graphiques.
import { useEffect, useState } from "react";

// Couleurs des series (ordre fixe : une serie garde toujours la meme couleur)
export const COULEURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"];
export const BLEU = "#2a78d6";
export const GRILLE = "#edf1f7";
export const AXE = { fontSize: 12, fill: "#7d8aa3" };
export const VILLES = ["Paris", "Lyon", "Marseille", "Toulouse", "Nice", "Nantes", "Strasbourg",
  "Montpellier", "Bordeaux", "Lille", "Rennes"];
export const OMS = { pm25: 15, pm10: 45, no2: 25, o3: 100, co: 4000 };
export const NOMS_POLLUANTS = { pm25: "PM2.5", pm10: "PM10", no2: "NO2", o3: "O3", co: "CO" };

// Lit une route de l'API et la relit toutes les "secondes" (temps reel)
export function useApi(chemin, secondes = 60) {
  const [etat, setEtat] = useState({ data: null, erreur: null, charge: true });
  useEffect(() => {
    if (!chemin) return;
    let actif = true;
    const lire = () =>
      fetch(chemin)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
        .then((data) => actif && setEtat({ data, erreur: null, charge: false }))
        .catch((e) => actif && setEtat((s) => ({ ...s, erreur: e.message, charge: false })));
    lire();
    const id = setInterval(lire, secondes * 1000);
    return () => { actif = false; clearInterval(id); };
  }, [chemin, secondes]);
  return etat;
}

const nf = (d) => new Intl.NumberFormat("fr-FR", { maximumFractionDigits: d, minimumFractionDigits: 0 });
export const fmt = (v, d = 0) => (v === null || v === undefined || Number.isNaN(v) ? "–" : nf(d).format(v));
export const pct = (v, d = 0) => (v === null || v === undefined ? "–" : `${nf(d).format(v * 100)} %`);
export const date = (iso) => (iso ? new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" }) : "–");
export const heure = (iso) => (iso ? new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) : "–");
export const dateHeure = (iso) => (iso ? new Date(iso).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "–");
export const mois = (iso) => new Date(iso).toLocaleDateString("fr-FR", { month: "short", year: "2-digit" });

export function Carte({ titre, sousTitre, droite, children, className = "" }) {
  return (
    <div className={`carte ${className}`}>
      <div className="carte-haut">
        <div>
          <h3>{titre}</h3>
          {sousTitre && <p className="sous-titre">{sousTitre}</p>}
        </div>
        {droite}
      </div>
      {children}
    </div>
  );
}

export function Kpi({ label, valeur, unite, detail, icone }) {
  return (
    <div className="carte kpi">
      <div className="kpi-label">
        <span className="kpi-icone">{icone}</span>
        {label}
      </div>
      <div className="kpi-valeur">
        {valeur}
        {unite && <small>{unite}</small>}
      </div>
      {detail && <div className="kpi-detail">{detail}</div>}
    </div>
  );
}

export function Vide({ children }) {
  return <div className="vide">{children || "Pas encore de données. Lancer le pipeline : python -m urbanhub.pipeline"}</div>;
}

export function Hero({ titre, puces = [] }) {
  return (
    <div className="hero">
      <div className="hero-haut">
        <h1>{titre}</h1>
        <div className="puces">{puces.filter(Boolean).map((p) => <span key={p} className="puce">{p}</span>)}</div>
      </div>
    </div>
  );
}

export function Filtres({ options, valeur, onChange }) {
  return (
    <div className="filtres">
      {options.map((o) => {
        const [v, l] = Array.isArray(o) ? o : [o, o];
        return (
          <button key={v} className={v === valeur ? "actif" : ""} onClick={() => onChange(v)}>
            {l}
          </button>
        );
      })}
    </div>
  );
}

export function ChoixVille({ valeur, onChange, villes = VILLES }) {
  return (
    <select value={valeur} onChange={(e) => onChange(e.target.value)}>
      {villes.map((v) => <option key={v}>{v}</option>)}
    </select>
  );
}

// Infobulle des graphiques
export function Bulle({ active, payload, label, formatLabel = (l) => l, formatValeur = (v) => fmt(v, 1), unite = "" }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <b>{formatLabel(label)}</b>
      {payload.map((p) => (
        <div key={p.dataKey}>
          <i style={{ background: p.color || p.fill }} /> {p.name} : <strong>{formatValeur(p.value)}{unite}</strong>
        </div>
      ))}
    </div>
  );
}

export function Legende({ items }) {
  return (
    <div className="legende">
      {items.map(([nom, couleur]) => (
        <span key={nom}><i style={{ background: couleur }} />{nom}</span>
      ))}
    </div>
  );
}

// Badge de qualite par rapport a la valeur guide OMS
export function BadgeOms({ ratio }) {
  if (ratio === null || ratio === undefined) return <span className="badge info">–</span>;
  const cls = ratio <= 1 ? "bon" : ratio <= 2 ? "moyen" : "mauvais";
  const txt = ratio <= 1 ? "sous la valeur OMS" : `${fmt(ratio, 1)} × OMS`;
  return <span className={`badge ${cls}`}>{txt}</span>;
}

// Icones (traits simples)
const I = (d) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
);
export const Icones = {
  accueil: I(<><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" /></>),
  meteo: I(<><path d="M17.5 19a4.5 4.5 0 1 0-1.4-8.8A6 6 0 0 0 4.5 13 3.5 3.5 0 0 0 6 19z" /></>),
  velo: I(<><circle cx="6" cy="17" r="3.5" /><circle cx="18" cy="17" r="3.5" /><path d="M6 17l4-8h5l3 8M10 9 8.5 6H6M15 9l-3 8" /></>),
  air: I(<><path d="M3 8h11a3 3 0 1 0-3-3" /><path d="M3 12h16a3 3 0 1 1-3 3" /><path d="M3 16h7" /></>),
  croisement: I(<><circle cx="9" cy="12" r="6" /><circle cx="15" cy="12" r="6" /></>),
  lac: I(<><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>),
  thermo: I(<><path d="M14 14.8V4a2 2 0 1 0-4 0v10.8a4 4 0 1 0 4 0z" /></>),
  alerte: I(<><path d="M12 3 2 20h20z" /><path d="M12 10v4M12 17h.01" /></>),
  station: I(<><path d="M12 21s-7-6.2-7-11a7 7 0 1 1 14 0c0 4.8-7 11-7 11z" /><circle cx="12" cy="10" r="2.5" /></>),
  jauge: I(<><path d="M4 18a8 8 0 1 1 16 0" /><path d="m12 18 4-6" /></>),
  lien: I(<><path d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" /><path d="M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" /></>),
  vent: I(<><path d="M3 8h10a3 3 0 1 0-3-3M3 16h13a3 3 0 1 1-3 3M3 12h17" /></>),
};
