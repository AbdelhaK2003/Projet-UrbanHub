"""Meteo recente des grandes villes (Open-Meteo), pour la partie 4.

Pourquoi ce script ? Le depot NOAA s'arrete en 2025 (derniere mise a jour : octobre 2025). Or les velos et la
pollution sont collectes maintenant. Pour croiser les trois, il faut une meteo
horaire sur la meme periode : on la prend chez Open-Meteo (gratuit, sans cle).

Variables identiques a la partie 1 : temperature, vent, pression, pluie, visibilite.

Lancer : python -m urbanhub.meteo.recente   (a relancer de temps en temps, ex. chaque jour)
"""
from datetime import datetime, timezone

import pandas as pd
import requests

from urbanhub import config, datalake
from urbanhub.villes import VILLES

API = "https://api.open-meteo.com/v1/forecast"
VARIABLES = "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,pressure_msl,visibility"


def main():
    datalake.init_buckets()
    maintenant = datetime.now(timezone.utc)
    morceaux = []
    for ville, (lat, lon) in VILLES.items():
        r = requests.get(API, params={"latitude": lat, "longitude": lon, "hourly": VARIABLES, "past_days": 92,
                                      "forecast_days": 1, "timezone": "UTC"},
                         headers={"User-Agent": config.USER_AGENT}, timeout=60)
        r.raise_for_status()
        brut = r.json()
        datalake.put_json("bronze", f"meteo/openmeteo/{maintenant:%Y-%m-%d}/{ville}.json", brut)
        h = pd.DataFrame(brut["hourly"])
        morceaux.append(pd.DataFrame({
            "city": ville,
            "timestamp": pd.to_datetime(h["time"], utc=True),
            "temperature": h["temperature_2m"],
            "wind_speed_kmh": h["wind_speed_10m"],
            "wind_direction": h["wind_direction_10m"],
            "pressure": h["pressure_msl"],
            "precipitation": h["precipitation"],
            "visibility": h["visibility"] / 1000,  # m -> km
        }))

    nouveau = pd.concat(morceaux)
    nouveau = nouveau[nouveau["timestamp"] <= maintenant]  # on enleve les previsions
    # on garde aussi ce qui avait deja ete recupere avant (au-dela des 92 jours)
    key = "meteo_recente/meteo_recente.parquet"
    if datalake.existe("silver", key):
        nouveau = pd.concat([datalake.get_parquet("silver", key), nouveau])
    nouveau["timestamp"] = nouveau["timestamp"].astype("datetime64[ns, UTC]")
    nouveau = nouveau.drop_duplicates(["city", "timestamp"], keep="last").sort_values(["city", "timestamp"])
    datalake.put_parquet("silver", key, nouveau)
    print(f"Meteo recente : {len(nouveau):,} heures pour {nouveau['city'].nunique()} villes, "
          f"du {nouveau['timestamp'].min():%Y-%m-%d} au {nouveau['timestamp'].max():%Y-%m-%d %H:%M}")


if __name__ == "__main__":
    main()
