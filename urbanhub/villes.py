"""Principales villes de France etudiees et petits outils geographiques."""
import numpy as np

# nom : (latitude, longitude) du centre-ville
VILLES = {
    "Paris": (48.8566, 2.3522),
    "Marseille": (43.2965, 5.3698),
    "Lyon": (45.7640, 4.8357),
    "Toulouse": (43.6047, 1.4442),
    "Nice": (43.7102, 7.2620),
    "Nantes": (47.2184, -1.5536),
    "Strasbourg": (48.5734, 7.7521),
    "Montpellier": (43.6108, 3.8767),
    "Bordeaux": (44.8378, -0.5792),
    "Lille": (50.6292, 3.0573),
    "Rennes": (48.1173, -1.6778),
}

# Une station meteo ou un capteur est rattache a une ville s'il est a moins de RAYON_KM
RAYON_KM = 30


def distance_km(lat1, lon1, lat2, lon2):
    """Distance a vol d'oiseau (formule de haversine). Marche aussi sur des colonnes."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def ville_proche(lat, lon, rayon_km=RAYON_KM):
    """Renvoie la ville la plus proche si elle est a moins de rayon_km, sinon None."""
    if lat is None or lon is None or np.isnan(lat) or np.isnan(lon):
        return None
    meilleure, dmin = None, rayon_km
    for nom, (vlat, vlon) in VILLES.items():
        d = distance_km(lat, lon, vlat, vlon)
        if d <= dmin:
            meilleure, dmin = nom, d
    return meilleure
