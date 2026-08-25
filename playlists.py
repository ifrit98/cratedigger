"""Fast-path playlists: facet .m3u8 files straight from the filesystem.

    python playlists.py --root "L:\\Music" --out "L:\\Music\\_playlists"

No ffprobe, no manifest, no tag reading -- it walks the tree, applies
credits.py to each folder path, and writes playlists foobar2000 can open
immediately. A 90k-file library takes about half a minute.

This is deliberately the cheap route. It groups by what a folder name can
tell you: conductor, ensemble, composer, genre, format. For work-level views
('every recording of K.626') you need the full pipeline, because that
requires reading tags out of the files themselves -- see organize.py.
"""
import argparse
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import credits  # noqa: E402

try:
    from build import CANON            # composer surname -> canonical name
except Exception:                      # noqa: BLE001 - build.py is optional
    CANON = {}

AUDIO_EXT = {".flac", ".mp3", ".dsf", ".dff", ".aif", ".aiff", ".aifc",
             ".wav", ".wv", ".ape", ".m4a", ".ogg", ".opus", ".alac"}
SKIP_DIRS = {"System Volume Information", "$RECYCLE.BIN", "_library",
             "_playlists", "Artwork", "artwork", "Scans", "scans", "Logs",
             "logs", "Covers", "covers", "original cue"}

LOSSLESS = {".flac", ".wav", ".wv", ".ape", ".aif", ".aiff", ".aifc", ".alac"}
DSD_EXT = {".dsf", ".dff"}
LOSSY = {".mp3", ".m4a", ".ogg", ".opus"}

GENRE_KEYWORDS = {
    "Classical": ["classical", "orchestra", "conductor", "opera", "baroque",
                  "chamber", "symphon", "philharmon", "box set"],
    "Jazz": ["jazz", "bebop", "fusion", "blue note", "coltrane"],
    "Rock": ["rock", "metal", "prog", "punk", "indie"],
    "Electronic": ["electronic", "techno", "ambient", "house"],
    "Hip-Hop": ["hip hop", "hip-hop", "rap"],
    "Blues": ["blues", "soul", "r&b", "funk"],
    "Eastern": ["eastern", "raga", "gamelan"],
}

MAX_NAME = 80
_NUM = re.compile(r"(\d+)")


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in _NUM.split(s)]


def safe(name):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name))
    s = re.sub(r"\s{2,}", " ", s).strip(" .")
    return s[:MAX_NAME] or "untitled"


def walk_folders(root):
    """[(relative folder, [filenames])] for folders holding audio."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        audio = sorted((f for f in filenames
                        if os.path.splitext(f)[1].lower() in AUDIO_EXT),
                       key=natural_key)
        if audio:
            rel = os.path.relpath(dirpath, root).replace("\\", "/")
            out.append(("" if rel == "." else rel, audio))
    return out


def infer_genre(folder):
    low = folder.lower()
    for seg in low.split("/"):
        for genre, keys in GENRE_KEYWORDS.items():
            for k in keys:
                if k in seg:
                    return genre
        if seg.strip() in CANON:
            return "Classical"
    return None


def infer_composer(folder):
    """Canonical composer from a surname in the path."""
    flat = credits._flat(folder)
    for seg in reversed(flat.split("/")):
        for surname, canon in CANON.items():
            if re.search(r"\b" + re.escape(credits._flat(surname)) + r"\b",
                         seg):
                return canon
    return None


def format_tier(exts, folder):
    low = folder.lower()
    if exts & DSD_EXT or "dsd" in low or "sacd" in low:
        return "DSD-SACD"
    if exts & LOSSLESS:
        if re.search(r"24[\s\-_]?(bit|/|96|192|88|176)|\b24\-\d", low) \
                or "24 bit" in low or "hi-res" in low:
            return "Lossless Hi-Res"
        return "Lossless"
    if exts & LOSSY:
        return "Lossy"
    return "Other"


def write_playlist(path, entries, title, root, absolute):
    if not entries:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    base = os.path.dirname(path)
    with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("#EXTM3U\n")
        fh.write(f"#PLAYLIST:{title}\n")
        for rel, fn, label in entries:
            full = os.path.join(root, rel.replace("/", os.sep), fn)
            if absolute:
                out = os.path.abspath(full)
            else:
                out = os.path.relpath(full, base).replace(os.sep, "/")
            # duration -1: foobar2000 reads the real length from the file
            fh.write(f"#EXTINF:-1,{label}\n{out}\n")
    return True


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", default=None,
                    help="playlist directory (default <root>/_playlists)")
    ap.add_argument("--min-tracks", type=int, default=8,
                    help="skip playlists smaller than this")
    ap.add_argument("--relative", action="store_true",
                    help="relative paths (for removable drives); default is "
                         "absolute, which is what foobar2000 prefers on a "
                         "fixed drive")
    ap.add_argument("--vocab", default=None)
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    out = os.path.abspath(args.out or os.path.join(root, "_playlists"))
    if args.vocab:
        credits.reload_vocab(args.vocab)
    absolute = not args.relative

    print(f"root: {root}")
    folders = walk_folders(root)
    total = sum(len(f) for _, f in folders)
    print(f"{len(folders):,} folders, {total:,} audio files")

    by_conductor = defaultdict(list)
    by_ensemble = defaultdict(list)
    by_composer = defaultdict(list)
    by_genre = defaultdict(list)
    by_format = defaultdict(list)
    conf_of = {}

    for folder, files in folders:
        genre = infer_genre(folder)
        classical = genre == "Classical" or (
            genre is None and bool(infer_composer(folder)))
        cond, conf, ens = credits.extract_credits(
            folder, None, (), is_classical=classical)
        composer = infer_composer(folder) if classical else None
        exts = {os.path.splitext(f)[1].lower() for f in files}
        tier = format_tier(exts, folder)
        album = folder.split("/")[-1] if folder else "(root)"

        for fn in files:
            label = f"{album} - {os.path.splitext(fn)[0]}"
            item = (folder, fn, label)
            if cond:
                by_conductor[cond].append(item)
                conf_of[cond] = conf
            for e in ens:
                by_ensemble[e].append(item)
            if composer:
                by_composer[composer].append(item)
            if genre:
                by_genre[genre].append(item)
            by_format[tier].append(item)

    made = 0
    plan = [("conductor", by_conductor), ("ensemble", by_ensemble),
            ("composer", by_composer), ("genre", by_genre),
            ("format", by_format)]
    for facet, mapping in plan:
        kept = 0
        for name, entries in sorted(mapping.items()):
            if len(entries) < args.min_tracks:
                continue
            fname = safe(name) + ".m3u8"
            title = f"{facet.title()}: {name}"
            if facet == "conductor" and conf_of.get(name) in (
                    "ambiguous", "structural"):
                fname = "_review " + fname       # sorts together for checking
                title += "  [unverified]"
            if write_playlist(os.path.join(out, facet, fname), entries,
                              title, root, absolute):
                made += 1
                kept += 1
        print(f"  {facet:10s} {kept:4d} playlists "
              f"({len(mapping)} groups before the {args.min_tracks}-track cut)")

    # one big playlist per facet is handy as a foobar2000 starting point
    print(f"\n{made} playlists -> {out}")
    print("\nfoobar2000:  File > Load Playlist, or drag a .m3u8 in.")
    print("             Select many at once to open them as separate tabs.")


if __name__ == "__main__":
    main()
