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
      <Hero titre="Analyse croisée" puces={["Ville × heure", "Q1 : nov. 2023 → aujourd'hui", "Q2 à Q4 : nov. 2024 → aujourd'hui"]} />
      <div className="contenu">
        <div className="grille g4">
          <Kpi icone={Icones.vent} label="Vent et NO2" valeur={fmt(val("wind_speed", "no2"), 2)} detail="Corrélation" />
          <Kpi icone={Icones.thermo} label="Température et ozone" valeur={fmt(val("temperature", "o3"), 2)} detail="Corrélation" />
          <Kpi icone={Icones.meteo} label="Humidité et PM2.5" valeur={fmt(val("humidity", "pm25"), 2)} detail="Corrélation" />
          <Kpi icone={Icones.velo} label="Heures ville analysées" valeur={fmt((usage || []).filter((u) => u.facteur === "pluie").reduce((s, u) => s + u.nb_heures, 0))} detail="Météo + vélos" />
        </div>

        <Carte titre="Q1 · Météo et pollution" sousTitre="Corrélation de −1 (bleu) à +1 (orange)">
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
          <Carte titre="Pollution selon le vent" sousTitre="µg/m³">
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
          <Carte titre="Ozone selon la température" sousTitre="µg/m³">
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
          <Carte titre="Q2 · Météo et usage des vélos" sousTitre="Indice d'usage (1 = habituel)">
            {usage?.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={[...usage].sort((a, b) => a.facteur.localeCompare(b.facteur) || a.ordre - b.ordre).map((u) => ({ ...u, nom: u.facteur === "temperature (C)" ? `${u.classe} °C` : u.facteur === "vent" ? `vent ${u.classe}` : u.classe }))} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
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
          <Carte titre="Q3 · Conditions favorables au vélo">
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

        <Carte titre="Q4 · Interactions fortes" sousTitre={`${fmt(interactions?.length)} jours détectés · les plus récents`}>
          {interactions?.length ? (
            <div className="defile"><table className="tableau">
              <thead><tr><th>Date</th><th>Ville</th><th className="nb">Indice vélo</th><th className="nb">NO2 (µg/m³)</th><th className="nb">Température</th><th className="nb">Pluie</th></tr></thead>
              <tbody>
                {[...interactions].sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, 30).map((d, i) => (
                  <tr key={i}><td>{date(d.date)}</td><td>{d.city}</td><td className="nb">{fmt(d.usage, 2)}</td><td className="nb">{fmt(d.pollution, 1)}</td>
                    <td className="nb">{fmt(d.temperature, 1)} °C</td><td className="nb">{fmt(d.pluie, 1)} mm</td></tr>
                ))}
              </tbody>
            </table></div>
          ) : <Vide>Aucun jour détecté pour l'instant : il faut plusieurs jours de collecte vélo.</Vide>}
        </Carte>
      </div>
    </>
  );
}
