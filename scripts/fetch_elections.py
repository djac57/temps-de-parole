"""Télécharge les relevés Arcom de temps de parole « en période électorale ».

Pendant une campagne, l'Arcom ne publie plus ces temps dans les relevés
mensuels : ils sont publiés par chaîne et par période (cumulée) sur
https://www.arcom.fr/temps-parole/election/<scrutin>. Ce script découvre les
scrutins en cours ou récents (année >= START_YEAR), lit chaque relevé et
enregistre data/raw/elections/<scrutin>.csv (une ligne par entité et période).
"""
import base64
import datetime
import csv
import html
import os
import re
import sys
import time
import urllib.parse
import urllib.request

START_YEAR = 2025
BASE = "https://www.arcom.fr"
UA = "Mozilla/5.0 (compatible; temps-de-parole-viz/1.0)"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "elections")
MOIS = {m: i + 1 for i, m in enumerate(["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
                                         "août", "septembre", "octobre", "novembre", "décembre"])}
FIELDS = ["scrutin", "chaine", "tour", "debut", "fin", "type", "circonscription", "libelle", "secondes"]


def get(path, retries=3):
    url = path if path.startswith("http") else BASE + path
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            if attempt == retries - 1:
                raise
            print(f"  nouvel essai {url} ({e})", file=sys.stderr)
            time.sleep(5 * (attempt + 1))


def action_urls(page):
    # Les liens du site sont encodés (base64 d'une URL échappée) dans data-action-url
    out = []
    for raw in re.findall(r'data-action-url="([^"]+)"', page):
        try:
            out.append(urllib.parse.unquote(base64.b64decode(raw + "=" * (-len(raw) % 4)).decode()))
        except Exception:
            pass
    return out


def text(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def secs(v):
    h, m, s = (int(x) for x in v.split(":"))
    return h * 3600 + m * 60 + s


def parse_period(title):
    # « … : Du 2 au 13 février 2026 » ou « Du 2 février au 13 mars 2026 »
    m = re.search(r"Du (\d{1,2})(?:er)? ?([a-zéû]+)? ?(\d{4})? au (\d{1,2})(?:er)? ([a-zéû]+) (\d{4})", title)
    if not m:
        raise ValueError(f"période illisible : {title}")
    d1, m1, y1, d2, m2, y2 = m.groups()
    m1, y1 = m1 or m2, y1 or y2
    return f"{y1}-{MOIS[m1]:02d}-{int(d1):02d}", f"{y2}-{MOIS[m2]:02d}-{int(d2):02d}"


def parse_releve(page):
    title = text(re.search(r"<title>(.*?)</title>", page, re.S).group(1))
    tour = "2" if "Second tour" in title else "1"
    debut, fin = parse_period(title)
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    headings = {hid: text(h) for hid, h in re.findall(
        r'id="(headingAccordion-\d+)".*?accordion-button[^>]*>(.*?)</div>', body, re.S)}
    rows = []
    for attrs, table in re.findall(r"<table([^>]*)>(.*?)</table>", body, re.S):
        cells = [[text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
                 for tr in re.findall(r"<tr.*?</tr>", table, re.S)]
        if not cells:
            continue
        kind = cells[0][0]
        circ = ""
        lab = re.search(r'aria-labelledby="([^"]+)"', attrs)
        if lab:
            circ = headings.get(lab.group(1), "")
        for r in cells[1:]:
            if len(r) < 2 or not re.fullmatch(r"\d+:\d{2}:\d{2}", r[1]) or r[0].startswith("Total"):
                continue
            rows.append({"tour": tour, "debut": debut, "fin": fin, "type": kind,
                         "circonscription": circ, "libelle": r[0], "secondes": secs(r[1])})
    return rows


def elections():
    index = get("/temps-parole/election")
    found = {}
    for path in sorted(set(re.findall(r'href="(/temps-parole/election/[a-z-]+)"', index))):
        for u in action_urls(get(path)):
            m = re.match(r"/temps-parole/election/releves/([a-z-]+)/((\d{4})[^/]*)$", u)
            if m and int(m.group(3)) >= START_YEAR:
                found[f"{m.group(1)}-{m.group(2)}"] = u
    return found


def main():
    os.makedirs(OUT, exist_ok=True)
    found = elections()
    print(f"{len(found)} scrutin(s) : {', '.join(found) or '-'}")
    for slug, url in found.items():
        path = os.path.join(OUT, slug + ".csv")
        if os.path.exists(path):
            # Scrutin terminé depuis plus de 90 jours : les relevés ne bougent plus
            with open(path, encoding="utf-8") as fh:
                last = max((r["fin"] for r in csv.DictReader(fh)), default="")
            if last and datetime.date.fromisoformat(last) < datetime.date.today() - datetime.timedelta(days=90):
                print(f"  {slug} : terminé le {last}, déjà téléchargé")
                continue
        links = sorted({u for u in action_urls(get(url)) if u.startswith(url + "/")})
        rows = []
        for link in links:
            chaine = link.rstrip("/").split("/")[-2]
            for r in parse_releve(get(link)):
                rows.append({"scrutin": slug, "chaine": chaine, **r})
            time.sleep(0.2)
        if not rows:
            print(f"  {slug} : aucun relevé exploitable, fichier inchangé")
            continue
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"  {slug} : {len(links)} relevés, {len(rows)} lignes")


if __name__ == "__main__":
    main()
