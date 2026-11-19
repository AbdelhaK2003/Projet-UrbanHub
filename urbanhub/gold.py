"""Enregistrement des indicateurs dans la couche gold.

Chaque resultat d'analyse est un tableau (DataFrame) range en Parquet :
  gold/<partie>/<nom>.parquet
Il est ensuite charge dans ClickHouse (table gold_<partie>_<nom>) et affiche par l'interface.
Pas d'image : l'interface dessine elle-meme les graphiques a partir de ces tableaux.
"""
from urbanhub import datalake


def sauver_table(df, partie, nom):
    df = df.reset_index(drop=True)
    df.columns = [str(c) for c in df.columns]
    for c in df.select_dtypes("category").columns:  # categories pandas -> texte simple
        df[c] = df[c].astype(str)
    flottants = df.select_dtypes("float").columns
    df[flottants] = df[flottants].round(3)  # 3 decimales suffisent pour l'affichage
    datalake.put_parquet("gold", f"{partie}/{nom}.parquet", df)
    print(f"  gold/{partie}/{nom}.parquet ({len(df)} lignes)")


def titre(texte):
    print("\n" + texte)
    print("-" * len(texte))
