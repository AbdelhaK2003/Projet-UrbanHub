import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXE, BLEU, Bulle, COULEURS, Carte, ChoixVille, Filtres, GRILLE, Hero, Icones, Kpi, Vide, date, fmt, mois, pct, useApi } from "../outils.jsx";

const MOIS = ["janv", "févr", "mars", "avr", "mai", "juin", "juil", "août", "sept", "oct", "nov", "déc"];
const NOM_VARIABLE = { temperature: "Température", humidity: "Humidité", wind_speed: "Vent", pressure: "Pression",
  precipitation: "Pluie", cloud_cover: "Nuages" };

export default function Meteo() {
  const [ville, setVille] = useState("Paris");
  const [facteur, setFacteur] = useState("humidite (%)");
  const { data: anomalies } = useApi("/api/gold/meteo_q1_anomalies_journalieres", 600);
  const { data: periodes } = useApi("/api/gold/meteo_q1_periodes_anormales", 600);
  const { data: corr } = useApi("/api/gold/meteo_q2_correlations", 600);
  const { data: visi } = useApi("/api/gold/meteo_q2_visibilite_par_condition", 600);
  const { data: mensuel } = useApi("/api/gold/meteo_q3_temperature_mensuelle", 600);
  const { data: ecart } = useApi("/api/gold/meteo_q3_ecart_ete_hiver", 600);
  const { data: extremes } = useApi("/api/gold/meteo_q4_jours_extremes", 600);
  const { data: parVille } = useApi("/api/gold/meteo_q4_extremes_par_ville", 600);
  const { data: live } = useApi("/api/meteo/live", 300);

  // anomalies : moyenne par semaine pour garder un graphique lisible
  const semaines = useMemo(() => {
    if (!anomalies) return [];
    const g = {};
    anomalies.forEach((d) => {
      const t = new Date(d.date); t.setDate(t.getDate() - ((t.getDay() + 6) % 7));
      const k = t.toISOString().slice(0, 10);
      (g[k] ||= []).push(d.anomalie);
    });
    return Object.entries(g).map(([k, v]) => ({ semaine: k, anomalie: v.reduce((a, b) => a + b, 0) / v.length }));
  }, [anomalies]);

  const courbe = useMemo(() => {
    if (!mensuel) return [];
    const g = {};
    mensuel.forEach((d) => {
      if (d.city !== ville && d.city !== "France") return;
      (g[d.mois] ||= { mois: d.mois })[d.city === "France" ? "france" : "ville"] = d.temperature;
    });
    return Object.values(g).sort((a, b) => a.mois.localeCompare(b.mois));
  }, [mensuel, ville]);

  const types = useMemo(() => [...new Set((parVille || []).map((d) => d.type))].sort(), [parVille]);
  const extremesVilles = useMemo(() => {
    const g = {};
    (parVille || []).forEach((d) => { (g[d.city] ||= { city: d.city })[d.type] = d.nb_jours; });
    return Object.values(g).sort((a, b) => types.reduce((s, t) => s + (b[t] || 0) - (a[t] || 0), 0));
  }, [parVille, types]);

  const compte = (t) => (periodes || []).filter((p) => p.type === t).length;
  const max = ecart?.[0];
  const villeLive = live?.find((d) => d.city === ville);

  return (
    <>
      <Hero titre="Météo" puces={["Open-Meteo", "Nov. 2021 → aujourd'hui", "Horaire"]} />
      <div className="contenu">
        <div className="grille g4">
          <Kpi icone={Icones.thermo} label="Vagues de chaleur" valeur={fmt(compte("vague de chaleur"))} detail="≥ 3 jours nettement au-dessus de la normale" />
          <Kpi icone={Icones.meteo} label="Vagues de froid" valeur={fmt(compte("vague de froid"))} detail="≥ 3 jours nettement sous la normale" />
          <Kpi icone={Icones.alerte} label="Jours-ville extrêmes" valeur={fmt((parVille || []).reduce((s, d) => s + d.nb_jours, 0))} detail="Chaleur, gel, tempête, pluie, brouillard" />
          <Kpi icone={Icones.jauge} label="Plus fort écart été / hiver" valeur={fmt(max?.ecart, 1)} unite="°C" detail={max?.city} />
        </div>

        <Carte titre="Q1 · Anomalies de température"
               sousTitre="Écart à la normale de saison, par semaine">
          {semaines.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={semaines} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap={1}>
                <CartesianGrid stroke={GRILLE} vertical={false} />
                <XAxis dataKey="semaine" tickFormatter={mois} tick={AXE} axisLine={false} tickLine={false} minTickGap={50} />
                <YAxis tick={AXE} axisLine={false} tickLine={false} unit=" °C" width={56} />
                <ReferenceLine y={0} stroke="#b8c3d6" />
                <Tooltip cursor={{ fill: "#f3f8fe" }} content={<Bulle formatLabel={(l) => `Semaine du ${date(l)}`} formatValeur={(v) => (v > 0 ? "+" : "") + fmt(v, 1)} unite=" °C" />} />
                <Bar isAnimationActive={false} dataKey="anomalie" name="Écart à la normale" radius={[2, 2, 0, 0]}>
                  {semaines.map((d) => <Cell key={d.semaine} fill={d.anomalie >= 0 ? "#eb6834" : BLEU} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <Vide />}
        </Carte>

        <div className="grille g2">
          <Carte titre="Q1 · Périodes anormales">
            {periodes?.length ? (
              <div className="defile">
                <table className="tableau">
                  <thead><tr><th>Type</th><th>Début</th><th className="nb">Durée</th><th className="nb">Écart</th></tr></thead>
                  <tbody>
                    {[...periodes].sort((a, b) => b.debut.localeCompare(a.debut)).map((p) => (
                      <tr key={p.type + p.debut}>
                        <td><span className={`badge ${p.type.includes("chaleur") || p.type.includes("seche") ? "moyen" : "info"}`}>{p.type}</span></td>
                        <td>{date(p.debut)}</td>
                        <td className="nb">{p.duree_jours} j</td>
                        <td className="nb">{p.ecart_temp_moyen > 0 ? "+" : ""}{fmt(p.ecart_temp_moyen, 1)} °C</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <Vide />}
          </Carte>

          <Carte titre="Q2 · Météo et visibilité"
                 sousTitre="Part des heures sous 10 km de visibilité"
                 droite={<Filtres options={[["humidite (%)", "Humidité"], ["pluie (mm/h)", "Pluie"], ["nuages (%)", "Nuages"]]} valeur={facteur} onChange={setFacteur} />}>
            {visi?.length ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={visi.filter((d) => d.facteur === facteur).sort((a, b) => a.ordre - b.ordre)} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={GRILLE} vertical={false} />
                  <XAxis dataKey="classe" tick={AXE} axisLine={false} tickLine={false} />
                  <YAxis tick={AXE} axisLine={false} tickLine={false} tickFormatter={(v) => pct(v)} width={56} />
                  <Tooltip cursor={{ fill: "#f3f8fe" }} content={<Bulle formatValeur={(v) => pct(v, 1)} />} />
                  <Bar isAnimationActive={false} dataKey="part_visibilite_reduite" name="Visibilité sous 10 km" fill={BLEU} radius={[4, 4, 0, 0]} barSize={42} />
                </BarChart>
              </ResponsiveContainer>
            ) : <Vide />}
            {corr?.length > 0 && (
              <div className="legende" style={{ marginTop: 6 }}>
                {[...corr].sort((a, b) => Math.abs(b.correlation) - Math.abs(a.correlation)).map((c) => (
                  <span key={c.variable}>{NOM_VARIABLE[c.variable] || c.variable} <b>{c.correlation > 0 ? "+" : ""}{fmt(c.correlation, 2)}</b></span>
                ))}
              </div>
            )}
          </Carte>
        </div>

        <Carte titre="Q3 · Évolution saisonnière"
               sousTitre="Température mensuelle"
               droite={<ChoixVille valeur={ville} onChange={setVille} />}>
          {courbe.length ? (
            <>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={courbe} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={GRILLE} vertical={false} />
                  <XAxis dataKey="mois" tickFormatter={mois} tick={AXE} axisLine={false} tickLine={false} minTickGap={40} />
                  <YAxis tick={AXE} axisLine={false} tickLine={false} unit=" °C" width={56} />
                  <Tooltip content={<Bulle formatLabel={(l) => new Date(l).toLocaleDateString("fr-FR", { month: "long", year: "numeric" })} formatValeur={(v) => fmt(v, 1)} unite=" °C" />} />
                  <Line isAnimationActive={false} type="monotone" dataKey="ville" name={ville} stroke={BLEU} strokeWidth={2} dot={false} />
                  <Line isAnimationActive={false} type="monotone" dataKey="france" name="Moyenne 11 villes" stroke="#9aa7bd" strokeWidth={2} strokeDasharray="5 4" dot={false} />
                </LineChart>
              </ResponsiveContainer>
              <div className="legende">
                <span><i style={{ background: BLEU }} />{ville}</span>
                <span><i style={{ background: "#9aa7bd" }} />Moyenne 11 villes</span>
                {villeLive && <span style={{ marginLeft: "auto" }}>Maintenant à {ville} : <b>&nbsp;{fmt(villeLive.temperature, 1)} °C</b>, vent {fmt(villeLive.wind_speed)} km/h</span>}
              </div>
            </>
          ) : <Vide />}
        </Carte>

        <div className="grille g2">
          <Carte titre="Q4 · Jours extrêmes par ville">
            {extremesVilles.length ? (
              <>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={extremesVilles} layout="vertical" margin={{ left: 10, right: 12 }}>
                    <CartesianGrid stroke={GRILLE} horizontal={false} />
                    <XAxis type="number" tick={AXE} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="city" tick={AXE} axisLine={false} tickLine={false} width={90} />
                    <Tooltip cursor={{ fill: "#f3f8fe" }} content={<Bulle formatValeur={(v) => fmt(v)} unite=" j" />} />
                    {types.map((t, i) => <Bar isAnimationActive={false} key={t} dataKey={t} name={t} stackId="a" fill={COULEURS[i]} stroke="#fff" strokeWidth={1} barSize={16} />)}
                  </BarChart>
                </ResponsiveContainer>
                <div className="legende">{types.map((t, i) => <span key={t}><i style={{ background: COULEURS[i] }} />{t}</span>)}</div>
              </>
            ) : <Vide />}
          </Carte>

          <Carte titre="Q4 · Journées les plus extrêmes">
            {extremes?.length ? (
              <div className="defile">
                <table className="tableau">
                  <thead><tr><th>Date</th><th>Événement</th><th className="nb">Villes</th></tr></thead>
                  <tbody>
                    {extremes.slice(0, 15).map((e) => (
                      <tr key={e.date} title={e.villes}>
                        <td>{date(e.date)}</td>
                        <td>{e.type_principal}</td>
                        <td className="nb">{e.villes_en_extreme} / {e.villes_mesurees} <span style={{ color: "#7d8aa3" }}>({pct(e.part_villes)})</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <Vide />}
          </Carte>
        </div>
      </div>
    </>
  );
}
