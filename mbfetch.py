"""Populate vocab/*.json from MusicBrainz.

    python mbfetch.py --conductors 1500 --ensembles 1200

Writes vocab/conductors.json and vocab/ensembles.json, merging with whatever
is already there (hand edits and mined additions survive a refetch).

MusicBrainz asks for <=1 request/second and a descriptive User-Agent; both are
respected here. A full fetch takes a few minutes and is entirely read-only
with respect to your music.
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

VOCAB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vocab")
UA = "MusicLibraryOntology/1.0 (personal library cataloging)"
BASE = "https://musicbrainz.org/ws/2/"
RATE = 1.05          # seconds between requests
PAGE = 100           # MB max limit per page

_last = [0.0]


def _flat(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def get(endpoint, params, retries=4):
    """Rate-limited GET returning parsed JSON, or None."""
    params = dict(params, fmt="json")
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        wait = RATE - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as fh:
                return json.loads(fh.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (503, 429):
                time.sleep(2 * (attempt + 1))
                continue
            print(f"  HTTP {e.code} on {endpoint}", file=sys.stderr)
            return None
        except Exception as e:  # noqa: BLE001 - keep the harvest going
            print(f"  {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(1.5 * (attempt + 1))
    return None


def surname_key(name):
    """Match key for a person: the surname, lowercased and unaccented."""
    n = re.sub(r"\s*\([^)]*\)", "", name).strip()
    n = re.sub(r"\b(sir|dame|lord|maestro|jr\.?|iii?)\b", "", n, flags=re.I)
    n = n.strip(" ,.")
    if "," in n:                       # 'Karajan, Herbert von'
        return _flat(n.split(",")[0].strip())
    parts = [p for p in n.split() if p]
    if not parts:
        return None
    # keep nobiliary particles attached: 'von Dohnanyi' -> 'dohnanyi'
    return _flat(parts[-1])


def harvest_people(limit, query):
    """Artists of type Person whose disambiguation marks them a conductor."""
    out, offset = {}, 0
    while offset < limit:
        data = get("artist", {"query": query, "limit": PAGE, "offset": offset})
        if not data or not data.get("artists"):
            break
        for a in data["artists"]:
            if a.get("type") != "Person":
                continue
            disamb = (a.get("disambiguation") or "").lower()
            name = a.get("name") or ""
            if "conductor" not in disamb:
                continue
            key = surname_key(name)
            if not key or len(key) < 3:
                continue
            entry = out.setdefault(key, {"name": name, "aliases": [],
                                         "mbid": a.get("id"),
                                         "source": "musicbrainz"})
            # prefer the longest/most complete rendering of the name
            if len(name) > len(entry["name"]):
                entry["name"] = name
        offset += PAGE
        print(f"    people {offset}/{limit} -> {len(out)} conductors",
              flush=True)
    return out


def harvest_groups(limit, query):
    """Orchestras, choirs and ensembles."""
    out, offset = {}, 0
    while offset < limit:
        data = get("artist", {"query": query, "limit": PAGE, "offset": offset})
        if not data or not data.get("artists"):
            break
        for a in data["artists"]:
            if a.get("type") not in ("Group", "Orchestra", "Choir"):
                continue
            name = (a.get("name") or "").strip()
            if len(name) < 6 or len(name) > 70:
                continue
            if not re.search(r"orchestra|philharmoni|symphon|sinfoni|"
                             r"staatskapelle|kapelle|ensemble|chor|choir|"
                             r"academy|akademie|camerata|collegium|consort|"
                             r"capella|cappella|quartet|concert",
                             name, re.I):
                continue
            # 'Orchestra' or 'Chorus' as a whole band name would match every
            # folder containing the word; unusable as a pattern
            bare = re.sub(r"[^a-z]", "", _flat(name))
            if bare in {"orchestra", "chorus", "choir", "ensemble", "concert",
                        "quartet", "quintet", "consort", "academy", "camerata",
                        "philharmonic", "symphony", "sinfonia", "capella"}:
                continue
            if len(name.split()) < 2:
                continue
            out[_flat(name)] = {"name": name, "mbid": a.get("id"),
                                "source": "musicbrainz"}
        offset += PAGE
        print(f"    groups {offset}/{limit} -> {len(out)} ensembles",
              flush=True)
    return out


# Surnames shared with composers. A bare 'Bach' in a folder name is the
# composer essentially always, so these may never match on surname alone.
COMPOSER_SURNAMES = {
    "bach", "mozart", "beethoven", "brahms", "mahler", "wagner", "strauss",
    "schubert", "schumann", "liszt", "chopin", "haydn", "handel", "bruckner",
    "britten", "berg", "franck", "stravinsky", "debussy", "ravel", "vivaldi",
    "tchaikovsky", "dvorak", "sibelius", "faure", "bartok", "ligeti",
    "shostakovich", "rachmaninov", "berlioz", "schoenberg", "webern",
    "hindemith", "janacek", "elgar", "copland", "gershwin", "scarlatti",
    "telemann", "purcell", "monteverdi", "prokofiev", "mendelssohn",
    "messiaen", "barber", "ives", "respighi", "saint-saens", "verdi",
    "puccini", "rossini", "donizetti", "bellini", "gluck", "weber",
}

# Ordinary words and very common surnames: too collision-prone to trust
# on their own inside a folder name.
COMMON_WORDS = {
    "young", "white", "black", "green", "brown", "king", "law", "long",
    "field", "stone", "wood", "bell", "gold", "rose", "may", "best",
    "price", "frost", "winter", "church", "cross", "hall", "park", "ward",
    "grant", "hill", "lake", "moore", "cook", "page", "reed", "bishop",
    "marshall", "porter", "mason", "shepherd", "walker", "turner", "carter",
    "parker", "foster", "baker", "fisher", "hunter", "gardner", "day",
    "west", "east", "north", "south", "wells", "york", "kent", "grace",
    "abbey", "chapel", "temple", "angel", "bird", "fox", "wolf", "lamb",
    "sharp", "flat", "major", "minor", "opus", "sound", "voice", "song",
    # surnames that are also ordinary given names -- these collide constantly
    # with jazz and pop artists ('Clark Terry', 'Herbie Hancock')
    "george", "michael", "frank", "prince", "terry", "jones", "coleman",
    "jackson", "hancock", "gilbert", "hopkins", "guest", "lewis", "morgan",
    "harris", "james", "thomas", "martin", "lawrence", "howard", "arthur",
    "philip", "vincent", "warren", "dean", "glenn", "gordon", "ross",
    "curtis", "duncan", "neil", "ray", "leon", "roy", "dennis", "craig",
    "allen", "alan", "keith", "scott", "todd", "wayne", "bruce", "carl",
    "clark", "clarke", "davis", "evans", "roberts", "richards", "edwards",
    "simon", "stewart", "murray", "douglas", "leonard", "russell", "kelly",
    "campbell", "murphy", "collins", "cooper", "watson", "hughes", "morris",
    "rogers", "peterson", "hamilton", "gray", "graham", "franklin",
}


def classify_risk(key, name):
    """'drop' | 'guarded' | None.

    guarded entries require a forename in the text, or a structural position
    next to an ensemble, before the conducting role is asserted.
    """
    if len(key) <= 3:
        return "drop"
    if key in COMPOSER_SURNAMES:
        return "guarded"
    if key in COMMON_WORDS:
        return "guarded"
    if len(key) == 4:
        return "guarded"
    if not re.fullmatch(r"[a-z][a-z'\-]+", key):
        return "drop"
    return None


def apply_risk(entries, protected):
    """Tag or drop risky entries. Seeded names are never dropped."""
    dropped, guarded = [], 0
    for key in list(entries):
        if key in protected:
            # seed names are hand-curated: never dropped, never guarded, and
            # trusted enough to assert without a named ensemble
            entries[key].pop("guarded", None)
            entries[key]["trusted"] = True
            continue
        risk = classify_risk(key, entries[key].get("name", ""))
        if risk == "drop":
            dropped.append(key)
            del entries[key]
        elif risk == "guarded":
            entries[key]["guarded"] = True
            guarded += 1
        else:
            entries[key].pop("guarded", None)
    return dropped, guarded


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--conductors", type=int, default=1200,
                    help="max conductor records to page through")
    ap.add_argument("--ensembles", type=int, default=1000,
                    help="max ensemble records to page through")
    ap.add_argument("--vocab", default=VOCAB_DIR)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.vocab, exist_ok=True)
    cpath = os.path.join(args.vocab, "conductors.json")
    epath = os.path.join(args.vocab, "ensembles.json")

    import credits  # seed values, and the existing structures

    cur_c = load_json(cpath, {})
    cur_e = load_json(epath, {})

    # ---- seed anything not yet on disk, so a fetch never loses hand edits
    entries = dict(cur_c.get("entries") or {})
    if not entries:
        entries = {k: {"name": v[0], "aliases": v[1], "source": "seed"}
                   for k, v in credits.SEED_CONDUCTORS.items()}
    ambiguous = cur_c.get("ambiguous") or {
        k: {"label": v[0], "variants": v[1]}
        for k, v in credits.SEED_AMBIGUOUS.items()}
    needs = cur_c.get("needs_ensemble") or list(credits.SEED_NEEDS_ENSEMBLE)

    abbrev = dict(cur_e.get("abbreviations") or credits.SEED_ABBREV)
    patterns = [list(p) for p in (cur_e.get("patterns")
                                  or credits.SEED_PATTERNS)]

    before_c, before_p = len(entries), len(patterns)

    if not args.dry_run:
        print("fetching conductors from MusicBrainz...")
        for q in ['type:person AND tag:conductor',
                  'type:person AND comment:conductor',
                  'type:person AND comment:conductor AND country:DE',
                  'type:person AND comment:conductor AND country:GB',
                  'type:person AND comment:conductor AND country:US',
                  'type:person AND comment:conductor AND country:RU',
                  'type:person AND comment:conductor AND country:IT',
                  'type:person AND comment:conductor AND country:FR',
                  'type:person AND comment:conductor AND country:AT']:
            got = harvest_people(args.conductors // 3, q)
            for k, v in got.items():
                if k not in entries:
                    entries[k] = v
                elif not entries[k].get("mbid") and v.get("mbid"):
                    entries[k]["mbid"] = v["mbid"]

        print("fetching ensembles from MusicBrainz...")
        seen_names = {p[1] for p in patterns}
        for q in ['type:orchestra', 'type:choir',
                  'type:group AND tag:orchestra',
                  'type:group AND orchestra',
                  'type:group AND philharmonic']:
            got = harvest_groups(args.ensembles // 3, q)
            for k, v in got.items():
                if v["name"] in seen_names:
                    continue
                seen_names.add(v["name"])
                patterns.append([re.escape(_flat(v["name"])), v["name"]])

    dropped, guarded = apply_risk(entries, set(credits.SEED_CONDUCTORS))
    print(f"\nrisk pass: dropped {len(dropped)}, guarded {guarded}")
    if dropped:
        print("  dropped e.g.", ", ".join(sorted(dropped)[:14]))

    # prune any generic single-word ensemble names already stored
    _BARE = {"orchestra", "chorus", "choir", "ensemble", "concert", "quartet",
             "quintet", "consort", "academy", "camerata", "philharmonic",
             "symphony", "sinfonia", "capella"}
    before_pat = len(patterns)
    patterns = [p for p in patterns
                if re.sub(r"[^a-z]", "", _flat(p[1])) not in _BARE]
    if before_pat != len(patterns):
        print(f"pruned {before_pat - len(patterns)} generic ensemble names")

    # keep the most specific patterns first so they win over generic ones
    patterns.sort(key=lambda p: -len(p[0]))

    cout = {"version": 2, "source": "seed + musicbrainz",
            "entries": entries, "ambiguous": ambiguous,
            "needs_ensemble": needs}
    eout = {"version": 2, "source": "seed + musicbrainz",
            "abbreviations": abbrev, "patterns": patterns}

    with open(cpath, "w", encoding="utf-8") as fh:
        json.dump(cout, fh, ensure_ascii=False, indent=1, sort_keys=True)
    with open(epath, "w", encoding="utf-8") as fh:
        json.dump(eout, fh, ensure_ascii=False, indent=1)

    print(f"\nconductors: {before_c} -> {len(entries)}")
    print(f"ensembles : {before_p} patterns -> {len(patterns)} "
          f"(+{len(abbrev)} abbreviations)")
    print(f"wrote {cpath}\n      {epath}")


if __name__ == "__main__":
    main()
