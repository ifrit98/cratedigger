"""Phase 0: probe every audio file -> raw_probe.jsonl

Read-only. Never writes to the music tree.

Incremental by default: a file whose path, size and mtime are unchanged
since the last scan is reused from the previous probe rather than
re-read. ffprobe is the entire cost of this stage, so on a library that
has barely moved a rescan drops from minutes to seconds.

The reuse index lives beside the probe as `<out>.index.json`, not inside
the JSONL. Downstream loaders route unknown record kinds to "sidecar",
so a metadata record embedded in the probe would quietly corrupt
release provenance.
"""
import argparse
import json
import os
import subprocess
import time
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.getcwd()
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_probe.jsonl")
WORKERS = 12
INDEX_VERSION = 1

AUDIO_EXT = {".flac", ".mp3", ".dsf", ".dff", ".aif", ".aiff", ".aifc",
             ".wav", ".wv", ".ape", ".m4a", ".ogg", ".opus", ".alac"}
CONTAINER_EXT = {".iso"}
SIDECAR_EXT = {".cue", ".log", ".txt", ".nfo", ".pdf", ".md5", ".sfv",
               ".accurip", ".jpg", ".jpeg", ".png", ".webp", ".m3u",
               ".m3u8", ".fpl", ".mht", ".rtf"}
SKIP_DIRS = {"System Volume Information", "$RECYCLE.BIN", "_library"}


def walk():
    """Yield (kind, abspath) for everything we care about."""
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            # AppleDouble sidecars ("._Track.flac") a Mac leaves behind when
            # copying onto this drive. Same extension as the real track next
            # to them, so they would otherwise be probed as audio and only
            # dropped by chance when ffprobe finds nothing playable in them.
            if fn.startswith("._"):
                continue
            ext = os.path.splitext(fn)[1].lower()
            full = os.path.join(dirpath, fn)
            if ext in AUDIO_EXT:
                yield ("audio", full)
            elif ext in CONTAINER_EXT:
                yield ("container", full)
            elif ext in SIDECAR_EXT:
                yield ("sidecar", full)


def probe(path):
    """ffprobe one file. Returns a dict; never raises."""
    rec = {"path": os.path.relpath(path, ROOT).replace("\\", "/")}
    try:
        rec["size"] = os.path.getsize(path)
        rec["mtime"] = int(os.path.getmtime(path))
    except OSError as e:
        rec["error"] = f"stat: {e}"
        return rec

    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        rec["error"] = "ffprobe timeout"
        return rec
    except Exception as e:  # noqa: BLE001 - want the scan to survive anything
        rec["error"] = f"ffprobe: {e}"
        return rec

    if proc.returncode != 0 or not proc.stdout.strip():
        rec["error"] = "ffprobe failed"
        return rec

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        rec["error"] = f"json: {e}"
        return rec

    fmt = data.get("format", {})
    rec["tags"] = fmt.get("tags", {})
    rec["duration"] = fmt.get("duration")
    rec["format_name"] = fmt.get("format_name")
    rec["bit_rate"] = fmt.get("bit_rate")

    # first audio stream only; cover-art streams are ignored
    for st in data.get("streams", []):
        if st.get("codec_type") != "audio":
            continue
        rec["codec"] = st.get("codec_name")
        rec["sample_rate"] = st.get("sample_rate")
        rec["channels"] = st.get("channels")
        rec["bits_per_raw_sample"] = st.get("bits_per_raw_sample")
        rec["bits_per_sample"] = st.get("bits_per_sample")
        rec["sample_fmt"] = st.get("sample_fmt")
        if not rec.get("duration"):
            rec["duration"] = st.get("duration")
        break
    rec["has_embedded_art"] = any(
        s.get("codec_type") == "video" for s in data.get("streams", [])
    )
    return rec


def index_path(out):
    return out + ".index.json"


def load_cache(out, root, retry_errors=False):
    """Previous audio records keyed by path, when they are still valid.

    Returns {} whenever anything is off -- a different root, a version bump,
    a missing or unreadable file. Reuse has to be provably safe or not
    attempted.
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
                if r.get("kind") != "audio":
                    continue
                if r.get("error") and retry_errors:
                    continue
                if r.get("size") is None or r.get("mtime") is None:
                    continue
                cache[r["path"]] = r
    except OSError:
        return {}
    return cache


def write_index(out, root, counts):
    try:
        with open(index_path(out), "w", encoding="utf-8") as fh:
            json.dump({"version": INDEX_VERSION,
                       "root": os.path.abspath(root),
                       "scanned": int(time.time()),
                       "counts": counts}, fh, indent=1)
    except OSError:
        pass


def main():
    global ROOT, OUT, WORKERS
    ap = argparse.ArgumentParser(
        description="Probe every audio file under a root (read-only).")
    ap.add_argument("--root", default=ROOT, help="music directory to scan")
    ap.add_argument("--out", default=OUT, help="raw_probe.jsonl to write")
    ap.add_argument("--skip", action="append", default=[],
                    help="directory name to skip (repeatable)")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--full", action="store_true",
                    help="re-probe everything, ignoring the previous scan")
    ap.add_argument("--retry-errors", action="store_true",
                    help="re-probe files that failed last time")
    args = ap.parse_args()
    ROOT, OUT, WORKERS = args.root, args.out, args.workers
    SKIP_DIRS.update(args.skip)

    out_dir = os.path.dirname(os.path.abspath(OUT))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    audio, containers, sidecars = [], [], []
    for kind, p in walk():
        (audio if kind == "audio" else
         containers if kind == "container" else sidecars).append(p)

    print(f"audio={len(audio)} containers={len(containers)} "
          f"sidecars={len(sidecars)}", flush=True)

    cache = {} if args.full else load_cache(OUT, ROOT, args.retry_errors)
    if cache:
        print(f"previous scan: {len(cache):,} usable records", flush=True)

    # Decide per file: reuse, or probe. A cached record is only trusted when
    # path, size and mtime all agree -- any of them moving means re-read.
    reuse, todo = [], []
    for p in audio:
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        hit = cache.get(rel)
        if hit is not None:
            try:
                st = os.stat(p)
            except OSError:
                todo.append(p)
                continue
            if hit.get("size") == st.st_size and \
                    hit.get("mtime") == int(st.st_mtime):
                reuse.append(hit)
                continue
        todo.append(p)

    removed = len(cache) - len(reuse) if cache else 0
    if cache:
        print(f"  reusing {len(reuse):,}, probing {len(todo):,}"
              + (f", {removed:,} gone or changed" if removed > 0 else ""),
              flush=True)

    done = 0
    with open(OUT, "w", encoding="utf-8") as fh:
        for rec in reuse:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

        if todo:
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                for rec in pool.map(probe, todo):
                    rec["kind"] = "audio"
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    done += 1
                    if done % 250 == 0:
                        print(f"  probed {done}/{len(todo)}", flush=True)

        containers_set = set(containers)
        for p in containers + sidecars:
            kind = "container" if p in containers_set else "sidecar"
            try:
                size = os.path.getsize(p)
            except OSError:
                size = None
            fh.write(json.dumps({
                "kind": kind,
                "path": os.path.relpath(p, ROOT).replace("\\", "/"),
                "size": size,
            }, ensure_ascii=False) + "\n")

    errs = 0
    with open(OUT, encoding="utf-8") as fh:
        for line in fh:
            if '"error"' in line:
                errs += 1
    write_index(OUT, ROOT, {"audio": len(audio), "probed": done,
                            "reused": len(reuse), "errors": errs})
    saved = ""
    if reuse:
        saved = f"  ({len(reuse):,} reused, ~{len(reuse)/750:.0f} min saved)"
    print(f"done. {done} probed, {errs} errors -> {OUT}{saved}")


if __name__ == "__main__":
    sys.exit(main())
