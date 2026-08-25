"""Environment check. Run this first on a new machine.

    python doctor.py --root "D:\\Coltrane"

Verifies the few things this toolkit needs and says plainly what to install
if something is missing. Exits non-zero if the pipeline cannot run.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO_EXT = {".flac", ".mp3", ".dsf", ".dff", ".aif", ".aiff", ".aifc",
             ".wav", ".wv", ".ape", ".m4a", ".ogg", ".opus", ".alac"}
SKIP = {"System Volume Information", "$RECYCLE.BIN", "_library", "_playlists"}
OK, WARN, FAIL = "  ok  ", " warn ", " FAIL "


def line(status, label, detail=""):
    print(f"[{status}] {label}" + (f"  --  {detail}" if detail else ""))


def check_python():
    if sys.version_info < (3, 8):
        line(FAIL, "Python 3.8+", f"found {sys.version.split()[0]}")
        return False
    line(OK, f"Python {sys.version.split()[0]}", "standard library only")
    return True


def check_ffprobe():
    exe = shutil.which("ffprobe")
    if not exe:
        line(FAIL, "ffprobe not on PATH", "install FFmpeg")
        print("        Windows : winget install Gyan.FFmpeg")
        print("        macOS   : brew install ffmpeg")
        print("        Debian  : sudo apt install ffmpeg")
        print("        (only scan.py needs it; the browser and views do not)")
        return False
    try:
        out = subprocess.run([exe, "-version"], capture_output=True,
                             encoding="utf-8", errors="replace", timeout=20)
        ver = (out.stdout or "").splitlines()[0][:58]
    except Exception as e:  # noqa: BLE001
        line(FAIL, "ffprobe found but not runnable", str(e))
        return False
    line(OK, "ffprobe", ver)
    return True


def check_scripts():
    need = ["scan.py", "coltrane.py", "coltrane_build.py", "coltrane_views.py",
            "coltrane_app.py", "coltrane_audit.py"]
    missing = [f for f in need if not os.path.exists(os.path.join(HERE, f))]
    if missing:
        line(FAIL, "scripts missing", ", ".join(missing))
        return False
    line(OK, "Coltrane toolchain complete", f"{len(need)} scripts")
    return True


def check_vocab():
    ok = True
    for fname, label, key in (
            ("coltrane_sessions.json", "discography", "sessions"),
            ("coltrane_personnel.json", "personnel", "lineups")):
        p = os.path.join(HERE, "vocab", fname)
        if not os.path.exists(p):
            line(WARN, f"vocab/{fname} missing",
                 "dates or personnel will be far less complete")
            ok = False
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            n = len(d.get(key, []))
            extra = (f", {len(d.get('musicians', []))} musicians"
                     if key == "lineups" else "")
            line(OK, f"vocab: {label}", f"{n} {key}{extra}")
        except (OSError, json.JSONDecodeError) as e:
            line(FAIL, f"vocab/{fname} unreadable", str(e))
            ok = False
    return ok


def check_output():
    out = os.path.join(HERE, "output-coltrane")
    man = os.path.join(out, "coltrane.json")
    if not os.path.exists(man):
        line(WARN, "no manifest yet", "run scan.py then coltrane_build.py")
        return True
    try:
        with open(man, encoding="utf-8") as fh:
            c = json.load(fh)["counts"]
        line(OK, "manifest", ", ".join(f"{v:,} {k}" for k, v in c.items()))
    except Exception as e:  # noqa: BLE001
        line(FAIL, "manifest unreadable", str(e))
        return False
    b = os.path.join(out, "coltrane-browser.html")
    if os.path.exists(b):
        line(OK, "browser", f"{os.path.getsize(b)/1024:,.0f} KB -- open it "
                            f"from disk")
    else:
        line(WARN, "no browser yet", "run coltrane_app.py")
    return True


def check_root(root):
    if not os.path.isdir(root):
        line(FAIL, "archive root not a directory", root)
        return False
    n = folders = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        hit = [f for f in filenames
               if os.path.splitext(f)[1].lower() in AUDIO_EXT]
        if hit:
            folders += 1
            n += len(hit)
    if not n:
        line(FAIL, "no audio found under root", root)
        return False
    line(OK, "archive", f"{n:,} audio files in {folders:,} folders")
    print(f"        full scan estimate: ~{n/750:.0f} min at ~750 files/min")
    if os.access(root, os.W_OK):
        print("        note: root is writable; the toolkit still never "
              "writes there")
    return True


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="archive to check")
    args = ap.parse_args()

    print("music library toolkit -- environment check\n")
    results = [check_python(), check_scripts(), check_vocab(), check_output()]
    ff = check_ffprobe()
    if args.root:
        print()
        results.append(check_root(os.path.abspath(args.root)))

    print()
    if not all(results):
        print("Something required is missing -- see FAIL lines above.")
        return 1
    if not ff:
        print("Browser and views will work; scan.py needs ffprobe.")
        return 1
    print("All good.")
    print("  browse : output-coltrane/coltrane-browser.html")
    print("  verify : python coltrane_audit.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
