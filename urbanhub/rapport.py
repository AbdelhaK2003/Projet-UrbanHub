"""Petits outils pour enregistrer les resultats (graphiques et tableaux) dans la couche gold."""
import matplotlib

matplotlib.use("Agg")  # pas besoin d'ecran pour generer les images
import matplotlib.pyplot as plt

from urbanhub import config, datalake

plt.rcParams.update({"figure.figsize": (11, 5), "axes.grid": True, "grid.alpha": 0.3})
# 20 couleurs differentes (la palette par defaut n'en a que 10, or on a 11 villes)
plt.rcParams["axes.prop_cycle"] = plt.cycler(color=plt.cm.tab20.colors[::2] + plt.cm.tab20.colors[1::2])


def sauver_figure(fig, partie, nom):
    """Enregistre l'image en local (rapports/figures) et dans gold/<partie>/figures."""
    chemin = config.FIGURES / f"{partie}_{nom}.png"
    fig.tight_layout()
    fig.savefig(chemin, dpi=120)
    plt.close(fig)
    datalake.put_fichier("gold", f"{partie}/figures/{nom}.png", chemin, "image/png")
    print(f"  figure : {chemin.name}")


def sauver_table(df, partie, nom):
    """Enregistre un tableau d'indicateurs en Parquet dans gold et en CSV en local."""
    datalake.put_parquet("gold", f"{partie}/{nom}.parquet", df)
    df.to_csv(config.FIGURES.parent / f"{partie}_{nom}.csv", index=False)
    print(f"  table  : gold/{partie}/{nom}.parquet ({len(df)} lignes)")


def titre(texte):
    print("\n" + texte)
    print("-" * len(texte))
