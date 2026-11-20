"""Parametres communs du projet (lus depuis le fichier .env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent.parent
load_dotenv(RACINE / ".env")

MINIO_URL = os.getenv("MINIO_URL", "http://127.0.0.1:9010")
MINIO_USER = os.getenv("MINIO_ROOT_USER", "urbanhub")
MINIO_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "urbanhub123")

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "urbanhub")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "urbanhub123")

OPENAQ_API_KEY = os.getenv("OPENAQ_API_KEY", "")

# En-tete HTTP envoye aux API publiques
USER_AGENT = "UrbanHub-projet-etudiant/1.0"
