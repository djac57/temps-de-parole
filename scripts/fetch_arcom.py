"""Télécharge les relevés mensuels Arcom « temps de parole hors périodes électorales ».

Pour chaque année depuis START_YEAR, lit la liste des fichiers publiés sur
https://www.arcom.fr/temps-parole/hors-elections/recherche/source/<année>
(embarquée dans le JSON des réglages Drupal de la page) et enregistre les CSV
sous data/raw/<partis|personnalites>_<AAAA-MM>.csv.
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.request

START_YEAR = 2025
BASE = "https://www.arcom.fr"
PAGE = BASE + "/temps-parole/hors-elections/recherche/source/{year}"
KINDS = {"uploaded_csv_partis_politiques": "partis", "uploaded_csv_personnalites": "personnalites"}
UA = "Mozilla/5.0 (compatible; temps-de-parole-viz/1.0)"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def get(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # réseau capricieux : on réessaie
            if attempt == retries - 1:
                raise
            print(f"  nouvel essai ({e})", file=sys.stderr)
            time.sleep(5 * (attempt + 1))


def list_files(year):
    html = get(PAGE.format(year=year)).decode("utf-8")
    m = re.search(r'<script type="application/json" data-drupal-selector="drupal-settings-json">(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError(f"réglages Drupal introuvables pour {year}")
    files = {}
    for block in json.loads(m.group(1)).get("tphpe", []):
        for month in block.get("mois", []):
            for f in month.get("fichiers", []):
                kind = KINDS.get(f.get("type"))
                if not kind or f.get("format") != "csv":
                    continue
                d, mo, y = f["date_start"].split("/")
                key = f"{kind}_{y}-{mo}"
                files.setdefault(key, BASE + f["file_uri"])  # premier listé = version courante
    return files


def main():
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for year in range(START_YEAR, datetime.date.today().year + 1):
        files = list_files(year)
        print(f"{year} : {len(files)} fichiers")
        for key, url in sorted(files.items()):
            body = get(url)
            if not body.lstrip(b"\xef\xbb\xbf").startswith(b";"):
                raise RuntimeError(f"contenu inattendu pour {url}")
            with open(os.path.join(OUT, key + ".csv"), "wb") as fh:
                fh.write(body)
            total += 1
    if total == 0:
        raise SystemExit("aucun fichier récupéré")
    print(f"{total} fichiers enregistrés dans data/raw")


if __name__ == "__main__":
    main()
