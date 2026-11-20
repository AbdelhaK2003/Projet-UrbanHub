import { useEffect, useState } from "react";
import { CircleMarker, MapContainer, TileLayer, Tooltip as InfoCarte, useMap } from "react-leaflet";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXE, BLEU, Bulle, Carte, ChoixVille, CourbeTemps, GRILLE, Hero, Icones, Kpi, Legende, Vide, date, dateHeure, fmt, heure, mois, pct, useApi } from "../outils.jsx";

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
  const zonesVille = (zones || []).filter((d) => d.city === ville);
  const etat = (s) => (s.bikes_available === 0 ? "vide" : s.free_slots === 0 ? "pleine" : "normale");

  return (
    <>
      <Hero titre="Mobilité vélo" puces={["CityBikes", "Nov. 2024 → aujourd'hui", "Direct · 3 min"]} />
      <div className="contenu">
        <div className="carte" style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 20px" }}>
          <span style={{ color: "#4a5a78" }}>Ville</span>
          <ChoixVille valeur={ville} onChange={setVille} villes={villes.length ? villes : undefined} />
        </div>

        <div className="grille g4">
          <Kpi icone={Icones.velo} label="Vélos disponibles" valeur={fmt(v?.velos)} detail={`${fmt(v?.capacite)} places`} />
          <Kpi icone={Icones.jauge} label="Taux de remplissage" valeur={v ? fmt((v.velos / v.capacite) * 100) : "–"} unite="%" detail={`${fmt(v?.stations)} stations`} />
          <Kpi icone={Icones.alerte} label="Stations vides / pleines" valeur={v ? `${fmt(v.stations_vides)} / ${fmt(v.stations_pleines)}` : "–"} detail="En ce moment" />
          <Kpi icone={Icones.station} label="Heures de pointe" valeur={pic ? `${Math.min(pic.heure_de_pointe, pic.second_pic ?? 99)} h · ${Math.max(pic.heure_de_pointe, pic.second_pic ?? 0)} h` : "–"} detail={`${fmt(crit.length)} stations à rééquilibrer`} />
        </div>

        <div className="grille g2">
          <Carte titre={`Stations · ${ville} · direct`}>
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

          <Carte titre="Vélos disponibles · en direct">
            {evolution?.length ? (
              <CourbeTemps data={evolution} cle="collected_at" valeur="velos" nom="Vélos disponibles" id="degradeVille"
                           hauteur={355} formatX={heure} formatLabel={dateHeure} />
            ) : <Vide />}
          </Carte>
        </div>

        <Carte titre={`Usage quotidien · ${ville}`} sousTitre="Vélos pris ou rendus par jour · plus longue période sans mois manquant dans l'archive CityBikes">
          {journalier?.length ? (
            <CourbeTemps data={journalier} cle="date" valeur="mouvements" nom="Mouvements" id="degradeJour"
                         formatX={mois} formatLabel={date} trouMinutes={4 * 24 * 60} largeurY={64} choix="longue" formatPeriode={date} />
          ) : <Vide />}
        </Carte>

        <div className="grille g2">
          <Carte titre="Q1 · Stations les plus utilisées" sousTitre="Rotations par place et par jour · toutes villes">
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

          <Carte titre={`Q2 · Zones où l'offre manque · ${ville}`} sousTitre={`${fmt(zonesVille.length)} zones de 500 m où les stations sont vides plus de 25 % du temps`}>
            {zonesVille.length ? (
              <div className="defile">
                <table className="tableau">
                  <thead><tr><th>Stations de la zone</th><th className="nb">Stations</th><th className="nb">Temps vide</th></tr></thead>
                  <tbody>
                    {zonesVille.map((z) => (
                      <tr key={`${z.zone_lat}|${z.zone_lon}`}><td>{z.stations}</td><td className="nb">{fmt(z.nb_stations)}</td>
                        <td className="nb"><b>{pct(z.part_temps_vide)}</b></td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <Vide>Aucune zone en manque de vélos à {ville}.</Vide>}
          </Carte>
        </div>

        <div className="grille g2">
          <Carte titre="Q3 · Pics d'utilisation" sousTitre="Part des mouvements par heure">
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

          <Carte titre="Q4 · Déséquilibres géographiques" sousTitre="Remplissage selon la distance au centre">
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

        <div className="grille">
          <Carte titre={`Q5 · Stations à rééquilibrer · ${ville}`}
                 sousTitre={crit.length ? `30 derniers jours de données · du ${date(crit[0].periode_debut)} au ${date(crit[0].periode_fin)}` : "30 derniers jours de données"}>
            {crit.length ? (
              <div className="defile">
                <table className="tableau">
                  <thead><tr><th>Station</th><th>Action</th><th className="nb">Vélos maintenant</th><th className="nb">Temps vide</th><th className="nb">Temps pleine</th></tr></thead>
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
