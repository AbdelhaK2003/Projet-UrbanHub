import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXE, BLEU, BadgeOms, Bulle, COULEURS, Carte, ChoixVille, Filtres, GRILLE, Hero, Icones, Kpi, Legende, NOMS_POLLUANTS, OMS, Vide, date, dateHeure, fmt, mois, useApi } from "../outils.jsx";

const POLS = ["pm25", "pm10", "no2", "o3"];

export default function Air() {
  const [ville, setVille] = useState("Paris");
  const [pol, setPol] = useState("no2");
  const { data: live } = useApi("/api/pollution/live", 120);
  const { data: k } = useApi("/api/kpis", 120);
  const { data: jour } = useApi(`/api/gold/pollution_pollution_journaliere?city=${encodeURIComponent(ville)}`, 600);
  const { data: profil } = useApi("/api/gold/pollution_q2_profil_horaire", 600);
  const { data: zones } = useApi("/api/gold/pollution_q1_niveaux_par_zone", 600);
  const { data: dominants } = useApi("/api/gold/pollution_q3_polluants_dominants", 600);
  const { data: ratios } = useApi("/api/gold/pollution_q3_ratio_oms_par_ville", 600);
  const { data: episodes } = useApi("/api/gold/pollution_q4_episodes", 600);
  const { data: depassements } = useApi(`/api/gold/pollution_jours_depassement_oms?city=${encodeURIComponent(ville)}`, 600);

  // tableau temps reel : une ligne par ville, une colonne par polluant
  const tableauLive = useMemo(() => {
    const g = {};
    (live || []).forEach((d) => { (g[d.city] ||= { city: d.city })[d.pollutant] = d; });
    return Object.values(g).sort((a, b) => a.city.localeCompare(b.city));
  }, [live]);

  // tendance : moyenne mensuelle du polluant choisi
  const tendance = useMemo(() => {
    const g = {};
    (jour || []).filter((d) => d.pollutant === pol).forEach((d) => {
      const m = d.date.slice(0, 7) + "-01";
      (g[m] ||= []).push(d.valeur);
    });
    return Object.entries(g).sort().map(([m, v]) => ({ mois: m, valeur: v.reduce((a, b) => a + b, 0) / v.length }));
  }, [jour, pol]);

  const profilLarge = useMemo(() => {
    const g = {};
    (profil || []).forEach((d) => { (g[d.heure] ||= { heure: d.heure })[d.pollutant] = d.indice; });
    return Object.values(g).sort((a, b) => a.heure - b.heure);
  }, [profil]);

  const ratiosVilles = useMemo(() => (ratios || []).filter((d) => d.pollutant === pol).sort((a, b) => b.ratio_oms - a.ratio_oms), [ratios, pol]);
  const topZones = (zones || []).filter((d) => d.pollutant === pol).sort((a, b) => b.moyenne - a.moyenne).slice(0, 10);
  const dep = (depassements || []).filter((d) => d.pollutant === pol).sort((a, b) => a.annee - b.annee);
  const derniers = (episodes || []).slice(0, 12);
  const choixPol = POLS.map((p) => [p, NOMS_POLLUANTS[p]]);

  return (
    <>
      <Hero titre="Qualité de l'air" puces={["OpenAQ", "Nov. 2023 → aujourd'hui", "Direct · 15 min"]} />
      <div className="contenu">
        <div className="grille g4">
          <Kpi icone={Icones.air} label="PM2.5 (24 h)" valeur={fmt(k?.pollution?.pm25, 1)} unite="µg/m³" detail="OMS : 15" />
          <Kpi icone={Icones.air} label="NO2 (24 h)" valeur={fmt(k?.pollution?.no2, 1)} unite="µg/m³" detail="OMS : 25" />
          <Kpi icone={Icones.meteo} label="Ozone O3 (24 h)" valeur={fmt(k?.pollution?.o3, 1)} unite="µg/m³" detail="OMS : 100" />
          <Kpi icone={Icones.alerte} label="Épisodes de pollution" valeur={fmt(k?.pollution?.episodes_30j)} detail="30 derniers jours" />
        </div>

        <Carte titre="Par ville · 24 h">
          {tableauLive.length ? (
            <div style={{ overflowX: "auto" }}>
              <table className="tableau">
                <thead><tr><th>Ville</th>{POLS.map((p) => <th key={p}>{NOMS_POLLUANTS[p]}</th>)}</tr></thead>
                <tbody>
                  {tableauLive.map((l) => (
                    <tr key={l.city}>
                      <td><b>{l.city}</b></td>
                      {POLS.map((p) => (
                        <td key={p}>{l[p] ? <><span style={{ display: "inline-block", minWidth: 44 }}>{fmt(l[p].valeur, 1)}</span><BadgeOms ratio={l[p].ratio_oms} /></> : <span style={{ color: "#7d8aa3" }}>–</span>}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <Vide />}
        </Carte>

        <div className="carte" style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 20px", flexWrap: "wrap" }}>
          <span style={{ color: "#4a5a78" }}>Polluant</span>
          <Filtres options={choixPol} valeur={pol} onChange={setPol} />
          <span style={{ color: "#4a5a78", marginLeft: 12 }}>Ville</span>
          <ChoixVille valeur={ville} onChange={setVille} />
        </div>

        <div className="grille g3">
          <Carte className="large" titre={`Tendance ${NOMS_POLLUANTS[pol]} · ${ville}`} sousTitre="Moyenne mensuelle · ligne rouge = OMS">
            {tendance.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={tendance} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={GRILLE} vertical={false} />
                  <XAxis dataKey="mois" tickFormatter={mois} tick={AXE} axisLine={false} tickLine={false} minTickGap={40} />
                  <YAxis tick={AXE} axisLine={false} tickLine={false} width={48} />
                  <Tooltip content={<Bulle formatLabel={(l) => new Date(l).toLocaleDateString("fr-FR", { month: "long", year: "numeric" })} formatValeur={(v) => fmt(v, 1)} unite=" µg/m³" />} />
                  <ReferenceLine y={OMS[pol]} stroke="#d13b3b" strokeDasharray="4 4" />
                  <Line isAnimationActive={false} type="monotone" dataKey="valeur" name={NOMS_POLLUANTS[pol]} stroke={BLEU} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : <Vide>Pas de capteur de {NOMS_POLLUANTS[pol]} à {ville}.</Vide>}
          </Carte>
          <Carte titre="Jours au-dessus de l'OMS">
            {dep.length ? (
              <table className="tableau">
                <thead><tr><th>Année</th><th className="nb">Jours</th><th>Part</th></tr></thead>
                <tbody>
                  {dep.map((d) => (
                    <tr key={d.annee}><td>{d.annee}</td><td className="nb"><b>{d.jours_depassement}</b> / {d.nb_jours}</td>
                      <td><div className="barre"><div style={{ width: `${d.part_jours_depassement * 100}%` }} /></div></td></tr>
                  ))}
                </tbody>
              </table>
            ) : <Vide />}
          </Carte>
        </div>

        <div className="grille g2">
          <Carte titre="Q1 · Zones les plus polluées" sousTitre={`Top 10 · ${NOMS_POLLUANTS[pol]}`}>
            {topZones.length ? (
              <div className="defile">
                <table className="tableau">
                  <thead><tr><th>Station</th><th>Ville</th><th className="nb">Moyenne</th><th>OMS</th></tr></thead>
                  <tbody>
                    {topZones.map((z) => (
                      <tr key={z.location_id}><td>{z.location_name}</td><td>{z.city}</td>
                        <td className="nb">{fmt(z.moyenne, 1)}</td><td><BadgeOms ratio={z.ratio_oms} /></td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <Vide />}
          </Carte>

          <Carte titre="Q2 · Variation journalière" sousTitre="100 = moyenne de la journée">
            {profilLarge.length ? (
              <>
                <ResponsiveContainer width="100%" height={230}>
                  <LineChart data={profilLarge} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke={GRILLE} vertical={false} />
                    <XAxis dataKey="heure" tick={AXE} axisLine={false} tickLine={false} unit=" h" />
                    <YAxis tick={AXE} axisLine={false} tickLine={false} width={40} domain={["auto", "auto"]} />
                    <ReferenceLine y={100} stroke="#b8c3d6" />
                    <Tooltip content={<Bulle formatLabel={(l) => `${l} h`} formatValeur={(v) => fmt(v)} />} />
                    {POLS.map((p, i) => <Line isAnimationActive={false} key={p} type="monotone" dataKey={p} name={NOMS_POLLUANTS[p]} stroke={COULEURS[i]} strokeWidth={p === pol ? 3 : 1.5} dot={false} />)}
                  </LineChart>
                </ResponsiveContainer>
                <Legende items={POLS.map((p, i) => [NOMS_POLLUANTS[p], COULEURS[i]])} />
              </>
            ) : <Vide />}
          </Carte>
        </div>

        <div className="grille g2">
          <Carte titre="Q3 · Polluants dominants" sousTitre="Niveau moyen / valeur OMS">
            {ratiosVilles.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={ratiosVilles} layout="vertical" margin={{ left: 10, right: 16 }}>
                  <CartesianGrid stroke={GRILLE} horizontal={false} />
                  <XAxis type="number" tick={AXE} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="city" tick={AXE} axisLine={false} tickLine={false} width={90} />
                  <ReferenceLine x={1} stroke="#d13b3b" strokeDasharray="4 4" />
                  <Tooltip cursor={{ fill: "#f3f8fe" }} content={<Bulle formatValeur={(v) => `${fmt(v, 2)} × OMS`} />} />
                  <Bar isAnimationActive={false} dataKey="ratio_oms" name={NOMS_POLLUANTS[pol]} fill={BLEU} radius={[0, 4, 4, 0]} barSize={14} />
                </BarChart>
              </ResponsiveContainer>
            ) : <Vide />}
            {dominants?.length > 0 && (
              <div className="legende">
                {dominants.map((d) => <span key={d.city}>{d.city} : <b>&nbsp;{d.polluant_dominant}</b></span>)}
              </div>
            )}
          </Carte>

          <Carte titre="Q4 · Épisodes de pollution" sousTitre="Les plus récents">
            {derniers.length ? (
              <div className="defile">
                <table className="tableau">
                  <thead><tr><th>Début</th><th>Ville</th><th>Polluant</th><th className="nb">Durée</th><th className="nb">Pic</th></tr></thead>
                  <tbody>
                    {derniers.map((e, i) => (
                      <tr key={i}><td>{date(e.debut)}</td><td>{e.city}</td><td>{e.pollutant}</td>
                        <td className="nb">{e.duree_h} h</td><td className="nb"><BadgeOms ratio={e.pic_vs_oms} /></td></tr>
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
