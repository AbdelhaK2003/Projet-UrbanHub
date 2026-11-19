import { Fragment } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXE, Bulle, COULEURS, Carte, GRILLE, Hero, Icones, Kpi, Legende, NOMS_POLLUANTS, Vide, date, fmt, useApi } from "../outils.jsx";

const METEO = { temperature: "Température", humidity: "Humidité", wind_speed: "Vent", precipitation: "Pluie",
  pressure: "Pression", visibility: "Visibilité" };
const POLS = ["pm25", "pm10", "no2", "o3"];

// couleur divergente : bleu (lien negatif) -> gris (aucun lien) -> orange (lien positif)
function couleur(c) {
  const mel = (a, b, t) => a.map((x, i) => Math.round(x + (b[i] - x) * t));
  const gris = [238, 241, 246], bleu = [42, 120, 214], orange = [235, 104, 52];
  const t = Math.min(Math.abs(c) / 0.7, 1);
  const [r, g, b] = mel(gris, c < 0 ? bleu : orange, t);
  return { background: `rgb(${r},${g},${b})`, color: t > 0.55 ? "#fff" : "#0e1b33" };
}

export default function Croisement() {
  const { data: corr } = useApi("/api/gold/croisement_q1_correlation_meteo_pollution", 600);
  const { data: vent } = useApi("/api/gold/croisement_q1_pollution_selon_vent", 600);
  const { data: temp } = useApi("/api/gold/croisement_q1_pollution_selon_temperature", 600);
  const { data: usage } = useApi("/api/gold/croisement_q2_usage_selon_meteo", 600);
  const { data: favorables } = useApi("/api/gold/croisement_q3_conditions_favorables", 600);
  const { data: interactions } = useApi("/api/gold/croisement_q4_jours_interaction_forte", 600);

  const c = {};
  (corr || []).forEach((d) => { c[`${d.meteo}|${d.pollutant}`] = d.correlation; });
  const val = (m, p) => c[`${m}|${p}`];
  const polsPresents = POLS.filter((p) => Object.keys(c).some((k) => k.endsWith(`|${p}`)));

  return (
    <>
      <Hero titre="Analyse croisée" texte="Météo, pollution et vélos réunis heure par heure et ville par ville, pour comprendre comment ils s'influencent." />
      <div className="contenu">
        <div className="grille g4">
          <Kpi icone={Icones.vent} label="Vent et NO2" valeur={fmt(val("wind_speed", "no2"), 2)} detail="Négatif : le vent disperse la pollution" />
          <Kpi icone={Icones.thermo} label="Température et ozone" valeur={fmt(val("temperature", "o3"), 2)} detail="Positif : le soleil et la chaleur forment l'ozone" />
          <Kpi icone={Icones.meteo} label="Humidité et PM2.5" valeur={fmt(val("humidity", "pm25"), 2)} detail="Corrélation de rang (Spearman)" />
          <Kpi icone={Icones.velo} label="Heures vélo analysées" valeur={fmt((usage || []).filter((u) => u.facteur === "pluie").reduce((s, u) => s + u.nb_heures, 0))} detail="Q2 à Q4 demandent au moins 24 h de collecte vélo" />
        </div>

        <Carte titre="Q1 · Lien entre météo et pollution" sousTitre="Chaque case va de −1 à +1. Bleu : quand la météo augmente, la pollution baisse. Orange : elles montent ensemble.">
          {polsPresents.length ? (
            <div className="heat" style={{ gridTemplateColumns: `140px repeat(${polsPresents.length}, minmax(60px, 1fr))` }}>
              <div />
              {polsPresents.map((p) => <div key={p} className="tete">{NOMS_POLLUANTS[p]}</div>)}
              {Object.keys(METEO).map((m) => (
                <Fragment key={m}>
                  <div className="ligne-tete">{METEO[m]}</div>
                  {polsPresents.map((p) => {
                    const v = val(m, p);
                    return <div key={m + p} className="cel" style={couleur(v ?? 0)} title={`${METEO[m]} / ${NOMS_POLLUANTS[p]}`}>{v === undefined ? "–" : (v > 0 ? "+" : "") + fmt(v, 2)}</div>;
                  })}
                </Fragment>
              ))}
            </div>
          ) : <Vide />}
        </Carte>

        <div className="grille g2">
          <Carte titre="Q1 · Pollution selon la force du vent" sousTitre="Moyenne horaire en µg/m³. Plus le vent souffle, plus l'air est propre.">
            {vent?.length ? (
              <>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={vent} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
                    <CartesianGrid stroke={GRILLE} vertical={false} />
                    <XAxis dataKey="vent_kmh" tick={AXE} axisLine={false} tickLine={false} unit=" km/h" />
                    <YAxis tick={AXE} axisLine={false} tickLine={false} width={40} />
                    <Tooltip cursor={{ fill: "#f3f8fe" }} content={<Bulle formatLabel={(l) => `Vent ${l} km/h`} unite=" µg/m³" />} />
                    {["pm25", "no2"].map((p, i) => <Bar isAnimationActive={false} key={p} dataKey={p} name={NOMS_POLLUANTS[p]} fill={COULEURS[i]} radius={[4, 4, 0, 0]} barSize={22} />)}
                  </BarChart>
                </ResponsiveContainer>
                <Legende items={[["PM2.5", COULEURS[0]], ["NO2", COULEURS[1]]]} />
              </>
            ) : <Vide />}
          </Carte>
          <Carte titre="Q1 · Ozone selon la température" sousTitre="L'ozone se forme sous l'effet du soleil et de la chaleur.">
            {temp?.length ? (
              <ResponsiveContainer width="100%" height={262}>
                <BarChart data={temp} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={GRILLE} vertical={false} />
                  <XAxis dataKey="temperature_c" tick={AXE} axisLine={false} tickLine={false} unit=" °C" />
                  <YAxis tick={AXE} axisLine={false} tickLine={false} width={40} />
                  <Tooltip cursor={{ fill: "#f3f8fe" }} content={<Bulle formatLabel={(l) => `${l} °C`} unite=" µg/m³" />} />
                  <Bar isAnimationActive={false} dataKey="o3" name="O3" fill={COULEURS[0]} radius={[4, 4, 0, 0]} barSize={30} />
                </BarChart>
              </ResponsiveContainer>
            ) : <Vide />}
          </Carte>
        </div>

        <div className="grille g2">
          <Carte titre="Q2 · Usage des vélos selon la météo" sousTitre="Indice d'usage : 1 = utilisation habituelle à cette heure-là ; 1,2 = 20 % de plus.">
            {usage?.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={usage.map((u) => ({ ...u, nom: `${u.facteur === "temperature (C)" ? "" : u.facteur + " "}${u.classe}${u.facteur === "temperature (C)" ? " °C" : ""}` }))} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={GRILLE} vertical={false} />
                  <XAxis dataKey="nom" tick={{ ...AXE, fontSize: 11 }} axisLine={false} tickLine={false} interval={0} angle={-30} textAnchor="end" height={60} />
                  <YAxis tick={AXE} axisLine={false} tickLine={false} width={40} />
                  <ReferenceLine y={1} stroke="#b8c3d6" />
                  <Tooltip cursor={{ fill: "#f3f8fe" }} content={<Bulle formatValeur={(v) => fmt(v, 2)} />} />
                  <Bar isAnimationActive={false} dataKey="indice_usage" name="Indice d'usage" fill={COULEURS[0]} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <Vide>Disponible après au moins 24 heures de collecte vélo (idéalement une semaine). Les collecteurs tournent : revenir plus tard.</Vide>}
          </Carte>
          <Carte titre="Q3 · Conditions favorables au vélo" sousTitre="Combinaisons température, pluie et vent où l'on roule le plus.">
            {favorables?.length ? (
              <div className="defile">
                <table className="tableau">
                  <thead><tr><th>Température</th><th>Ciel</th><th>Vent</th><th className="nb">Indice</th></tr></thead>
                  <tbody>
                    {favorables.slice(0, 10).map((f, i) => (
                      <tr key={i}><td>{f.classe_temp} °C</td><td>{f.pluie}</td><td>{f.classe_vent}</td><td className="nb"><b>{fmt(f.indice_usage_moyen, 2)}</b></td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <Vide>Disponible après au moins 24 heures de collecte vélo.</Vide>}
          </Carte>
        </div>

        <Carte titre="Q4 · Jours d'interaction forte" sousTitre="Jours où l'usage des vélos, la pollution et la météo s'écartent tous fortement de la normale en même temps.">
          {interactions?.length ? (
            <table className="tableau">
              <thead><tr><th>Date</th><th>Ville</th><th className="nb">Usage vélo</th><th className="nb">Pollution</th><th className="nb">Température</th><th className="nb">Pluie</th></tr></thead>
              <tbody>
                {interactions.map((d, i) => (
                  <tr key={i}><td>{date(d.date)}</td><td>{d.city}</td><td className="nb">{fmt(d.usage, 2)}</td><td className="nb">{fmt(d.pollution, 1)}</td>
                    <td className="nb">{fmt(d.temperature, 1)} °C</td><td className="nb">{fmt(d.pluie, 1)} mm</td></tr>
                ))}
              </tbody>
            </table>
          ) : <Vide>Aucun jour détecté pour l'instant : il faut plusieurs jours de collecte vélo.</Vide>}
        </Carte>
      </div>
    </>
  );
}
