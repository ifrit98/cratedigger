"""Propose vocabulary additions found in your own folder names.

    python mine.py --root "L:\\Music" --verify        # review candidates
    python mine.py --root "L:\\Music" --apply         # merge into vocab/

Finds names sitting in a conductor position ('XXX_Name', 'Ensemble, Name')
that the vocabulary does not yet know, ranked by how often they occur. With
--verify each candidate is checked against MusicBrainz before being offered,
so private abbreviations and typos do not become permanent vocabulary.

Nothing is written unless you pass --apply.
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
        "artwork", "Scans", "scans", "Logs", "Covers"}
CLASSICAL_HINT = re.compile(
    r"classical|orchestra|symphon|conductor|opera|philharmon|chamber|"
    r"baroque|concerto|quartet|sonata|mass\b|requiem|cantata|oratorio", re.I)


def audio_folders(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        if any(os.path.splitext(f)[1].lower() in AUDIO_EXT for f in filenames):
            out.append(os.path.relpath(dirpath, root).replace("\\", "/"))
    return out


def mb_is_conductor(name):
    """Ask MusicBrainz whether this person is described as a conductor."""
    import mbfetch
    data = mbfetch.get("artist", {"query": f'artist:"{name}"', "limit": 5})
    if not data:
        return None
    for a in data.get("artists", []):
        if a.get("type") != "Person":
            continue
        if credits._flat(a.get("name", "")).endswith(credits._flat(name)) or \
                credits._flat(name) in credits._flat(a.get("name", "")):
            disamb = (a.get("disambiguation") or "").lower()
            if "conductor" in disamb:
                return a.get("name")
    return None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--min-count", type=int, default=2,
                    help="ignore names seen fewer than this many times")
    ap.add_argument("--verify", action="store_true",
                    help="confirm each candidate against MusicBrainz")
    ap.add_argument("--apply", action="store_true",
                    help="merge accepted candidates into vocab/")
    ap.add_argument("--vocab", default=credits.VOCAB_DIR)
    ap.add_argument("--out", default="mined_candidates.json")
    args = ap.parse_args()

    vocab = credits.reload_vocab(args.vocab)
    folders = audio_folders(args.root)
    print(f"scanning {len(folders)} audio folders")

    cand = Counter()
    examples = {}
    for f in folders:
        if not CLASSICAL_HINT.search(f):
            continue
        known, _conf, _ens = credits.extract_credits(
            f, None, (), is_classical=True, vocab=vocab,
            allow_structural=False)
        if known:
            continue                       # vocabulary already covers it
        name, rule = credits.find_conductor_structural(f)
        if not name or not credits._looks_like_person(name):
            continue
        key = credits._flat(name.split()[-1])
        if key in vocab.conductors or key in vocab.ambiguous:
            continue
        cand[name.strip()] += 1
        examples.setdefault(name.strip(), f)

    ranked = [(n, c) for n, c in cand.most_common() if c >= args.min_count]
    print(f"{len(ranked)} candidates seen >={args.min_count} times\n")

    accepted = {}
    for name, count in ranked:
        verdict = ""
        if args.verify:
            mb = mb_is_conductor(name)
            if not mb:
                verdict = "  [not a conductor in MusicBrainz - skipped]"
                print(f"  {count:4d}  {name:28s}{verdict}")
                continue
            verdict = f"  -> {mb}"
            accepted[credits._flat(name.split()[-1])] = {
                "name": mb, "aliases": [], "source": "mined+musicbrainz"}
        else:
            accepted[credits._flat(name.split()[-1])] = {
                "name": name, "aliases": [], "source": "mined"}
        print(f"  {count:4d}  {name:28s}{verdict}")
        print(f"        e.g. {examples[name][-72:]}")

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"candidates": [{"name": n, "count": c,
                                   "example": examples[n]}
                                  for n, c in ranked],
                   "accepted": accepted}, fh, ensure_ascii=False, indent=1)
    print(f"\nwrote {args.out}")

    if args.apply and accepted:
        cpath = os.path.join(args.vocab, "conductors.json")
        with open(cpath, encoding="utf-8") as fh:
            data = json.load(fh)
        added = 0
        for k, v in accepted.items():
            if k not in data["entries"]:
                data["entries"][k] = v
                added += 1
        with open(cpath, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
        print(f"merged {added} new entries into {cpath}")
    elif args.apply:
        print("nothing to merge")


if __name__ == "__main__":
    main()
