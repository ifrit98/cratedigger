"""cratedigger -- one command for the whole pipeline.

    python cratedigger.py init          point it at a library, once
    python cratedigger.py all           scan, build, views, browser
    python cratedigger.py status        what is configured and what is built

Everything else in this repo is a stage you can still run by hand with
explicit paths. This wraps them so you do not have to repeat
`--root ... --out ... --manifest ...` on every invocation: `init` writes a
small `cratedigger.json` next to your project and every later command reads
it.

Commands
--------
  init      create or update the project config; optionally bootstrap an
            artist profile from MusicBrainz
  status    configuration, artist profile, vocabulary and build state
  scan      probe every audio file            (the slow stage)
  build     derive the manifest               (seconds)
  views     generate the playlist splines     (seconds)
  browse    generate the interactive browser and open it
  audit     adversarial data checks
  enrich    pull session data from MusicBrainz / David Wild
  artists   list, show or create artist profiles
  all       scan -> build -> views -> browse
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_NAME = "cratedigger.json"
ARTISTS_DIR = os.path.join(HERE, "vocab", "artists")
UA = "cratedigger/1.0 (personal library cataloging)"

AUDIO_EXT = {".flac", ".mp3", ".dsf", ".dff", ".aif", ".aiff", ".aifc",
             ".wav", ".wv", ".ape", ".m4a", ".ogg", ".opus", ".alac"}
SKIP_DIRS = {"System Volume Information", "$RECYCLE.BIN", "_library",
             "_playlists", "Artwork", "artwork", "Scans", "scans", "Logs"}


# ----------------------------------------------------------------- config

def ask(prompt, default=""):
    """Prompt only when there is a human there.

    input() raises EOFError under a script, a pipe or CI, which turned a
    missing flag into a traceback instead of a clear message.
    """
    if not sys.stdin or not sys.stdin.isatty():
        return default
    try:
        return input(prompt).strip().strip('"')
    except (EOFError, KeyboardInterrupt):
        return default


def config_path(start=None):
    return os.path.join(start or os.getcwd(), CONFIG_NAME)


def load_config(required=True):
    p = config_path()
    if not os.path.exists(p):
        # also accept a config sitting beside the toolkit
        alt = config_path(HERE)
        if os.path.exists(alt):
            p = alt
        elif required:
            sys.exit("No cratedigger.json here.\n"
                     "  Run:  python cratedigger.py init")
        else:
            return {}
    with open(p, encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["_path"] = p
    return cfg


def save_config(cfg, path=None):
    path = path or config_path()
    out = {k: v for k, v in cfg.items() if not k.startswith("_")}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    return path


def out_dir(cfg):
    return os.path.abspath(cfg.get("output") or "output")


def manifest_path(cfg):
    name = "coltrane.json" if cfg.get("mode") == "artist" else "library.json"
    return os.path.join(out_dir(cfg), name)


# ----------------------------------------------------------------- helpers

def run(script, args, label=None):
    if label:
        print(f"\n=== {label} ===", flush=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if os.environ.get("CRATEDIGGER_ARTIST"):
        env["CRATEDIGGER_ARTIST"] = os.environ["CRATEDIGGER_ARTIST"]
    t0 = time.time()
    proc = subprocess.run([sys.executable, os.path.join(HERE, script)] + args,
                          env=env)
    if proc.returncode != 0:
        sys.exit(f"!! {script} exited {proc.returncode}")
    if label:
        print(f"    [{time.time() - t0:.1f}s]", flush=True)


def survey(root):
    """(files, folders, extensions) without probing anything."""
    n = folders = 0
    exts = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        hit = [f for f in filenames
               if os.path.splitext(f)[1].lower() in AUDIO_EXT]
        if hit:
            folders += 1
            n += len(hit)
            for f in hit:
                e = os.path.splitext(f)[1].lower()
                exts[e] = exts.get(e, 0) + 1
    return n, folders, exts


def mb_get(endpoint, params):
    url = ("https://musicbrainz.org/ws/2/" + endpoint + "?"
           + urllib.parse.urlencode(dict(params, fmt="json")))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    time.sleep(1.1)
    with urllib.request.urlopen(req, timeout=25) as fh:
        return json.loads(fh.read().decode("utf-8"))


# ------------------------------------------------------------------- init

def cmd_init(args):
    cfg = load_config(required=False)
    library = args.library or cfg.get("library")

    if not library:
        print("Point cratedigger at a music folder.\n")
        library = ask("  path to your library: ")
    if not library:
        sys.exit("No library given. Pass one:\n"
                 '  python cratedigger.py init --library "D:\\Music"')
    library = os.path.abspath(os.path.expanduser(library))
    if not os.path.isdir(library):
        sys.exit(f"not a directory: {library}")

    print(f"\nsurveying {library} ...")
    n, folders, exts = survey(library)
    if not n:
        sys.exit("no audio files found there")
    top = sorted(exts.items(), key=lambda kv: -kv[1])[:5]
    print(f"  {n:,} audio files in {folders:,} folders")
    print("  " + ", ".join(f"{e} {c:,}" for e, c in top))
    print(f"  a full scan will take roughly {n/750:.0f} min")

    mode = args.mode
    if not mode:
        mode = "artist" if args.artist else (
            cfg.get("mode") or ("artist" if folders < 1500 else "library"))
    artist_slug = cfg.get("artist")

    if mode == "artist":
        name = args.artist
        if not name and not artist_slug:
            name = ask("\n  artist for this archive (blank to skip): ")
        if name:
            artist_slug = ensure_profile(name, offline=args.offline)
        elif not artist_slug:
            mode = "library"

    output = args.output or cfg.get("output") or (
        f"output-{artist_slug}" if artist_slug else "output")

    cfg.update({"library": library.replace("\\", "/"),
                "output": output,
                "mode": mode})
    if artist_slug:
        cfg["artist"] = artist_slug
    p = save_config(cfg)

    print(f"\nwrote {p}")
    print(f"  library : {library}")
    print(f"  output  : {output}")
    print(f"  mode    : {mode}" + (f" ({artist_slug})" if artist_slug else ""))
    print("\nNext:")
    print("  python cratedigger.py all        # scan, build, views, browser")
    print("  python cratedigger.py status")


def slugify(name):
    s = "".join(c.lower() if c.isalnum() else "-" for c in name)
    return "-".join(x for x in s.split("-") if x)


def ensure_profile(name, offline=False):
    """Find or create vocab/artists/<slug>.json for this artist."""
    os.makedirs(ARTISTS_DIR, exist_ok=True)
    slug = slugify(name)

    # an existing profile wins, matched on slug or on the name inside it
    for fn in sorted(os.listdir(ARTISTS_DIR)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(ARTISTS_DIR, fn)
        try:
            with open(path, encoding="utf-8") as fh:
                prof = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if fn[:-5] == slug or slugify(prof.get("name", "")) == slug:
            print(f"  using existing profile: {fn[:-5]}  ({prof.get('name')})")
            return fn[:-5]

    print(f"\n  no profile for {name!r} yet -- creating one")
    prof = {
        "_comment": "Artist profile. Everything here is data: copy it, change "
                    "the values, and the same pipeline serves another artist.",
        "slug": slug, "name": name,
        "musicbrainz_mbid": None,
        "active_from": "1900-01-01", "active_to": "2100-01-01",
        "sessions_file": f"{slug}_sessions.json",
        "personnel_file": f"{slug}_personnel.json",
        "eras": [], "venues": [], "cities": [], "other_leaders": [],
    }
    if not offline:
        try:
            res = mb_get("artist", {"query": name, "limit": 3})
            for a in res.get("artists", []):
                if a.get("type") not in ("Person", "Group", "Orchestra"):
                    continue
                prof["musicbrainz_mbid"] = a["id"]
                span = a.get("life-span") or {}
                if span.get("begin"):
                    prof["active_from"] = span["begin"][:10]
                if span.get("ended") and span.get("end"):
                    prof["active_to"] = span["end"][:10]
                    prof["active_to_note"] = (
                        f"{a.get('name')} died {span['end'][:10]}; dates after "
                        "this are release or compilation years, not sessions.")
                prof["name"] = a.get("name") or name
                print(f"  MusicBrainz: {a.get('name')}  "
                      f"[{span.get('begin','?')} - {span.get('end','')}]"
                      f"  {a['id']}")
                break
        except Exception as e:  # noqa: BLE001
            print(f"  (MusicBrainz lookup failed: {type(e).__name__}; "
                  f"profile created with placeholder dates)")

    path = os.path.join(ARTISTS_DIR, slug + ".json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(prof, fh, ensure_ascii=False, indent=1)
    print(f"  wrote vocab/artists/{slug}.json")

    for key, seed in (("sessions_file", {"sessions": []}),
                      ("personnel_file", {"lineups": [], "musicians": []})):
        fp = os.path.join(HERE, "vocab", prof[key])
        if not os.path.exists(fp):
            with open(fp, "w", encoding="utf-8") as fh:
                json.dump(seed, fh, ensure_ascii=False, indent=1)
            print(f"  wrote vocab/{prof[key]}  (empty -- fill as you learn)")

    print("\n  The profile drives dating and personnel. Fill in `eras`,")
    print("  `venues` and `other_leaders` as you go; see")
    print("  vocab/artists/coltrane.json for a worked example.")
    return slug


# ----------------------------------------------------------------- status

def cmd_status(args):
    cfg = load_config(required=False)
    if not cfg:
        print("No project here. Run:  python cratedigger.py init")
        return
    lib = cfg.get("library", "")
    out = out_dir(cfg)
    print(f"config   {cfg.get('_path')}")
    print(f"library  {lib}" + ("" if os.path.isdir(lib) else "   [MISSING]"))
    print(f"output   {out}")
    print(f"mode     {cfg.get('mode')}"
          + (f"  ({cfg['artist']})" if cfg.get("artist") else ""))

    if cfg.get("artist"):
        p = os.path.join(ARTISTS_DIR, cfg["artist"] + ".json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                prof = json.load(fh)
            print(f"\nartist   {prof.get('name')}")
            print(f"  active {prof.get('active_from')} -> "
                  f"{prof.get('active_to')}")
            print(f"  mbid   {prof.get('musicbrainz_mbid') or '(none)'}")
            print(f"  eras {len(prof.get('eras', []))}, "
                  f"venues {len(prof.get('venues', []))}, "
                  f"leaders {len(prof.get('other_leaders', []))}")
            for key, label in (("sessions_file", "sessions"),
                               ("personnel_file", "personnel")):
                fp = os.path.join(HERE, "vocab", prof.get(key, ""))
                if os.path.exists(fp):
                    with open(fp, encoding="utf-8") as fh:
                        d = json.load(fh)
                    k = "sessions" if label == "sessions" else "lineups"
                    n = len(d.get(k, []))
                    extra = (f", {len(d.get('musicians', []))} musicians"
                             if label == "personnel" else "")
                    print(f"  {label}: {n} {k}{extra}")

    print("\nbuild state")
    raw = os.path.join(out, "raw_probe.jsonl")
    man = manifest_path(cfg)
    for label, path in (("probe", raw), ("manifest", man),
                        ("views", os.path.join(out, "views")),
                        ("browser", os.path.join(
                            out, "coltrane-browser.html"))):
        if os.path.exists(path):
            if os.path.isdir(path):
                n = sum(len(f) for _r, _d, f in os.walk(path))
                print(f"  {label:9s} {n:,} files")
            else:
                age = (time.time() - os.path.getmtime(path)) / 86400
                print(f"  {label:9s} {os.path.getsize(path)/1024:,.0f} KB"
                      f"   {age:.1f} days old")
        else:
            print(f"  {label:9s} --  not built")

    if os.path.exists(man):
        with open(man, encoding="utf-8") as fh:
            c = json.load(fh).get("counts", {})
        print("\n  " + ", ".join(f"{v:,} {k}" for k, v in c.items()))


# ------------------------------------------------------------------ stages

def cmd_scan(args):
    cfg = load_config()
    out = out_dir(cfg)
    os.makedirs(out, exist_ok=True)
    run("scan.py", ["--root", cfg["library"],
                    "--out", os.path.join(out, "raw_probe.jsonl"),
                    "--workers", str(args.workers)], "probing files")


def cmd_build(args):
    cfg = load_config()
    out = out_dir(cfg)
    raw = os.path.join(out, "raw_probe.jsonl")
    if not os.path.exists(raw):
        sys.exit("no probe yet -- run:  python cratedigger.py scan")
    if cfg.get("mode") == "artist":
        run("coltrane_build.py", ["--raw", raw, "--out", out,
                                  "--root", cfg["library"]], "deriving model")
    else:
        run("build.py", ["--raw", raw, "--out", out,
                         "--root", cfg["library"]], "deriving model")


def cmd_views(args):
    cfg = load_config()
    out = out_dir(cfg)
    man = manifest_path(cfg)
    if not os.path.exists(man):
        sys.exit("no manifest yet -- run:  python cratedigger.py build")
    if cfg.get("mode") == "artist":
        run("coltrane_views.py", ["--manifest", man,
                                  "--out", os.path.join(out, "views"),
                                  "--root", cfg["library"]], "generating views")
    else:
        run("views.py", ["--out", out, "--root", cfg["library"]],
            "generating views")


def cmd_browse(args):
    cfg = load_config()
    out = out_dir(cfg)
    man = manifest_path(cfg)
    if not os.path.exists(man):
        sys.exit("no manifest yet -- run:  python cratedigger.py build")
    if cfg.get("mode") != "artist":
        sys.exit("the browser is currently artist-mode only")
    html = os.path.join(out, "coltrane-browser.html")
    run("coltrane_app.py", ["--manifest", man, "--out", html,
                            "--root", cfg["library"]], "building browser")
    print(f"\n  {html}")
    if args.open:
        try:
            import webbrowser
            webbrowser.open("file:///" + html.replace("\\", "/"))
            print("  opened in your browser")
        except Exception:  # noqa: BLE001
            print("  (could not open automatically -- open it from disk)")


def cmd_audit(args):
    cfg = load_config()
    man = manifest_path(cfg)
    if not os.path.exists(man):
        sys.exit("no manifest yet -- run:  python cratedigger.py build")
    run("coltrane_audit.py", ["--manifest", man, "--root", cfg["library"]])


def cmd_enrich(args):
    cfg = load_config()
    man = manifest_path(cfg)
    if not os.path.exists(man):
        sys.exit("no manifest yet -- run:  python cratedigger.py build")
    src = args.source
    if src in ("musicbrainz", "all"):
        run("coltrane_mb.py", ["--manifest", man, "--limit", str(args.limit)],
            "MusicBrainz")
        run("coltrane_mb.py", ["--manifest", man, "--report"], "MB report")
    if src in ("wild", "all"):
        if cfg.get("artist") != "coltrane":
            print("\n(skipping Wild: that source covers Coltrane only)")
        else:
            run("coltrane_wild.py", ["--fetch"], "David Wild")
            run("coltrane_wild.py", ["--tracks"], "Wild track proposals")
    if src == "all" and cfg.get("artist") == "coltrane":
        run("coltrane_consensus.py", [], "three-way consensus")
    print("\nNothing was applied. Review the CSVs in the output directory,")
    print("or adjudicate in the browser's Reconcile mode.")


def cmd_artists(args):
    os.makedirs(ARTISTS_DIR, exist_ok=True)
    if args.create:
        ensure_profile(args.create, offline=args.offline)
        return
    files = sorted(f for f in os.listdir(ARTISTS_DIR) if f.endswith(".json"))
    if not files:
        print("no artist profiles yet")
        print("  python cratedigger.py artists --create \"Bill Evans\"")
        return
    print(f"{len(files)} artist profile(s) in vocab/artists/\n")
    for fn in files:
        with open(os.path.join(ARTISTS_DIR, fn), encoding="utf-8") as fh:
            p = json.load(fh)
        print(f"  {fn[:-5]:16s} {p.get('name','?'):26s} "
              f"{p.get('active_from','?')} -> {p.get('active_to','?')}")
        print(f"  {'':16s} eras {len(p.get('eras',[]))}, "
              f"venues {len(p.get('venues',[]))}, "
              f"leaders {len(p.get('other_leaders',[]))}"
              f"{'  [mbid]' if p.get('musicbrainz_mbid') else ''}")


def cmd_all(args):
    cmd_scan(args)
    cmd_build(args)
    cmd_views(args)
    cmd_browse(args)
    print("\nDone. Verify with:  python cratedigger.py audit")


# -------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        prog="cratedigger", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("init", help="create or update the project config")
    p.add_argument("--library"), p.add_argument("--output")
    p.add_argument("--artist"), p.add_argument("--mode",
                                               choices=["artist", "library"])
    p.add_argument("--offline", action="store_true",
                   help="skip the MusicBrainz lookup")
    p.set_defaults(fn=cmd_init)

    sub.add_parser("status", help="configuration and build state"
                   ).set_defaults(fn=cmd_status)

    p = sub.add_parser("scan", help="probe every audio file")
    p.add_argument("--workers", type=int, default=12)
    p.set_defaults(fn=cmd_scan)

    sub.add_parser("build", help="derive the manifest").set_defaults(
        fn=cmd_build)
    sub.add_parser("views", help="generate playlists").set_defaults(
        fn=cmd_views)

    p = sub.add_parser("browse", help="build the interactive browser")
    p.add_argument("--open", action="store_true", help="open it when done")
    p.set_defaults(fn=cmd_browse)

    sub.add_parser("audit", help="adversarial data checks").set_defaults(
        fn=cmd_audit)

    p = sub.add_parser("enrich", help="pull session data from a source")
    p.add_argument("--source", choices=["musicbrainz", "wild", "all"],
                   default="musicbrainz")
    p.add_argument("--limit", type=int, default=400)
    p.set_defaults(fn=cmd_enrich)

    p = sub.add_parser("artists", help="list or create artist profiles")
    p.add_argument("--create", metavar="NAME")
    p.add_argument("--offline", action="store_true")
    p.set_defaults(fn=cmd_artists)

    p = sub.add_parser("all", help="scan, build, views, browser")
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--open", action="store_true")
    p.set_defaults(fn=cmd_all)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return 0
    args.fn(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
