"""Reconcile a mixed library against MusicBrainz.

    python general_mb.py --manifest output/library.json        # fetch
    python general_mb.py --report                              # compare

Populates release date, label, catalogue number, and -- the point of this --
**work identity**. The same piece titled three ways in three folders becomes
three works, because most repertoire has no universally-used catalogue
number. A MusicBrainz work id is the stable key that catalogue numbers
cannot supply.

Matching is validated on **durations**, not titles. In a classical library
only 28% of releases carry an album artist and titles vary wildly
("I. Allegro" against "Symphony No. 7 in E major: I. Allegro moderato"), but
every track has a duration from the probe. A sequence of track lengths is
close to unique for a release, which makes it the honest signal.

Nothing is applied. Findings carry an MBID citation; disagreements go to a
conflict report.
"""
import argparse
import collections
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
# Installed, the package lives in site-packages, which is a poor
# place to hand-edit curated vocabulary. CRATEDIGGER_VOCAB points
# somewhere writable without touching the install.
VOCAB = (os.environ.get("CRATEDIGGER_VOCAB")
         or os.path.join(HERE, "vocab"))
CACHE = os.path.join(VOCAB, "general_mb_cache.json")
FINDINGS = os.path.join(VOCAB, "general_mb_works.json")

UA = "cratedigger/1.0 (personal library cataloging)"
BASE = "https://musicbrainz.org/ws/2/"
RATE = 1.1
_last = [0.0]

# A track matches when its length is within this many seconds. Rips vary by
# a second or two from the catalogue; five is loose enough to survive that
# and tight enough that a different performance will not pass.
DURATION_TOLERANCE = 5
MIN_DURATION_MATCH = 0.70     # fraction of our tracks that must line up
MIN_TRACKS = 2


def flat(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def get(endpoint, params, retries=4):
    """(payload, transient) -- transient is True when the server never
    answered. A throttled request looks exactly like an empty result unless
    they are kept apart, and caching a throttle as "no match" poisons the
    cache permanently. On a first measurement this alone accounted for six
    of seven apparent misses.
    """
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
                return json.loads(fh.read().decode("utf-8")), False
        except urllib.error.HTTPError as e:
            if e.code in (503, 429):
                time.sleep(2 ** attempt)      # 1, 2, 4, 8
                continue
            if e.code == 404:
                return None, False            # a real, cacheable absence
            return None, True
        except Exception:  # noqa: BLE001
            time.sleep(2 ** attempt)
    return None, True


# Folder-derived titles carry things MusicBrainz never has: a disc marker, an
# artist prefix, an edition note. "BACH - Brandenburg Concerti CD1" finds
# nothing; "Brandenburg Concerti" scores 100.
#
# No \b after the keyword: "CD1" has no boundary between the letters and the
# digit, and that spelling is common in folder names.
_DISC = re.compile(r"[\s(\[_.,-]*\b(?:cd|disc|disk|vol(?:ume)?|part|pt)"
                   r"\s*\.?\s*(?:\d+|[ivx]{1,5})\s*[)\]]?\s*$", re.I)
_BRACKET = re.compile(r"[\[(][^\])]*[\])]")
_NOISE = re.compile(r"\b(?:remaster(?:ed)?|reissue|deluxe|expanded|edition|"
                    r"hdtracks|24[\s-]?bit|\d{2,3}\s?khz|flac|dsd|sacd)\b", re.I)


def unquote(s):
    """Strip the two characters Lucene treats as syntax."""
    return (s or "").replace('"', " ").replace('\\', " ")


def clean_title(title):
    """Search keys for one release title, best first."""
    t = (title or "").strip()
    if not t:
        return []
    out = []
    for _ in range(3):                       # "... Part One - Part 1(Disc 1)"
        nt = _DISC.sub("", t).strip(" -_.")
        if nt == t:
            break
        t = nt
    t = _NOISE.sub(" ", _BRACKET.sub(" ", t))
    t = re.sub(r"\s{2,}", " ", t).strip(" -_.,;:")
    if t:
        out.append(t)
    # drop a leading "Composer - " / "Performer: " prefix
    m = re.match(r"^[^-:]{2,40}?\s*[-:]\s*(.{6,})$", t)
    if m and m.group(1).strip() not in out:
        out.append(m.group(1).strip())
    return out


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def duration_match(ours, theirs):
    """Greedy pairing of two duration lists. Returns (matched, ratio).

    Greedy is adequate here: durations within a release are far enough apart
    that an optimal assignment would rarely differ, and a wrong pairing costs
    only a slightly lower score.
    """
    pool = list(theirs)
    matched = 0
    for d in ours:
        best, best_diff = None, None
        for i, t in enumerate(pool):
            diff = abs(d - t)
            if best_diff is None or diff < best_diff:
                best, best_diff = i, diff
        if best is not None and best_diff <= DURATION_TOLERANCE:
            pool.pop(best)
            matched += 1
    return matched, matched / max(1, len(ours))


def plausible(cand, n_ours):
    """Can this search hit possibly match, judging only by the search result?

    Search results carry a track count. Fetching full detail costs a second
    per candidate, and most candidates are eliminable without it: a 67-track
    anthology cannot be our 4-track release. Skipping those took the budget
    from ~36 calls per release to under 10.

    The window is generous in one direction only. A release of ours may be
    one disc of a set MusicBrainz models as a whole, so their count may
    legitimately exceed ours -- but never by more than a few discs' worth,
    and it can never be far below.
    """
    n = cand.get("track-count")
    if not n:
        media = cand.get("media") or []
        n = sum(m.get("track-count") or 0 for m in media) or None
    if not n:
        return True                       # unknown: let evaluate() decide
    if n < n_ours * MIN_DURATION_MATCH:   # too few to ever reach the floor
        return False
    return n <= max(n_ours * 4, n_ours + 30)


def evaluate(release_json, our_durations):
    """(accepted, info). info always explains the decision."""
    media = release_json.get("media") or []
    tracks = [t for md in media for t in (md.get("tracks") or [])]
    if not tracks:
        return False, {"reason": "no tracks"}

    theirs = []
    for t in tracks:
        ms = t.get("length") or (t.get("recording") or {}).get("length")
        if ms:
            theirs.append(round(ms / 1000))
    if not theirs:
        return False, {"reason": "no durations in MusicBrainz"}

    matched, ratio = duration_match(our_durations, theirs)
    info = {"matched": matched, "our_tracks": len(our_durations),
            "mb_tracks": len(theirs), "ratio": round(ratio, 2)}
    if ratio < MIN_DURATION_MATCH:
        info["reason"] = "durations do not line up"
        return False, info

    works, per_track = {}, []
    for t in tracks:
        rec = t.get("recording") or {}
        wl = [r["work"] for r in (rec.get("relations") or []) if r.get("work")]
        ms = t.get("length") or rec.get("length")
        per_track.append({
            "title": t.get("title") or rec.get("title"),
            "seconds": round(ms / 1000) if ms else None,
            "work_id": wl[0]["id"] if wl else None,
            "work_title": wl[0].get("title") if wl else None,
        })
        for w in wl:
            works[w["id"]] = w.get("title")

    labels, catnos = [], []
    for li in release_json.get("label-info") or []:
        if li.get("label") and li["label"].get("name"):
            labels.append(li["label"]["name"])
        if li.get("catalog-number"):
            catnos.append(li["catalog-number"])

    info.update({
        "date": release_json.get("date"),
        "barcode": release_json.get("barcode"),
        "label": labels[0] if labels else None,
        "catalog_number": catnos[0] if catnos else None,
        "works": works,
        "tracks": per_track,
    })
    return True, info


def fetch(manifest_path, limit, only):
    man = load_json(manifest_path, {})
    if not man:
        sys.exit("cannot read %s" % manifest_path)

    cache = load_json(CACHE, {})
    releases = [r for r in man["releases"]
                if not r.get("is_container_release")
                and r.get("track_count", 0) >= MIN_TRACKS]
    todo = [r for r in releases if r["path"] not in cache]
    if only:
        todo = [r for r in todo if only.lower() in r["path"].lower()]
    todo = todo[:limit]
    print("%d releases, %d cached, fetching %d"
          % (len(releases), len(cache), len(todo)))
    skipped = 0

    for i, r in enumerate(todo, 1):
        ours = sorted(round(t["duration_seconds"]) for t in r["tracks"]
                      if t.get("duration_seconds"))
        entry = {"path": r["path"], "title": r.get("title"),
                 "fetched": time.strftime("%Y-%m-%d"),
                 "our_tracks": len(ours)}
        if not ours:
            entry["reason"] = "no durations locally"
            cache[r["path"]] = entry
            continue

        keys = clean_title(r.get("title")) or [r.get("title") or ""]
        artist = unquote(r.get("album_artist"))[:50]

        # Query strategies, most selective first. A track count is a far
        # stronger filter than a title score: "Brandenburg Concerti" returns
        # eight plausible releases, and the same query with tracks:19 returns
        # one.
        #
        # The last strategy drops the quotes. Folder names are often a
        # description of contents rather than a release title -- a performer
        # prefix, several works joined by ";" or "&", a date, a label. An
        # exact phrase can never match those, but bare terms can: the quoted
        # form of "The Miraculous Mandarin; Music for Strings, Percussion and
        # Celesta" returns nothing, and the bare form returns the right
        # release at score 100, titled with slashes instead. Bare terms drag
        # in junk too, which is affordable because durations are the gate.
        def variants(key):
            v = []
            if len(ours) >= MIN_TRACKS:
                v.append(('release:"%s" AND tracks:%d' % (key, len(ours)),
                          False))
            if artist:
                v.append(('release:"%s" AND artist:"%s"' % (key, artist),
                          False))
            v.append(('release:"%s"' % key, False))
            bare = re.sub(r"[^\w\s]+", " ", key)
            bare = re.sub(r"\s{2,}", " ", bare).strip()
            if bare and bare.lower() != key.lower():
                v.append((bare, True))
            elif bare:
                v.append((bare, True))
            return v

        best, best_ratio, transient = None, 0.0, False
        seen = set()
        for key in keys:
            key = unquote(key)[:70]
            for query, is_fallback in variants(key):
                # Only spend the loose query when the precise ones found
                # nothing at all to look at.
                if is_fallback and seen:
                    continue
                res, tr = get("release", {"query": query, "limit": 5})
                transient = transient or tr
                for cand in ((res or {}).get("releases") or [])[:5]:
                    if cand["id"] in seen:
                        continue
                    seen.add(cand["id"])
                    if not plausible(cand, len(ours)):
                        entry.setdefault("rejected", []).append(
                            {"mbid": cand["id"], "mb_title": cand.get("title"),
                             "reason": "track count cannot match",
                             "mb_tracks": cand.get("track-count")})
                        continue
                    full, tr = get("release/%s" % cand["id"],
                                   {"inc": "recordings+work-rels+"
                                           "recording-level-rels+labels"})
                    transient = transient or tr
                    if not full:
                        continue
                    ok, info = evaluate(full, ours)
                    info["mbid"] = cand["id"]
                    info["mb_title"] = cand.get("title")
                    info["query"] = query
                    if ok and info["ratio"] > best_ratio:
                        best, best_ratio = info, info["ratio"]
                    elif not ok:
                        entry.setdefault("rejected", []).append(
                            {k: info.get(k) for k in
                             ("mbid", "mb_title", "reason", "ratio",
                              "mb_tracks")})
                if best_ratio >= 0.90:
                    break
            if best_ratio >= 0.90:        # good enough; stop spending calls
                break

        if best is None and transient:
            # Leave it out of the cache entirely so the next run retries it.
            print("  [%d/%d] .. %s  (server unavailable, will retry)"
                  % (i, len(todo), (r.get("title") or r["path"])[:56]))
            skipped += 1
            continue

        if best:
            entry["accepted"] = best
        cache[r["path"]] = entry
        print("  [%d/%d] %s%s"
              % (i, len(todo), "ok " if best else "-- ",
                 (r.get("title") or r["path"])[:56])
              + ("  %d/%d durations, %d works"
                 % (best["matched"], best["our_tracks"], len(best["works"]))
                 if best else ""))
        if i % 10 == 0:
            with open(CACHE, "w", encoding="utf-8") as fh:
                json.dump(cache, fh, ensure_ascii=False, indent=1)

    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1)
    acc = sum(1 for v in cache.values() if v.get("accepted"))
    print("\ncached %d releases, %d matched -> %s" % (len(cache), acc, CACHE))


def report(manifest_path):
    cache = load_json(CACHE, {})
    if not cache:
        sys.exit("no cache yet -- run without --report first")
    man = load_json(manifest_path, {})
    by_path = {r["path"]: r for r in man.get("releases", [])}

    rows, works_out = [], {}
    agree = differ = newly = 0
    for path, e in sorted(cache.items()):
        a = e.get("accepted")
        if not a:
            continue
        r = by_path.get(path, {})
        ours_year = str(r.get("recording_year") or r.get("release_year") or "")
        mb_year = (a.get("date") or "")[:4]
        # A MusicBrainz release date is THAT PRESSING's date, not the date of
        # the recording. A 1962 performance on a 2001 remaster is not a
        # disagreement, and labelling it one invites someone to overwrite a
        # correct recording year with a reissue year. The same trap as
        # first-release-date in the artist reconciler.
        if not ours_year or not mb_year:
            state = "unknown"
        elif ours_year == mb_year:
            state = "same year"
        elif mb_year > ours_year:
            state = "mb pressing later"      # expected for a reissue
        else:
            state = "REVIEW mb earlier"      # ours may be a reissue date
        if state == "same year":
            agree += 1
        elif state == "REVIEW mb earlier":
            differ += 1
        else:
            newly += 1
        rows.append({
            "state": state, "our_year": ours_year,
            "mb_pressing_year": mb_year,
            "our_label": r.get("label") or "", "mb_label": a.get("label") or "",
            "mb_catalog": a.get("catalog_number") or "",
            "durations": "%d/%d" % (a["matched"], a["our_tracks"]),
            "works": len(a.get("works") or {}),
            "release": (r.get("title") or "")[:60],
            "mbid": a.get("mbid"), "path": path,
        })
        for wid, wt in (a.get("works") or {}).items():
            works_out.setdefault(wid, {"work_id": wid, "title": wt,
                                       "releases": []})
            works_out[wid]["releases"].append(path)

    with open(FINDINGS, "w", encoding="utf-8") as fh:
        json.dump({"_comment": "MusicBrainz work identity for a mixed "
                               "library. A work id is stable where a "
                               "catalogue number does not exist. Advisory: "
                               "nothing is applied automatically.",
                   "_source": "musicbrainz", "works": list(works_out.values())},
                  fh, ensure_ascii=False, indent=1)

    out = os.path.join(os.path.dirname(os.path.abspath(manifest_path)),
                       "mb_conflicts.csv")
    if rows:
        with open(out, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            order = {"REVIEW mb earlier": 0, "same year": 1,
                     "mb pressing later": 2, "unknown": 3}
            for row in sorted(rows, key=lambda x: (order.get(x["state"], 9),
                                                   x["release"])):
                w.writerow(row)

    shared = sum(1 for w in works_out.values() if len(set(w["releases"])) > 1)
    rejected = sum(1 for v in cache.values() if not v.get("accepted"))
    print("releases matched        : %d" % len(rows))
    print("  same year             : %d" % agree)
    later = sum(1 for x in rows if x["state"] == "mb pressing later")
    unknown = sum(1 for x in rows if x["state"] == "unknown")
    print("  mb pressing is later  : %d   (a reissue -- expected, not a"
          " conflict)" % later)
    print("  REVIEW, mb earlier    : %d   (our year may be a reissue date)"
          % differ)
    print("  one side has no year  : %d" % unknown)
    print("releases unmatched      : %d" % rejected)
    print("distinct works          : %d" % len(works_out))
    print("  works appearing in >1 release: %d   <- the fragmentation fix"
          % shared)
    print("\n-> %s\n-> %s" % (FINDINGS, out))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default="output/library.json")
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--only", default=None)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    os.makedirs(VOCAB, exist_ok=True)
    report(args.manifest) if args.report else fetch(args.manifest, args.limit,
                                                    args.only)


if __name__ == "__main__":
    main()
