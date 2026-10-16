# Qui parle à la télé et à la radio ?

Visualisation interactive du temps de parole des personnalités politiques sur 25 chaînes de télévision et radios nationales, d'après les relevés mensuels de l'Arcom « hors périodes électorales », depuis janvier 2025.

- Course animée des personnalités les plus entendues
- Fiche détaillée par personnalité (évolution mensuelle, chaînes, types d'émission)
- Paysage politique mois par mois, par formation
- Équilibre de chaque chaîne (part de chaque formation)
- Filtre « candidats 2027 » déclarés ou pressentis

## Structure

```
site/            page publiée (index.html + data.js généré)
scripts/
  fetch_arcom.py      relevés mensuels hors périodes électorales → data/raw/
  fetch_history.py    historique par parti 2012-2024 (à lancer une fois) → data/raw/history.csv
  history_logos.json  logos de chaînes reconnus dans les vieux fichiers
  fetch_elections.py  relevés de campagne (scrutins en cours ou récents) → data/raw/elections/
  build_data.py       fusionne le tout → site/data.js
data/raw/        CSV bruts Arcom, un fichier par mois et par type
data/raw/elections/  un CSV par scrutin (périodes cumulées par chaîne)
.github/workflows/update.yml
```

## Historique 2012-2024

Avant 2025, l'Arcom (ex-CSA) ne publie que des relevés **par parti**, un fichier par type de média, type d'émission et mois, en Excel (.xls, 2012-2021), OpenDocument (.odt, 2021) ou Word (.docx, 2022-2024). Dans les fichiers .xls et .odt, les en-têtes de chaînes sont des **logos** : `fetch_history.py` extrait chaque image et la reconnaît grâce à `scripts/history_logos.json` (empreinte → chaîne, établie une fois à la main). Le résultat, `data/raw/history.csv`, est versionné ; les fichiers sources restent dans `data/cache/` (non versionné).

Les relevés historiques ne changent plus : le script se lance à la main, une fois (`pip install xlrd` puis `python3 scripts/fetch_history.py`). Trous connus : 2014 – août 2015 (PDF seulement) et février – juin 2017 (aucun relevé). Les anciens noms de partis et de chaînes sont regroupés avec le nom actuel (UMP → LR, FN → RN, LREM → Renaissance, EELV → Les Écologistes, i>Télé → CNews, D8 → C8, NT1 → TFX…), voir `PARTY_LINEAGE` dans `build_data.py`.

## Périodes électorales

Pendant une campagne (environ six semaines avant un scrutin), l'Arcom retire des relevés mensuels le temps de parole lié à l'élection et le publie à part, par chaîne et par période cumulée. `fetch_elections.py` découvre ces scrutins automatiquement sur arcom.fr/temps-parole/election (à partir de 2025, présidentielle 2027 comprise), et `build_data.py` les réintègre mois par mois sous le type d'émission « Campagne ». Le temps des listes municipales, sans étiquette nationale, apparaît sous « Listes municipales (campagne) » ; pour un scrutin à candidats, le temps est rattaché à la personnalité quand elle est reconnue.

## Mise à jour automatique

Le workflow GitHub Actions tourne chaque lundi (et à chaque push sur `main`). Il retélécharge les relevés publiés par l'Arcom, régénère `site/data.js`, committe s'il y a du nouveau, puis déploie `site/` sur GitHub Pages. On peut aussi le lancer à la main depuis l'onglet **Actions** (« Run workflow »).

## En local

```sh
python3 scripts/fetch_arcom.py       # facultatif : rafraîchit data/raw
python3 scripts/fetch_elections.py   # facultatif : relevés de campagne (~5 min)
python3 scripts/build_data.py
open site/index.html
```

Aucune dépendance Python hors bibliothèque standard.

## Liste des candidats 2027

Elle est maintenue à la main dans `site/index.html` (constante `CANDIDATES`), à partir de la presse. Elle ne vaut pas liste officielle : celle-ci dépend de la validation des parrainages.

## Source

Arcom, [relevés des temps de parole hors périodes électorales](https://www.arcom.fr/temps-parole/hors-elections). Données également publiées sur [data.gouv.fr](https://www.data.gouv.fr/fr/datasets/temps-de-parole-des-partis-et-personnalites-politiques-elections-municipales-2026/) pour 2025.
