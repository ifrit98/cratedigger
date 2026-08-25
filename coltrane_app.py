"""Generate a self-contained interactive browser for the Coltrane archive.

    python coltrane_app.py --manifest output-coltrane/coltrane.json \\
                           --out output-coltrane/coltrane-browser.html \\
                           --root "D:\\Coltrane"

Writes ONE html file with the whole ontology embedded. Open it from disk and
it works offline, with no server. Because it is a local file it can point an
<audio> element at the archive, so tracks play in place.

The data is compacted before embedding -- repeated strings (era, lineup,
venue, personnel) become indexes into lookup tables, which takes the payload
from ~4.5 MB of JSON to roughly a third of that.
"""
import argparse
import json
import os
import sys

from browser_core import write_html


def compact(manifest):
    """Index repeated strings so the payload stays small."""
    tables = {}
    order = {}

    def idx(table, value):
        if value is None or value == "":
            return -1
        t = tables.setdefault(table, [])
        o = order.setdefault(table, {})
        if value not in o:
            o[value] = len(t)
            t.append(value)
        return o[value]

    rel = {r["release_id"]: r for r in manifest["releases"]}
    rows = []
    for t in manifest["tracks"]:
        r = rel.get(t["release_id"], {})
        rows.append([
            t.get("recording_date") or "",
            idx("era", t.get("era")),
            idx("lineup", t.get("lineup")),
            idx("prov", t.get("provenance")),
            idx("auth", t.get("authority")),
            idx("role", t.get("role")),
            idx("venue", t.get("venue") or t.get("city")),
            idx("fmt", t.get("format_tier")),
            idx("album", t.get("album")),
            t.get("tune") or t.get("title") or "",
            t.get("path") or "",
            int(t.get("duration_seconds") or 0),
            [idx("person", p) for p in (t.get("personnel") or [])],
            idx("dsrc", t.get("date_source")),
            1 if r.get("is_compilation") else 0,
        ])
    rows.sort(key=lambda x: (x[0] or "9999", x[8], x[10]))
    return {"cols": ["date", "era", "lineup", "prov", "auth", "role", "venue",
                     "fmt", "album", "tune", "path", "dur", "people", "dsrc",
                     "comp"],
            "tables": tables, "rows": rows,
            "counts": manifest["counts"]}


def attach_proposals(data, proposals_path):
    """Fold Wild's per-track session candidates into the payload.

    Sessions are stored once and referenced by index; a track carries only
    the indexes of its candidates. Without that, 1,675 tracks with up to six
    candidates each would triple the file size.
    """
    if not os.path.exists(proposals_path):
        return 0
    try:
        with open(proposals_path, encoding="utf-8") as fh:
            src = json.load(fh)["tracks"]
    except (OSError, json.JSONDecodeError, KeyError):
        return 0

    sessions, index = [], {}

    def sidx(c):
        key = c["session"]
        if key not in index:
            index[key] = len(sessions)
            sessions.append([c["session"], c["date"], c.get("group") or "",
                             c.get("location") or "",
                             "; ".join(c.get("personnel") or [])])
        return index[key]

    row_of = {r[10]: i for i, r in enumerate(data["rows"])}
    props = {}
    for path, info in src.items():
        i = row_of.get(path)
        if i is None:
            continue
        cands = info.get("candidates") or []
        if not cands:
            continue
        idxs = [sidx(c) for c in cands]
        cur = data["rows"][i][0]
        exact = [j for j, c in enumerate(cands) if c["date"] == cur]
        if len(cands) == 1:
            conf = "unique"
            best = 0
        elif len(exact) == 1:
            conf = "corroborated"
            best = exact[0]
        else:
            conf = "ambiguous"
            best = 0
        props[str(i)] = {"c": idxs, "b": best, "k": conf}
    data["wild_sessions"] = sessions
    data["proposals"] = props
    return len(props)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default="output-coltrane/coltrane.json")
    ap.add_argument("--out", default="output-coltrane/coltrane-browser.html")
    ap.add_argument("--root", required=True,
                    help="archive root the manifest paths are relative to")
    ap.add_argument("--proposals",
                    default="output-coltrane/wild_track_proposals.json",
                    help="Wild per-track session candidates, if present")
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as fh:
        man = json.load(fh)
    data = compact(man)
    data["root"] = os.path.abspath(args.root).replace("\\", "/")
    # The browser core is generic; this is what makes it an artist archive.
    data.update({
        "title": "John Coltrane Archive",
        "heading": "John Coltrane",
        "subheading": "archive browser",
        "facets": [["era", "Era"], ["lineup", "Lineup"],
                   ["prov", "Recording"], ["auth", "Issue"],
                   ["role", "Role"], ["person", "Personnel"],
                   ["venue", "Venue"], ["fmt", "Format"],
                   ["dsrc", "Date source"]],
        "multi_facets": ["person"],
        "multi_col": {"person": "people"},
        "modes": [["timeline", "Timeline"], ["tracks", "Track list"],
                  ["tunes", "Tunes"], ["reconcile", "Reconcile dates"]],
        "labels": {"group": "Tune"},
    })
    n_prop = attach_proposals(data, args.proposals)

    kb = write_html(args.out, data) / 1024
    print(f"wrote {args.out}  ({kb:,.0f} KB)")
    print(f"  {len(data['rows']):,} tracks embedded")
    if n_prop:
        print(f"  {n_prop:,} tracks carry Wild session candidates "
              f"({len(data['wild_sessions'])} sessions)")
    print(f"  open it directly from disk -- no server needed")



if __name__ == "__main__":
    sys.exit(main())
