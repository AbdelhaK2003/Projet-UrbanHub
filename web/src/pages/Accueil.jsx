import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXE, BLEU, BadgeOms, Bulle, Carte, GRILLE, Hero, Icones, Kpi, NOMS_POLLUANTS, Vide, dateHeure, fmt, heure, useApi } from "../outils.jsx";

export default function Accueil({ aller }) {
  const { data: k } = useApi("/api/kpis", 30);
  const { data: evolution } = useApi("/api/velos/evolution?heures=24", 60);
  const { data: air } = useApi("/api/pollution/live", 120);
  const { data: velosVilles } = useApi("/api/velos/live", 60);

  const pm25 = (air || []).filter((d) => d.pollutant === "pm25").sort((a, b) => b.ratio_oms - a.ratio_oms);

  return (
    <>
      <Hero
        titre="UrbanHub"
        texte="Météo, mobilité vélo et qualité de l'air des 11 plus grandes villes de France, réunies dans un seul tableau de bord."
        enDirect={k?.velos?.derniere_collecte ? `En direct · mis à jour à ${heure(k.velos.derniere_collecte)}` : "Connexion…"}
      />
      <div className="contenu">
        <div className="grille g4">
          <Kpi icone={Icones.velo} label="Vélos disponibles" valeur={fmt(k?.velos?.disponibles)}
               detail={`${fmt(k?.velos?.stations)} stations dans ${fmt(k?.velos?.villes)} villes`} />
          <Kpi icone={Icones.jauge} label="Taux de remplissage" valeur={fmt(k?.velos?.remplissage)} unite="%"
               detail={`${fmt(k?.velos?.stations_vides)} stations vides en ce moment`} />
          <Kpi icone={Icones.air} label="PM2.5 moyen (24 h)" valeur={fmt(k?.pollution?.pm25, 1)} unite="µg/m³"
               detail={`${fmt(k?.pollution?.villes_pm25_au_dessus_oms)} villes sur ${fmt(k?.pollution?.villes_mesurees)} au-dessus de la valeur OMS (15)`} />
          <Kpi icone={Icones.thermo} label="Température moyenne" valeur={fmt(k?.meteo?.temperature, 1)} unite="°C"
               detail={`Relevé de ${dateHeure(k?.meteo?.derniere_heure)}`} />
        </div>

        <div className="grille g3">
          <Carte className="large" titre="Vélos disponibles, dernières 24 heures"
                 sousTitre="Total des vélos en station à chaque collecte (toutes les 3 minutes). La courbe baisse quand les habitants roulent.">
            {evolution?.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={evolution} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="degradeVelos" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={BLEU} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={BLEU} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={GRILLE} vertical={false} />
                  <XAxis dataKey="collected_at" tickFormatter={heure} tick={AXE} axisLine={false} tickLine={false} minTickGap={40} />
                  <YAxis tick={AXE} axisLine={false} tickLine={false} tickFormatter={(v) => fmt(v)} width={56} domain={["auto", "auto"]} />
                  <Tooltip content={<Bulle formatLabel={dateHeure} formatValeur={(v) => fmt(v)} />} />
                  <Area isAnimationActive={false} type="monotone" dataKey="velos" name="Vélos disponibles" stroke={BLEU} strokeWidth={2} fill="url(#degradeVelos)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : <Vide>La collecte vélos n'a pas encore commencé.</Vide>}
          </Carte>

          <Carte titre="Points clés" sousTitre="Ce qu'il faut retenir des analyses.">
            <table className="tableau">
              <tbody>
                <tr><td>Vagues de chaleur (5 ans)</td><td className="nb"><b>{fmt(k?.meteo?.vagues_chaleur)}</b></td></tr>
                <tr><td>Vagues de froid (5 ans)</td><td className="nb"><b>{fmt(k?.meteo?.vagues_froid)}</b></td></tr>
                <tr><td>Jours-ville extrêmes (5 ans)</td><td className="nb"><b>{fmt(k?.meteo?.jours_extremes)}</b></td></tr>
                <tr><td>Épisodes de pollution (30 j)</td><td className="nb"><b>{fmt(k?.pollution?.episodes_30j)}</b></td></tr>
                <tr><td>Lien vent / NO2</td><td className="nb"><b>{fmt(k?.croisement?.vent_no2, 2)}</b></td></tr>
                <tr><td>Lien température / O3</td><td className="nb"><b>{fmt(k?.croisement?.temperature_o3, 2)}</b></td></tr>
              </tbody>
            </table>
            <p className="note">Un lien de −1 à +1 : proche de −1, quand l'un monte l'autre baisse ; proche de +1, ils montent ensemble.</p>
          </Carte>
        </div>

        <div className="grille g2">
          <Carte titre="Particules fines PM2.5 par ville"
                 sousTitre="Moyenne des 24 dernières heures. La ligne rouge est la valeur guide de l'OMS (15 µg/m³)."
                 droite={<button className="badge info" style={{ border: 0, cursor: "pointer" }} onClick={() => aller("air")}>Détails</button>}>
            {pm25.length ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={pm25} layout="vertical" margin={{ left: 10, right: 16 }}>
                  <CartesianGrid stroke={GRILLE} horizontal={false} />
                  <XAxis type="number" tick={AXE} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="city" tick={AXE} axisLine={false} tickLine={false} width={90} />
                  <Tooltip cursor={{ fill: "#f3f8fe" }} content={<Bulle formatValeur={(v) => fmt(v, 1)} unite=" µg/m³" />} />
                  <ReferenceLine x={15} stroke="#d13b3b" strokeDasharray="4 4" />
                  <Bar isAnimationActive={false} dataKey="valeur" name="PM2.5" radius={[0, 4, 4, 0]} barSize={14}>
                    {pm25.map((d) => <Cell key={d.city} fill={d.ratio_oms > 1 ? "#1746a2" : "#4f95e8"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <Vide />}
          </Carte>

          <Carte titre="Vélos par ville, en ce moment" sousTitre="État des stations lors de la dernière collecte."
                 droite={<button className="badge info" style={{ border: 0, cursor: "pointer" }} onClick={() => aller("mobilite")}>Détails</button>}>
            {velosVilles?.length ? (
              <div className="defile">
                <table className="tableau">
                  <thead><tr><th>Ville</th><th className="nb">Vélos</th><th className="nb">Stations vides</th><th>Remplissage</th></tr></thead>
                  <tbody>
                    {velosVilles.map((v) => (
                      <tr key={v.city}>
                        <td>{v.city}</td>
                        <td className="nb">{fmt(v.velos)}</td>
                        <td className="nb">{fmt(v.stations_vides)}</td>
                        <td><div className="barre"><div style={{ width: `${(v.velos / v.capacite) * 100}%` }} /></div></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <Vide />}
          </Carte>
        </div>

        {air?.length > 0 && (
          <Carte titre="Qualité de l'air par ville" sousTitre="Polluant le plus préoccupant de chaque ville sur les dernières 24 heures, comparé à la valeur guide OMS.">
            <div className="grille g4" style={{ gap: 12 }}>
              {Object.values(air.reduce((acc, d) => {
                if (!acc[d.city] || d.ratio_oms > acc[d.city].ratio_oms) acc[d.city] = d;
                return acc;
              }, {})).map((d) => (
                <div key={d.city} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 4px", borderBottom: "1px solid #edf1f7" }}>
                  <span>{d.city} <span style={{ color: "#7d8aa3", fontSize: 12 }}>({NOMS_POLLUANTS[d.pollutant]})</span></span>
                  <BadgeOms ratio={d.ratio_oms} />
                </div>
              ))}
            </div>
          </Carte>
        )}
      </div>
    </>
  );
}
