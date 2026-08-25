"""Measure credits.py coverage against a real library's folder names.

Filesystem only -- no ffprobe, no reads of audio content. Reports hit rate and
dumps the misses so the vocabulary gaps are visible rather than guessed at.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import credits  # noqa: E402

AUDIO_EXT = {".flac", ".mp3", ".dsf", ".dff", ".aif", ".aiff", ".wav", ".wv",
             ".ape", ".m4a", ".ogg", ".opus", ".iso"}
SKIP = {"System Volume Information", "$RECYCLE.BIN", "_library", "Artwork",
        "artwork", "Scans", "scans", "Logs", "Covers", "original cue"}

CLASSICAL_HINT = re.compile(
    r"classical|orchestra|symphon|conductor|opera|philharmon|chamber|"
    r"baroque|concerto|quartet|sonata|mass\b|requiem|cantata|oratorio", re.I)


def audio_folders(root):
    """Folders that directly contain audio files."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        if any(os.path.splitext(f)[1].lower() in AUDIO_EXT for f in filenames):
            out.append(os.path.relpath(dirpath, root).replace("\\", "/"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", default="credits_eval.json")
    ap.add_argument("--misses", type=int, default=60)
    args = ap.parse_args()

    folders = audio_folders(args.root)
    print(f"audio-bearing folders: {len(folders)}")

    hits, miss, ens_only, conf = 0, [], 0, Counter()
    names = Counter()
    for f in folders:
        classical = bool(CLASSICAL_HINT.search(f))
        cond, c, ens = credits.extract_credits(f, None, (),
                                               is_classical=classical)
        if cond:
            hits += 1
            conf[c] += 1
            names[cond] += 1
        else:
            if ens:
                ens_only += 1
            # only count a miss where a conductor plausibly belongs
            if classical:
                miss.append(f)

    n = len(folders) or 1
    print(f"conductor resolved : {hits} ({hits*100//n}%)")
    print(f"ensemble only      : {ens_only}")
    print(f"classical w/o cond : {len(miss)}")
    print(f"confidence         : {dict(conf)}")
    print(f"distinct conductors: {len(names)}")

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"folders": len(folders), "hits": hits,
                   "misses": miss, "names": names.most_common()},
                  fh, ensure_ascii=False, indent=1)

    print(f"\n--- sample misses (classical folders, no conductor) ---")
    for m in miss[:args.misses]:
        print("   ", m[-110:])


if __name__ == "__main__":
    main()
