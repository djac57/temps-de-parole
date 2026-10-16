"""Historique Arcom (CSA) avant 2025 : relevés mensuels par parti et par chaîne.

Avant 2025, l'Arcom ne publie pas de CSV : un fichier par type de média, type
d'émission et mois, en Excel (.xls, 2012-2021), OpenDocument (.odt, 2021) ou
Word (.docx, 2022-2024). Ce script les télécharge (cache local, non versionné),
extrait leur tableau partis x chaînes et écrit data/raw/history.csv.

Les relevés historiques ne changent plus : à lancer à la main, une fois.
Dépendance : xlrd (pour les .xls), installable avec `pip install xlrd`.

    python3 scripts/fetch_history.py [année_début] [année_fin]
"""
import csv
import hashlib
import html
import json
import os
import re
import struct
import sys
import time
import urllib.request
import zipfile

BASE = "https://www.arcom.fr"
INDEX = BASE + "/temps-parole/hors-elections/recherche/service/{year}/mois/service"
UA = "Mozilla/5.0 (compatible; temps-de-parole-viz/1.0)"
HERE = os.path.dirname(__file__)
CACHE = os.path.join(HERE, "..", "data", "cache", "history")
OUT = os.path.join(HERE, "..", "data", "raw", "history.csv")
PREFERRED = ["docx", "odt", "xlsx", "xls"]
TIME = re.compile(r"^\d{1,4}:\d{2}:\d{2}$|^\d{1,4}h\d{1,2}min\d{1,2}s$")
LOGOS_FILE = os.path.join(HERE, "history_logos.json")  # empreinte d'image -> chaîne
FIELDS = ["mois", "service", "emission", "chaine", "libelle", "secondes"]


def get(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            if attempt == retries - 1:
                raise
            print(f"  nouvel essai {url} ({e})", file=sys.stderr)
            time.sleep(5 * (attempt + 1))


def list_files(year):
    page = get(INDEX.format(year=year)).decode("utf-8")
    m = re.search(r'drupal-settings-json">(.*?)</script>', page, re.S)
    best = {}
    for block in json.loads(m.group(1)).get("tphpe") or []:
        for month in block.get("mois", []):
            for g in month.get("groupes", []):
                if g.get("type") != "partis" or g.get("type_emission") not in ("JTF", "MAG", "PROG"):
                    continue
                d1, m1, y1 = g["date_start"].split("/")
                d2, m2, y2 = g["date_end"].split("/")
                if d1 != "01" or (m1, y1) != (m2, y2):
                    continue  # relevés par quinzaine : on garde le mois entier
                files = {f["format"]: f["file_uri"] for f in g["fichiers"]}
                fmt = next((k for k in PREFERRED if k in files), None)
                if not fmt:
                    continue  # PDF seulement
                key = (f"{y1}-{m1}", g["type_service"], g["type_emission"])
                span = int(d2)
                if key not in best or span > best[key][0]:
                    best[key] = (span, BASE + files[fmt], fmt)
    return {k: (url, fmt) for k, (_, url, fmt) in best.items()}


# ---------- Lecture des tableaux : chaque format -> grille de chaînes de caractères ----------

def grid_docx(path):
    x = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    rows = []
    for tb in re.findall(r"<w:tbl>.*?</w:tbl>", x, re.S):
        for tr in re.findall(r"<w:tr[ >].*?</w:tr>", tb, re.S):
            rows.append([html.unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", tc))).strip()
                         for tc in re.findall(r"<w:tc>.*?</w:tc>", tr, re.S)])
    return rows


def grid_odt(path):
    x = zipfile.ZipFile(path).read("content.xml").decode("utf-8")
    rows = []
    for tr in re.findall(r"<table:table-row[ >].*?</table:table-row>", x, re.S):
        cells = []
        for attrs, body in re.findall(r"<table:(?:covered-)?table-cell([^>]*?)(?:/>|>(.*?)</table:(?:covered-)?table-cell>)", tr, re.S):
            rep = re.search(r'number-columns-repeated="(\d+)"', attrs)
            img = re.search(r'xlink:href="([^"]+)"', body or "")
            if img:  # logo de chaîne en guise d'en-tête
                txt = "IMG:" + hashlib.md5(zipfile.ZipFile(path).read(img.group(1))).hexdigest()[:12]
            else:
                txt = html.unescape(re.sub(r"<[^>]+>", "", body or "")).strip()
            cells.extend([txt] * min(int(rep.group(1)) if rep else 1, 64))
        rows.append(cells)
    return rows


def _biff_records(stream):
    pos = 0
    while pos + 4 <= len(stream):
        rid, ln = struct.unpack_from("<HH", stream, pos)
        yield rid, stream[pos + 4:pos + 4 + ln]
        pos += 4 + ln


def _escher(buf, pos=0, end=None):
    end = len(buf) if end is None else end
    while pos + 8 <= end:
        verinst, typ, ln = struct.unpack_from("<HHI", buf, pos)
        start, stop = pos + 8, min(pos + 8 + ln, end)
        yield typ, verinst >> 4, buf[start:stop]
        if verinst & 0xF == 0xF:  # conteneur
            yield from _escher(buf, start, stop)
        pos = stop


def xls_images(path):
    """Logos d'en-tête d'un .xls : [(feuille, ligne, colonne, empreinte)].

    Les images vivent dans le flux Escher (MSODRAWINGGROUP pour les images,
    MSODRAWING de chaque feuille pour leurs ancrages)."""
    from xlrd import compdoc
    cd = compdoc.CompDoc(open(path, "rb").read())
    wb = cd.get_named_stream("Workbook") or cd.get_named_stream("Book")
    group, sheets, cur, last = b"", [], None, None
    for rid, d in _biff_records(wb):
        if rid == 0x00EB:
            group += d; last = "g"
        elif rid == 0x0809:
            cur = bytearray(); sheets.append(cur); last = None
        elif rid == 0x00EC and cur is not None:
            cur += d; last = "s"
        elif rid == 0x003C and last == "g":
            group += d
        elif rid == 0x003C and last == "s":
            cur += d
        else:
            last = None
    blips = []
    for typ, inst, body in _escher(group):
        if typ == 0xF007:
            blip = body[36:]
            _, _, bln = struct.unpack_from("<HHI", blip, 0) if len(blip) >= 8 else (0, 0, 0)
            blips.append(hashlib.md5(blip[25:8 + bln]).hexdigest()[:12] if bln else None)
    out = []
    for si, sh in enumerate(sheets[1:]):  # sheets[0] : flux global du classeur
        pib = None
        for typ, inst, body in _escher(bytes(sh)):
            if typ == 0xF004:
                pib = None
            elif typ == 0xF00B:
                for k in range(inst):
                    pid, val = struct.unpack_from("<HI", body, 6 * k)
                    if pid & 0x3FFF == 0x0104:
                        pib = val
            elif typ == 0xF010 and len(body) >= 18 and pib and pib <= len(blips):
                _, c1, _, r1 = struct.unpack_from("<HHHH", body, 0)
                out.append((si, r1, c1, blips[pib - 1]))
                pib = None
    return out


def grid_xls(path):
    import xlrd  # noqa: import tardif, seulement utile pour les vieux fichiers
    book = xlrd.open_workbook(path)
    try:
        imgs = xls_images(path)
    except Exception:
        imgs = []
    rows = []
    for si, sh in enumerate(book.sheets()):
        logos = {(r, c): h for s_, r, c, h in imgs if s_ == si and h}
        for r in range(max(sh.nrows, max([k[0] + 1 for k in logos] or [0]))):
            row = []
            for c in range(max(sh.ncols, 1 + max([k[1] for k in logos if k[0] == r] or [0]))):
                if (r, c) in logos:
                    row.append("IMG:" + logos[(r, c)])
                    continue
                if r >= sh.nrows or c >= sh.ncols:
                    row.append("")
                    continue
                cell = sh.cell(r, c)
                if cell.ctype in (xlrd.XL_CELL_NUMBER, xlrd.XL_CELL_DATE) and 0 < cell.value < 50 and r > 0:
                    s = round(cell.value * 86400)  # durée stockée en fraction de jour
                    row.append(f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}")
                else:
                    row.append(str(cell.value).strip())
            rows.append(row)
    return rows


READERS = {"docx": grid_docx, "odt": grid_odt, "xls": grid_xls, "xlsx": None}


def secs(v):
    h, m, s = (int(x) for x in re.findall(r"\d+", v))
    return h * 3600 + m * 60 + s


LOGOS = json.load(open(LOGOS_FILE, encoding="utf-8")) if os.path.exists(LOGOS_FILE) else {}
# Anciens noms -> nom actuel (i>Télé est devenue CNews, D8 C8, NT1 TFX, Numéro 23 RMC Story…)
CHANNEL_ALIASES = {"BFM": "BFM Business", "BFM TV": "BFMTV", "I>TELE": "CNews", "I-TELE": "CNews", "ITELE": "CNews",
                   "D8": "C8", "DIRECT 8": "C8", "NT1": "TFX", "NUMERO 23": "RMC Story", "N°23": "RMC Story",
                   "RMC DECOUVERTE": "RMC Decouverte", "FRANCEINFO": "franceinfo:", "FRANCEINFO:": "franceinfo:"}


CHANNELS = ["TF1", "France 2", "France 3", "France 4", "France 5", "Canal+", "M6", "C8", "TMC", "TFX", "W9",
            "RMC Story", "RMC Decouverte", "BFMTV", "CNews", "LCI", "franceinfo:", "France Inter", "France Info",
            "France Culture", "Radio Classique", "BFM Business", "RMC", "RTL", "Europe 1", "Sud Radio"]


def _key(h):
    import unicodedata
    return " ".join(unicodedata.normalize("NFKD", h).encode("ascii", "ignore").decode().upper().split())


CANON = {_key(c): c for c in CHANNELS} | {_key(k): v for k, v in CHANNEL_ALIASES.items()}


def channel(h):
    """Nom de chaîne normalisé, ou None si l'en-tête n'est pas une chaîne connue."""
    if h.startswith("IMG:"):
        return LOGOS.get(h[4:])
    return CANON.get(_key(h))


def extract(rows):
    """Repère la ligne d'en-tête (noms de chaînes) puis lit les lignes partis."""
    out, header = [], None
    for r in rows:
        cells = [c.strip() for c in r]
        if len(cells) < 2:
            continue
        values = cells[1:]
        times = [v for v in values if TIME.match(v)]
        if not times:
            names = [v for v in values if v and v not in ("-", "_") and not re.match(r"^[\d,.%\s]+$", v)]
            if names and not cells[0]:
                header = cells
            continue
        label = cells[0]
        if not header or not label or re.match(r"^(TOTAL|PART|dont|Total|Part)\b", label):
            continue
        for j, v in enumerate(values, start=1):
            if j < len(header) and header[j] and not header[j].upper().startswith("POUR INFO") and TIME.match(v):
                s = secs(v)
                ch = channel(header[j])
                if s and ch:
                    out.append((ch, label, s))
    return out


def main():
    y0 = int(sys.argv[1]) if len(sys.argv) > 1 else 2012
    y1 = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
    os.makedirs(CACHE, exist_ok=True)
    rows, empty = [], []
    for year in range(y0, y1 + 1):
        files = list_files(year)
        print(f"{year} : {len(files)} fichiers exploitables")
        for (ym, service, emission), (url, fmt) in sorted(files.items()):
            path = os.path.join(CACHE, os.path.basename(url))
            if not os.path.exists(path):
                with open(path, "wb") as fh:
                    fh.write(get(url))
                time.sleep(0.1)
            try:
                got = extract(READERS[fmt](path))
            except Exception as e:
                print(f"  illisible {os.path.basename(url)} : {e}", file=sys.stderr)
                got = []
            if not got:
                empty.append(os.path.basename(url))
            rows += [{"mois": ym, "service": service, "emission": emission, "chaine": c, "libelle": l, "secondes": s}
                     for c, l, s in got]
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} lignes -> data/raw/history.csv")
    if empty:
        print(f"{len(empty)} fichiers sans tableau exploitable : {', '.join(empty[:10])}{' …' if len(empty) > 10 else ''}")


if __name__ == "__main__":
    main()
