# UrbanHub

UrbanHub est un jumeau numerique urbain. Il recupere des donnees sur les grandes villes francaises, les range dans un Data Lake, les nettoie, puis repond aux questions metier du sujet avec des tableaux et des graphiques.

Ce document explique chaque etape en detail :
- ce qu'elle fait et pourquoi
- dans quel fichier et quelle fonction c'est code
- ou arrivent les donnees
- comment regarder les resultats

Villes etudiees : Paris, Marseille, Lyon, Toulouse, Nice, Nantes, Strasbourg, Montpellier, Bordeaux, Lille, Rennes.


## Sommaire

1. Vue d'ensemble
2. Les outils et les fichiers du projet
3. Installation
4. Les briques communes (code partage par toutes les parties)
5. Partie 1 - Meteo (flux batch)
6. Partie 2 - Velos (flux streaming)
7. Partie 3 - Pollution (flux IoT)
8. Partie 4 - Analyse croisee
9. Bonus : ClickHouse et tableau de bord
10. Comment regarder les resultats
11. Resultats et interpretation
12. Limites et problemes rencontres
13. En cas de probleme


---

## 1. Vue d'ensemble

Le sujet demande trois flux de donnees, comme dans une vraie plateforme Big Data :

| Flux | Source | Rythme | Ce qu'on recupere |
|---|---|---|---|
| Batch | NOAA | une fois | 5 ans de meteo horaire de toutes les stations francaises |
| Streaming | CityBikes | toutes les 2 min 30 | l'etat de chaque station de velos (velos dispo, places libres) |
| IoT | OpenAQ | toutes les 15 min | les mesures des capteurs de pollution |

Les trois flux suivent exactement le meme chemin, celui de l'architecture cible du sujet :

```
Source (API ou fichiers)
   |
   |  1. collecter   : on recupere les donnees et on les depose telles quelles
   v
BRONZE  (donnees brutes : CSV, JSON)
   |
   |  2. nettoyer    : on garde les bonnes variables, on corrige, on convertit
   v
SILVER  (donnees propres, format Parquet)
   |
   |  3. analyser    : on calcule les indicateurs et on repond aux questions
   v
GOLD    (indicateurs : tableaux Parquet + graphiques PNG)
```

C'est pour ca que chaque partie a toujours trois scripts : `collecter` (ou `telecharger`), `nettoyer` et `analyser`.

Pourquoi trois couches ?
- **bronze** garde la donnee d'origine. Si on se trompe dans le nettoyage, on peut tout refaire sans retelecharger. Le versioning est active : meme un fichier ecrase garde son ancienne version.
- **silver** contient une donnee fiable et rapide a lire. Parquet est un format en colonnes, compresse, standard dans les Data Lakes.
- **gold** contient ce qu'un decideur veut voir : des chiffres et des graphiques, pas des millions de lignes.


---

## 2. Les outils et les fichiers du projet

Les outils sont ceux des TP :

| Outil | Role dans le projet |
|---|---|
| Docker | lance MinIO et ClickHouse avec une seule commande |
| MinIO | le Data Lake, compatible S3, avec les buckets bronze, silver et gold |
| boto3 | la librairie Python pour parler a MinIO (comme au TP Data Lake) |
| pandas + pyarrow | nettoyage, calculs, lecture et ecriture Parquet |
| matplotlib | les graphiques |
| ClickHouse | base OLAP pour faire du SQL rapide sur les donnees silver (comme au TP OLAP) |
| Streamlit | petit tableau de bord pour les videos de demo |

Organisation des fichiers :

```
Projet UrbanHub/
  docker-compose.yml          lance MinIO + ClickHouse
  requirements.txt            librairies Python a installer
  .env                        mots de passe et cle OpenAQ (jamais partage)
  .env.example                modele du fichier .env

  urbanhub/                   tout le code Python
    config.py                 lit le fichier .env, definit les dossiers
    villes.py                 liste des 11 villes + calcul de distance
    datalake.py               lecture / ecriture dans MinIO
    rapport.py                enregistre les graphiques et tableaux dans gold
    init_datalake.py          cree les buckets

    meteo/                    PARTIE 1
      telecharger.py          telechargement parallele NOAA -> bronze
      nettoyer.py             bronze -> silver
      analyser.py             silver -> gold (4 questions)
      recente.py              meteo recente Open-Meteo (pour la partie 4)

    velos/                    PARTIE 2
      collecter.py            collecte CityBikes toutes les 2 min 30 -> bronze
      nettoyer.py             bronze -> silver
      analyser.py             silver -> gold (5 questions)

    pollution/                PARTIE 3
      collecter.py            collecte OpenAQ (flux + historique) -> bronze
      nettoyer.py             bronze -> silver
      analyser.py             silver -> gold (4 questions)

    croisement/               PARTIE 4
      analyser.py             croise les 3 sources -> gold (4 questions)

    charger_clickhouse.py     copie les donnees silver dans ClickHouse

  sql/requetes.sql            exemples de requetes ClickHouse
  dashboard/app.py            tableau de bord Streamlit
  rapports/                   resultats en local (CSV)
    figures/                  graphiques en local (PNG)
```


---

## 3. Installation

A faire une seule fois, dans un terminal ouvert dans le dossier du projet.

**Etape 1 : creer l'environnement Python et installer les librairies**

```
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`.venv` est un environnement Python isole, propre au projet. Il faut l'activer (deuxieme ligne) a chaque fois qu'on ouvre un nouveau terminal. On sait qu'il est actif quand `(.venv)` apparait au debut de la ligne.

**Etape 2 : le fichier .env**

```
copy .env.example .env
```

Ouvrir `.env` et remplir `OPENAQ_API_KEY=` avec la cle OpenAQ (gratuite sur explore.openaq.org). Ce fichier contient des secrets : il est exclu de git par `.gitignore` et ne doit pas etre rendu.

**Etape 3 : lancer l'infrastructure**

Demarrer Docker Desktop, puis :

```
docker compose up -d
```

Cela lance deux conteneurs, decrits dans [docker-compose.yml](docker-compose.yml) :
- `urbanhub-minio` : API S3 sur le port 9010, console web sur http://localhost:9011
- `urbanhub-clickhouse` : sur le port 8123, interface SQL sur http://localhost:8123/play

Pour verifier : `docker compose ps` doit afficher les deux conteneurs avec le statut `Up`.

Remarques :
- **Ports :** on utilise 9010 et 9011, et non 9000 et 9001, pour ne pas entrer en conflit avec le MinIO des TP s'il tourne encore.
- **Image :** l'image officielle `minio/minio` n'est plus publiee, on utilise `pgsty/minio`, qui est identique.
- **Stockage :** les donnees sont dans un volume Docker (`minio_data`), pas dans un dossier du projet. Le projet est dans OneDrive, et il ne faut pas synchroniser plusieurs Go.

**Etape 4 : creer les buckets**

```
python -m urbanhub.init_datalake
```

Resultat attendu : `Buckets prets : bronze, silver, gold (versioning actif sur bronze)`

Code : [urbanhub/datalake.py](urbanhub/datalake.py), fonction `init_buckets`. Elle cree les buckets qui manquent et active le versioning sur bronze (`put_bucket_versioning`), comme au TP Data Lake.

**Comment lancer un script.** Tous les scripts se lancent depuis la racine du projet avec `python -m urbanhub.<dossier>.<script>`. Le `-m` permet a Python de trouver le package `urbanhub`.


---

## 4. Les briques communes

Ces fichiers sont utilises par toutes les parties. Les comprendre aide a lire le reste.

### config.py : les parametres

[urbanhub/config.py](urbanhub/config.py) lit le fichier `.env` avec `load_dotenv`, puis expose :
- les identifiants MinIO et ClickHouse
- la cle OpenAQ
- le dossier ou sont enregistres les graphiques (`rapports/figures`)

### villes.py : les villes et les distances

[urbanhub/villes.py](urbanhub/villes.py) contient :
- `VILLES` : les 11 villes avec les coordonnees GPS de leur centre
- `distance_km` : la distance a vol d'oiseau entre deux points GPS (formule de haversine)
- `ville_proche` : la ville la plus proche d'un point, si elle est a moins de 30 km (`RAYON_KM`). Sinon, la fonction renvoie `None`.

C'est grace a `ville_proche` qu'une station meteo NOAA ou un capteur de pollution est rattache a une ville. On peut ensuite comparer les sources ville par ville.

### datalake.py : parler a MinIO

[urbanhub/datalake.py](urbanhub/datalake.py) cache les details de boto3 derriere des fonctions simples :

| Fonction | Ce qu'elle fait |
|---|---|
| `client()` | cree la connexion boto3 vers MinIO (une seule fois, puis reutilisee) |
| `init_buckets()` | cree bronze, silver et gold, et active le versioning sur bronze |
| `put_bytes`, `put_json`, `put_parquet`, `put_fichier` | ecrire un fichier dans un bucket |
| `get_bytes`, `get_json`, `get_parquet` | lire un fichier |
| `existe(bucket, cle)` | savoir si un fichier existe deja |
| `lister(bucket, prefixe)` | lister tous les fichiers d'un dossier (gere la pagination S3) |
| `lire_parquets(bucket, prefixe)` | lire et coller ensemble tous les Parquet d'un dossier |

`put_parquet` transforme un DataFrame pandas en Parquet en memoire (`to_parquet` dans un `BytesIO`), puis l'envoie. Aucun fichier temporaire n'est ecrit sur le disque.

### rapport.py : enregistrer les resultats

[urbanhub/rapport.py](urbanhub/rapport.py) :
- `sauver_figure(fig, partie, nom)` enregistre un graphique dans `rapports/figures/<partie>_<nom>.png` et dans `gold/<partie>/figures/<nom>.png`.
- `sauver_table(df, partie, nom)` enregistre un tableau dans `gold/<partie>/<nom>.parquet` et en CSV dans `rapports/<partie>_<nom>.csv`.
- `titre(texte)` affiche un titre souligne dans le terminal.

Chaque resultat existe donc en deux endroits : dans le Data Lake (gold) et en local (`rapports`), pour l'ouvrir facilement.


---

## 5. Partie 1 - Meteo (flux batch)

Source : NOAA Global Hourly, des observations meteo horaires de stations du monde entier. Un fichier CSV par station et par annee.

### Etape 1.1 : telecharger en parallele

```
python -m urbanhub.meteo.telecharger
```

Options :
- `--workers 16` : nombre de telechargements en meme temps
- `--annees 5` : nombre d'annees completes
- `--grandes-villes` : seulement les stations a moins de 30 km d'une grande ville (test rapide, environ 130 fichiers)
- `--max-stations 5` : limiter a N stations (test tres rapide)

Code : [urbanhub/meteo/telecharger.py](urbanhub/meteo/telecharger.py)

Le script fait trois choses.

**a) Trouver les stations francaises.** C'est la fonction `stations_france`.
- Elle telecharge la liste officielle des stations NOAA : `isd-history.csv`.
- Elle garde les lignes ou `CTRY == "FR"` (France).
- Elle garde les stations encore actives au debut de la periode (colonne `END`).
- Elle garde seulement la metropole : latitude entre 41 et 52, longitude entre -5,5 et 10.
- Elle fabrique l'identifiant de station en collant `USAF` et `WBAN` (exemple : `07149099999` = Orly). C'est aussi le nom du fichier a telecharger.

Resultat : environ 210 stations. La liste est gardee dans `bronze/meteo/reference/stations_france.parquet`.

**b) Preparer toutes les taches.** On fabrique toutes les combinaisons station x annee. Les annees vont de 2021 a l'annee en cours, soit 210 x 6 = environ 1 260 fichiers.

**c) Telecharger en parallele.** C'est la fonction `main`, avec `ThreadPoolExecutor`.
- Un pool de 16 threads telecharge 16 fichiers en meme temps, au lieu d'un par un. C'est la demande du sujet.
- `as_completed` recupere les resultats au fur et a mesure, et `tqdm` affiche une barre de progression.

Chaque thread execute `telecharger_un(annee, station)`, qui :
- saute le fichier s'il est deja dans bronze (si on relance le script, il reprend ou il s'etait arrete)
- telecharge le CSV, avec 3 essais en cas d'erreur reseau
- renvoie "absent" si la station n'a rien publie cette annee-la (erreur 404), ce qui est normal
- depose le fichier tel quel dans `bronze/meteo/noaa/year=AAAA/STATION.csv`

Le dossier `year=AAAA` est un partitionnement par annee, comme au TP (`year=/month=/day=`).

**A savoir.** Le lien du sujet (`ncei.noaa.gov/data/global-hourly/access/`) redirige maintenant vers un depot AWS. Le script va donc directement sur `noaa-global-hourly-pds.s3.amazonaws.com` (variable `URL_FICHIER`). Les donnees s'arretent en aout 2025.

**Resultat attendu** a la fin :

```
Termine en 130 s : {'ok': 980, 'absent': 280}
```

**Ou regarder :** console MinIO (http://localhost:9011), bucket `bronze`, dossier `meteo/noaa/`.

### Etape 1.2 : nettoyer

```
python -m urbanhub.meteo.nettoyer
```

Code : [urbanhub/meteo/nettoyer.py](urbanhub/meteo/nettoyer.py)

**Le probleme a resoudre.** Les colonnes NOAA sont codees. Plusieurs informations sont collees dans une meme case, separees par des virgules :

| Colonne | Exemple | Signification |
|---|---|---|
| TMP | `+0123,1` | 12,3 degres (en dixiemes), qualite 1 |
| WND | `220,1,N,0036,1` | direction 220 degres, vitesse 3,6 m/s (en dixiemes) |
| SLP | `10132,1` | pression 1013,2 hPa (en dixiemes) |
| VIS | `010000,1,N,1` | visibilite 10 000 metres |
| AA1 | `06,0012,9,1` | 1,2 mm de pluie tombes en 6 heures |

Les valeurs manquantes sont codees par des 9 : `+9999`, `99999`, `999999`.

**Ce que fait le code, fonction par fonction :**

- `champ(serie, i)` decoupe la case a chaque virgule et prend le morceau numero i.
- `valeur(serie, i_val, i_qual, manquant, echelle)` :
  - prend la valeur et son code qualite
  - met a vide les codes "manquant" (9999...)
  - met a vide les mesures que la NOAA juge douteuses ou fausses (codes qualite 2, 3, 6, 7)
  - divise par l'echelle (10 pour les dixiemes, 1000 pour passer de metres a km)
- `nettoyer_fichier(contenu)` traite un fichier complet. Elle :
  1. lit seulement les colonnes utiles (`COLONNES`)
  2. decode les variables demandees : `temperature`, `wind_speed`, `wind_direction`, `pressure`, `visibility`, `precipitation`. La pluie est ramenee en mm par heure : hauteur divisee par la duree de mesure.
  3. convertit `DATE` en vraie date UTC (`timestamp`), arrondie a l'heure
  4. supprime les valeurs impossibles avec les `BORNES` (exemple : une temperature hors de -40 a 50 degres)
  5. regroupe en une seule ligne par heure (`groupby`), car certaines stations envoient plusieurs releves par heure. On fait la moyenne, sauf pour la direction du vent : on ne fait pas la moyenne d'un angle (la moyenne de 350 et 10 degres donnerait 180).
  6. cree une grille horaire complete (`asfreq("h")`), puis bouche les trous de 3 heures maximum par interpolation, pour la temperature et la pression seulement. Ces deux variables changent doucement, contrairement a la pluie.
  7. ajoute `wind_speed_kmh` (m/s x 3,6), le nom de la station, sa position et sa ville (`ville_proche`)
- `traiter(cle)` lit un fichier dans bronze et le nettoie. Si un fichier est abime, il est ignore et le reste continue.
- `main()` traite annee par annee : tous les fichiers d'une annee en parallele, puis un Parquet par annee.

**Ou arrivent les donnees :**
- `silver/meteo/year=AAAA/meteo.parquet` : une ligne par station et par heure
- `silver/meteo/stations.parquet` : la liste des stations avec leur ville

**Resultat attendu :**

```
  2021 : 197,422 lignes horaires, 25 stations
  ...
Silver pret. 26 stations, dont 26 rattachees a une grande ville.
```

### Etape 1.3 : analyser

```
python -m urbanhub.meteo.analyser
```

Code : [urbanhub/meteo/analyser.py](urbanhub/meteo/analyser.py)

**Chargement : fonction `charger`.** Cinq ans de donnees horaires, c'est beaucoup. On fabrique donc deux tables plus petites :
- **un tableau journalier par station** : temperature moyenne, min et max, vent moyen et max, pression, visibilite, cumul de pluie. Les jours avec moins de 12 heures mesurees sont retires, car pas fiables. Ce tableau est aussi sauve dans `gold/meteo/meteo_journaliere.parquet`.
- **un echantillon de 10 % des heures**, pour les correlations.

**Q1 - Periodes meteorologiques anormales : fonction `q1_anomalies`**
1. On calcule la temperature moyenne de la France pour chaque jour.
2. On calcule la "normale" de chaque jour de l'annee : la moyenne du meme jour sur les 5 ans, lissee sur 15 jours.
3. L'anomalie est la difference entre le jour et sa normale. On la divise par l'ecart-type pour obtenir un score z.
4. Un score superieur a 1,5 pendant au moins 3 jours d'affilee donne une vague de chaleur. Un score inferieur a -1,5 donne une vague de froid. La fonction `periodes` trouve ces suites de jours.
5. On fait pareil avec le cumul de pluie sur 30 jours, pour les periodes tres seches ou tres humides.

Resultats :
- tableau `q1_periodes_anormales` (type, debut, fin, duree, ecart moyen)
- graphique `meteo_q1_anomalies_temperature.png`

**Q2 - Meteo et visibilite : fonction `q2_visibilite`**
- On calcule la correlation de Spearman entre toutes les variables. Spearman suit le classement des valeurs et marche meme si la relation n'est pas une droite.
- On calcule la visibilite mediane selon l'intensite de la pluie : aucune, faible, moderee, forte.

Resultats :
- tableau `q2_correlations`
- graphique `meteo_q2_visibilite.png` : a gauche une carte de chaleur des correlations, a droite des barres

**Q3 - Evolution saisonniere : fonction `q3_saisons`**
- Temperature moyenne de chaque mois pour chaque ville, avec la moyenne France en noir.
- Cycle saisonnier moyen : la moyenne de chaque mois de janvier a decembre, par ville.
- Ecart ete / hiver de chaque ville (juillet-aout moins decembre-janvier).

Resultats :
- tableau `q3_profil_saisonnier_villes`
- graphique `meteo_q3_saisons.png`

**Q4 - Jours extremes : fonction `q4_extremes`**

Pour chaque station et chaque jour, on teste 5 regles :
- chaleur : maximum de 35 degres ou plus
- gel fort : minimum de -10 degres ou moins
- vent fort : 72 km/h ou plus
- pluie forte : 50 mm ou plus
- brouillard : visibilite moyenne sous 1 km

Ensuite, pour chaque jour, on calcule la part des stations en situation extreme. Les 20 jours avec la plus grande part sont les plus extremes.

Resultats :
- tableau `q4_jours_extremes`
- graphique `meteo_q4_extremes_par_mois.png` : nombre d'extremes par mois et par type


---

## 6. Partie 2 - Velos (flux streaming)

Source : l'API CityBikes, qui donne en temps reel l'etat des stations de velos en libre-service.

### Etape 2.1 : collecter en continu

```
python -m urbanhub.velos.collecter
```

Options :
- `--intervalle 150` : secondes entre deux collectes, a garder entre 120 et 180
- `--une-fois` : une seule collecte, pour tester
- `--toutes-villes` : tous les reseaux francais, pas seulement les 11 grandes villes

Ce script tourne sans fin : il faut le laisser dans un terminal ouvert. `Ctrl + C` l'arrete.

Code : [urbanhub/velos/collecter.py](urbanhub/velos/collecter.py)

**a) Trouver les reseaux : fonction `reseaux_france`**
- Elle appelle `https://api.citybik.es/v2/networks`, qui liste les reseaux du monde entier.
- Elle garde ceux dont le pays est `FR` et dont la ville correspond a une des 11 villes.
- La comparaison des noms passe par `simplifier`, qui enleve accents et majuscules.

On obtient 12 reseaux, dont Velib (Paris), Velo'v (Lyon), V3 (Bordeaux) et V'Lille. La liste est rafraichie toutes les heures.

**b) Recuperer les stations : fonction `stations_du_reseau`.** Elle appelle `https://api.citybik.es/v2/networks/<id>`, qui renvoie toutes les stations d'un reseau.

**c) Une collecte : fonction `collecter`**
- Les 12 reseaux sont interroges en meme temps (8 threads).
- Tout est regroupe dans un seul fichier JSON, une "photo" de toutes les stations a cet instant.
- Le fichier est depose dans `bronze/velos/citybikes/year=AAAA/month=MM/day=JJ/snapshot_AAAAMMJJTHHMMSS.json`.

**d) La boucle : fonction `main`**
- Elle collecte, puis attend le temps qu'il faut pour respecter l'intervalle.
- En cas d'erreur (coupure reseau, API en panne), elle affiche l'erreur et reessaie au tour suivant. Le script ne s'arrete pas.

**Resultat attendu**, une ligne toutes les 2 min 30 :

```
08:48:06 UTC  12 reseaux, 3352 stations
08:50:35 UTC  12 reseaux, 3352 stations
```

**Important.** L'API ne donne que l'etat du moment, sans historique. L'historique se construit en laissant tourner la collecte : une semaine minimum, pour voir la difference entre semaine et week-end.

### Etape 2.2 : nettoyer

```
python -m urbanhub.velos.nettoyer
python -m urbanhub.velos.nettoyer --jour 2026-11-19   (un seul jour)
```

Code : [urbanhub/velos/nettoyer.py](urbanhub/velos/nettoyer.py)

- `lignes_snapshot(cle)` ouvre une photo et en sort une ligne par station, avec les variables du sujet :
  - `station_id`, `station_name`, `latitude`, `longitude`, `timestamp`
  - `bikes_available` (appele `free_bikes` dans l'API)
  - `free_slots` (appele `empty_slots` dans l'API)
  - plus `city`, `network_id` et `collected_at` (l'heure de notre collecte)
- `nettoyer_jour(prefixe)` lit toutes les photos d'un jour (16 en parallele), puis :
  - convertit les dates et les nombres
  - supprime les lignes sans identifiant ou sans position GPS
  - met a vide les nombres negatifs (erreurs de l'API)
  - calcule `capacity` (velos + places libres) et `fill_rate` (velos / capacite, le taux de remplissage)
  - supprime les doublons (meme station, meme collecte)
- `main()` traite chaque jour et ecrit un Parquet par jour dans `silver/velos/date=AAAA-MM-JJ/velos.parquet`.

On peut relancer ce script autant de fois qu'on veut : le jour en cours est simplement reecrit avec les nouvelles photos.

### Etape 2.3 : analyser

```
python -m urbanhub.velos.analyser
```

Code : [urbanhub/velos/analyser.py](urbanhub/velos/analyser.py)

**L'idee cle : les "mouvements".** On ne voit pas les trajets, seulement le nombre de velos dans chaque station. Mais entre deux photos (2 min 30 d'ecart) :
- si une station passe de 10 a 7 velos, 3 velos ont ete pris
- si elle passe de 7 a 9, 2 velos ont ete deposes

La somme de ces changements, en valeur absolue, s'appelle les "mouvements". C'est notre mesure de l'utilisation.

**Chargement : fonction `charger`**
- Elle lit tous les jours de silver et trie par station puis par heure.
- Elle calcule `mouvements` = valeur absolue de la difference avec la photo precedente (`diff`). Si plus de 15 minutes separent deux photos (collecte interrompue), le changement n'est pas compte, car on ne sait pas ce qui s'est passe entre les deux.
- Elle marque les moments ou la station est vide (0 velo) ou pleine (0 place).
- Elle ecarte les villes dont l'API renvoie toujours 0 velo (Marseille, voir les limites).

**Resume par station : fonction `stats_stations`.** Pour chaque station :
- capacite et position
- total des mouvements et taux de remplissage moyen
- part du temps vide et part du temps pleine
- rotations par jour = mouvements / capacite / nombre de jours. Cela permet de comparer une petite et une grande station.
- distance au centre-ville

Ce resume est sauve dans `gold/velos/stations_resume.parquet`.

**Q1 - Stations les plus utilisees : fonction `q1_utilisation`.** Top 20 des stations avec le plus de rotations par jour. Les stations de moins de 5 places sont ignorees, car trop petites pour etre significatives.

Resultats : tableau `q1_top_stations`, graphique `velos_q1_top_stations.png`.

**Q2 - Zones ou l'offre est insuffisante : fonction `q2_offre_insuffisante`**
- On decoupe chaque ville en carres d'environ 500 m : la latitude et la longitude sont arrondies a 0,005 degre.
- Pour chaque carre, on calcule la part du temps ou ses stations sont vides.
- Un carre est en manque si ses stations sont vides plus de 25 % du temps.

Resultats : tableau `q2_zones_insuffisantes`, graphique `velos_q2_carte_stations_vides.png` (carte des stations, plus le rouge est fonce, plus elles sont souvent vides).

**Q3 - Pics d'utilisation : fonction `q3_pics`**
- Pour chaque ville, on calcule la part des mouvements de la journee faite a chaque heure (heure de Paris).
- On compare la semaine et le week-end.

Resultats : tableau `q3_heure_de_pointe`, graphique `velos_q3_pics_journaliers.png`.

**Q4 - Desequilibres geographiques : fonction `q4_desequilibres`**
- On classe les stations par distance au centre : 0-2 km, 2-4, 4-6, 6-10, plus de 10.
- On calcule le taux de remplissage moyen de chaque bande, par ville.
- On compare le matin (7h-10h) et le soir (17h-20h). Le matin, les gens vont travailler au centre, donc le centre se remplit et la peripherie se vide. Le soir, c'est l'inverse.

Resultats : tableau `q4_remplissage_par_distance`, graphique `velos_q4_desequilibres.png`.

**Q5 - Stations critiques a reequilibrer : fonction `q5_critiques`**
- **"A remplir"** : la station est vide plus de 30 % du temps, ou elle a 1 velo ou moins a la derniere photo.
- **"A vider"** : la station est pleine plus de 30 % du temps, ou elle a 1 place ou moins a la derniere photo.
- Les stations sont classees par urgence, c'est-a-dire la plus grande des deux parts de temps.

Resultats : tableau `q5_stations_critiques` (avec la position GPS, pour envoyer un camion), graphique `velos_q5_stations_critiques.png` (carte de la plus grande ville).


---

## 7. Partie 3 - Pollution (flux IoT)

Source : l'API OpenAQ v3, qui regroupe les capteurs de pollution du monde entier. Elle demande une cle API, lue dans `.env`.

### Etape 3.1 : collecter

Deux modes :

```
python -m urbanhub.pollution.collecter --historique 60    une fois : les 60 derniers jours
python -m urbanhub.pollution.collecter                    en continu : toutes les 15 min
```

Code : [urbanhub/pollution/collecter.py](urbanhub/pollution/collecter.py)

**a) Appeler l'API proprement : fonction `appel`.** Elle passe toujours par la meme fonction, qui :
- ajoute la cle dans l'en-tete `X-API-Key`
- attend au moins 1,1 seconde entre deux appels, car OpenAQ limite a 60 requetes par minute
- si l'API repond 429 (trop de requetes), attend la fin de la fenetre (en-tete `x-ratelimit-reset`) puis recommence
- si le serveur est en panne (code 500 et plus), reessaie jusqu'a 5 fois

**b) Trouver les capteurs : fonction `chercher_capteurs`.** Pour chaque ville :
- elle demande les stations de mesure a moins de 25 km du centre (`/locations?coordinates=lat,lon&radius=25000`)
- elle ignore celles qui n'ont rien envoye depuis 30 jours (station arretee)
- dans chaque station, elle garde les capteurs des 5 polluants demandes : `pm25`, `pm10`, `o3`, `no2` et `co`

Resultat : environ 286 capteurs, dont 84 a Paris. Ils sont enregistres dans :
- `bronze/pollution/openaq/reference/capteurs.json` : la liste propre
- `bronze/pollution/openaq/reference/locations_<date>.json` : la reponse brute de l'API

**c) Mode flux, la simulation IoT : fonction `collecte_flux`**
- Toutes les 15 minutes, elle demande la derniere mesure de chaque station (`/locations/<id>/latest`).
- C'est comme si les capteurs nous envoyaient leurs donnees en direct.
- Chaque collecte donne un fichier : `bronze/pollution/openaq/flux/year=/month=/day=/snapshot_....json`.

**d) Mode historique : fonction `collecte_historique`**
- Pour chaque capteur, elle demande les moyennes horaires des N derniers jours (`/sensors/<id>/hours`).
- Elle tourne les pages de 1000 resultats si besoin.
- Un fichier par capteur : `bronze/pollution/openaq/historique/sensor=<id>/<debut>_<fin>.json`.

L'historique sert a avoir tout de suite assez de donnees a analyser, sans attendre des semaines. Comptez 10 a 15 minutes pour 60 jours, a cause de la limite de 60 requetes par minute.

### Etape 3.2 : nettoyer

```
python -m urbanhub.pollution.nettoyer
```

Code : [urbanhub/pollution/nettoyer.py](urbanhub/pollution/nettoyer.py)

- `lire_historique(cle)` et `lire_flux(cle, capteurs)` transforment les JSON en lignes. Pour le flux, l'API ne donne que l'identifiant du capteur : on retrouve le polluant, l'unite et la ville grace a `capteurs.json`.
- `vers_ugm3(df)` met tout en microgrammes par m3, car certains capteurs donnent des ppm ou des ppb. La formule est : µg/m3 = ppm x masse molaire x 1000 / 24,45 (24,45 litres = volume d'une mole de gaz a 25 degres). Une unite inconnue donne une valeur mise a vide.
- `main()` :
  - regroupe historique et flux
  - arrondit l'heure
  - supprime les valeurs negatives et impossibles (`MAXI`)
  - supprime les doublons (meme capteur, meme heure)

Variables gardees : `sensor_id`, `pollutant`, `value`, `unit`, `latitude`, `longitude`, `timestamp`, plus `city`, `location_id` et `location_name`.

Les donnees arrivent dans `silver/pollution/pollution.parquet`. Le script affiche aussi le nombre de mesures par ville et par polluant.

### Etape 3.3 : analyser

```
python -m urbanhub.pollution.analyser
```

Code : [urbanhub/pollution/analyser.py](urbanhub/pollution/analyser.py)

**Pourquoi l'OMS ?** On ne peut pas comparer directement 30 µg/m3 de NO2 et 30 µg/m3 de PM2.5 : leur danger n'est pas le meme. On divise donc chaque mesure par la valeur guide de l'OMS (2021), dans le dictionnaire `OMS` :

| Polluant | Valeur guide OMS |
|---|---|
| PM2.5 | 15 µg/m3 sur 24 h |
| PM10 | 45 µg/m3 sur 24 h |
| NO2 | 25 µg/m3 sur 24 h |
| O3 | 100 µg/m3 sur 8 h |
| CO | 4 000 µg/m3 sur 24 h |

Un rapport de 2 veut dire "deux fois la valeur conseillee". C'est la colonne `ratio_oms`, calculee dans `charger`.

**Q1 - Zones les plus polluees : fonction `q1_zones`.** Moyenne de chaque polluant pour chaque station de mesure, puis top 15 des stations pour PM2.5 et pour NO2, avec la valeur OMS en pointilles rouges.

Resultats : tableau `q1_niveaux_par_zone`, graphique `pollution_q1_zones_polluees.png`.

**Q2 - Variation journaliere : fonction `q2_journee`**
- Profil moyen heure par heure de chaque polluant, en % de sa moyenne : 100 = moyenne de la journee, 130 = 30 % au-dessus.
- NO2 en semaine contre le week-end. Le NO2 vient surtout du trafic, on attend donc moins de NO2 le week-end.

Resultats : tableau `q2_profil_horaire`, graphique `pollution_q2_variation_journaliere.png`.

**Q3 - Polluants dominants : fonction `q3_dominants`.** Pour chaque ville, la moyenne du rapport a l'OMS de chaque polluant. Le polluant dominant est celui qui depasse le plus sa valeur guide.

Resultats : tableau `q3_polluants_dominants`, graphique `pollution_q3_polluants_dominants.png`.

**Q4 - Episodes anormaux : fonction `q4_episodes`**
1. Moyenne de tous les capteurs d'une ville, heure par heure.
2. Moyenne glissante sur 24 h (8 h pour l'ozone), comme dans la definition de l'OMS.
3. Une heure est anormale si la moyenne glissante depasse la valeur OMS, ou si la valeur fait partie des 1 % les plus hautes jamais vues dans cette ville.
4. Un episode = au moins 6 heures anormales d'affilee. On note le debut, la fin, la duree et le pic.

Resultats : tableau `q4_episodes`, graphique `pollution_q4_episodes.png` (courbes de la ville la plus touchee, episodes en orange).


---

## 8. Partie 4 - Analyse croisee

### Etape 4.1 : recuperer la meteo recente

```
python -m urbanhub.meteo.recente
```

Code : [urbanhub/meteo/recente.py](urbanhub/meteo/recente.py)

**Pourquoi ce script ?** La NOAA s'arrete en aout 2025, alors que les velos et la pollution sont collectes maintenant. Pour les croiser, il faut une meteo sur la meme periode. On la prend chez Open-Meteo (gratuit, sans cle) :
- ce sont les memes variables que la partie 1, pour les 92 derniers jours, heure par heure, au centre de chaque ville
- le JSON brut va dans `bronze/meteo/openmeteo/<date>/<ville>.json`
- la table propre va dans `silver/meteo_recente/meteo_recente.parquet`

A chaque lancement, les nouvelles heures s'ajoutent aux anciennes. Il faut donc le relancer de temps en temps, par exemple une fois par jour.

### Etape 4.2 : analyser

```
python -m urbanhub.croisement.analyser
```

Code : [urbanhub/croisement/analyser.py](urbanhub/croisement/analyser.py)

**Construire la table commune : fonction `construire_table`.** On fabrique une table ou une ligne = une ville x une heure.
- `meteo_horaire` : la meteo de la ville. On utilise NOAA quand elle existe, sinon Open-Meteo. Si les deux ont la meme heure, NOAA est gardee, car c'est une vraie station.
- `pollution_horaire` : la moyenne des capteurs de la ville, avec une colonne par polluant.
- `velos_horaire` : les mouvements de velos de la ville, divises par le nombre de collectes de l'heure. Les heures avec moins de 10 collectes sont ignorees, car trop incompletes.
- `meme_format_date` met les dates des 3 sources exactement au meme format, sinon la jointure echoue.

Les trois sont jointes sur ville + heure. La table est sauvee dans `gold/croisement/table_ville_heure.parquet`.

**L'indice d'usage des velos.** Il y a toujours moins de velos a 3 h du matin qu'a 18 h, qu'il pleuve ou non. Pour voir l'effet de la meteo, il faut enlever cet effet de l'heure. On divise donc les mouvements par la moyenne habituelle a cette heure-la, pour ce type de jour (semaine ou week-end) et dans cette ville :
- indice 1 = normal
- indice 1,2 = 20 % de plus que d'habitude
- indice 0,7 = 30 % de moins

**Q1 - Meteo et pollution : fonction `q1_meteo_pollution`**
- Correlation de Spearman entre chaque variable meteo et chaque polluant.
- Pollution moyenne selon la force du vent : le vent disperse la pollution, on attend donc moins de pollution quand il y a du vent.

Resultats : tableau `q1_correlation_meteo_pollution`, graphique `croisement_q1_meteo_pollution.png`.

**Q2 - Meteo et velos : fonction `q2_meteo_velos`**
- `classes_meteo` range chaque heure dans des classes : temperature par tranches de 5 degres, pluie ou sec (plus ou moins de 0,2 mm), vent calme, modere ou fort.
- On calcule l'indice d'usage moyen de chaque classe.

Resultats : tableau `q2_correlation_meteo_velos`, graphique `croisement_q2_meteo_velos.png` (3 graphiques en barres).

**Q3 - Conditions favorables : fonction `q3_favorables`**
- On teste toutes les combinaisons temperature x pluie x vent qui ont au moins 10 heures de donnees.
- On les classe par indice d'usage.

Resultats :
- tableau `q3_conditions_favorables` : la premiere ligne donne la meilleure meteo pour le velo
- graphique `croisement_q3_conditions_favorables.png` : carte de chaleur temperature x vent, par temps sec

**Q4 - Interactions fortes : fonction `q4_interactions`**
1. On passe au niveau du jour : usage moyen, NO2 moyen (ou PM2.5), temperature, pluie, vent.
2. Pour chaque ville, on transforme chaque variable en score z (ecart a la moyenne de la ville, en ecarts-types).
3. Un jour d'interaction forte est un jour ou les trois s'ecartent nettement de la normale en meme temps (score superieur a 1) : usage des velos, pollution et meteo (le plus fort ecart parmi temperature, pluie et vent).

Exemple typique : un jour de tempete, avec beaucoup de pluie et de vent, peu de velos et peu de pollution, car le vent la disperse.

Resultats : tableau `q4_jours_interaction_forte`, graphique `croisement_q4_interactions.png` (les ecarts de la ville principale, jours forts en orange).


---

## 9. Bonus : ClickHouse et tableau de bord

### ClickHouse (SQL rapide, comme au TP OLAP)

```
python -m urbanhub.charger_clickhouse
```

Code : [urbanhub/charger_clickhouse.py](urbanhub/charger_clickhouse.py)

ClickHouse lit directement les Parquet de MinIO avec la fonction `s3()`. Le script cree trois tables (`urbanhub.meteo`, `urbanhub.velos`, `urbanhub.pollution`) avec le moteur MergeTree.

Les requetes sont ecrites ainsi :

```
CREATE TABLE ... ENGINE = MergeTree ORDER BY ... AS SELECT * FROM s3('http://minio:9000/silver/...', ...)
```

Dans le reseau Docker, MinIO s'appelle `minio` et ecoute sur 9000 : c'est le port interne au conteneur.

Ensuite :
1. Ouvrir http://localhost:8123/play
2. Se connecter avec l'utilisateur `urbanhub` et le mot de passe `urbanhub123` (en haut a droite)
3. Copier une requete de [sql/requetes.sql](sql/requetes.sql)

Il y a des exemples avec `GROUP BY`, `argMax` et une window function (`lagInFrame ... OVER (PARTITION BY ...)`), comme au TP.

### Tableau de bord (pour les videos de demo)

```
streamlit run dashboard/app.py
```

Code : [dashboard/app.py](dashboard/app.py)

Il s'ouvre dans le navigateur (http://localhost:8501) et contient :
- **onglet "Temps reel"** : la derniere photo des velos, lue directement dans bronze. On choisit une ville et on voit une carte (vert = velos disponibles, rouge = station vide), 3 chiffres cles et la liste des stations. Les donnees se rafraichissent toutes les 2 minutes.
- **onglets "1 Meteo" a "4 Croisement"** : chaque question avec son explication, son graphique et son tableau de resultats (a deplier).
- **onglet "Data Lake"** : le nombre de fichiers et la taille de chaque dossier dans bronze, silver et gold. Pratique pour montrer l'architecture dans la video.


---

## 10. Comment regarder les resultats

Il y a cinq facons de voir les resultats, de la plus simple a la plus technique.

**1. Le terminal.** Chaque script d'analyse affiche ses chiffres principaux pendant qu'il tourne : top 10, correlations, nombre d'episodes, etc. C'est la premiere chose a lire.

**2. Les fichiers locaux (dans VS Code)**
- `rapports/figures/` : tous les graphiques en PNG. Cliquer dessus dans VS Code les ouvre.
- `rapports/` : tous les tableaux en CSV, a ouvrir dans VS Code ou Excel.

Les noms suivent toujours la meme regle : `<partie>_<question>_<sujet>`, par exemple `velos_q5_stations_critiques.png`.

**3. La console MinIO** (http://localhost:9011, `urbanhub` / `urbanhub123`)
- Menu "Object Browser" puis choisir un bucket.
- `bronze` : les donnees brutes. On peut ouvrir un JSON de velos pour voir exactement ce que renvoie l'API.
- `silver` : les Parquet propres.
- `gold` : les indicateurs. Les PNG de `gold/<partie>/figures/` s'affichent avec le bouton "Preview".
- Sur un fichier de bronze, l'onglet "Versions" montre l'historique (versioning).

**4. ClickHouse** (http://localhost:8123/play) pour poser ses propres questions en SQL, voir la section 9.

**5. En Python**, pour explorer une table a la main :

```
python
>>> from urbanhub import datalake
>>> df = datalake.get_parquet("gold", "velos/q5_stations_critiques.parquet")
>>> df.head(20)
>>> meteo = datalake.get_parquet("silver", "meteo/year=2024/meteo.parquet")
>>> meteo.describe()
```

**Et pour les videos :** tableau de bord Streamlit (section 9) et console MinIO pour montrer le Data Lake.


---

## 11. Resultats et interpretation

### Partie 1 - Meteo

Donnees : 1 026 fichiers NOAA telecharges en parallele, 208 stations de France metropolitaine, de janvier 2021 a aout 2025, soit 7,1 millions de lignes horaires apres nettoyage.

**1. Periodes anormales.** La methode trouve 19 vagues de chaleur, 17 vagues de froid, 4 periodes tres seches et 8 tres humides. Elles correspondent a des evenements reels, ce qui montre que la methode fonctionne :
- l'automne 2023 tres pluvieux (du 30 octobre au 3 decembre, 35 jours : tempetes Ciaran et Domingos)
- l'automne 2024 tres pluvieux (du 9 octobre au 4 novembre)
- la secheresse de l'ete 2022 (du 26 juillet au 15 aout)
- la vague de froid de debut janvier 2021 (4,4 degres sous la normale pendant 11 jours)

**2. Visibilite.** Elle baisse nettement avec la pluie :

| Pluie | Visibilite mediane |
|---|---|
| aucune | 13,3 km |
| faible | 12,0 km |
| moderee | 8,3 km |
| forte | 6,7 km |

Elle augmente un peu avec la temperature (correlation de 0,20), car le brouillard se forme surtout par temps froid. Les correlations restent faibles : la visibilite depend aussi de l'humidite et de la pollution, que l'on n'a pas ici.

**3. Saisons.** Toutes les villes suivent le meme cycle : minimum en janvier, maximum en juillet-aout.
- L'ecart ete / hiver est plus grand a l'interieur des terres (Lyon 18,4 degres, Strasbourg 17,2) que pres de l'Atlantique (Nantes 13,6, Rennes 12,9). C'est l'effet de l'ocean, qui adoucit le climat.
- Nice et Marseille sont les plus chaudes toute l'annee.

**4. Jours extremes.** Les 10 jours les plus extremes sont tous des jours de chaleur :
- le 18 juillet 2022, 75 % des stations francaises ont depasse 35 degres
- le 1er juillet 2025, 65 %
- les 11 a 15 aout 2025, entre 45 et 61 %

Les autres extremes sont plus rares et plus locaux : pluies fortes en octobre 2024, brouillard en hiver.

### Partie 3 - Pollution

Donnees : 60 jours (du 20 septembre au 19 novembre 2026), 269 capteurs dans les 11 villes, environ 300 000 mesures horaires.

**1. Zones les plus polluees.**
- **NO2 :** la station la plus touchee est Feyzin Stade, au sud de Lyon, avec 62 µg/m3 en moyenne, soit 2,5 fois la valeur OMS. C'est le "couloir de la chimie" (raffinerie, industrie) le long de l'autoroute A7.
- **PM2.5 :** la plus touchee est le boulevard Ornano a Paris (18e), avec 16 µg/m3, juste au-dessus de la valeur OMS. C'est un grand axe tres circule.

Les zones les plus polluees sont donc les grands axes routiers et les zones industrielles.

**2. Variation dans la journee.** Oui, elle est forte :
- **NO2 :** deux pics, vers 9 h et 21 h, aux heures de pointe du trafic. L'ecart entre le minimum et le maximum vaut 75 % de la moyenne. En semaine, le pic du matin est presque deux fois plus haut que le week-end (30 contre 17 µg/m3), ce qui prouve le lien avec les trajets domicile-travail.
- **Ozone :** il fait l'inverse. Il est au plus bas le matin et culmine vers 16 h, car il se forme sous l'effet du soleil a partir des gaz d'echappement du matin.
- **Particules (PM2.5) :** elles montent le soir et la nuit (chauffage au bois en automne, air plus stable la nuit).

**3. Polluant dominant.** Rapporte a la valeur OMS, le NO2 domine dans 8 villes sur 11 (Paris 0,95, Marseille 0,99, Strasbourg 0,91). Le PM2.5 domine a Lille, Nantes et Rennes. Le CO est partout tres loin de sa limite (moins de 0,1) : il n'est plus un probleme en ville.

**4. Episodes anormaux.** 149 episodes detectes, surtout du NO2 : Montpellier 16, Marseille 14, Paris 13. Les episodes de NO2 durent souvent plusieurs jours : ce sont des periodes sans vent, ou la pollution s'accumule (voir partie 4). Les episodes d'ozone touchent surtout le Sud (Marseille, Nice), plus ensoleille.

### Partie 4 - Croisement (premiers resultats)

**1. Meteo et pollution.** Oui, la relation est nette (correlations de Spearman, heure par heure) :
- **Le vent disperse la pollution :** -0,51 avec le NO2, -0,46 avec le CO, -0,35 avec les PM2.5. Quand le vent tombe, la pollution s'accumule.
- **La chaleur et le soleil fabriquent l'ozone :** +0,63 entre temperature et O3.
- **La pluie lave un peu l'air :** correlation faiblement negative avec tous les polluants.
- **La haute pression va avec plus de pollution** (+0,14 a +0,21) : c'est le temps calme et stable des anticyclones.

**Questions 2 a 4 (velos).** Il faut plusieurs jours de collecte velos. A completer ensuite.

Ce qu'il faudra regarder :
- **Velos :** les heures de pointe (on attend 8 h et 18 h en semaine), et si le centre se remplit le matin puis se vide le soir.
- **Croisement :** la pluie et le froid devraient faire baisser l'indice d'usage des velos.


---

## 12. Limites et problemes rencontres

- **Velos, pas d'historique :** CityBikes ne donne que l'etat actuel. L'historique "depuis l'existence du reseau Velib" demande par le sujet n'est pas disponible par cette source. On construit le notre en laissant tourner la collecte.
- **Marseille :** le reseau renvoie toujours 0 velo disponible. La ville est collectee mais ecartee des analyses velos.
- **Nice :** le seul reseau connu de CityBikes (Pony) est en free-floating, sans stations. Il n'y a donc rien a analyser pour Nice cote velos.
- **NOAA :** le lien du sujet a change (redirection vers AWS) et les donnees s'arretent en aout 2025. D'ou Open-Meteo pour la partie 4.
- **Mouvements :** quand l'operateur reequilibre une station en camion, ces deplacements comptent aussi comme des mouvements.
- **Pollution :** les capteurs ne sont pas partout. Certaines villes ont peu de stations, surtout pour le CO.
- **Image MinIO :** l'image officielle `minio/minio` a ete retiree, on utilise `pgsty/minio`.


---

## 13. En cas de probleme

| Message | Cause | Solution |
|---|---|---|
| `Could not connect to the endpoint URL` | MinIO n'est pas lance | demarrer Docker Desktop puis `docker compose up -d` |
| `InvalidAccessKeyId` | mauvais identifiants ou mauvais MinIO (port 9000 au lieu de 9010) | verifier `MINIO_URL=http://localhost:9010` dans `.env` |
| `port is already allocated` | un autre programme utilise le port | arreter l'autre conteneur, ou changer le port dans `docker-compose.yml` et `.env` |
| `Cle OpenAQ manquante` | `.env` vide | remplir `OPENAQ_API_KEY` |
| `No module named urbanhub` | lance depuis le mauvais dossier ou sans `-m` | se placer a la racine du projet et utiliser `python -m urbanhub....` |
| `No module named boto3` (ou autre) | environnement non active | `.venv\Scripts\activate` |
| `Connection was closed before we received a valid response` | coupure passagere de Docker Desktop sous Windows quand il y a beaucoup d'envois en meme temps | boto3 reessaie deja 10 fois tout seul. Si ca arrive encore, relancer le script : il reprend ou il s'etait arrete |
| `Q2, Q3 et Q4 : seulement N heures de collecte velos` | pas assez de collecte velos pour le croisement | laisser tourner le collecteur velos au moins 24 h, idealement une semaine |
| `Pas de donnees` dans une analyse | l'etape precedente n'a pas ete lancee | lancer collecter puis nettoyer avant analyser |

Pour tout arreter : `docker compose down`. Les donnees restent dans le volume Docker. `docker compose down -v` efface aussi les donnees, a eviter.
