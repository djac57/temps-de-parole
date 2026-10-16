"""Convertit les CSV Arcom (temps de parole mensuels) en un JSON compact pour la visualisation."""
import csv, glob, json, os, re, sys, unicodedata
from collections import Counter, defaultdict

HERE = os.path.dirname(__file__)
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "data", "raw")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "site", "data.js")
SHORT = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
FULL = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
SKIP = re.compile(r"^(Total|Part|dont) ")


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
P, G = defaultdict(int), []  # sparse records


def idx(lst, v):
    if v not in lst:
        lst.append(v)
    return lst.index(v)


paths = sorted(glob.glob(os.path.join(SRC, "**", "*.csv"), recursive=True))
periods = sorted({period_of(p) for p in paths})
pindex = {p: i for i, p in enumerate(periods)}

for path in paths:
    m = pindex[period_of(path)]
    rows = list(csv.reader(open(path, encoding="utf-8-sig"), delimiter=";"))
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
            gid = parties.setdefault(label, len(parties))
            for j, ci, ti in cols:
                s = secs(r[j]) if j < len(r) else 0
                if s:
                    G.append([gid, m, ci, ti, s])

party_names = list(parties)
ROLES = {"Ministre", "Premier Ministre"}
keys = [k for k, v in people.items() if v["names"]]
pidx = {k: i for i, k in enumerate(keys)}
people_out = []
for k in keys:
    v = people[k]
    affs = [a for a, _ in v["affs"].most_common() if a not in ROLES]
    roles = [a for a in v["affs"] if a in ROLES]
    aff = affs[0] if affs else "Gouvernement"
    if aff.startswith("Président de la République"):
        aff = "Président de la République"
    people_out.append([display(v["names"]), aff, 1 if roles else 0])
P = [[pidx[k], m, ci, ti, s] for (k, m, ci, ti), s in P.items()]
data = {
    "months": [SHORT[mm - 1] for y, mm in periods],
    "years": [y for y, mm in periods],
    "monthsFull": [f"{FULL[mm - 1]} {y}" for y, mm in periods],
    "channels": [{"n": c, "t": chan_type[c]} for c in channels],
    "types": ["Journaux", "Magazines", "Autres programmes"],
    "parties": party_names,
    "people": people_out,
    "P": P,
    "G": G,
}
with open(OUT, "w", encoding="utf-8") as f:
    f.write("window.TP_DATA=")
    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";")
print(len(periods), "mois,", len(people_out), "personnalités,", len(party_names), "partis,", len(channels), "chaînes,", len(P), "+", len(G), "enregistrements,", os.path.getsize(OUT) // 1024, "Ko")
