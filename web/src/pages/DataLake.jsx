import { Carte, Hero, Icones, Kpi, Vide, dateHeure, fmt, useApi } from "../outils.jsx";

export default function DataLake() {
  const { data: lac } = useApi("/api/datalake", 60);
  const { data: etat } = useApi("/api/etat", 30);
  const total = (b) => (lac || []).filter((d) => d.bucket === b).reduce((s, d) => ({ f: s.f + d.fichiers, t: s.t + d.taille_mo }), { f: 0, t: 0 });

  return (
    <>
      <Hero titre="Data Lake" puces={["Silo · bronze / silver / gold", "ClickHouse"]} />
      <div className="contenu">
        <Carte titre="Architecture">
          <div className="flux">
            <div className="etape"><b>Sources</b>Open-Meteo · CityBikes · OpenAQ</div>
            <div className="etape"><b>Bronze</b>Données brutes</div>
            <div className="etape"><b>Silver</b>Données nettoyées</div>
            <div className="etape"><b>Gold</b>Indicateurs</div>
            <div className="etape"><b>ClickHouse → API → React</b>Interface temps réel</div>
          </div>
        </Carte>

        <div className="grille g4">
          {["bronze", "silver", "gold"].map((b) => (
            <Kpi key={b} icone={Icones.lac} label={`Bucket ${b}`} valeur={fmt(total(b).f)} unite="fichiers" detail={`${fmt(total(b).t)} Mo`} />
          ))}
          <Kpi icone={Icones.jauge} label="Tables gold dans ClickHouse" valeur={fmt(etat?.tables_gold)} detail="Indicateurs" />
        </div>

        <div className="grille g2">
          <Carte titre="Contenu du Data Lake">
            {lac?.length ? (
              <div className="defile" style={{ maxHeight: 520 }}>
                <table className="tableau">
                  <thead><tr><th>Bucket</th><th>Dossier</th><th className="nb">Fichiers</th><th className="nb">Taille</th></tr></thead>
                  <tbody>
                    {lac.map((d) => (
                      <tr key={d.bucket + d.dossier}><td><span className="badge info">{d.bucket}</span></td><td>{d.dossier}</td>
                        <td className="nb">{fmt(d.fichiers)}</td><td className="nb">{fmt(d.taille_mo, 1)} Mo</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <Vide>MinIO ne répond pas.</Vide>}
          </Carte>
          <Carte titre="Tables ClickHouse">
            {etat ? (
              <table className="tableau">
                <thead><tr><th>Table</th><th className="nb">Lignes</th><th>Donnée la plus récente</th></tr></thead>
                <tbody>
                  {["meteo", "velos", "pollution"].map((t) => (
                    <tr key={t}><td><b>{t}</b></td><td className="nb">{fmt(etat[t]?.lignes)}</td><td>{dateHeure(etat[t]?.derniere)}</td></tr>
                  ))}
                </tbody>
              </table>
            ) : <Vide />}
          </Carte>
        </div>
      </div>
    </>
  );
}
