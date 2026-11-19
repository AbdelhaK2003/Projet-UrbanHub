import { useEffect, useState } from "react";
import { CircleMarker, MapContainer, TileLayer, Tooltip as InfoCarte, useMap } from "react-leaflet";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXE, BLEU, Bulle, Carte, ChoixVille, GRILLE, Hero, Icones, Kpi, Legende, Vide, date, dateHeure, fmt, heure, mois, pct, useApi } from "../outils.jsx";

const ETAT = { vide: "#d13b3b", pleine: "#eda100", normale: "#2a78d6" };

function Recentrer({ points }) {
  const map = useMap();
  const cle = points.length ? `${points[0].station_name}` : "";
  useEffect(() => {  // on recadre la carte quand on change de ville
    if (points.length) map.fitBounds(points.map((p) => [p.latitude, p.longitude]), { padding: [20, 20] });
  }, [cle]); // eslint-disable-line
  return null;
}

export default function Mobilite() {
  const [ville, setVille] = useState("Paris");
  const { data: live } = useApi("/api/velos/live", 30);
  const { data: evolution } = useApi(`/api/velos/evolution?heures=24&city=${encodeURIComponent(ville)}`, 60);
  const { data: stations } = useApi(`/api/velos/stations?city=${encodeURIComponent(ville)}`, 60);
  const { data: top } = useApi("/api/gold/velos_q1_top_stations", 300);
  const { data: profil } = useApi("/api/gold/velos_q3_profil_horaire", 300);
  const { data: pointe } = useApi("/api/gold/velos_q3_heure_de_pointe", 300);
  const { data: distance } = useApi("/api/gold/velos_q4_remplissage_par_distance", 300);
  const { data: critiques } = useApi("/api/gold/velos_q5_stations_critiques", 300);
  const { data: zones } = useApi("/api/gold/velos_q2_zones_insuffisantes", 300);
  const { data: journalier } = useApi(`/api/gold/velos_velos_journalier?city=${encodeURIComponent(ville)}`, 600);

  const villes = (live || []).map((d) => d.city);
  const v = live?.find((d) => d.city === ville);
  const profilVille = (profil || []).filter((d) => d.city === ville).sort((a, b) => a.heure - b.heure);
  const pic = pointe?.find((d) => d.city === ville);
  const bandes = (distance || []).filter((d) => d.city === ville);
  const crit = (critiques || []).filter((d) => d.city === ville);
  const nbZones = (zones || []).filter((d) => d.city === ville).length;
  const etat = (s) => (s.bikes_available === 0 ? "vide" : s.free_slots === 0 ? "pleine" : "normale");

  return (
    <>
      <Hero titre="Mobilité vélo"
            texte="Historique des stations de vélos en libre-service depuis novembre 2024 (archive CityBikes), complété en direct toutes les 3 minutes. Chaque collecte arrive directement dans ClickHouse."
            enDirect={v ? `Dernière collecte ${heure(v.heure_collecte)}` : null} />
      <div className="contenu">
        <div className="carte" style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 20px" }}>
          <span style={{ color: "#4a5a78" }}>Ville</span>
          <ChoixVille valeur={ville} onChange={setVille} villes={villes.length ? villes : undefined} />
          <span className="note" style={{ margin: 0 }}>Bike-share data by CityBikes contributors, <a href="https://data.citybik.es" target="_blank" rel="noreferrer">data.citybik.es</a> (ODbL). Marseille et Nice ne publient pas le nombre de vélos : elles n'apparaissent pas.</span>
        </div>

        <div className="grille g4">
          <Kpi icone={Icones.velo} label="Vélos disponibles" valeur={fmt(v?.velos)} detail={`sur ${fmt(v?.capacite)} points d'attache`} />
          <Kpi icone={Icones.jauge} label="Taux de remplissage" valeur={v ? fmt((v.velos / v.capacite) * 100) : "–"} unite="%" detail={`${fmt(v?.stations)} stations`} />
          <Kpi icone={Icones.alerte} label="Stations vides / pleines" valeur={v ? `${fmt(v.stations_vides)} / ${fmt(v.stations_pleines)}` : "–"} detail="Impossible d'y prendre / d'y rendre un vélo" />
          <Kpi icone={Icones.station} label="Heures de pointe" valeur={pic ? `${Math.min(pic.heure_de_pointe, pic.second_pic ?? 99)} h · ${Math.max(pic.heure_de_pointe, pic.second_pic ?? 0)} h` : "–"} detail={`${fmt(crit.length)} stations à rééquilibrer, ${fmt(nbZones)} zones sous-équipées`} />
        </div>

        <div className="grille g2">
          <Carte titre={`Stations de ${ville}, en ce moment`} sousTitre="Chaque point est une station. Survoler pour voir le détail.">
            {stations?.length ? (
              <>
                <div className="carte-map">
                  <MapContainer center={[stations[0].latitude, stations[0].longitude]} zoom={12} style={{ height: "100%" }} scrollWheelZoom={false}>
                    <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap" />
                    <Recentrer points={stations} />
                    {stations.map((s, i) => (
                      <CircleMarker key={i} center={[s.latitude, s.longitude]} radius={4.5}
                                    pathOptions={{ color: "#fff", weight: 1, fillColor: ETAT[etat(s)], fillOpacity: 0.9 }}>
                        <InfoCarte>{s.station_name}<br />{s.bikes_available} vélos · {s.free_slots} places</InfoCarte>
                      </CircleMarker>
                    ))}
                  </MapContainer>
                </div>
                <Legende items={[["Station vide", ETAT.vide], ["Station pleine", ETAT.pleine], ["Normale", ETAT.normale]]} />
              </>
            ) : <Vide>Pas encore de collecte pour cette ville.</Vide>}
          </Carte>

          <Carte titre="Vélos disponibles, dernières 24 heures" sousTitre="Quand la courbe baisse, des vélos sont en circulation.">
            {evolution?.length ? (
              <ResponsiveContainer width="100%" height={380}>
                <AreaChart data={evolution} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="degradeVille" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={BLEU} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={BLEU} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={GRILLE} vertical={false} />
                  <XAxis dataKey="collected_at" tickFormatter={heure} tick={AXE} axisLine={false} tickLine={false} minTickGap={40} />
                  <YAxis tick={AXE} axisLine={false} tickLine={false} width={56} domain={["auto", "auto"]} tickFormatter={(x) => fmt(x)} />
                  <Tooltip content={<Bulle formatLabel={dateHeure} formatValeur={(x) => fmt(x)} />} />
                  <Area isAnimationActive={false} type="monotone" dataKey="velos" name="Vélos disponibles" stroke={BLEU} strokeWidth={2} fill="url(#degradeVille)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : <Vide />}
          </Carte>
        </div>

        <Carte titre={`Usage des vélos à ${ville}, jour par jour`} sousTitre="Nombre de vélos pris ou rendus chaque jour sur toute la période (archive CityBikes puis collecte en direct).">
          {journalier?.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={journalier} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="degradeJour" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={BLEU} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={BLEU} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={GRILLE} vertical={false} />
                <XAxis dataKey="date" tickFormatter={mois} tick={AXE} axisLine={false} tickLine={false} minTickGap={50} />
                <YAxis tick={AXE} axisLine={false} tickLine={false} width={64} tickFormatter={(x) => fmt(x)} />
                <Tooltip content={<Bulle formatLabel={date} formatValeur={(x) => fmt(x)} />} />
                <Area isAnimationActive={false} type="monotone" dataKey="mouvements" name="Mouvements" stroke={BLEU} strokeWidth={1.5} fill="url(#degradeJour)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : <Vide />}
        </Carte>

        <div className="grille g2">
          <Carte titre="Q3 · Pics d'utilisation dans la journée" sousTitre="Part des mouvements de vélos (prises et retours) selon l'heure.">
            {profilVille.length ? (
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={profilVille} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={GRILLE} vertical={false} />
                  <XAxis dataKey="heure" tick={AXE} axisLine={false} tickLine={false} unit=" h" />
                  <YAxis tick={AXE} axisLine={false} tickLine={false} unit=" %" width={48} />
                  <Tooltip content={<Bulle formatLabel={(l) => `${l} h`} formatValeur={(x) => fmt(x, 1)} unite=" %" />} />
                  <Line isAnimationActive={false} type="monotone" dataKey="part_mouvements" name="Part des mouvements" stroke={BLEU} strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : <Vide>Il faut plusieurs heures de collecte pour ce graphique.</Vide>}
          </Carte>

          <Carte titre="Q4 · Remplissage selon la distance au centre" sousTitre="Part moyenne des places occupées par un vélo. Un écart fort signale un déséquilibre centre / périphérie.">
            {bandes.length ? (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={bandes} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke={GRILLE} vertical={false} />
                  <XAxis dataKey="bande" tick={AXE} axisLine={false} tickLine={false} />
                  <YAxis tick={AXE} axisLine={false} tickLine={false} tickFormatter={(x) => pct(x)} width={48} />
                  <Tooltip cursor={{ fill: "#f3f8fe" }} content={<Bulle formatLabel={(l) => `À ${l} du centre`} formatValeur={(x) => pct(x)} />} />
                  <Bar isAnimationActive={false} dataKey="taux_remplissage" name="Remplissage" fill={BLEU} radius={[4, 4, 0, 0]} barSize={40} />
                </BarChart>
              </ResponsiveContainer>
            ) : <Vide />}
          </Carte>
        </div>

        <div className="grille g2">
          <Carte titre="Q1 · Stations les plus utilisées" sousTitre="Rotations par jour : nombre de mouvements divisé par le nombre de places.">
            {top?.length ? (
              <div className="defile">
                <table className="tableau">
                  <thead><tr><th>Station</th><th>Ville</th><th className="nb">Places</th><th className="nb">Rotations / jour</th></tr></thead>
                  <tbody>
                    {top.map((s) => (
                      <tr key={s.city + s.station_name}><td>{s.station_name}</td><td>{s.city}</td>
                        <td className="nb">{fmt(s.capacity)}</td><td className="nb"><b>{fmt(s.rotations_par_jour, 1)}</b></td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <Vide />}
          </Carte>

          <Carte titre="Q5 · Stations à rééquilibrer" sousTitre={`Stations de ${ville} trop souvent vides (à remplir) ou pleines (à vider).`}>
            {crit.length ? (
              <div className="defile">
                <table className="tableau">
                  <thead><tr><th>Station</th><th>Action</th><th className="nb">Vélos</th><th className="nb">Temps vide</th><th className="nb">Temps pleine</th></tr></thead>
                  <tbody>
                    {crit.slice(0, 60).map((s) => (
                      <tr key={s.station_name}><td>{s.station_name}</td>
                        <td><span className={`badge ${s.action === "a remplir" ? "mauvais" : "moyen"}`}>{s.action === "a remplir" ? "à remplir" : "à vider"}</span></td>
                        <td className="nb">{fmt(s.bikes_available)}</td><td className="nb">{pct(s.part_temps_vide)}</td><td className="nb">{pct(s.part_temps_plein)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <Vide>Aucune station critique pour l'instant.</Vide>}
          </Carte>
        </div>
      </div>
    </>
  );
}
