"""Generate the Coltrane view splines as .m3u8 playlists.

    python coltrane_views.py --manifest output-coltrane/coltrane.json \\
                             --out output-coltrane/views --root "D:\\Coltrane"

Splines
-------
by-date        the chronological spine. One playlist per session date, plus
               per-year rollups and a single all-archive chronology. Studio,
               live, broadcast and bootleg interleave in true date order,
               which is the view a folder tree cannot give you.
by-release     the album spine: one playlist per release folder.
by-era         Coltrane's working bands, in sequence.
by-tune        every performance of a tune, oldest first.
by-provenance  studio / live / broadcast / rehearsal.
by-authority   official issue vs collector's tape.
by-venue       Village Vanguard, Birdland, Half Note, Antibes ...
by-role        leader / co-leader / sideman.

Paths are absolute when the archive and the output are on different drives,
which is the normal case for a read-only archive.
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coltrane  # noqa: E402

MAX_NAME = 90


def safe(name):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name))
    s = re.sub(r"\s{2,}", " ", s).strip(" .")
    return s[:MAX_NAME] or "untitled"


def write(path, tracks, title, root, absolute):
    if not tracks:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    base = os.path.dirname(path)
    with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("#EXTM3U\n")
        fh.write(f"#PLAYLIST:{title}\n")
        for t in tracks:
            dur = int(t["duration_seconds"]) if t.get("duration_seconds") else -1
            date = t.get("recording_date") or "undated"
            label = f"{date} - {t.get('tune') or t.get('title')}"
            if t.get("take"):
                label += f" (take {t['take']})"
            if t.get("provenance") and t["provenance"] != "studio":
                label += f" [{t['provenance']}]"
            label = re.sub(r"\s+", " ", label).strip()
            fh.write(f"#EXTINF:{dur},{label}\n")
            full = os.path.join(root, t["path"].replace("/", os.sep))
            if absolute:
                fh.write(os.path.abspath(full) + "\n")
            else:
                try:
                    fh.write(os.path.relpath(full, base).replace(os.sep, "/")
                             + "\n")
                except ValueError:
                    fh.write(os.path.abspath(full) + "\n")
    return True


def chrono_key(t):
    """Date first, then release, then track order. Undated sorts last."""
    d = t.get("recording_date") or "9999"
    m = re.match(r"\d+", str(t.get("track_number") or "0"))
    n = int(m.group()) if m else 0
    return (d, t.get("album") or "", n, t.get("path") or "")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--min-tracks", type=int, default=1)
    ap.add_argument("--min-tune-versions", type=int, default=3)
    ap.add_argument("--min-personnel-tracks", type=int, default=5,
                    help="skip musicians with fewer tracks than this")
    ap.add_argument("--relative", action="store_true")
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as fh:
        m = json.load(fh)
    root = os.path.abspath(args.root)
    out = os.path.abspath(args.out)
    tracks = m["tracks"]
    rel_by_id = {r["release_id"]: r for r in m["releases"]}

    absolute = not args.relative
    if args.relative:
        try:
            os.path.relpath(root, out)
        except ValueError:
            absolute = True
            print("note: archive and output are on different drives; "
                  "using absolute paths")

    made = 0
    used = set()

    def emit(facet, name, ts, title=None, sort=chrono_key, distinguish=None):
        """Write one playlist, never silently overwriting another.

        Release names collide constantly in an archive like this -- a dozen
        folders called 'CD1', and the same album present in the 16, 24 and
        DSD tiers. Without disambiguation those playlists overwrite each
        other and most of the archive vanishes from the view.
        """
        nonlocal made
        if len(ts) < args.min_tracks:
            return
        stem = safe(name)
        key = (facet, stem.lower())
        if key in used and distinguish:
            stem = safe(f"{name} ({distinguish})")
            key = (facet, stem.lower())
        n = 2
        while key in used:
            stem = safe(f"{name} #{n}")
            key = (facet, stem.lower())
            n += 1
        used.add(key)
        if write(os.path.join(out, facet, stem + ".m3u8"),
                 sorted(ts, key=sort), title or name, root, absolute):
            made += 1

    # ---------------------------------------------------- by-date
    # One playlist per session date, named so they sort chronologically in
    # any file browser, with the character of the date in the filename.
    by_date = defaultdict(list)
    for t in tracks:
        if t.get("recording_date"):
            by_date[t["recording_date"]].append(t)

    for date, ts in sorted(by_date.items()):
        place = ts[0].get("venue") or ts[0].get("city") or ""
        prov = ts[0].get("provenance") or ""
        auth = ts[0].get("authority") or ""
        tag = "" if prov == "studio" else prov
        if auth == "unofficial":
            tag = (tag + " unofficial").strip()
        name = date + (f" - {place}" if place else "")
        name += f" [{tag}]" if tag else ""
        emit("by-date", name, ts, f"{date} {place}".strip())

    by_year = defaultdict(list)
    for t in tracks:
        if t.get("recording_date"):
            by_year[t["recording_date"][:4]].append(t)
    for year, ts in sorted(by_year.items()):
        emit("by-date/_years", year, ts, f"Coltrane {year}")

    dated = [t for t in tracks if t.get("recording_date")]
    emit("by-date", "_ALL - complete chronology", dated,
         "John Coltrane - complete chronology")
    emit("by-date", "_UNDATED",
         [t for t in tracks if not t.get("recording_date")],
         "Undated / compilations")

    # ---------------------------------------------------- by-release
    by_rel = defaultdict(list)
    for t in tracks:
        by_rel[t["release_id"]].append(t)
    for rid, ts in by_rel.items():
        r = rel_by_id.get(rid, {})
        year = str(r.get("recording_date") or r.get("issue_year") or "")[:4]
        base = r.get("title") or r.get("folder_name") or "untitled"
        name = f"{year} - {base}" if year else base
        # tier tells apart the same album held at 16-bit, 24-bit and DSD
        emit("by-release", name, ts, name,
             distinguish=r.get("archive_tier") or r.get("format_tier"))

    # ---------------------------------------------------- by-era
    era_order = {label: i for i, (_d, label) in enumerate(coltrane.ERAS)}
    by_era = defaultdict(list)
    for t in tracks:
        if t.get("era"):
            by_era[t["era"]].append(t)
    for era, ts in by_era.items():
        emit("by-era", f"{era_order.get(era, 99):02d} - {era}", ts, era)

    # ---------------------------------------------------- by-tune
    by_tune = defaultdict(list)
    for t in tracks:
        if t.get("tune_key"):
            by_tune[t["tune_key"]].append(t)
    tune_title = {x["tune_key"]: x["title"] for x in m["tunes"]}
    n_tunes = 0
    for key, ts in by_tune.items():
        if len(ts) < args.min_tune_versions:
            continue
        n_tunes += 1
        emit("by-tune", f"{len(ts):03d} - {tune_title.get(key, key)}", ts,
             tune_title.get(key, key))

    # ---------------------------------------------------- by-personnel
    # One playlist per musician: every date Coltrane and they were in a room
    # together, in chronological order.
    by_person = defaultdict(list)
    for t in tracks:
        for name in (t.get("personnel") or []):
            by_person[name].append(t)
    n_people = 0
    for name, ts in by_person.items():
        if len(ts) < args.min_personnel_tracks:
            continue
        n_people += 1
        instr = coltrane.instrument_of(name)
        label = f"{name} ({instr})" if instr else name
        emit("by-personnel", f"{len(ts):04d} - {label}", ts, label)

    # ---------------------------------------------------- by-lineup
    lineup_order = {lu["id"]: i for i, lu in enumerate(coltrane.LINEUPS)}
    by_lineup = defaultdict(list)
    for t in tracks:
        if t.get("lineup_id"):
            by_lineup[(t["lineup_id"], t["lineup"])].append(t)
    for (lid, lname), ts in by_lineup.items():
        emit("by-lineup", f"{lineup_order.get(lid, 99):02d} - {lname}", ts,
             lname)

    # ---------------------------------------------------- simple facets
    for facet, field in (("by-provenance", "provenance"),
                         ("by-authority", "authority"),
                         ("by-role", "role"),
                         ("by-venue", "venue"),
                         ("by-format", "format_tier")):
        groups = defaultdict(list)
        for t in tracks:
            v = t.get(field)
            if v:
                groups[v].append(t)
        for name, ts in groups.items():
            emit(facet, name, ts, f"{field}: {name}")

    print(f"playlists written: {made}")
    print(f"  session dates       : {len(by_date)}")
    print(f"  years               : {len(by_year)}")
    print(f"  releases            : {len(by_rel)}")
    print(f"  tunes ({args.min_tune_versions}+ versions) : {n_tunes}")
    print(f"  musicians           : {n_people}")
    print(f"  lineups             : {len(by_lineup)}")
    print(f"  -> {out}")


if __name__ == "__main__":
    main()
