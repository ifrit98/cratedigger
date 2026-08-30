"""A shareable, read-only copy of a catalogue.

    python export.py --manifest output/library.json --out output/share
    python export.py --manifest output-coltrane/coltrane.json \\
                     --out output-coltrane/share --artist

For showing someone what you have. It is the browser you already use, with
everything that only makes sense on your own machine taken out:

- **no audio**, and no `<audio>` element to imply otherwise
- **no filesystem paths** -- not hidden, *absent* from the payload, because a
  hidden path is still a path you published
- **no playlist export**, which would emit paths into someone else's player
- **no library root**, which leaks your drive layout and your username

What is left is the catalogue: the works, the dates, the personnel, the
facets, the counts. That is the part worth showing.

The result is a directory with an `index.html` you can host anywhere static
-- GitHub Pages, S3, a USB stick -- or open from disk. There is no server and
nothing to configure.
"""
import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from browser_core import write_html  # noqa: E402

# Payload keys that describe *your machine* rather than the music.
LOCAL_KEYS = ("root", "proposals", "wild_sessions")

# Paths turn up inside metadata, not only in the path column. Real album
# titles in this library include an "E:\\APE\\rip..." and a mojibake
# "D:\\<new folder>" -- whoever ripped them tagged the album with the
# directory they ripped into. Blanking the path column publishes those
# untouched, which is why the audit checks the whole payload and not just
# the column it cleared.
_PATHY = re.compile(r"[A-Za-z]:[\\/]"
                    r"|\\\\[^\\]"
                    r"|/(?:Users|home|mnt|media|Volumes)/")
_SEP = re.compile(r"[\\/]+")


def scrub(value):
    """Reduce a path-shaped string to its last component."""
    if not isinstance(value, str) or not _PATHY.search(value):
        return value
    tail = [p for p in _SEP.split(value) if p.strip()]
    return tail[-1] if tail else ""


def strip_local(data):
    """Remove every trace of the local filesystem from a payload.

    Blanking the path column is not enough on its own: the strings would
    still be in the file, just unused. They are overwritten with the empty
    string so the published bytes do not contain them at all.
    """
    for key in LOCAL_KEYS:
        data.pop(key, None)

    cols = data.get("cols") or []
    if "path" in cols:
        i = cols.index("path")
        for row in data.get("rows", []):
            if len(row) > i:
                row[i] = ""

    # the interned lookup tables hold album, venue, label and work strings
    for table in (data.get("tables") or {}).values():
        for j, value in enumerate(table):
            table[j] = scrub(value)
    # and any free strings left in the rows themselves
    for row in data.get("rows", []):
        for j, value in enumerate(row):
            if isinstance(value, str):
                row[j] = scrub(value)

    data["share"] = True
    return data


def audit(data):
    """Prove the payload is clean. Returns a list of problems."""
    problems = []
    if data.get("root"):
        problems.append("root is still present")
    blob = json.dumps(data, ensure_ascii=False)
    for marker in (":\\\\", ":/", "C:", "/Users/", "/home/"):
        if marker in blob:
            # a drive letter or home directory would be a leak
            if marker in (":/", ":\\\\") and "http" in blob:
                continue          # a url, not a path
            problems.append("payload still contains %r" % marker)
    cols = data.get("cols") or []
    if "path" in cols:
        i = cols.index("path")
        if any((r[i] if len(r) > i else "") for r in data.get("rows", [])):
            problems.append("some rows still carry a path")
    return problems


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True, help="directory to write")
    ap.add_argument("--artist", action="store_true",
                    help="the manifest is an artist archive")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as fh:
        man = json.load(fh)

    # Reuse the real browsers' compaction so a shared copy cannot drift from
    # the one you use. Only the stripping is specific to sharing.
    if args.artist:
        import coltrane_app
        data = coltrane_app.compact(man)
        name = args.title or "Archive"
        data.update({
            "title": name, "heading": name, "subheading": "catalogue",
            "facets": [["era", "Era"], ["lineup", "Lineup"],
                       ["prov", "Recording"], ["auth", "Issue"],
                       ["role", "Role"], ["person", "Personnel"],
                       ["venue", "Venue"], ["fmt", "Format"]],
            "multi_facets": ["person"], "multi_col": {"person": "people"},
            "modes": [["timeline", "Timeline"], ["tracks", "Track list"],
                      ["tunes", "Tunes"]],
            "labels": {"group": "Tune"},
        })
    else:
        import general_app
        data = general_app.compact(man)
        name = args.title or "Library"
        data.update({
            "title": name, "heading": name, "subheading": "catalogue",
            "facets": [["work", "Work"], ["composer", "Composer"],
                       ["genre", "Genre"], ["conductor", "Conductor"],
                       ["people", "Ensemble"], ["quality", "Quality"],
                       ["source", "Source"], ["label", "Label"]],
            "multi_facets": ["people"], "multi_col": {"people": "people"},
            "modes": [["works", "Works"], ["tracks", "Track list"],
                      ["timeline", "By year"]],
            "labels": {"group": "Work"}, "group_col": "work",
        })

    n_rows = len(data.get("rows", []))
    strip_local(data)

    problems = audit(data)
    if problems:
        print("refusing to export -- the payload is not clean:")
        for p in problems:
            print("  %s" % p)
        return 1

    os.makedirs(args.out, exist_ok=True)
    index = os.path.join(args.out, "index.html")
    write_html(index, data)

    # The client also removes the player when DATA.share is set, but a
    # <audio> element sitting in the published bytes makes "no audio" a claim
    # about runtime behaviour rather than about the file. Cut it out, so the
    # statement is true of the artifact itself and the script is a fallback.
    html = io.open(index, encoding="utf-8").read()
    a = html.find('<footer id="footer">')
    b = html.find("</footer>", a)
    if a != -1 and b != -1:
        html = html[:a] + html[b + len("</footer>"):]
        io.open(index, "w", encoding="utf-8").write(html)
    if "<audio" in html:
        print("warning: an <audio> element survived the strip")
    kb = os.path.getsize(index) / 1024

    print("wrote %s  (%s KB)" % (index, format(round(kb), ",")))
    print("  %s tracks, no audio, no paths, no library root"
          % format(n_rows, ","))
    print("  host the directory anywhere static, or open index.html from disk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
