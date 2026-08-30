"""Incremental scan: reuse must be provably equivalent to a full scan.

Builds a tiny library in a temp directory from silent generated files, so it
needs no fixtures and no real audio. ffprobe is still exercised -- these are
real files it really reads.

The dangerous case is the last one: reusing a cache across a different root
would produce a probe describing files that are not there.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir, "cratedigger")
sys.path.insert(0, ROOT)

SCAN = os.path.join(ROOT, "scan.py")
CASE_COUNT = 7


def have_ffmpeg():
    return bool(shutil.which("ffprobe")) and bool(shutil.which("ffmpeg"))


def make_wav(path, seconds=1):
    """A real audio file, made by ffmpeg, so ffprobe has something to read."""
    subprocess.run(
        ["ffmpeg", "-loglevel", "quiet", "-y", "-f", "lavfi",
         "-i", "anullsrc=r=8000:cl=mono", "-t", str(seconds), path],
        check=True)


def run_scan(root, out, *extra):
    p = subprocess.run(
        [sys.executable, SCAN, "--root", root, "--out", out, "--workers", "2"]
        + list(extra),
        capture_output=True, encoding="utf-8", errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return p.stdout + p.stderr


def records(out):
    with open(out, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def paths(out):
    return sorted(r["path"] for r in records(out) if r.get("kind") == "audio")


def main():
    if not have_ffmpeg():
        print("SKIP  ffmpeg/ffprobe not available; incremental scan "
              "untestable here")
        return 0

    tmp = tempfile.mkdtemp(prefix="cratedigger-scan-")
    fails = []

    def check(name, ok, detail=""):
        if not ok:
            fails.append((name, detail))
        print("%s  %-44s %s" % ("PASS" if ok else "FAIL", name, detail))

    try:
        lib = os.path.join(tmp, "lib")
        os.makedirs(os.path.join(lib, "a"))
        os.makedirs(os.path.join(lib, "b"))
        for p in ("a/one.wav", "a/two.wav", "b/three.wav"):
            make_wav(os.path.join(lib, p))
        out = os.path.join(tmp, "probe.jsonl")

        # 1 -- a first scan probes everything
        o = run_scan(lib, out)
        first = records(out)
        check("first scan probes everything",
              "3 probed" in o and len(paths(out)) == 3,
              "%d audio records" % len(paths(out)))

        # 2 -- an unchanged rescan reuses everything and produces the same
        #      content, not merely the same count
        o = run_scan(lib, out)
        second = records(out)
        same = (sorted(json.dumps(r, sort_keys=True) for r in first)
                == sorted(json.dumps(r, sort_keys=True) for r in second))
        check("unchanged rescan reuses all",
              "reusing 3, probing 0" in o and same,
              "output identical" if same else "OUTPUT DIFFERS")

        # 3 -- a touched file is re-probed
        time.sleep(1.1)                      # mtime has 1s resolution
        os.utime(os.path.join(lib, "a/one.wav"), None)
        o = run_scan(lib, out)
        check("touched file is re-probed", "probing 1" in o)

        # 4 -- a new file is probed
        make_wav(os.path.join(lib, "b/four.wav"))
        o = run_scan(lib, out)
        check("new file is probed",
              "probing 1" in o and len(paths(out)) == 4)

        # 5 -- a removed file leaves the probe
        os.remove(os.path.join(lib, "b/three.wav"))
        o = run_scan(lib, out)
        p = paths(out)
        check("removed file drops out",
              len(p) == 3 and not any("three" in x for x in p),
              ", ".join(p))

        # 6 -- --full ignores the cache
        o = run_scan(lib, out, "--full")
        check("--full re-probes everything",
              "3 probed" in o and "reusing" not in o)

        # 7 -- the same out file under a DIFFERENT root must not be reused.
        #      Without the root check this yields a probe describing files
        #      that do not exist under the new root.
        lib2 = os.path.join(tmp, "lib2")
        os.makedirs(os.path.join(lib2, "x"))
        make_wav(os.path.join(lib2, "x/other.wav"))
        o = run_scan(lib2, out)
        p = paths(out)
        check("cross-root reuse refused",
              "previous scan" not in o and p == ["x/other.wav"],
              ", ".join(p))

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d/%d passed" % (CASE_COUNT - len(fails), CASE_COUNT))
    for name, detail in fails:
        print("  %s: %s" % (name, detail))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
