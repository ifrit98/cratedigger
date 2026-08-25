"""Build the Coltrane session manifest from a raw probe.

    python coltrane_build.py --raw output-coltrane/raw_probe.jsonl \\
                             --out output-coltrane --root "D:\\Coltrane"

The organizing unit is the **session** -- a date, a place, a band -- not the
album. Albums are a second spine over the same tracks, because a Coltrane
archive contains far more music than the catalogue: bootlegs, broadcasts and
alternate takes only make sense next to the studio dates they sit between.

Read-only with respect to the archive.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coltrane  # noqa: E402

AUDIO_JUNK = re.compile(r"^\._")


def sid(prefix, s):
    return prefix + "_" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def tget(tags, *names):
    low = {k.lower().strip(): v for k, v in (tags or {}).items()}
    for n in names:
        v = low.get(n)
        if v and str(v).strip():
            return re.sub(r"\s+", " ", str(v)).strip()
    return None


def majority(values):
    vals = [v for v in values if v]
    return Counter(vals).most_common(1)[0][0] if vals else None


def tag_year(tags):
    d = tget(tags, "date", "year", "originaldate")
    if not d:
        return None
    m = re.search(r"(19[3-7]\d)", str(d))
    return m.group(1) if m else None


# --------------------------------------------------------------- resolution

def resolve_date(folder, tags, sessions):
    """(iso, precision, source) for one release folder.

    Precedence matters and is not obvious:

    1. a day/month date in the folder name -- specific to *this* recording,
       which is how the bootleg tier is named
    2. the discography table -- '1957 - Blue Train' says only the year, but
       the session is documented as 15 September 1957
    3. a year-only folder name
    4. the DATE tag, trusted last because on reissues it is the reissue year
    """
    leaf = folder.split("/")[-1]
    compilation = coltrane.is_compilation(folder)

    def ok(iso, prec, src):
        """Reject anything outside Coltrane's recording life."""
        if iso and coltrane.is_plausible_recording_date(iso):
            return iso, prec, src
        return None

    for cand in (coltrane.parse_recording_date(leaf),
                 coltrane.parse_recording_date(folder)):
        iso, prec = cand
        if prec in ("day", "month"):
            got = ok(iso, prec, "folder")
            if got:
                return got

    entry = coltrane.lookup_session(folder, sessions)
    if entry and entry.get("recorded"):
        return entry["recorded"], entry.get("precision", "day"), "discography"

    # A compilation's year is an issue year, not a session date.
    if not compilation:
        for iso, prec in (coltrane.parse_recording_date(leaf),
                          coltrane.parse_recording_date(folder)):
            got = ok(iso, prec, "folder")
            if got:
                return got
        y = tag_year(tags)
        got = ok(y, "year", "tag")
        if got:
            return got
    return None, None, None


def load(raw_path):
    audio = []
    with open(raw_path, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            base = os.path.basename(r["path"])
            if AUDIO_JUNK.match(base):
                continue
            if r.get("kind") != "audio" or r.get("error"):
                continue
            audio.append(r)
    return audio


FORMAT_TIER = [
    ("DSD", {".dsf", ".dff"}),
    ("Lossless", {".flac", ".wav", ".wv", ".ape", ".aif", ".aiff", ".alac"}),
    ("Lossy", {".mp3", ".m4a", ".ogg", ".opus"}),
]


def format_tier(ext, bits, rate):
    for name, exts in FORMAT_TIER:
        if ext in exts:
            if name == "Lossless" and ((bits or 0) > 16 or (rate or 0) > 48000):
                return "Lossless Hi-Res"
            return name
    return "Other"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--root", required=True,
                    help="archive root the probe paths are relative to")
    ap.add_argument("--vocab", default=None)
    args = ap.parse_args()

    sessions_tbl = (coltrane.load_sessions(args.vocab) if args.vocab
                    else coltrane.SESSIONS)

    # Human decisions outrank every inferred source.
    overrides = {}
    ov_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "vocab", "coltrane_date_overrides.json")
    if os.path.exists(ov_path):
        try:
            with open(ov_path, encoding="utf-8") as fh:
                overrides = json.load(fh).get("overrides", {})
        except (OSError, json.JSONDecodeError):
            overrides = {}
    if overrides:
        print(f"date overrides loaded: {len(overrides):,}")
    os.makedirs(args.out, exist_ok=True)

    audio = load(args.raw)
    print(f"tracks: {len(audio):,}")

    by_folder = defaultdict(list)
    for r in audio:
        by_folder[os.path.dirname(r["path"])].append(r)

    releases, tracks = [], []
    for folder, items in sorted(by_folder.items()):
        tag_list = [i.get("tags") or {} for i in items]
        album = majority([tget(t, "album") for t in tag_list])
        album_artist = majority([tget(t, "album_artist", "albumartist")
                                 for t in tag_list])

        iso, prec, src = resolve_date(folder, tag_list[0] if tag_list else {},
                                      sessions_tbl)
        entry = coltrane.lookup_session(folder, sessions_tbl) or {}

        provenance = entry.get("provenance") or \
            coltrane.classify_provenance(folder)
        authority = coltrane.classify_authority(folder)
        role = entry.get("leader") or coltrane.classify_role(folder,
                                                             album_artist)
        if role == "coltrane":
            role = "leader"
        venue, city, country = coltrane.parse_venue(folder)
        venue = venue or entry.get("venue")
        era = coltrane.band_era(iso)

        artist_tag = majority([tget(t, "artist") for t in tag_list])
        personnel, lineup, lineup_id, pers_src = coltrane.personnel_for(
            folder, album_artist, artist_tag, iso)

        tier_top = folder.split("/")[0] if "/" in folder else folder
        rel_id = sid("rel", folder)

        exts = {os.path.splitext(i["path"])[1].lower() for i in items}
        bits = [int(i["bits_per_raw_sample"]) for i in items
                if str(i.get("bits_per_raw_sample") or "").isdigit()]
        rates = [int(i["sample_rate"]) for i in items
                 if str(i.get("sample_rate") or "").isdigit()]
        tier = format_tier(next(iter(exts), ""), max(bits, default=None),
                           max(rates, default=None))

        issue_year = tag_year(tag_list[0] if tag_list else {})
        release = {
            "release_id": rel_id,
            "is_compilation": coltrane.is_compilation(folder),
            "issue_year": issue_year,
            "path": folder,
            "folder_name": folder.split("/")[-1],
            "title": entry.get("title") or album or folder.split("/")[-1],
            "album_tag": album,
            "album_artist": album_artist,
            "recording_date": iso,
            "date_precision": prec,
            "date_source": src,
            "date_confidence": entry.get("confidence") if src == "discography"
                               else ("exact" if prec == "day" else "approx"),
            "era": era,
            "provenance": provenance,
            "authority": authority,
            "role": role,
            "venue": venue,
            "city": city,
            "country": country,
            "label": entry.get("label"),
            "personnel": personnel,
            "personnel_source": pers_src,
            "lineup": lineup,
            "lineup_id": lineup_id,
            "format_tier": tier,
            "archive_tier": tier_top,
            "track_count": len(items),
            "duration_seconds": round(sum(float(i["duration"]) for i in items
                                          if i.get("duration")), 1),
            "size_bytes": sum(i.get("size") or 0 for i in items),
        }
        releases.append(release)

        for i in items:
            t = i.get("tags") or {}
            raw_title = tget(t, "title") or os.path.splitext(
                os.path.basename(i["path"]))[0]
            tune, tune_key = coltrane.normalize_tune(raw_title)
            take = None
            m = re.search(r"take\s*(\d+)|\(alt(?:ernate)?\)", raw_title, re.I)
            if m:
                take = m.group(1) or "alt"
            bd = i.get("bits_per_raw_sample") or i.get("bits_per_sample")
            # a per-track decision beats the release-level date
            t_iso, t_prec, t_src = iso, prec, src
            t_venue, t_personnel = venue, personnel
            ovr = overrides.get(i["path"])
            if ovr and ovr.get("action") == "accept" and ovr.get("date"):
                t_iso = ovr["date"]
                t_prec = ovr.get("precision", "day")
                t_src = "decision"
                t_venue = ovr.get("location") or venue
                if ovr.get("personnel"):
                    t_personnel = ovr["personnel"]
            tracks.append({
                "track_id": sid("trk", i["path"]),
                "release_id": rel_id,
                "path": i["path"],
                "filename": os.path.basename(i["path"]),
                "title": raw_title,
                "tune": tune,
                "tune_key": tune_key,
                "take": take,
                "track_number": tget(t, "track", "tracknumber"),
                "recording_date": t_iso,
                "date_precision": t_prec,
                "date_source": t_src,
                "era": coltrane.band_era(t_iso),
                "provenance": provenance,
                "authority": authority,
                "role": role,
                "venue": t_venue,
                "city": city,
                "country": country,
                "album": release["title"],
                "artist_tag": tget(t, "artist"),
                "personnel": t_personnel,
                "personnel_source": ("decision" if t_src == "decision" and ovr
                                     and ovr.get("personnel") else pers_src),
                "lineup": lineup,
                "lineup_id": lineup_id,
                "duration_seconds": round(float(i["duration"]), 1)
                                    if i.get("duration") else None,
                "format_tier": tier,
                "codec": i.get("codec"),
                "bit_depth": int(bd) if str(bd or "").isdigit() else None,
                "sample_rate": int(i["sample_rate"])
                               if str(i.get("sample_rate") or "").isdigit()
                               else None,
                "size_bytes": i.get("size"),
            })

    # ---- sessions: distinct (date, venue) with day or month precision
    sess = defaultdict(list)
    for t in tracks:
        if t["recording_date"] and t["date_precision"] in ("day", "month"):
            sess[(t["recording_date"], t["venue"] or t["city"] or "")].append(t)
    session_list = []
    for (date, place), ts in sorted(sess.items()):
        session_list.append({
            "session_id": sid("ses", f"{date}|{place}"),
            "date": date,
            "precision": ts[0]["date_precision"],
            "venue": ts[0]["venue"],
            "city": ts[0]["city"],
            "country": ts[0]["country"],
            "era": ts[0]["era"],
            "provenance": ts[0]["provenance"],
            "authority": ts[0]["authority"],
            "lineup": ts[0].get("lineup"),
            "personnel": ts[0].get("personnel") or [],
            "track_count": len(ts),
            "release_ids": sorted({t["release_id"] for t in ts}),
            "tunes": sorted({t["tune"] for t in ts if t["tune"]}),
        })

    # ---- tunes
    tunes = defaultdict(list)
    for t in tracks:
        if t["tune_key"]:
            tunes[t["tune_key"]].append(t)
    tune_list = []
    for key, ts in tunes.items():
        dated = [x for x in ts if x["recording_date"]]
        tune_list.append({
            "tune_key": key,
            "title": Counter(x["tune"] for x in ts).most_common(1)[0][0],
            "performance_count": len(ts),
            "first_recorded": min((x["recording_date"] for x in dated),
                                  default=None),
            "last_recorded": max((x["recording_date"] for x in dated),
                                 default=None),
            "live_count": sum(1 for x in ts if x["provenance"] == "live"),
            "studio_count": sum(1 for x in ts if x["provenance"] == "studio"),
        })
    tune_list.sort(key=lambda x: -x["performance_count"])

    manifest = {
        "schema": "coltrane-session-archive/1.0",
        "generated_from": args.root,
        "entity_tiers": ["tune", "performance(track)", "session", "release"],
        "counts": {
            "tracks": len(tracks), "releases": len(releases),
            "sessions": len(session_list), "tunes": len(tune_list),
        },
        "facets": {
            "provenance": ["studio", "live", "broadcast", "rehearsal",
                           "interview"],
            "authority": ["official", "unofficial"],
            "role": ["leader", "co-leader", "sideman"],
            "date_source": ["folder", "discography", "tag"],
        },
        "sessions": session_list,
        "tunes": tune_list,
        "releases": releases,
        "tracks": tracks,
    }
    with open(os.path.join(args.out, "coltrane.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)

    def dump_csv(name, rows, cols):
        with open(os.path.join(args.out, name), "w", encoding="utf-8-sig",
                  newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: ("; ".join(v) if isinstance(v, list) else v)
                            for k, v in r.items()})

    dump_csv("tracks.csv", sorted(tracks, key=lambda x: (
        x["recording_date"] or "9999", x["path"])),
        ["recording_date", "date_precision", "date_source", "era",
         "provenance", "authority", "role", "venue", "city", "country",
         "tune", "take", "title", "album", "track_number", "lineup",
         "personnel", "personnel_source", "format_tier",
         "duration_seconds", "path"])
    dump_csv("chronology.csv", sorted(
        [r for r in releases if r["recording_date"]],
        key=lambda x: (x["recording_date"], x["path"])),
        ["recording_date", "date_precision", "date_source", "date_confidence",
         "era", "provenance", "authority", "role", "venue", "city", "country",
         "title", "label", "lineup", "personnel", "personnel_source",
         "track_count", "format_tier", "archive_tier", "path"])
    dump_csv("sessions.csv", session_list,
             ["date", "precision", "venue", "city", "country", "era",
              "lineup", "personnel", "provenance", "authority",
              "track_count", "tunes"])
    dump_csv("tunes.csv", tune_list,
             ["title", "performance_count", "first_recorded", "last_recorded",
              "studio_count", "live_count", "tune_key"])

    c = manifest["counts"]
    print(f"releases {c['releases']:,}  sessions {c['sessions']:,}  "
          f"tunes {c['tunes']:,}")
    print("\ndate precision:",
          dict(Counter(r["date_precision"] for r in releases)))
    print("date source   :",
          dict(Counter(r["date_source"] for r in releases)))
    print("provenance    :",
          dict(Counter(r["provenance"] for r in releases)))
    print("authority     :",
          dict(Counter(r["authority"] for r in releases)))
    print("role          :", dict(Counter(r["role"] for r in releases)))
    print("personnel src :",
          dict(Counter(r["personnel_source"] for r in releases)))
    print("lineups       :",
          dict(Counter(r["lineup"] for r in releases if r["lineup"])))
    print(f"\nwrote -> {args.out}")


if __name__ == "__main__":
    main()
