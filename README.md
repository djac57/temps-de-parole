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
  fetch_elections.py  relevés de campagne (scrutins en cours ou récents) → data/raw/elections/
  build_data.py       fusionne le tout → site/data.js
data/raw/        CSV bruts Arcom, un fichier par mois et par type
data/raw/elections/  un CSV par scrutin (périodes cumulées par chaîne)
.github/workflows/update.yml
```

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
