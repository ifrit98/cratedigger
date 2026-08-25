"""Phase 3b: project the faceted manifest into m3u8 playlist views.

Each facet becomes a folder of playlists. Paths are relative to the playlist
file, so the whole drive stays portable across machines and drive letters.
"""
import argparse
import json
import os
import re
from collections import defaultdict

OUTDIR = "D:\\_library"
ROOT = "D:\\"
VIEWS = os.path.join(OUTDIR, "views")
# Relative hop from a playlist back to the music root. Recomputed in main()
# so the output directory can live anywhere, inside the tree or beside it.
PREFIX = "../../../"

MAX_NAME = 80


def safe(name):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name))
    s = re.sub(r"\s{2,}", " ", s).strip(" .")
    return (s[:MAX_NAME] or "untitled")


def write_playlist(path, tracks, title):
    if not tracks:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("#EXTM3U\n")
        fh.write(f"#PLAYLIST:{title}\n")
        for t in tracks:
            dur = int(t["duration_seconds"]) if t.get("duration_seconds") else -1
            label_artist = (t.get("composer") or t.get("album_artist")
                            or (t.get("artist_raw") or "").split(";")[0]
                            or "Unknown")
            label_title = t.get("title") or t.get("filename")
            fh.write(f"#EXTINF:{dur},{label_artist} - {label_title}\n")
            # forward slashes throughout: portable, and accepted by
            # foobar2000, VLC, FiiO and every player worth supporting
            fh.write(PREFIX + t["path"].replace("\\", "/") + "\n")
    return True


def sort_key(t):
    return (t.get("_album") or "", t.get("disc_number") or 0,
            t.get("track_number") or 0, t.get("path") or "")


def work_order(t):
    """Movements in score order, recordings grouped by release."""
    return (t.get("_album") or "", t.get("disc_number") or 0,
            t.get("movement_number") or t.get("track_number") or 0,
            t.get("path") or "")


def compute_prefix(root, views_dir):
    """Relative path from views/<facet>/ back to the music root."""
    facet_dir = os.path.join(views_dir, "x")
    rel = os.path.relpath(os.path.abspath(root), os.path.abspath(facet_dir))
    return rel.replace(os.sep, "/") + "/"


def main():
    global OUTDIR, VIEWS, ROOT, PREFIX
    ap = argparse.ArgumentParser(description="Generate m3u8 facet views.")
    ap.add_argument("--out", default=OUTDIR, help="library manifest directory")
    ap.add_argument("--root", default=ROOT, help="music root the paths are relative to")
    args = ap.parse_args()
    OUTDIR, ROOT = args.out, args.root
    VIEWS = os.path.join(OUTDIR, "views")
    PREFIX = compute_prefix(ROOT, VIEWS)

    with open(os.path.join(OUTDIR, "library.json"), encoding="utf-8") as fh:
        m = json.load(fh)

    relmap = {r["release_id"]: r for r in m["releases"]}
    workmap = {w["work_id"]: w for w in m["works"]}

    tracks = []
    for r in m["releases"]:
        for t in r["tracks"]:
            t = dict(t)
            t["_album"] = r["title"]
            t["_release"] = r
            t["album_artist"] = r["album_artist"]
            tracks.append(t)

    made = 0

    # ---- facet: collections (BANGERS)
    coll = defaultdict(list)
    for t in tracks:
        for c in t["_release"]["collections"]:
            coll[c].append(t)
    for c, ts in coll.items():
        made += write_playlist(
            os.path.join(VIEWS, "collections", safe(c) + ".m3u8"),
            sorted(ts, key=sort_key), c)

    # ---- facet: quality tier
    q = defaultdict(list)
    for t in tracks:
        q[t.get("quality_tier") or "Unknown"].append(t)
    for k, ts in q.items():
        made += write_playlist(
            os.path.join(VIEWS, "quality", safe(k) + ".m3u8"),
            sorted(ts, key=sort_key), f"Quality: {k}")

    # ---- facet: source medium
    src = defaultdict(list)
    for t in tracks:
        src[t["_release"].get("source_medium") or "Unknown"].append(t)
    for k, ts in src.items():
        made += write_playlist(
            os.path.join(VIEWS, "source", safe(k) + ".m3u8"),
            sorted(ts, key=sort_key), f"Source: {k}")

    # ---- facet: genre
    g = defaultdict(list)
    for t in tracks:
        g[t["_release"].get("genre_primary") or "Unfiled"].append(t)
    for k, ts in g.items():
        made += write_playlist(
            os.path.join(VIEWS, "genre", safe(k) + ".m3u8"),
            sorted(ts, key=sort_key), f"Genre: {k}")

    # ---- facet: composer (only where it is a real organizing axis)
    comp = defaultdict(list)
    for t in tracks:
        if t.get("composer"):
            comp[t["composer"]].append(t)
    for k, ts in sorted(comp.items()):
        if len(ts) < 4:
            continue
        made += write_playlist(
            os.path.join(VIEWS, "composer", safe(k) + ".m3u8"),
            sorted(ts, key=work_order), k)

    # ---- facet: work, but only works with more than one recording.
    # This is the view a single-hierarchy filesystem cannot express:
    # every performance of one piece, side by side.
    multi = 0
    for wid, w in workmap.items():
        if (w.get("recording_count") or 0) < 2:
            continue
        ts = [t for t in tracks if t.get("work_id") == wid]
        if len(ts) < 2:
            continue
        cat = (f"{w['catalog_system']}.{w['catalog_number']}"
               if w.get("catalog_system") else "")
        surname = (w["composer"] or "").split(",")[0]
        name = " - ".join(x for x in [surname, cat, w.get("title")] if x)
        if write_playlist(
                os.path.join(VIEWS, "works-multiple-recordings",
                             safe(name) + ".m3u8"),
                sorted(ts, key=work_order), name):
            made += 1
            multi += 1

    # ---- facet: decade of recording
    dec = defaultdict(list)
    for t in tracks:
        y = t["_release"].get("recording_year") or \
            t["_release"].get("release_year")
        if y:
            dec[f"{(y // 10) * 10}s"].append(t)
    for k, ts in sorted(dec.items()):
        made += write_playlist(
            os.path.join(VIEWS, "decade", safe(k) + ".m3u8"),
            sorted(ts, key=sort_key), f"Recorded: {k}")

    print(f"playlists written: {made}")
    print(f"  works with >1 recording: {multi}")
    print(f"  composers: {sum(1 for k,v in comp.items() if len(v)>=4)}")
    print(f"  -> {VIEWS}")


if __name__ == "__main__":
    main()
