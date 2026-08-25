"""Adversarial audit of the Coltrane manifest.

    python coltrane_audit.py --manifest output-coltrane/coltrane.json

Looks for things that are *wrong*, not things that are present. Every check
prints examples so a claim can be verified rather than trusted. Exit code is
the number of high-severity findings.
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coltrane  # noqa: E402

HIGH, MED, LOW = "HIGH", "MED ", "LOW "
findings = []


def report(sev, name, count, detail="", examples=()):
    findings.append((sev, name, count))
    flag = " " if count == 0 else "!"
    print(f"[{sev}]{flag} {name}: {count}" + (f"  -- {detail}" if detail else ""))
    for e in list(examples)[:5]:
        print(f"        {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="output-coltrane/coltrane.json")
    ap.add_argument("--root", required=True,
                    help="archive root, so paths can be checked on disk")
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as fh:
        m = json.load(fh)
    rel = m["releases"]
    tr = m["tracks"]
    by_id = {r["release_id"]: r for r in rel}

    print(f"=== auditing {len(tr):,} tracks / {len(rel)} releases ===\n")

    # ---------------------------------------------------------- dates
    bad = [r for r in rel if r["recording_date"]
           and not coltrane.is_plausible_recording_date(r["recording_date"])]
    report(HIGH, "dates outside Coltrane's life", len(bad),
           "recorded 1945-1967 only",
           [f"{r['recording_date']}  {r['path'][:70]}" for r in bad])

    # a release whose date came from a tag but whose folder says otherwise
    conflict = []
    for r in rel:
        if r["date_source"] != "tag" or not r["recording_date"]:
            continue
        iso, prec = coltrane.parse_recording_date(r["path"])
        if iso and iso[:4] != r["recording_date"][:4]:
            conflict.append(f"tag={r['recording_date']} folder={iso}  "
                            f"{r['path'][:60]}")
    report(MED, "tag date disagrees with folder date", len(conflict),
           examples=conflict)

    # same album title, different recording dates across format tiers
    by_title = collections.defaultdict(set)
    for r in rel:
        if r["recording_date"] and r.get("title"):
            key = re.sub(r"[^a-z0-9]", "", r["title"].lower())[:28]
            if key:
                by_title[key].add(r["recording_date"])
    split = {k: v for k, v in by_title.items() if len(v) > 1}
    report(MED, "same album dated differently in different tiers", len(split),
           "usually one copy matched the discography and another did not",
           [f"{k}: {sorted(v)}" for k, v in list(split.items())])

    # ---------------------------------------------------------- coverage
    undated = [r for r in rel if not r["recording_date"]]
    report(LOW, "releases with no date", len(undated),
           f"{len(undated)*100//len(rel)}% of releases",
           [r["path"][:74] for r in undated])

    no_person = [r for r in rel if not r.get("personnel")]
    report(LOW, "releases with no personnel", len(no_person),
           examples=[r["path"][:74] for r in no_person])

    # ---------------------------------------------------------- tunes
    junk = []
    for t in m["tunes"]:
        title = (t["title"] or "").strip()
        if (not title or re.fullmatch(r"[\d\W_]+", title)
                or re.match(r"^(track|untitled|audio|unknown|cd\d)", title,
                            re.I)
                or len(title) <= 2):
            junk.append(f"{t['performance_count']:3d}x  {title!r}")
    report(MED, "junk tune titles", len(junk),
           "unnamed or numeric track titles becoming pseudo-tunes",
           junk)

    singles = sum(1 for t in m["tunes"] if t["performance_count"] == 1)
    report(LOW, "tunes with a single performance", singles,
           f"of {len(m['tunes'])} tunes -- inflated by tagging noise")

    # tune spans that cross Coltrane's whole career suspiciously
    wide = []
    for t in m["tunes"]:
        f, l = t.get("first_recorded"), t.get("last_recorded")
        if f and l and t["performance_count"] >= 5:
            if int(l[:4]) - int(f[:4]) >= 11:
                wide.append(f"{t['title'][:40]}  {f[:4]}-{l[:4]}  "
                            f"({t['performance_count']}x)")
    report(LOW, "tunes spanning 11+ years", len(wide),
           "plausible for repertoire staples, suspicious otherwise", wide)

    # ---------------------------------------------------------- personnel
    anach = []
    for r in rel:
        if not r["recording_date"] or not r.get("personnel"):
            continue
        lu = coltrane.lineup_for(r["recording_date"])
        if not lu:
            continue
        band = {mm["name"] for mm in lu["members"]}
        if r.get("personnel_source") == "named":
            odd = [p for p in r["personnel"] if p not in band]
            if len(odd) == len(r["personnel"]) and len(odd) > 2:
                anach.append(f"{r['recording_date']}  {lu['name'][:26]}  "
                             f"named={odd[:3]}  {r['folder_name'][:34]}")
    report(LOW, "named personnel entirely outside the date's band",
           len(anach), "expected for one-off session dates", anach)

    # ---------------------------------------------------------- structure
    empty = [r for r in rel if r["track_count"] == 0]
    report(HIGH, "releases with zero tracks", len(empty),
           examples=[r["path"] for r in empty])

    orphan = [t for t in tr if t["release_id"] not in by_id]
    report(HIGH, "tracks pointing at a missing release", len(orphan))

    dupe_ids = [k for k, v in collections.Counter(
        t["track_id"] for t in tr).items() if v > 1]
    report(HIGH, "duplicate track ids", len(dupe_ids))

    # ---------------------------------------------------------- files
    missing = []
    for t in tr:
        p = os.path.join(args.root, t["path"].replace("/", os.sep))
        if not os.path.exists(p):
            missing.append(t["path"])
        if len(missing) > 40:
            break
    report(HIGH, "manifest paths not on disk", len(missing),
           examples=missing)

    # ---------------------------------------------------------- provenance
    # a studio-classified release at a known live venue
    contradiction = []
    for r in rel:
        if r["provenance"] == "studio" and r.get("venue") and \
                "studio" not in (r["venue"] or "").lower():
            contradiction.append(f"{r['venue'][:24]}  {r['folder_name'][:44]}")
    report(MED, "marked studio but venue is not a studio", len(contradiction),
           examples=contradiction)

    print()
    high = sum(c for s, _n, c in findings if s == HIGH)
    med = sum(c for s, _n, c in findings if s == MED)
    print(f"HIGH severity total: {high}")
    print(f"MED  severity total: {med}")
    return min(high, 250)


if __name__ == "__main__":
    sys.exit(main())
