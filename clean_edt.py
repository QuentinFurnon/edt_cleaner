#!/usr/bin/env python3
"""Nettoie les titres d'un flux ICS d'emploi du temps, fusionne les cours
identiques qui se suivent, et écrit un nouvel .ics.

Usage : clean_edt.py <url_source> <fichier_sortie>
Ex.   : clean_edt.py "https://.../edt.ics" edt-xxxx.ics
"""
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta

# Deux cours de même titre séparés par moins que ça sont fusionnés
ECART_MAX = timedelta(minutes=15)

# "TD - IN-R302-Algos corrects et efficaces, ATTIOGBE, Jeremie (Enseignant)"
TITRE = re.compile(
    r"^(?P<type>[^-]+?) - IN-(?:[A-Z]-)?[A-Z]+\d+-(?P<matiere>.+?), [^,]+, .*\(Enseignant\)\s*$"
)
# "Réunion - ATTIOGBE, Jeremie (Enseignant)" / "Atelier TD - COTTAIS, Kristell"
TITRE_SANS_CODE = re.compile(r"^(?P<type>[^,]+?) - [A-ZÀ-Ý][A-ZÀ-Ý'\- ]+, .+$")


def unesc(s):
    return s.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ").replace("\\\\", "\\")


def esc(s):
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")


def clean_block(block):
    loc = re.search(r"^LOCATION[^:\n]*:(.*)$", block, re.M)
    salle = unesc(loc.group(1)).strip() if loc else ""

    def repl(m):
        brut = unesc(m.group(2))
        t = TITRE.match(brut)
        if t:
            titre = f"{t['type'].strip()} {t['matiere'].strip()}"
        else:
            t = TITRE_SANS_CODE.match(brut)
            if not t:
                return m.group(0)  # format inconnu : on ne touche pas
            titre = t["type"].strip()
        if salle:
            titre += f" · {salle}"
        return "SUMMARY:" + esc(titre)

    return re.sub(r"^(SUMMARY[^:\n]*):(.*)$", repl, block, flags=re.M)


def champ(block, nom):
    """Renvoie (parametres, valeur) d'une propriété, ou None."""
    m = re.search(rf"^{nom}([^:\n]*):(.*)$", block, re.M)
    return (m.group(1), m.group(2).strip()) if m else None


def parse_dt(valeur):
    return datetime.strptime(valeur[:15], "%Y%m%dT%H%M%S")  # lève ValueError si all-day


def infos(block):
    """(titre, location, param_debut, debut, fin) ou None si non fusionnable."""
    try:
        s, d, e = champ(block, "SUMMARY"), champ(block, "DTSTART"), champ(block, "DTEND")
        if not (s and d and e):
            return None
        loc = champ(block, "LOCATION")
        return (s[1], loc[1] if loc else "", d[0], parse_dt(d[1]), parse_dt(e[1]))
    except ValueError:
        return None


def fusionne(blocs):
    """Fusionne les événements de même titre/salle qui se suivent ou se chevauchent."""
    items = [(infos(b), b) for b in blocs]
    fusionnables = sorted((x for x in items if x[0]), key=lambda x: x[0][3])
    autres = [b for i, b in items if not i]
    sortie = []
    for info, bloc in fusionnables:
        for k, (pinfo, pbloc) in enumerate(sortie):
            if pinfo[:3] == info[:3] and info[3] <= pinfo[4] + ECART_MAX and info[3] >= pinfo[3]:
                if info[4] > pinfo[4]:  # on étend la fin
                    d_old = champ(pbloc, "DTEND")
                    d_new = champ(bloc, "DTEND")
                    pbloc = pbloc.replace(
                        f"DTEND{d_old[0]}:{d_old[1]}", f"DTEND{d_new[0]}:{d_new[1]}", 1
                    )
                    pinfo = pinfo[:4] + (info[4],)
                    sortie[k] = (pinfo, pbloc)
                break
        else:
            sortie.append((info, bloc))
    return [b for _, b in sortie] + autres


def main(url, sortie):
    brut = urllib.request.urlopen(url, timeout=30).read().decode("utf-8")
    texte = re.sub(r"\r?\n[ \t]", "", brut)  # déplie les lignes coupées
    texte = texte.replace("\r\n", "\n")

    motif = re.compile(r"BEGIN:VEVENT.*?END:VEVENT", re.S)
    blocs = [clean_block(m.group(0)) for m in motif.finditer(texte)]
    blocs = fusionne(blocs)
    premier = texte.find("BEGIN:VEVENT")
    dernier = texte.rfind("END:VEVENT") + len("END:VEVENT")
    if premier == -1:
        resultat = texte
    else:
        resultat = texte[:premier] + "\n".join(blocs) + texte[dernier:]

    tmp = sortie + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(resultat.replace("\n", "\r\n"))
    os.replace(tmp, sortie)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
