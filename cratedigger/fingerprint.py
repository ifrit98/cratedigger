"""Identify tracks by their audio rather than their filename.

    python fingerprint.py --root "E:\\Music" --out output/fingerprints.jsonl
    python fingerprint.py --root "E:\\Music" --lookup        # needs a key

This is the answer to a folder of `track01.mp3` with no tags, which no amount
of filename parsing can rescue. It is also the only part of the toolkit with
dependencies outside the standard library, so it is **strictly optional**:
absent `fpcalc` or an API key, it explains what is missing and changes
nothing. Everything else keeps working exactly as before.

Two stages, deliberately separate:

  1. `fpcalc` computes a Chromaprint fingerprint locally. No network, no key,
     nothing leaves the machine.
  2. AcoustID turns a fingerprint into recording ids. Network, and a free
     API key from https://acoustid.org/new-application.

Stage 1 is cached so stage 2 can be run, re-run, or run much later without
touching the audio again -- fingerprinting a large library is expensive and
the fingerprint does not change unless the file does.

Nothing is applied. Results are candidates for `apply.py` to score.

Known gap: the bundled fpcalc cannot decode `.dff` (DSDIFF) files --
its own static ffmpeg lacks that demuxer, even though `ffprobe` on
this machine reads the same files fine. Real, playable SACD rips
come back as fingerprinting errors for this reason alone.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_VERSION = 1

AUDIO_EXT = {".flac", ".mp3", ".dsf", ".dff", ".aif", ".aiff", ".aifc",
             ".wav", ".m4a", ".ape", ".wv", ".ogg", ".opus", ".wma", ".mpc"}

ACOUSTID_URL = "https://api.acoustid.org/v2/lookup"
ACOUSTID_RATE = 0.34          # their published ceiling is 3 requests/second
UA = "cratedigger/1.0 (personal library cataloging)"
_last = [0.0]


# --------------------------------------------------------------------------
# locating fpcalc


def find_fpcalc(explicit=None):
    """Path to fpcalc, or None.

    winget installs it outside PATH until the shell restarts, which makes
    "I just installed it and it still says missing" the first thing a user
    hits. Looking in the package directory costs nothing and avoids that.
    """
    if explicit:
        return explicit if os.path.exists(explicit) else None

    from shutil import which
    found = which("fpcalc")
    if found:
        return found

    local = os.environ.get("LOCALAPPDATA")
    if local:
        pkgs = os.path.join(local, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(pkgs):
            for dirpath, _dirs, files in os.walk(pkgs):
                if "fpcalc.exe" in files:
                    return os.path.join(dirpath, "fpcalc.exe")
    return None


def api_key(explicit=None):
    return (explicit or os.environ.get("CRATEDIGGER_ACOUSTID_KEY")
            or os.environ.get("ACOUSTID_API_KEY") or "").strip() or None


# --------------------------------------------------------------------------
# stage 1: fingerprint locally


def fingerprint_one(fpcalc, path, timeout=120):
    """{'duration', 'fingerprint'} or {'error'}."""
    try:
        proc = subprocess.run([fpcalc, "-json", path],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": "fpcalc timed out"}
    except OSError as e:
        return {"error": "fpcalc failed: %s" % e}
    if proc.returncode != 0:
        msg = (proc.stderr or b"").decode("utf-8", "replace").strip()
        return {"error": msg[:200] or "fpcalc exited %d" % proc.returncode}
    try:
        d = json.loads(proc.stdout.decode("utf-8", "replace"))
    except ValueError:
        return {"error": "fpcalc returned unparseable json"}
    if not d.get("fingerprint"):
        return {"error": "no fingerprint produced"}
    return {"duration": int(round(d.get("duration") or 0)),
            "fingerprint": d["fingerprint"]}


def index_path(out):
    return out + ".index.json"


def load_cache(out, root):
    """Previous fingerprints keyed by path, when they are still valid.

    Same discipline as scan.py: a different root or a version bump discards
    everything, because reuse has to be provably safe or not attempted.
    """
    idx = index_path(out)
    if not (os.path.exists(out) and os.path.exists(idx)):
        return {}
    try:
        with open(idx, encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        return {}
    if meta.get("version") != INDEX_VERSION:
        return {}
    if os.path.normcase(os.path.abspath(meta.get("root", ""))) != \
            os.path.normcase(os.path.abspath(root)):
        return {}
    cache = {}
    try:
        with open(out, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("size") is None or r.get("mtime") is None:
                    continue
                cache[r["path"]] = r
    except OSError:
        return {}
    return cache


def walk(root, skip):
    skip = {s.lower() for s in skip}
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs
                   if d.lower() not in skip and not d.startswith(".")]
        for f in sorted(files):
            if f.startswith("._"):    # AppleDouble sidecar, not audio
                continue
            if os.path.splitext(f)[1].lower() in AUDIO_EXT:
                yield os.path.join(dirpath, f)


def stage_fingerprint(args):
    fpcalc = find_fpcalc(args.fpcalc)
    if not fpcalc:
        print("fpcalc not found -- fingerprinting is unavailable.\n")
        print("  Windows:  winget install AcoustID.Chromaprint")
        print("  macOS:    brew install chromaprint")
        print("  Linux:    apt install libchromaprint-tools\n")
        print("Everything else in cratedigger works without it.")
        return 2
    print("fpcalc: %s" % fpcalc)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".",
                exist_ok=True)
    cache = {} if args.full else load_cache(args.out, args.root)
    files = list(walk(args.root, args.skip))
    print("%d audio files, %d already fingerprinted" % (len(files), len(cache)))

    records, reused, done, errors = [], 0, 0, 0
    t0 = time.time()
    for i, full in enumerate(files, 1):
        rel = os.path.relpath(full, args.root).replace("\\", "/")
        try:
            st = os.stat(full)
        except OSError:
            continue
        hit = cache.get(rel)
        if hit and hit.get("size") == st.st_size \
                and hit.get("mtime") == int(st.st_mtime):
            records.append(hit)
            reused += 1
            continue

        rec = {"path": rel, "size": st.st_size, "mtime": int(st.st_mtime)}
        rec.update(fingerprint_one(fpcalc, full, args.timeout))
        records.append(rec)
        if rec.get("error"):
            errors += 1
        else:
            done += 1
        if args.limit and done >= args.limit:
            print("  stopping at --limit %d" % args.limit)
            break
        if done and done % 50 == 0:
            rate = done / max(0.001, time.time() - t0)
            print("  %d/%d  %.1f files/s" % (i, len(files), rate))

    # --limit stops early, and the file is rewritten whole. Without this,
    # every fingerprint past the break point would be dropped and have to be
    # recomputed -- turning a resume flag into a way to lose work.
    have = {r["path"] for r in records}
    for path, rec in cache.items():
        if path not in have:
            records.append(rec)
    records.sort(key=lambda r: r["path"])

    with open(args.out, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    try:
        with open(index_path(args.out), "w", encoding="utf-8") as fh:
            json.dump({"version": INDEX_VERSION,
                       "root": os.path.abspath(args.root),
                       "fingerprinted": int(time.time()),
                       "counts": {"files": len(records), "new": done,
                                  "reused": reused, "errors": errors}},
                      fh, indent=1)
    except OSError:
        pass

    print("\n%d fingerprinted, %d reused, %d errors  (%.0fs)"
          % (done, reused, errors, time.time() - t0))
    print("-> %s" % args.out)
    if not api_key(args.key):
        print("\nNo AcoustID key set, so nothing was looked up. To identify:")
        print("  1. free key from https://acoustid.org/new-application")
        print("  2. set CRATEDIGGER_ACOUSTID_KEY")
        print("  3. python fingerprint.py --root ... --lookup")
    return 0


# --------------------------------------------------------------------------
# stage 2: ask AcoustID what these are


class Fatal(Exception):
    """The run cannot continue -- a bad key, not a bad file."""


# AcoustID reports failures in the response body, not the status line, so a
# rejected key arrives as a 400 that looks exactly like any other 400. These
# are the codes where retrying is pointless: the key is wrong, and it will be
# wrong for every one of the next few thousand files.
FATAL_CODES = {4, 6}          # invalid API key, invalid user API key


def _describe(body):
    """(code, message) from an AcoustID error body."""
    try:
        d = json.loads(body)
    except ValueError:
        return None, (body or "").strip()[:200] or "no message"
    err = d.get("error") or {}
    return err.get("code"), err.get("message") or "unknown error"


def acoustid_lookup(key, duration, fp, retries=3):
    """(results, transient, error). Same contract as the MusicBrainz
    reconciler: a throttle must never be cached as an absence. Raises Fatal
    when the key itself is refused."""
    data = urllib.parse.urlencode({
        "client": key, "duration": str(duration), "fingerprint": fp,
        "meta": "recordings releasegroups compress",
    }).encode("ascii")
    problem = "no response"
    for attempt in range(retries):
        wait = ACOUSTID_RATE - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(
                ACOUSTID_URL, data=data,
                headers={"User-Agent": UA,
                         "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=30) as fh:
                d = json.loads(fh.read().decode("utf-8"))
            if d.get("status") != "ok":
                err = d.get("error") or {}
                if err.get("code") in FATAL_CODES:
                    raise Fatal(err.get("message") or "the key was refused")
                return None, False, err.get("message") or "not ok"
            return d.get("results") or [], False, None
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                problem = "HTTP %d (throttled)" % e.code
                time.sleep(2 ** attempt)
                continue
            code, msg = _describe(e.read().decode("utf-8", "replace"))
            if code in FATAL_CODES:
                raise Fatal(msg)
            # a real, cacheable refusal of this fingerprint
            return None, False, "HTTP %d: %s" % (e.code, msg)
        except Fatal:
            raise
        except Exception as e:  # noqa: BLE001
            problem = "%s: %s" % (type(e).__name__, e)
            time.sleep(2 ** attempt)
    return None, True, problem


def best_result(results):
    """The strongest identification, or None.

    AcoustID returns a score per match. A high score on a recording with no
    metadata is useless, so the pick is the highest-scoring result that
    actually carries a recording.
    """
    best = None
    for r in results or []:
        recs = r.get("recordings") or []
        if not recs:
            continue
        if best is None or (r.get("score") or 0) > (best.get("score") or 0):
            best = r
    if not best:
        return None
    rec = best["recordings"][0]
    groups = rec.get("releasegroups") or []
    return {
        "acoustid": best.get("id"),
        "score": round(best.get("score") or 0, 3),
        "recording_id": rec.get("id"),
        "title": rec.get("title"),
        "artists": [a.get("name") for a in (rec.get("artists") or [])
                    if a.get("name")],
        "release_group": (groups[0].get("title") if groups else None),
        "release_group_id": (groups[0].get("id") if groups else None),
        "n_candidates": len(results or []),
    }


def stage_lookup(args):
    key = api_key(args.key)
    if not key:
        print("No AcoustID API key.\n")
        print("  1. free key from https://acoustid.org/new-application")
        print("  2. set CRATEDIGGER_ACOUSTID_KEY=<key>")
        print("     (or pass --key)\n")
        print("Fingerprints already computed are kept; re-run when you have"
              " one.")
        return 2
    if not os.path.exists(args.out):
        print("no fingerprints yet -- run without --lookup first")
        return 2

    prints = []
    with open(args.out, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("fingerprint"):
                prints.append(r)

    ident_path = os.path.splitext(args.out)[0] + "_ids.json"
    ident = {}
    if os.path.exists(ident_path) and not args.full:
        try:
            with open(ident_path, encoding="utf-8") as fh:
                ident = json.load(fh)
        except (OSError, ValueError):
            ident = {}

    todo = [p for p in prints if p["path"] not in ident]
    if args.limit:
        todo = todo[:args.limit]
    print("%d fingerprints, %d already identified, looking up %d"
          % (len(prints), len(ident), len(todo)))

    found = skipped = 0
    reasons = {}
    try:
        for i, p in enumerate(todo, 1):
            results, transient, err = acoustid_lookup(key, p["duration"],
                                                      p["fingerprint"])
            if transient:
                skipped += 1
                reasons[err or "unknown"] = reasons.get(err or "unknown", 0) + 1
                continue                  # leave uncached so a rerun retries
            if err:
                reasons[err] = reasons.get(err, 0) + 1
            best = best_result(results)
            ident[p["path"]] = best or {"score": 0, "n_candidates": 0}
            if best:
                found += 1
            if i % 25 == 0:
                with open(ident_path, "w", encoding="utf-8") as fh:
                    json.dump(ident, fh, ensure_ascii=False, indent=1)
                print("  %d/%d  %d identified" % (i, len(todo), found))
    except Fatal as e:
        # Stop at the first one. Retrying a refused key once per file would
        # spend hours arriving at this same sentence.
        print("\nAcoustID refused the key: %s\n" % e)
        print("  key used: %s" % (key[:3] + "..." + key[-2:]))
        print("\nAcoustID issues TWO keys and the error is the same for")
        print("both. Signing in gives you a *user* API key, which is for")
        print("submitting fingerprints. Lookup needs an *application* key,")
        print("which only exists once you register an application:")
        print("\n  https://acoustid.org/new-application   (sign in first)")
        print("\nAny name and version will do. The key it issues is the one")
        print("to use here; existing ones are at /my-applications.")
        if ident:
            with open(ident_path, "w", encoding="utf-8") as fh:
                json.dump(ident, fh, ensure_ascii=False, indent=1)
            print("\n%d results from before the failure kept in %s"
                  % (len(ident), ident_path))
        return 2

    with open(ident_path, "w", encoding="utf-8") as fh:
        json.dump(ident, fh, ensure_ascii=False, indent=1)
    print("\n%d identified of %d looked up" % (found, len(todo)))
    if skipped:
        print("%d deferred after server errors -- run again to pick them up"
              % skipped)
    for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1])[:5]:
        print("  %4d  %s" % (n, reason))
    print("-> %s" % ident_path)
    print("\nNothing was applied. A dry run is the default; score these")
    print("with:  python apply.py --manifest <manifest>")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="music directory")
    ap.add_argument("--out", default="output/fingerprints.jsonl")
    ap.add_argument("--lookup", action="store_true",
                    help="stage 2: ask AcoustID to identify what was"
                         " fingerprinted")
    ap.add_argument("--skip", action="append", default=[])
    ap.add_argument("--full", action="store_true",
                    help="ignore the cache and redo everything")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--fpcalc", default=None, help="path to the fpcalc binary")
    ap.add_argument("--key", default=None, help="AcoustID API key")
    args = ap.parse_args()
    return stage_lookup(args) if args.lookup else stage_fingerprint(args)


if __name__ == "__main__":
    sys.exit(main())
