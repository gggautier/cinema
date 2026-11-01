#!/usr/bin/env python3
"""Séances du jour des cinémas de data/cinemas.json → data/showtimes.json.

Usage personnel. Une requête par cinéma (plus une par page de résultats),
une seconde de pause entre chaque, User-Agent explicite.

  python scripts/fetch_showtimes.py               # tous les cinémas, aujourd'hui (heure de Paris)
  python scripts/fetch_showtimes.py --only C0159  # un seul cinéma, pour tester
  python scripts/fetch_showtimes.py --probe       # teste le wrapper PyPI « allocine »
  python scripts/fetch_showtimes.py --resolve     # cherche les ids Allociné manquants (n'écrit rien)
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PARIS = ZoneInfo("Europe/Paris")
BASE = "https://www.allocine.fr"
PAUSE = 1.0
UA = "DejaVu-showtimes/1.0 (usage personnel ; github.com/gggautier/cinema)"

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json, text/html;q=0.8", "Accept-Language": "fr-FR,fr;q=0.9"})


def log(*a):
    print(*a, file=sys.stderr)


def load(name, default):
    p = DATA / name
    return json.loads(p.read_text("utf-8")) if p.exists() else default


def save(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# ---------------------------------------------------------------- wrapper PyPI

def probe_wrapper():
    try:
        from allocine import Allocine  # pip install allocine
    except Exception as e:
        return f"import impossible ({e})"
    try:
        t = Allocine().get_theater(theater_id="C0159")
        n = len(getattr(t, "showtimes", []) or [])
        return f"ok ({n} séances)" if n else "répond mais aucune séance renvoyée"
    except Exception as e:
        return f"cassé ({type(e).__name__}: {e})"


# ---------------------------------------------------------------- allocine.fr

def fetch_theater(cid, day):
    """Endpoint JSON appelé par la page /seance/salle_gen_csalle=… du site."""
    results, page, pages = [], 1, 1
    while page <= pages:
        url = f"{BASE}/_/showtimes/theater-{cid}/d-{day}/" + (f"p-{page}/" if page > 1 else "")
        r = S.get(url, timeout=20)
        r.raise_for_status()
        j = r.json()
        if j.get("error"):
            raise RuntimeError(j.get("message") or "erreur renvoyée par Allociné")
        results += j.get("results") or []
        pages = int((j.get("pagination") or {}).get("totalPages") or 1)
        page += 1
        if page <= pages:
            time.sleep(PAUSE)
    return results


def version_of(st, movie):
    v = str(st.get("diffusionVersion") or "").upper()
    langs = [str(l).upper() for l in (movie.get("languages") or [])]
    if v.startswith("ORIGINAL"):
        return "VF" if "FRENCH" in langs else "VOST"
    if v in ("DUBBED", "LOCAL"):
        return "VF"
    return None


def booking_of(st):
    for t in ((st.get("data") or {}).get("ticketing") or []):
        urls = t.get("urls") or ([t["url"]] if t.get("url") else [])
        if urls:
            return urls[0]
    return None


def year_of(movie):
    for rel in movie.get("releases") or []:
        d = ((rel.get("releaseDate") or {}).get("date")) or ""
        if d[:4].isdigit():
            return int(d[:4])
    y = (movie.get("data") or {}).get("productionYear")
    return int(y) if str(y or "").isdigit() else None


def parse(results, cid, day):
    fallback = f"{BASE}/seance/salle_gen_csalle={cid}.html"
    films = {}
    for res in results:
        m = res.get("movie") or {}
        aid = str(m.get("internalId") or "")
        if not aid:
            continue
        groups = res.get("showtimes") or {}
        sts = [s for g in groups.values() if isinstance(g, list) for s in g]
        seen, times = set(), []
        for s in sts:
            starts = str(s.get("startsAt") or "")
            if not starts.startswith(day):
                continue
            hm, v = starts[11:16], version_of(s, m)
            if (hm, v) in seen:
                continue
            seen.add((hm, v))
            times.append({"time": hm, "version": v, "booking_url": booking_of(s) or fallback})
        if not times:
            continue
        times.sort(key=lambda t: t["time"])
        films[aid] = {
            "allocine_id": aid,
            "title": m.get("title"),
            "original_title": m.get("originalTitle") or m.get("title"),
            "year": year_of(m),
            "showtimes": times,
        }
    return films


# ---------------------------------------------------------------- TMDB ↔ Allociné

def wikidata_map(allocine_ids):
    """P1265 = identifiant AlloCiné d'un film ; P4947 = identifiant TMDB d'un film."""
    out = {}
    ids = list(allocine_ids)
    for i in range(0, len(ids), 100):
        chunk = " ".join(f'"{x}"' for x in ids[i:i + 100])
        q = f"SELECT ?a ?t WHERE {{ VALUES ?a {{ {chunk} }} ?f wdt:P1265 ?a ; wdt:P4947 ?t . }}"
        try:
            r = S.get("https://query.wikidata.org/sparql", params={"query": q, "format": "json"}, timeout=60)
            r.raise_for_status()
            for b in r.json()["results"]["bindings"]:
                a, t = b["a"]["value"], b["t"]["value"]
                if t.isdigit():
                    out.setdefault(a, set()).add(int(t))
        except Exception as e:
            log(f"  Wikidata indisponible ({e}) — repli titre + année")
        time.sleep(PAUSE)
    # Plusieurs ids TMDB pour un même film Allociné : ambigu, on ne devine pas.
    return {a: next(iter(t)) for a, t in out.items() if len(t) == 1}


def tmdb_fallback(film, key):
    if not key or not film.get("original_title") or not film.get("year"):
        return None
    try:
        r = S.get("https://api.themoviedb.org/3/search/movie", timeout=20,
                  params={"api_key": key, "query": film["original_title"], "language": "fr-FR"})
        r.raise_for_status()
    except Exception:
        return None
    want, y = norm(film["original_title"]), film["year"]
    hits = []
    for m in r.json().get("results") or []:
        my = (m.get("release_date") or "")[:4]
        if not my.isdigit() or abs(int(my) - y) > 1:
            continue
        if want in (norm(m.get("original_title")), norm(m.get("title"))):
            hits.append(m["id"])
    return hits[0] if len(hits) == 1 else None


def match_ids(films):
    idmap = load("id-map.json", {})
    todo = [a for a in films if a not in idmap]
    if todo:
        found = wikidata_map(todo)
        idmap.update({a: t for a, t in found.items()})
        key = os.environ.get("TMDB_API_KEY", "").strip()
        for a in todo:
            if a in idmap:
                continue
            t = tmdb_fallback(films[a], key)
            if t:
                idmap[a] = t
            time.sleep(0.25)
        save("id-map.json", dict(sorted(idmap.items())))
    return idmap


# ---------------------------------------------------------------- cinémas

def resolve_cinemas(cinemas):
    for c in cinemas:
        if c.get("allocine_id"):
            continue
        r = S.get(f"{BASE}/rechercher/theater/", params={"q": c["name"]}, timeout=20)
        ids = list(dict.fromkeys(re.findall(r"(?:csalle=|cinema-)([A-Z]\d{4})", r.text)))
        print(f"{c['name']}: {', '.join(ids[:5]) or 'aucun résultat'}")
        time.sleep(PAUSE)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="id Allociné d'un seul cinéma")
    ap.add_argument("--day", help="AAAA-MM-JJ (défaut : aujourd'hui, heure de Paris)")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--resolve", action="store_true")
    args = ap.parse_args()

    cinemas = load("cinemas.json", {"cinemas": []})["cinemas"]
    if args.probe:
        print("wrapper allocine :", probe_wrapper())
        return 0
    if args.resolve:
        resolve_cinemas(cinemas)
        return 0

    now = datetime.now(PARIS)
    day = args.day or now.strftime("%Y-%m-%d")
    targets = [c for c in cinemas if c.get("allocine_id") and (not args.only or c["allocine_id"] == args.only)]
    skipped = [c["name"] for c in cinemas if not c.get("allocine_id")]
    if skipped:
        log("Sans id Allociné (ignorés) :", ", ".join(skipped))

    by_film, ok, failed = {}, [], []
    for i, c in enumerate(targets):
        cid = c["allocine_id"]
        try:
            films = parse(fetch_theater(cid, day), cid, day)
            ok.append(cid)
            log(f"✓ {c['name']} ({cid}) : {len(films)} films")
        except Exception as e:
            failed.append({"cinema_id": cid, "error": f"{type(e).__name__}: {e}"})
            log(f"✗ {c['name']} ({cid}) : {e}")
            films = {}
        for aid, f in films.items():
            entry = by_film.setdefault(aid, {k: f[k] for k in ("allocine_id", "title", "original_title", "year")} | {"cinemas": []})
            entry["cinemas"].append({"cinema_id": cid, "showtimes": f["showtimes"]})
        if i < len(targets) - 1:
            time.sleep(PAUSE)

    if targets and not ok:
        log("Aucun cinéma n'a répondu : showtimes.json n'est pas modifié.")
        return 1

    idmap = match_ids(by_film)
    films, unmatched = [], []
    for aid, f in sorted(by_film.items(), key=lambda kv: kv[1]["title"] or ""):
        f["tmdb_id"] = idmap.get(aid)
        films.append(f)
        if not f["tmdb_id"]:
            unmatched.append({k: f[k] for k in ("allocine_id", "title", "original_title", "year")})
    for u in unmatched:
        log(f"  non apparié : {u['title']} ({u['year']}) — Allociné {u['allocine_id']}")

    save("showtimes.json", {
        "date": day,
        "generated_at": now.isoformat(timespec="seconds"),
        "source": "allocine.fr",
        "cinemas_ok": ok,
        "cinemas_failed": failed,
        "films": films,
        "unmatched": unmatched,
    })
    log(f"{len(films)} films, {len(unmatched)} non appariés, {len(failed)} cinémas en échec.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
