"""Etape 0 : cree les buckets bronze / silver / gold dans MinIO.

Lancer : python -m urbanhub.init_datalake
"""
from urbanhub import datalake

if __name__ == "__main__":
    datalake.init_buckets()
    print("Buckets prets :", ", ".join(datalake.BUCKETS), "(versioning actif sur bronze)")
