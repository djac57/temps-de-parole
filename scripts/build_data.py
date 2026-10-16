"""Convertit les CSV Arcom en un JSON compact pour la visualisation.

Deux sources sont fusionnées :
- data/raw/<partis|personnalites>_AAAA-MM.csv : relevés mensuels hors périodes électorales ;
- data/raw/elections/<scrutin>.csv : relevés de campagne (fetch_elections.py), publiés en
  périodes cumulées par chaîne, ramenés ici à des montants mensuels.
"""
import csv, glob, json, os, re, sys, unicodedata
from collections import Counter, defaultdict

HERE = os.path.dirname(__file__)
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "data", "raw")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "site", "data.js")
SHORT = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
FULL = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
SKIP = re.compile(r"^(Total|Part|dont) ")
CAMPAIGN = 3  # type d'émission « campagne électorale » (non ventilé par l'Arcom)

# Identifiants de chaîne des relevés de campagne -> noms des relevés mensuels
CHANNEL_SLUGS = {
    "tf1": "TF1", "france_2": "France 2", "france_3": "France 3", "france_5": "France 5", "m6": "M6", "tmc": "TMC",
    "w9": "W9", "t18": "T18", "novo19": "Novo19", "rmc_life": "RMC Life", "rmc_decouverte": "RMC Decouverte",
    "rmc_story": "RMC Story", "c8": "C8", "bfmtv": "BFMTV", "cnews": "CNews", "lci": "LCI", "franceinfo_TV": "franceinfo:",
    "france_info": "France Info", "france_culture": "France Culture", "france_inter": "France Inter",
    "radio_classique": "Radio Classique", "bfm_business": "BFM Business", "rmc": "RMC", "rtl": "RTL",
    "europe_1": "Europe 1", "sud_radio": "Sud Radio",
}
NEW_CHANNEL_TYPES = {"W9": "Chaîne généraliste"}
ELECTION_NAMES = {"municipales": "Municipales", "presidentielle": "Présidentielle", "legislatives": "Législatives",
                  "europeennes": "Européennes", "europennes": "Européennes", "regionales-departementales": "Régionales"}
LISTS_LABEL = {"municipales": "Listes municipales (campagne)"}
EMISSIONS = {"JTF": 0, "MAG": 1, "PROG": 2}
SERVICE_TYPES = {"Chaînes généralistes": "Chaîne généraliste", "Chaînes d'information": "Chaîne d'information", "Radio": "Radio"}

# Filiations : anciens noms -> nom actuel, pour que les courbes ne se coupent pas
PARTY_LINEAGE = {
    "UNION POUR UN MOUVEMENT POPULAIRE": "Les Républicains", "UMP": "Les Républicains",
    "FRONT NATIONAL": "Rassemblement national",
    "EN MARCHE": "Renaissance", "LA REPUBLIQUE EN MARCHE": "Renaissance", "ENSEMBLE": "Renaissance",
    "EUROPE ECOLOGIE LES VERTS": "Les Ecologistes", "LES VERTS": "Les Ecologistes",
    "MODEM": "Mouvement démocrate", "MOUVEMENT DEMOCRATE": "Mouvement démocrate",
    "DEBOUT LA REPUBLIQUE": "Debout la France",
    "GENERATIONS": "Génération.s", "GENERATION S": "Génération.s",
    "UNION DES DEMOCRATES INDEPENDANTS": "Union des démocrates et indépendants",
    "PRESIDENCE DE LA REPUBLIQUE": "Président de la République",
    "COLLABORATEURS DU PRESIDENT DE LA REPUBLIQUE": "Président de la République",
}


def secs(v):
    v = v.strip()
    if not v or v == "-" or ":" not in v:
        return 0
    h, m, s = (int(x) for x in v.split(":"))
    return h * 3600 + m * 60 + s


def norm(n):
    # Insensible aux accents, à la casse et aux traits d'union (« JEAN-LUC » = « JEAN LUC »)
    return " ".join(unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().upper().replace("-", " ").split())


def display(variants):
    # Préfère la graphie « NOM Prénom » à la version tout en majuscules
    return max(variants, key=lambda v: (v != v.upper(), "-" in v, variants[v]))


def period_of(path):
    # Fichiers produits par fetch_arcom.py : <partis|personnalites>_AAAA-MM.csv
    yyyy, mm = re.search(r"_(\d{4})-(\d{2})\.csv$", os.path.basename(path)).groups()
    return int(yyyy), int(mm)


channels, chan_type, people, parties = [], {}, {}, {}
party_key = {}  # forme normalisée -> libellé retenu
P, G = defaultdict(int), defaultdict(int)  # clés -> secondes


def idx(lst, v):
    if v not in lst:
        lst.append(v)
    return lst.index(v)


def pkey(label):
    # « PARTI SOCIALISTE », « Parti socialiste » et « Partisocialiste » : même formation
    return re.sub(r"[^A-Z0-9]", "", norm(label))


LINEAGE = {pkey(k): v for k, v in PARTY_LINEAGE.items()}
party_variants = defaultdict(Counter)  # clé -> graphies rencontrées


def party_id(label):
    label = re.sub(r"\s+", " ", label).strip()
    k = pkey(label)
    if k in LINEAGE:
        label, k = LINEAGE[k], pkey(LINEAGE[k])
    party_variants[k][label] += 1
    if k not in party_key:
        party_key[k] = len(parties)
        parties[k] = len(parties)
    return parties[k]


def party_label(k):
    # Graphie la plus courante en casse mixte ; sinon, majuscules adoucies
    v = party_variants[k]
    mixed = [x for x in v if x != x.upper()]
    if mixed:
        return max(mixed, key=lambda x: (v[x], " " in x))
    return max(v, key=v.get).capitalize()


# ---------- Relevés mensuels hors périodes électorales ----------
paths = sorted(glob.glob(os.path.join(SRC, "partis_*.csv")) + glob.glob(os.path.join(SRC, "personnalites_*.csv")))
monthly = []
for path in paths:
    rows = list(csv.reader(open(path, encoding="utf-8-sig"), delimiter=";"))
    monthly.append((period_of(path), rows))

# ---------- Relevés de campagne : cumuls par période -> montants mensuels ----------
elections, campaign = [], []  # campaign : (année, mois, chaîne, type, libellé, circonscription, secondes)
for path in sorted(glob.glob(os.path.join(SRC, "elections", "*.csv"))):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    if not rows:
        continue
    slug = rows[0]["scrutin"]
    kind = re.match(r"[a-z-]+?(?=-\d{4})", slug).group(0)
    year = re.search(r"\d{4}", slug).group(0)
    elections.append({"name": f"{ELECTION_NAMES.get(kind, kind.title())} {year}",
                      "start": min(r["debut"] for r in rows), "end": max(r["fin"] for r in rows)})
    # Dans chaque tour, les périodes partagent leur date de début : ce sont des cumuls
    series = defaultdict(lambda: defaultdict(int))
    for r in rows:
        key = (r["chaine"], r["tour"], r["debut"], r["type"], r["circonscription"], r["libelle"])
        series[key][r["fin"]] += int(r["secondes"])
    for (chaine, tour, debut, typ, circ, lib), by_end in series.items():
        prev = 0
        by_month = defaultdict(int)
        for fin in sorted(by_end):
            by_month[fin[:7]] = max(by_month[fin[:7]], by_end[fin])
        for ym in sorted(by_month):
            cum = max(prev, by_month[ym])
            if cum > prev:
                y, mo = (int(x) for x in ym.split("-"))
                campaign.append((y, mo, chaine, typ, lib, circ, cum - prev, kind))
            prev = cum

# ---------- Historique 2012-2024 (fetch_history.py) : par parti seulement ----------
history = []
hist_path = os.path.join(SRC, "history.csv")
if os.path.exists(hist_path):
    for r in csv.DictReader(open(hist_path, encoding="utf-8")):
        y, mo = (int(x) for x in r["mois"].split("-"))
        history.append((y, mo, r["service"], r["emission"], r["chaine"], r["libelle"], int(r["secondes"])))

seen = {p for p, _ in monthly} | {(c[0], c[1]) for c in campaign} | {(h[0], h[1]) for h in history}
# Mois continus du premier au dernier : les mois sans relevé publié restent des trous
(y0, m0), (y1, m1) = min(seen), max(seen)
periods = [(y, mo) for y in range(y0, y1 + 1) for mo in range(1, 13) if (y0, m0) <= (y, mo) <= (y1, m1)]
pindex = {p: i for i, p in enumerate(periods)}

for period, rows in monthly:
    m = pindex[period]
    is_person = rows[0][1] == "Appartenance"
    off = 2 if is_person else 1
    hdr_c, hdr_s, hdr_t = rows[0], rows[1], rows[2]
    cols = []
    for j in range(off, len(hdr_c)):
        c = hdr_c[j].strip()
        chan_type[c] = hdr_s[j]
        cols.append((j, idx(channels, c), ["JTF", "MAG", "PROG"].index(hdr_t[j])))
    for r in rows[3:]:
        if not r or not r[0].strip():
            continue
        if is_person:
            name, aff = r[0].strip(), r[1].strip()
            key = norm(name)
            info = people.setdefault(key, {"names": Counter(), "affs": Counter()})
            for j, ci, ti in cols:
                s = secs(r[j]) if j < len(r) else 0
                if s:
                    info["names"][name] += s
                    info["affs"][aff] += s
                    P[(key, m, ci, ti)] += s
        else:
            label = r[0].strip()
            if SKIP.match(label):
                continue
            gid = party_id(label)
            for j, ci, ti in cols:
                s = secs(r[j]) if j < len(r) else 0
                if s:
                    G[(gid, m, ci, ti)] += s

HSKIP = ("TOTAL", "DONT", "PARTDE", "PARTDES", "PARTEXEC", "PARTPARTIS")  # mais pas « PARTI… »
for y, mo, service, emission, chaine, lib, s in history:
    if pkey(lib).startswith(HSKIP) or emission not in EMISSIONS:
        continue
    chan_type.setdefault(chaine, SERVICE_TYPES.get(service, "Chaîne généraliste"))
    G[(party_id(lib), pindex[(y, mo)], idx(channels, chaine), EMISSIONS[emission])] += s

ROLES = {"Ministre", "Premier Ministre"}


def main_affiliation(v):
    affs = [a for a, _ in v["affs"].most_common() if a not in ROLES]
    aff = affs[0] if affs else "Gouvernement"
    return "Président de la République" if aff.startswith("Président de la République") else aff


unmapped = Counter()
for y, mo, chaine, typ, lib, circ, s, kind in campaign:
    name = CHANNEL_SLUGS.get(chaine)
    if not name:
        unmapped[chaine] += s
        continue
    chan_type.setdefault(name, NEW_CHANNEL_TYPES.get(name, "Chaîne généraliste"))
    ci, m = idx(channels, name), pindex[(y, mo)]
    if typ.startswith("Président de la République"):
        G[(party_id("Président de la République"), m, ci, CAMPAIGN)] += s
    elif typ.startswith("Partis"):
        G[(party_id(lib), m, ci, CAMPAIGN)] += s
    elif typ.startswith("Listes"):
        G[(party_id(LISTS_LABEL.get(kind, "Listes candidates (campagne)")), m, ci, CAMPAIGN)] += s
    else:
        # Scrutins à candidats (présidentielle…) : rattachés à la personnalité si on la connaît
        key = norm(re.sub(r"^(Liste|M\.|Mme)\s+", "", lib))
        if key in people:
            P[(key, m, ci, CAMPAIGN)] += s
            people[key]["names"].setdefault(lib, 0)
            G[(party_id(main_affiliation(people[key])), m, ci, CAMPAIGN)] += s
        else:
            G[(party_id(f"{typ} (campagne)"), m, ci, CAMPAIGN)] += s
if unmapped:
    print("chaînes de campagne non reconnues :", dict(unmapped), file=sys.stderr)

party_names = [party_label(k) for k in parties]
keys = [k for k, v in people.items() if sum(v["names"].values())]
pidx = {k: i for i, k in enumerate(keys)}
people_out = []
for k in keys:
    v = people[k]
    roles = [a for a in v["affs"] if a in ROLES]
    people_out.append([display(v["names"]), main_affiliation(v), 1 if roles else 0])
P = [[pidx[k], m, ci, ti, s] for (k, m, ci, ti), s in P.items() if k in pidx]
G = [[g, m, ci, ti, s] for (g, m, ci, ti), s in G.items()]
data = {
    "months": [SHORT[mm - 1] for y, mm in periods],
    "years": [y for y, mm in periods],
    "monthsFull": [f"{FULL[mm - 1]} {y}" for y, mm in periods],
    "ym": [f"{y}-{mm:02d}" for y, mm in periods],
    "personStart": min((m for _, m, _, _, _ in P), default=0),
    "channels": [{"n": c, "t": chan_type[c]} for c in channels],
    "types": ["Journaux", "Magazines", "Autres programmes", "Campagne électorale"],
    "elections": elections,
    "parties": party_names,
    "people": people_out,
    "P": P,
    "G": G,
}
with open(OUT, "w", encoding="utf-8") as f:
    f.write("window.TP_DATA=")
    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";")
print(len(periods), "mois,", len(people_out), "personnalités,", len(party_names), "partis,", len(channels), "chaînes,",
      len(elections), "scrutin(s),", len(P), "+", len(G), "enregistrements,", os.path.getsize(OUT) // 1024, "Ko")
