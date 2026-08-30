"""Three-way agreement between our table, Wild, and MusicBrainz.

    python coltrane_consensus.py

Two independent sources agreeing is far stronger evidence than either alone,
and their disagreements are precisely the cases a human should look at. This
grades every album rather than picking a winner:

  confirmed        Wild and MusicBrainz agree, and so do we
  adopt            Wild and MusicBrainz agree with each other, we differ
  single-source    only one external source has anything
  contested        Wild and MusicBrainz disagree -- needs a person
  unsourced        neither has it; our date stands on its own

Nothing is applied. The output is a decision sheet.
"""
import collections
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
# Installed, the package lives in site-packages, which is a poor
# place to hand-edit curated vocabulary. CRATEDIGGER_VOCAB points
# somewhere writable without touching the install.
VOCAB = (os.environ.get("CRATEDIGGER_VOCAB")
         or os.path.join(HERE, "vocab"))
OUT = os.path.join(HERE, "output-coltrane")


def load(p, default):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def main():
    man = load(os.path.join(OUT, "coltrane.json"), {})
    wild_rows = {}
    wpath = os.path.join(OUT, "wild_reconciliation.csv")
    if os.path.exists(wpath):
        with open(wpath, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if r.get("wild_date") and r.get("album"):
                    wild_rows.setdefault(r["album"], r)

    mb = {}
    for s in load(os.path.join(VOCAB, "coltrane_mb_sessions.json"),
                  {"sessions": []})["sessions"]:
        if s.get("dates"):
            mb[s["album"]] = s

    rows = []
    tally = collections.Counter()
    for r in man.get("releases", []):
        album = r.get("title", "")
        ours = r.get("recording_date") or ""
        w = wild_rows.get(album[:60])
        m = mb.get(album)
        wd = (w or {}).get("wild_date") or ""
        md = next(iter(m["dates"]), "") if m else ""

        if wd and md:
            if wd[:10] == md[:10]:
                verdict = "confirmed" if ours[:10] == wd[:10] else "adopt"
            else:
                verdict = "contested"
        elif wd or md:
            single = wd or md
            verdict = ("confirmed" if ours[:10] == single[:10]
                       else "single-source")
        else:
            verdict = "unsourced"
        tally[verdict] += 1

        rows.append({
            "verdict": verdict,
            "ours": ours,
            "wild": wd,
            "musicbrainz": md,
            "our_source": r.get("date_source") or "",
            "our_precision": r.get("date_precision") or "",
            "mb_sessions": len(m["dates"]) if m else "",
            "wild_session": (w or {}).get("wild_session", ""),
            "wild_personnel": (w or {}).get("wild_personnel", ""),
            "album": album[:60],
            "path": r.get("path", ""),
        })

    order = {"contested": 0, "adopt": 1, "single-source": 2,
             "confirmed": 3, "unsourced": 4}
    out = os.path.join(OUT, "date_consensus.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w_.writeheader()
        for row in sorted(rows, key=lambda x: (order[x["verdict"]],
                                               x["album"])):
            w_.writerow(row)

    print(f"{len(rows)} releases graded\n")
    for k in order:
        print(f"  {k:14s} {tally[k]:4d}")
    print(f"\n  'adopt' = both sources agree and we differ -- the strongest")
    print(f"  case for changing a date. 'contested' = the two sources")
    print(f"  disagree, so no automated answer is defensible.")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
