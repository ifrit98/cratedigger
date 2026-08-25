"""Phase 0: raw probe of every audio file on the drive -> raw_probe.jsonl

Read-only. Never writes to the music tree.
"""
import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.getcwd()
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_probe.jsonl")
WORKERS = 12

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


def main():
    global ROOT, OUT, WORKERS
    ap = argparse.ArgumentParser(
        description="Probe every audio file under a root (read-only).")
    ap.add_argument("--root", default=ROOT, help="music directory to scan")
    ap.add_argument("--out", default=OUT, help="raw_probe.jsonl to write")
    ap.add_argument("--skip", action="append", default=[],
                    help="directory name to skip (repeatable)")
    ap.add_argument("--workers", type=int, default=WORKERS)
    args = ap.parse_args()
    ROOT, OUT, WORKERS = args.root, args.out, args.workers
    SKIP_DIRS.update(args.skip)

    audio, containers, sidecars = [], [], []
    for kind, p in walk():
        (audio if kind == "audio" else
         containers if kind == "container" else sidecars).append(p)

    print(f"audio={len(audio)} containers={len(containers)} "
          f"sidecars={len(sidecars)}", flush=True)

    done = 0
    with open(OUT, "w", encoding="utf-8") as fh:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for rec in pool.map(probe, audio):
                rec["kind"] = "audio"
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                done += 1
                if done % 250 == 0:
                    print(f"  probed {done}/{len(audio)}", flush=True)

        for p in containers + sidecars:
            kind = "container" if p in set(containers) else "sidecar"
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
    print(f"done. {done} audio probed, {errs} errors -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
