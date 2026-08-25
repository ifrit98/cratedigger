"""Interactive browser for a mixed library.

    python general_app.py --manifest output/library.json \\
                          --out output/library-browser.html \\
                          --root "L:\\Music"

Same client as the artist archive -- see browser_core.py -- driven by a
different payload. Where the artist model has a session spine, this one has
a **work** spine: every recording of a piece side by side, which is the view
a folder tree cannot express for classical music.
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_core import index_strings, write_html  # noqa: E402


def compact(manifest):
    """Manifest -> the row/table payload the client expects."""
    idx, tables = index_strings()
    rel = {r["release_id"]: r for r in manifest["releases"]}
    works = {w["work_id"]: w for w in manifest.get("works", [])}

    rows = []
    for r in manifest["releases"]:
        for t in r.get("tracks", []):
            w = works.get(t.get("work_id")) or {}
            # a work's display name carries its catalogue number, which is
            # what makes two recordings of the same piece recognisable
            wt = t.get("work_title") or w.get("title")
            if wt and t.get("catalog_system") and t.get("catalog_number"):
                wt = "%s (%s.%s)" % (wt, t["catalog_system"],
                                     t["catalog_number"])
            year = str(r.get("recording_year") or r.get("release_year") or "")
            rows.append([
                year,
                idx("composer", t.get("composer")),
                idx("work", wt),
                idx("genre", r.get("genre_primary")),
                idx("quality", t.get("quality_tier")),
                idx("source", r.get("source_medium")),
                idx("conductor", t.get("conductor")),
                idx("label", r.get("label")),
                idx("album", r.get("title")),
                t.get("title") or t.get("filename") or "",
                t.get("path") or "",
                int(t.get("duration_seconds") or 0),
                [idx("ensemble", e) for e in (t.get("ensembles") or [])],
                idx("dsrc", t.get("conductor_source")),
                1 if r.get("is_container_release") else 0,
            ])

    # work, then album, then path -- so a work's recordings sit together
    rows.sort(key=lambda x: (x[0] or "9999", x[8], x[10]))
    return {
        "cols": ["date", "composer", "work", "genre", "quality", "source",
                 "conductor", "label", "album", "tune", "path", "dur",
                 "people", "dsrc", "comp"],
        "tables": tables, "rows": rows,
        "counts": manifest.get("counts", {}),
    }


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--title", default=None,
                    help="heading for the page; defaults to the folder name")
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as fh:
        man = json.load(fh)

    data = compact(man)
    data["root"] = os.path.abspath(args.root).replace("\\", "/")
    name = args.title or os.path.basename(os.path.abspath(args.root)) or "Library"
    data.update({
        "title": "%s — cratedigger" % name,
        "heading": name,
        "subheading": "library browser",
        # 'work' first: for a mixed library that is the axis the folders
        # cannot express, the way session date is for an artist archive
        "facets": [["work", "Work"], ["composer", "Composer"],
                   ["genre", "Genre"], ["conductor", "Conductor"],
                   ["people", "Ensemble"], ["quality", "Quality"],
                   ["source", "Source"], ["label", "Label"]],
        "multi_facets": ["people"],
        "multi_col": {"people": "people"},
        "modes": [["works", "Works"], ["tracks", "Track list"],
                  ["timeline", "By year"]],
        "labels": {"group": "Work"},
        "group_col": "work",
    })

    kb = write_html(args.out, data) / 1024
    print("wrote %s  (%s KB)" % (args.out, format(round(kb), ",")))
    print("  %s tracks embedded" % format(len(data["rows"]), ","))

    multi = collections.Counter(r[data["cols"].index("work")]
                                for r in data["rows"])
    multi = sum(1 for k, v in multi.items() if k >= 0 and v > 1)
    print("  %s works with more than one track" % format(multi, ","))
    print("  open it directly from disk -- no server needed")


if __name__ == "__main__":
    main()
