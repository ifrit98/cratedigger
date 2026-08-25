"""Point this at any music directory and get the same analysis.

    python organize.py --root "E:\\Music" --out "E:\\Music\\_library"

Runs the three stages in order: probe every file, derive the faceted model,
generate the playlist views. Read-only with respect to the music itself —
the only thing written is the output directory.

    --collection NAME=RATING   treat a top-level folder as a curated set
                               (repeatable; default BANGERS=5, pass
                               --collection "" for none)
    --skip NAME                directory name to ignore (repeatable)
    --stage scan|build|views   run one stage only
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def run(script, args, label):
    print(f"\n=== {label} ===", flush=True)
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, os.path.join(HERE, script)] + args,
                          env=env)
    if proc.returncode != 0:
        print(f"!! {script} failed (exit {proc.returncode})")
        sys.exit(proc.returncode)
    print(f"    [{time.time() - t0:.1f}s]", flush=True)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="music directory to analyze")
    ap.add_argument("--out", default=None,
                    help="output directory (default: <root>/_library)")
    ap.add_argument("--collection", action="append", default=None,
                    metavar="NAME[=RATING]")
    ap.add_argument("--skip", action="append", default=[])
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--stage", choices=["scan", "build", "views", "all"],
                    default="all")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        sys.exit(f"not a directory: {root}")
    out = os.path.abspath(args.out or os.path.join(root, "_library"))
    os.makedirs(out, exist_ok=True)
    raw = os.path.join(out, "raw_probe.jsonl")

    # never scan our own output back into the library
    skips = list(args.skip) + [os.path.basename(out)]

    print(f"root : {root}")
    print(f"out  : {out}")

    if args.stage in ("scan", "all"):
        a = ["--root", root, "--out", raw, "--workers", str(args.workers)]
        for s in skips:
            a += ["--skip", s]
        run("scan.py", a, "1/3 probing files")

    if args.stage in ("build", "all"):
        a = ["--raw", raw, "--out", out]
        for c in (args.collection if args.collection is not None
                  else ["BANGERS=5"]):
            if c:
                a += ["--collection", c]
        run("build.py", a, "2/3 deriving model")

    if args.stage in ("views", "all"):
        run("views.py", ["--out", out, "--root", root],
            "3/3 generating views")

    print(f"\ndone -> {out}")


if __name__ == "__main__":
    main()
