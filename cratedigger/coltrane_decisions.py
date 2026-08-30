"""Apply date decisions exported from the browser.

    python coltrane_decisions.py --in ~/Downloads/coltrane-date-decisions.json

Reads the JSON the Reconcile view exports and writes
`vocab/coltrane_date_overrides.json`, which coltrane_build.py then treats as
the highest-precedence source -- above folder names, above the discography
table, above tags -- because it records a human decision with a citation.

Merges rather than replaces, so a second round of adjudication adds to the
first. Use --replace to start clean.
"""
import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OVERRIDES = os.path.join(HERE, "vocab", "coltrane_date_overrides.json")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--out", default=OVERRIDES)
    args = ap.parse_args()

    if not os.path.exists(args.src):
        sys.exit(f"no such file: {args.src}")
    with open(args.src, encoding="utf-8") as fh:
        incoming = json.load(fh)
    if not incoming.get("_schema", "").startswith("coltrane-date-decisions"):
        sys.exit("that file is not a decisions export")

    existing = {"_schema": "coltrane-date-overrides/1", "overrides": {}}
    if os.path.exists(args.out) and not args.replace:
        try:
            with open(args.out, encoding="utf-8") as fh:
                existing = json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass
    ov = existing.setdefault("overrides", {})

    added = updated = kept = 0
    tally = collections.Counter()
    for path, d in incoming.get("decisions", {}).items():
        tally[d.get("action")] += 1
        if d.get("action") == "keep":
            # an explicit decision to leave the existing date alone; record
            # it so a later pass does not re-propose the same change
            entry = {"action": "keep", "decided": incoming.get("_generated")}
            kept += 1
        else:
            entry = {
                "action": "accept",
                "date": d.get("date"),
                "precision": "day",
                "wild_session": d.get("wild_session"),
                "location": d.get("location"),
                "personnel": d.get("personnel") or [],
                "decided": incoming.get("_generated"),
                "source": "David Wild discography, adjudicated in browser",
            }
        if path in ov:
            updated += 1
        else:
            added += 1
        ov[path] = entry

    existing["_note"] = ("Human decisions. Highest precedence in "
                         "coltrane_build.py -- above folder names, the "
                         "discography table and tags.")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, ensure_ascii=False, indent=1)

    print(f"decisions read : {sum(tally.values()):,} "
          f"({dict(tally)})")
    print(f"  new          : {added:,}")
    print(f"  updated      : {updated:,}")
    print(f"  'keep' marks : {kept:,}")
    print(f"total overrides now: {len(ov):,}")
    print(f"\n-> {args.out}")
    print("\nRebuild to apply:")
    print('  python coltrane_build.py --raw output-coltrane/raw_probe.jsonl '
          '--out output-coltrane --root "D:\\Coltrane"')


if __name__ == "__main__":
    main()
