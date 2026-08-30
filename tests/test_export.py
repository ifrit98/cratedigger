"""The shareable export must not publish your filesystem.

This is a privacy guarantee, so it gets a test rather than a code review. The
interesting cases are the ones that are not the path column:

- a **library root**, which leaks a drive layout and often a username
- **paths inside metadata** -- this library really does contain album titles
  like `E:\\APE\\rip\\Bareboim Bruckner CSO\\CD01`, because whoever ripped
  them tagged the album with the directory they ripped into. Blanking the
  path column would publish those untouched.
- **`AC/DC`**, which must survive, because a naive slash-split would turn a
  band name into "DC".
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, os.pardir, "cratedigger")
sys.path.insert(0, PKG)

import export  # noqa: E402

B = chr(92)
CASE_COUNT = 12


def main():
    fails = []

    def check(label, ok, detail=""):
        print("%s  %-48s %s" % ("PASS" if ok else "FAIL", label, detail))
        if not ok:
            fails.append(label)

    # ---- scrub: path-shaped strings collapse, real titles survive
    for label, value, want in [
        ("windows path in a title", "E:" + B + "APE" + B + "rip" + B + "CD01",
         "CD01"),
        ("unc path", B + B + "nas" + B + "music" + B + "Album", "Album"),
        ("posix home", "/home/jason/Music/Album", "Album"),
        ("macos volume", "/Volumes/Backup/Music/Album", "Album"),
        ("users path", "C:/Users/bob/Music/Album", "Album"),
        ("ordinary title", "Bruckner 7 VPO Kleiber", "Bruckner 7 VPO Kleiber"),
        ("band name with a slash", "AC/DC Live", "AC/DC Live"),
        ("colon but not a drive", "Bach: The Art of Fugue",
         "Bach: The Art of Fugue"),
    ]:
        got = export.scrub(value)
        check(label, got == want, "" if got == want else "got %r" % got)

    # ---- strip_local: a payload carrying every kind of leak
    data = {
        "cols": ["date", "album", "path", "tune"],
        "tables": {"album": ["E:" + B + "APE" + B + "rip" + B + "CD01",
                             "Normal Album"]},
        "rows": [["1961", 0, "L:/Music/x.flac", "Naima"],
                 ["1962", 1, "L:/Music/y.flac", "Alabama"]],
        "root": "L:/Music/16 bit",
        "proposals": {"0": {"c": [1]}},
    }
    out = export.strip_local(data)

    check("root removed", "root" not in out)
    check("proposals removed", "proposals" not in out)
    check("share flag set", out.get("share") is True)
    check("paths blanked", all(r[2] == "" for r in out["rows"]))

    problems = export.audit(out)
    check("audit passes a clean payload", not problems,
          "; ".join(problems))

    print("\n%d/%d passed" % (CASE_COUNT - len(fails), CASE_COUNT))
    for f in fails:
        print("  failed: %s" % f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
