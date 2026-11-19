-- Exemples de requetes ClickHouse sur les donnees UrbanHub
-- A lancer dans http://localhost:8123/play (utilisateur urbanhub / urbanhub123)

-- Meteo : temperature moyenne par ville et par mois
SELECT city, toStartOfMonth(timestamp) AS mois, round(avg(temperature), 1) AS temp_moy
FROM urbanhub.meteo
WHERE city IS NOT NULL
GROUP BY city, mois
ORDER BY city, mois;

-- Meteo : les 10 heures les plus venteuses de France
SELECT station_name, city, timestamp, wind_speed_kmh
FROM urbanhub.meteo
ORDER BY wind_speed_kmh DESC
LIMIT 10;

-- Velos : etat le plus recent de chaque station de Paris
SELECT station_name, argMax(bikes_available, collected_at) AS velos, argMax(free_slots, collected_at) AS places
FROM urbanhub.velos
WHERE city = 'Paris'
GROUP BY station_name
ORDER BY velos ASC
LIMIT 20;

-- Velos : mouvements par heure avec une window function (comme au TP OLAP)
SELECT city, toHour(toTimeZone(collected_at, 'Europe/Paris')) AS heure, sum(abs(delta)) AS mouvements
FROM (
    SELECT city, collected_at,
           bikes_available - lagInFrame(bikes_available) OVER (PARTITION BY station_id ORDER BY collected_at) AS delta
    FROM urbanhub.velos
)
GROUP BY city, heure
ORDER BY city, heure;

-- Pollution : moyenne par ville et par polluant
SELECT city, pollutant, round(avg(value), 1) AS moyenne, count() AS nb_mesures
FROM urbanhub.pollution
GROUP BY city, pollutant
ORDER BY city, pollutant;

-- Pollution : profil horaire du NO2
SELECT toHour(toTimeZone(timestamp, 'Europe/Paris')) AS heure, round(avg(value), 1) AS no2
FROM urbanhub.pollution
WHERE pollutant = 'no2'
GROUP BY heure
ORDER BY heure;
