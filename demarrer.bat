@echo off
rem Lance tout UrbanHub : Silo + ClickHouse, les collecteurs, le pipeline et l'interface.
rem Chaque programme s'ouvre dans sa propre fenetre. Fermer une fenetre arrete ce programme.
cd /d "%~dp0"

docker compose up -d

start "UrbanHub - collecteur velos" cmd /k ".venv\Scripts\python.exe -u -m urbanhub.velos.collecter"
start "UrbanHub - collecteur pollution" cmd /k ".venv\Scripts\python.exe -u -m urbanhub.pollution.collecter"
start "UrbanHub - pipeline (toutes les heures)" cmd /k ".venv\Scripts\python.exe -u -m urbanhub.pipeline --boucle 3600"
start "UrbanHub - interface" cmd /k ".venv\Scripts\python.exe -m uvicorn api.main:app --port 8000"

timeout /t 5 >nul
start http://localhost:8000
