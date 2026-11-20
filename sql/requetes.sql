-- Exemples de requetes ClickHouse sur les donnees UrbanHub
-- A lancer dans http://127.0.0.1:8123/play (utilisateur urbanhub / urbanhub123)
-- Tables detaillees : urbanhub.meteo, urbanhub.velos, urbanhub.pollution
-- Indicateurs : urbanhub.gold_<partie>_<nom> (liste : SHOW TABLES FROM urbanhub)

-- Meteo : temperature moyenne par ville et par annee
SELECT city, toYear(timestamp) AS annee, round(avg(temperature), 1) AS temp_moy
FROM urbanhub.meteo
GROUP BY city, annee
ORDER BY city, annee;

-- Meteo : les 10 heures les plus venteuses (rafales)
SELECT city, timestamp, wind_gusts
FROM urbanhub.meteo
ORDER BY wind_gusts DESC
LIMIT 10;

-- Velos : etat le plus recent de chaque station de Paris (les moins fournies d'abord)
SELECT station_name, argMax(bikes_available, collected_at) AS velos, argMax(free_slots, collected_at) AS places
FROM urbanhub.velos FINAL
WHERE city = 'Paris'
GROUP BY station_name
ORDER BY velos ASC
LIMIT 20;

-- Velos : mouvements par heure avec une window function (comme au TP OLAP)
SELECT city, toHour(toTimeZone(collected_at, 'Europe/Paris')) AS heure, sum(abs(delta)) AS mouvements
FROM (
    SELECT city, collected_at,
           bikes_available - lagInFrame(bikes_available) OVER (PARTITION BY station_id ORDER BY collected_at) AS delta
    FROM urbanhub.velos FINAL
)
GROUP BY city, heure
ORDER BY city, heure;

-- Pollution : moyenne par ville, polluant et annee
SELECT city, pollutant, toYear(timestamp) AS annee, round(avg(value), 1) AS moyenne, count() AS nb_mesures
FROM urbanhub.pollution FINAL
GROUP BY city, pollutant, annee
ORDER BY city, pollutant, annee;

-- Pollution : profil horaire du NO2
SELECT toHour(toTimeZone(timestamp, 'Europe/Paris')) AS heure, round(avg(value), 1) AS no2
FROM urbanhub.pollution
WHERE pollutant = 'no2'
GROUP BY heure
ORDER BY heure;

-- Gold : les vagues de chaleur detectees
SELECT * FROM urbanhub.gold_meteo_q1_periodes_anormales WHERE type = 'vague de chaleur' ORDER BY debut;

-- Gold : correlation meteo / pollution
SELECT * FROM urbanhub.gold_croisement_q1_correlation_meteo_pollution ORDER BY abs(correlation) DESC;
