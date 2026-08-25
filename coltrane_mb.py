"""Reconcile the Coltrane discography against MusicBrainz.

    python coltrane_mb.py --manifest output-coltrane/coltrane.json      # fetch
    python coltrane_mb.py --report                                      # compare

Fetches session-level data -- recording date, studio, and per-musician
credits -- from MusicBrainz relationships, which is where jazz session data
actually lives (`first-release-date` is the release, not the session).

**Every match is validated against the tracklist before it is believed.**
Searching MusicBrainz for "Blue Train" returns a release whose tracks are
'On It' and 'Weeja', recorded 1956-05-07 -- the Elmo Hope date, not Blue
Train. Title search alone is not evidence. A candidate release is accepted
only when enough of its track titles match the tunes we actually hold.

Nothing is overwritten. Findings land in a separate file with an MBID
citation, and disagreements are written to a conflict report for review.
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
VOCAB = os.path.join(HERE, "vocab")
CACHE = os.path.join(VOCAB, "coltrane_mb_cache.json")
FINDINGS = os.path.join(VOCAB, "coltrane_mb_sessions.json")
COLTRANE_MBID = "b625448e-bf4a-41c3-a421-72ad46cdb831"

UA = "MusicLibraryOntology/1.0 (personal library cataloging)"
BASE = "https://musicbrainz.org/ws/2/"
RATE = 1.1
_last = [0.0]

# A candidate release must overlap OUR tracklist in BOTH directions.
#
# Checking one direction is not enough. MusicBrainz has a 70-track box set
# titled "Blue Train"; it contains the album's 5 tunes among 65 others from
# a dozen different sessions. Five matching titles clears any absolute
# threshold, but 5-of-70 means it is an anthology, not the album, and its
# dominant session date belongs to something else entirely.
MIN_OVERLAP_TRACKS = 3
MIN_COVERAGE_OURS = 0.50    # how much of our album MB accounts for
MIN_COVERAGE_MB = 0.40      # how much of MB's release is our album


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"\b(take|alt|alternate|version|mono|stereo|remaster(ed)?)\b",
               " ", s)
    s = re.sub(r"\b(the|a|an)\b", " ", s)
    s = re.sub(r"favourite", "favorite", s)
    return re.sub(r"[^a-z0-9]", "", s)


def get(endpoint, params, retries=3):
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
            return None
        except Exception:  # noqa: BLE001
            time.sleep(1.5 * (attempt + 1))
    return None


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def extract_sessions(release_json, our_tunes):
    """Pull per-recording session facts, after validating the tracklist.

    Returns (accepted, info). `info` always explains the decision so a
    rejection is auditable rather than silent.
    """
    media = release_json.get("media") or []
    tracks = [t for md in media for t in (md.get("tracks") or [])]
    if not tracks:
        return False, {"reason": "no tracks in MB release"}

    mb_titles = {norm(t.get("title") or
                      t.get("recording", {}).get("title")) for t in tracks}
    mb_titles.discard("")
    overlap = mb_titles & our_tunes
    cov_ours = len(overlap) / max(1, len(our_tunes))
    cov_mb = len(overlap) / max(1, len(mb_titles))
    if len(overlap) < MIN_OVERLAP_TRACKS or cov_ours < MIN_COVERAGE_OURS:
        return False, {
            "reason": "tracklist mismatch",
            "overlap": len(overlap),
            "mb_tracks": len(mb_titles),
            "our_tunes": len(our_tunes),
            "coverage_ours": round(cov_ours, 2),
            "coverage_mb": round(cov_mb, 2),
            "sample_mb": sorted(mb_titles)[:4]}

    # Session facts come from the OVERLAPPING tracks only. MusicBrainz dates
    # each recording individually, so a 70-track anthology still reports the
    # correct date for the five tunes we actually hold -- as long as the
    # other sixty-five are not allowed to vote.
    per_track, dates, places, people = [], collections.Counter(), \
        collections.Counter(), collections.Counter()
    for t in tracks:
        rec = t.get("recording") or {}
        if norm(rec.get("title") or t.get("title")) not in our_tunes:
            continue
        rels = rec.get("relations") or []
        d = sorted({r.get("begin") for r in rels
                    if r.get("begin") and re.match(r"^\d{4}-\d{2}-\d{2}$",
                                                   str(r.get("begin")))})
        pl = [r.get("place", {}).get("name") for r in rels
              if r.get("type") == "recorded at" and r.get("place")]
        mus = [(r.get("artist", {}).get("name"),
                ", ".join(r.get("attributes") or []))
               for r in rels if r.get("type") == "instrument" and r.get("artist")]
        if d:
            dates[d[0]] += 1
        for p in pl:
            places[p] += 1
        for nm, _i in mus:
            people[nm] += 1
        per_track.append({
            "title": rec.get("title") or t.get("title"),
            "key": norm(rec.get("title") or t.get("title")),
            "date": d[0] if d else None,
            "place": pl[0] if pl else None,
            "musicians": [{"name": n, "instrument": i} for n, i in mus],
        })
    return True, {
        "overlap": len(overlap), "mb_tracks": len(mb_titles),
        "coverage_ours": round(cov_ours, 2),
        "coverage_mb": round(cov_mb, 2),
        "is_anthology": cov_mb < MIN_COVERAGE_MB,
        "tracks": per_track,
        "dates": dict(dates.most_common()),
        "place": places.most_common(1)[0][0] if places else None,
        "personnel": [n for n, _ in people.most_common()],
    }


def fetch(manifest_path, limit, only=None):
    man = load_json(manifest_path, {})
    if not man:
        sys.exit(f"cannot read {manifest_path}")

    # group our tracks by album title so each album is searched once
    albums = collections.defaultdict(set)
    for t in man["tracks"]:
        a = t.get("album")
        if a and t.get("tune"):
            albums[a].add(norm(t["tune"]))
    cache = load_json(CACHE, {})
    todo = [a for a in albums if a not in cache]
    if only:
        todo = [a for a in todo if only.lower() in a.lower()]
    todo = todo[:limit]
    print(f"{len(albums)} distinct albums; {len(cache)} cached; "
          f"fetching {len(todo)}")

    for i, album in enumerate(todo, 1):
        our = albums[album]
        clean = re.sub(r'["\\]', " ", album)[:80]
        q = f'arid:{COLTRANE_MBID} AND release:"{clean}"'
        res = get("release", {"query": q, "limit": 6})
        entry = {"album": album, "fetched": time.strftime("%Y-%m-%d"),
                 "our_tunes": len(our)}
        best = None
        best_score = -1.0
        if res and res.get("releases"):
            # Evaluate every candidate and keep the best fit, rather than
            # trusting search rank. MusicBrainz ranks a 70-track box set
            # above the actual album for several of these titles.
            for cand in res["releases"][:6]:
                full = get(f"release/{cand['id']}",
                           {"inc": "recordings+recording-level-rels+"
                                   "artist-rels+place-rels"})
                if not full:
                    continue
                ok, info = extract_sessions(full, our)
                info["mbid"] = cand["id"]
                info["mb_title"] = cand.get("title")
                if ok:
                    dated = sum(1 for t in info["tracks"] if t["date"])
                    score = (info["coverage_ours"]
                             + dated / max(1, len(info["tracks"]))
                             + (0.5 if not info["is_anthology"] else 0))
                    if score > best_score:
                        best, best_score = info, score
                else:
                    entry.setdefault("rejected", []).append(
                        {k: info[k] for k in
                         ("mbid", "mb_title", "reason", "overlap",
                          "coverage_ours", "coverage_mb")
                         if k in info})
        if best:
            entry["accepted"] = best
        cache[album] = entry
        status = "ok " if best else "-- "
        print(f"  [{i}/{len(todo)}] {status}{album[:56]}"
              + (f"  dates={list(best['dates'])[:2]}" if best else ""))
        if i % 10 == 0:
            with open(CACHE, "w", encoding="utf-8") as fh:
                json.dump(cache, fh, ensure_ascii=False, indent=1)

    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1)
    acc = sum(1 for v in cache.values() if v.get("accepted"))
    print(f"\ncached {len(cache)} albums, {acc} with validated session data")
    print(f"-> {CACHE}")


def report(manifest_path):
    cache = load_json(CACHE, {})
    if not cache:
        sys.exit("no cache yet -- run without --report first")
    ours = {e["title"]: e for e in
            load_json(os.path.join(VOCAB, "coltrane_sessions.json"),
                      {"sessions": []})["sessions"]}
    man = load_json(manifest_path, {})
    rel_date = {}
    for r in man.get("releases", []):
        if r.get("title") and r.get("recording_date"):
            rel_date.setdefault(r["title"], r["recording_date"])

    rows, agree, differ, newly = [], 0, 0, 0
    sessions_out = []
    for album, e in sorted(cache.items()):
        a = e.get("accepted")
        if not a:
            continue
        mb_date = next(iter(a["dates"]), None)
        if not mb_date:
            continue
        mine = rel_date.get(album)
        state = ("no local date" if not mine else
                 "agree" if mine[:10] == mb_date[:10] else "DIFFER")
        if state == "agree":
            agree += 1
        elif state == "DIFFER":
            differ += 1
        else:
            newly += 1
        rows.append({
            "album": album, "state": state, "ours": mine or "",
            "musicbrainz": mb_date,
            "mb_distinct_dates": len(a["dates"]),
            "place": a.get("place") or "",
            "personnel": "; ".join(a.get("personnel", [])[:8]),
            "overlap_tracks": a.get("overlap"),
            "mbid": a.get("mbid"),
        })
        sessions_out.append({
            "album": album, "mbid": a.get("mbid"),
            "source": "musicbrainz", "fetched": e.get("fetched"),
            "dates": a["dates"], "place": a.get("place"),
            "personnel": a.get("personnel"),
            "tracks": [{"key": t["key"], "title": t["title"],
                        "date": t["date"], "place": t["place"],
                        "musicians": t["musicians"]}
                       for t in a["tracks"]],
        })

    with open(FINDINGS, "w", encoding="utf-8") as fh:
        json.dump({"_comment": "Validated MusicBrainz session data. Each entry "
                               "cites an MBID and fetch date. Advisory: "
                               "coltrane_build.py reads this only where it "
                               "raises precision, and never silently "
                               "overrides a hand-curated entry.",
                   "sessions": sessions_out}, fh, ensure_ascii=False, indent=1)

    out = os.path.join(HERE, "output-coltrane", "mb_conflicts.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else
                           ["album"], extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["state"] != "DIFFER",
                                             x["album"])):
            w.writerow(r)

    rejected = sum(1 for v in cache.values()
                   if not v.get("accepted") and v.get("rejected"))
    print(f"albums with validated MB data : {len(rows)}")
    print(f"  agree with our date         : {agree}")
    print(f"  DIFFER                      : {differ}")
    print(f"  we had no date              : {newly}")
    print(f"albums where every MB candidate failed validation: {rejected}")
    multi = sum(1 for s in sessions_out if len(s["dates"]) > 1)
    print(f"albums MB shows spanning >1 session: {multi}")
    print(f"\n-> {FINDINGS}\n-> {out}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default="output-coltrane/coltrane.json")
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--only", default=None, help="substring filter, for testing")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    os.makedirs(VOCAB, exist_ok=True)
    if args.report:
        report(args.manifest)
    else:
        fetch(args.manifest, args.limit, args.only)


if __name__ == "__main__":
    main()
