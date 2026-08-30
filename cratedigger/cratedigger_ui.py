"""Local control panel for cratedigger.

    cratedigger serve

Serves a single page on 127.0.0.1 that does what the CLI does: point at a
library, pick or create an artist profile, run the stages with live output,
and open the browser when it is built.

Why a server rather than a static page like the Coltrane browser: that one
only *reads* embedded data, so a file:// page is enough. This one has to
*run* the pipeline and list directories on your disk, which a page opened
from a file cannot do.

**Binds to 127.0.0.1 only, and executes local commands by design.** Do not
expose it to a network. There is no authentication because there is no
listener beyond this machine.
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cli as cd  # noqa: E402   (the package is on sys.path via the insert above)

AUDIO_EXT = cd.AUDIO_EXT

# ------------------------------------------------------------------- jobs


class Job:
    """One pipeline stage, run in a thread, with pollable output."""

    def __init__(self):
        self.lock = threading.Lock()
        self.lines = []
        self.stage = None
        self.running = False
        self.rc = None
        self.started = None

    def snapshot(self, since=0):
        with self.lock:
            return {"stage": self.stage, "running": self.running,
                    "rc": self.rc, "lines": self.lines[since:],
                    "total": len(self.lines),
                    "elapsed": (time.time() - self.started)
                    if self.started else 0}

    def start(self, stage, argv):
        with self.lock:
            if self.running:
                return False
            self.lines, self.stage, self.running = [], stage, True
            self.rc, self.started = None, time.time()
        threading.Thread(target=self._run, args=(argv,), daemon=True).start()
        return True

    def _log(self, text):
        with self.lock:
            self.lines.append(text.rstrip("\n"))
            if len(self.lines) > 4000:
                del self.lines[:1000]

    def _run(self, argv):
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8",
                       PYTHONUNBUFFERED="1")
            p = subprocess.Popen(
                [sys.executable, "-u"] + argv, cwd=os.getcwd(), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding="utf-8", errors="replace", bufsize=1)
            for line in p.stdout:
                self._log(line)
            p.wait()
            rc = p.returncode
        except Exception as e:  # noqa: BLE001
            self._log(f"!! {type(e).__name__}: {e}")
            rc = 1
        with self.lock:
            self.running, self.rc = False, rc
        self._log(f"\n[finished, exit {rc}]")


JOB = Job()


# -------------------------------------------------------------- filesystem

def list_dir(path):
    """Directories and an audio count, for the folder picker.

    A browser cannot hand a real filesystem path to a page, so the picking
    happens server-side.
    """
    if not path:
        # drive letters on Windows, / elsewhere
        roots = []
        if os.name == "nt":
            for c in "CDEFGHIJKLMNOPQRSTUVWXYZ":
                d = f"{c}:\\"
                if os.path.exists(d):
                    roots.append({"name": d, "path": d, "dir": True})
        else:
            roots.append({"name": "/", "path": "/", "dir": True})
        home = os.path.expanduser("~")
        roots.append({"name": "~ (home)", "path": home, "dir": True})
        return {"path": "", "parent": None, "entries": roots, "audio": 0}

    path = os.path.abspath(path)
    entries, audio = [], 0
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        if e.name in cd.SKIP_DIRS or e.name.startswith("$"):
                            continue
                        entries.append({"name": e.name, "path": e.path,
                                        "dir": True})
                    elif os.path.splitext(e.name)[1].lower() in AUDIO_EXT:
                        audio += 1
                except OSError:
                    continue
    except (OSError, PermissionError) as e:
        return {"path": path, "parent": os.path.dirname(path),
                "entries": [], "audio": 0, "error": str(e)}
    entries.sort(key=lambda x: x["name"].lower())
    parent = os.path.dirname(path.rstrip("\\/"))
    return {"path": path, "parent": parent if parent != path else None,
            "entries": entries[:400], "audio": audio}


def status_payload():
    cfg = cd.load_config(required=False)
    out = cd.out_dir(cfg) if cfg else None
    data = {"config": {k: v for k, v in (cfg or {}).items()
                       if not k.startswith("_")},
            "config_path": (cfg or {}).get("_path"),
            "cwd": os.getcwd(),
            "ffprobe": bool(shutil.which("ffprobe")),
            "artists": [], "profile": None, "build": {}, "library_ok": False}

    lib = (cfg or {}).get("library")
    data["library_ok"] = bool(lib and os.path.isdir(lib))

    if os.path.isdir(cd.ARTISTS_DIR):
        for fn in sorted(os.listdir(cd.ARTISTS_DIR)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(cd.ARTISTS_DIR, fn),
                          encoding="utf-8") as fh:
                    p = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            item = {"slug": fn[:-5], "name": p.get("name"),
                    "from": p.get("active_from"), "to": p.get("active_to"),
                    "mbid": p.get("musicbrainz_mbid"),
                    "eras": len(p.get("eras", [])),
                    "venues": len(p.get("venues", [])),
                    "leaders": len(p.get("other_leaders", []))}
            for key, label in (("sessions_file", "sessions"),
                               ("personnel_file", "personnel")):
                fp = os.path.join(HERE, "vocab", p.get(key, ""))
                item[label] = 0
                if p.get(key) and os.path.exists(fp):
                    try:
                        with open(fp, encoding="utf-8") as fh:
                            d = json.load(fh)
                        item[label] = len(d.get(
                            "sessions" if label == "sessions" else "lineups",
                            []))
                    except (OSError, json.JSONDecodeError):
                        pass
            data["artists"].append(item)
            if (cfg or {}).get("artist") == item["slug"]:
                data["profile"] = item

    if out:
        man = cd.manifest_path(cfg)
        for label, path in (("probe", os.path.join(out, "raw_probe.jsonl")),
                            ("manifest", man),
                            ("views", os.path.join(out, "views")),
                            ("browser", cd.browser_path(cfg))):
            if os.path.exists(path):
                if os.path.isdir(path):
                    n = sum(len(f) for _r, _d, f in os.walk(path))
                    data["build"][label] = {"ok": True, "detail":
                                            f"{n:,} playlists"}
                else:
                    kb = os.path.getsize(path) / 1024
                    age = (time.time() - os.path.getmtime(path)) / 86400
                    data["build"][label] = {
                        "ok": True, "path": path,
                        "detail": f"{kb:,.0f} KB, {age:.1f} d old"}
            else:
                data["build"][label] = {"ok": False, "detail": "not built"}
        if os.path.exists(man):
            try:
                with open(man, encoding="utf-8") as fh:
                    data["counts"] = json.load(fh).get("counts", {})
            except (OSError, json.JSONDecodeError):
                pass
    return data


# ------------------------------------------------------------------ vocab
#
# Editing vocabulary through the panel means an HTTP endpoint that writes
# files, so the name is never trusted. Callers pass a bare filename that must
# appear in the listing this module produced; anything else is refused. There
# is no path joining of user input, which is what makes traversal impossible
# rather than merely unlikely.

def vocab_root():
    return cd.VOCAB_DIR


def vocab_files():
    """{name: absolute path} for every editable vocabulary file."""
    out = {}
    root = vocab_root()
    for sub in ("", "artists"):
        d = os.path.join(root, sub) if sub else root
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json"):
                continue
            full = os.path.join(d, fn)
            if os.path.isfile(full):
                out[(sub + "/" + fn) if sub else fn] = full
    return out


def vocab_list():
    items = []
    for name, full in sorted(vocab_files().items()):
        try:
            size = os.path.getsize(full)
        except OSError:
            continue
        entries = None
        try:
            with open(full, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                for key in ("sessions", "works", "lineups", "conductors",
                            "ensembles", "musicians"):
                    if isinstance(data.get(key), (list, dict)):
                        entries = len(data[key])
                        break
                if entries is None:
                    entries = len(data)
            elif isinstance(data, list):
                entries = len(data)
        except (OSError, ValueError):
            entries = None
        items.append({"name": name, "bytes": size, "entries": entries})
    return items


def vocab_read(name):
    full = vocab_files().get(name)
    if not full:
        return None
    try:
        with open(full, encoding="utf-8", newline="") as fh:
            return fh.read()
    except OSError:
        return None


def vocab_write(name, text):
    """(ok, message). Refuses anything that is not valid JSON."""
    full = vocab_files().get(name)
    if not full:
        return False, "unknown vocabulary file"
    try:
        json.loads(text)
    except ValueError as e:
        return False, "not valid JSON: %s" % e
    # Keep one copy of what was there. Vocabulary is the one thing the
    # pipeline cannot regenerate from your files.
    backup = full + ".bak"
    try:
        if os.path.exists(full) and not os.path.exists(backup):
            with open(full, encoding="utf-8") as src:
                original = src.read()
            with open(backup, "w", encoding="utf-8", newline="") as dst:
                dst.write(original)
        # newline="" writes the text exactly as the browser sent it.
        # Without it Python translates to CRLF on Windows, so every save
        # rewrote a LF file wholesale and produced a diff of the entire
        # vocabulary for a one-line edit.
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    except OSError as e:
        return False, "could not write: %s" % e
    return True, "saved %s" % name


# Every stage is spelled as `-m cratedigger`, not as a path to a script.
# The 3.1 package move deleted cratedigger.py from the repo root, and this
# table still pointed at it -- the panel would have failed on every button.
CD = ["-m", "cratedigger"]

STAGES = {
    "scan":   CD + ["scan"],
    "build":  CD + ["build"],
    "views":  CD + ["views"],
    "browse": CD + ["browse"],
    "audit":  CD + ["audit"],
    "all":    CD + ["all"],
    "enrich-musicbrainz": CD + ["enrich", "--source", "musicbrainz"],
    "enrich-wild":        CD + ["enrich", "--source", "wild"],
    "enrich-all":         CD + ["enrich", "--source", "all"],
    "fingerprint":        CD + ["fingerprint"],
    "fingerprint-lookup": CD + ["fingerprint", "--lookup"],
    "apply-dry":          CD + ["apply"],
    "apply-write":        CD + ["apply", "--write"],
    "apply-tags":         CD + ["apply", "--tags"],
    "duplicates":         CD + ["duplicates"],
    "export":             CD + ["export"],
    # Tag writing is deliberately dry-run only from the panel. Arming a
    # filesystem write behind a button in a web page is exactly the ceremony
    # 3.3 exists to prevent; --write --yes stays a terminal decision.
    "tags-dry":           CD + ["tags"],
    "tags-verify":        CD + ["tags", "--verify"],
    "tags-undo":          CD + ["tags", "--undo"],
    "results":       CD + ["results"],
    "clean-dry":     CD + ["clean", "outputs", "--dry-run"],
    "clean-outputs": CD + ["clean", "outputs", "--yes"],
    "clean-all":     CD + ["clean", "all", "--yes"],
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            return self._send(200, PAGE, "text/html")
        if u.path == "/api/status":
            return self._send(200, json.dumps(status_payload()))
        if u.path == "/api/ls":
            return self._send(200, json.dumps(
                list_dir((q.get("path") or [""])[0])))
        if u.path == "/api/vocab":
            return self._send(200, json.dumps({"files": vocab_list(),
                                               "root": vocab_root()}))
        if u.path == "/api/vocab/get":
            name = (q.get("name") or [""])[0]
            text = vocab_read(name)
            if text is None:
                return self._send(404, json.dumps({"error": "unknown file"}))
            return self._send(200, json.dumps({"name": name, "text": text}))
        if u.path == "/api/job":
            since = int((q.get("since") or ["0"])[0])
            return self._send(200, json.dumps(JOB.snapshot(since)))
        if u.path == "/api/open":
            target = (q.get("path") or [""])[0]
            try:
                if os.path.exists(target):
                    if os.name == "nt":
                        os.startfile(target)  # noqa: S606
                    else:
                        subprocess.Popen(["open" if sys.platform == "darwin"
                                          else "xdg-open", target])
                    return self._send(200, json.dumps({"ok": True}))
            except Exception as e:  # noqa: BLE001
                return self._send(200, json.dumps({"ok": False,
                                                   "error": str(e)}))
            return self._send(200, json.dumps({"ok": False,
                                               "error": "not found"}))
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            body = {}

        if u.path == "/api/init":
            argv = CD + ["init",
                    "--library", body.get("library", "")]
            if body.get("output"):
                argv += ["--output", body["output"]]
            if body.get("artist"):
                argv += ["--artist", body["artist"]]
            if body.get("mode"):
                argv += ["--mode", body["mode"]]
            if body.get("offline"):
                argv += ["--offline"]
            ok = JOB.start("init", argv)
            return self._send(200, json.dumps({"started": ok}))

        if u.path == "/api/artist":
            argv = CD + ["artists", "--create",
                    body.get("name", "")]
            if body.get("offline"):
                argv += ["--offline"]
            ok = JOB.start("create artist", argv)
            return self._send(200, json.dumps({"started": ok}))

        if u.path == "/api/select-artist":
            cfg = cd.load_config(required=False)
            if not cfg:
                return self._send(200, json.dumps(
                    {"ok": False, "error": "no project yet"}))
            cfg["artist"] = body.get("slug")
            cfg["mode"] = "artist"
            cd.save_config(cfg, cfg.get("_path"))
            return self._send(200, json.dumps({"ok": True}))

        if u.path == "/api/vocab/save":
            ok, msg = vocab_write(body.get("name", ""), body.get("text", ""))
            return self._send(200 if ok else 400,
                              json.dumps({"ok": ok, "message": msg}))
        if u.path == "/api/run":
            stage = body.get("stage")
            if stage not in STAGES:
                return self._send(400, json.dumps({"error": "unknown stage"}))
            # STAGES now holds ["-m", "cratedigger", ...]; joining the
            # first element with HERE turned "-m" into a nonexistent
            # path and every stage failed to start.
            argv = list(STAGES[stage])
            if stage == "scan" and body.get("workers"):
                argv += ["--workers", str(int(body["workers"]))]
            ok = JOB.start(stage, argv)
            return self._send(200, json.dumps({"started": ok}))

        return self._send(404, json.dumps({"error": "not found"}))


def serve(port=8420, open_browser=True):
    os.chdir(os.getcwd())
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"cratedigger control panel  ->  {url}")
    print("  bound to localhost only; it runs local commands by design")
    print("  Ctrl-C to stop")
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()


PAGE = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>cratedigger</title><style>
:root{--bg:#faf8f5;--panel:#fff;--ink:#1a1714;--muted:#6b625a;--line:#e3ddd4;
 --accent:#9c4221;--accent-soft:#f4e6de;--ok:#2f7d4f;--warn:#a8763e;
 --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){
 --bg:#16130f;--panel:#1f1b16;--ink:#f0e9e0;--muted:#a2968a;--line:#332c24;
 --accent:#e08b5f;--accent-soft:#2e2119;--ok:#7fbf95;--warn:#d4a45f}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:16px 22px;border-bottom:1px solid var(--line);display:flex;
 gap:14px;align-items:baseline;flex-wrap:wrap}
h1{font-size:19px;margin:0}h1 span{color:var(--muted);font-weight:400}
.sub{color:var(--muted);font-size:13px;font-family:var(--mono)}
main{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:0;
 height:calc(100vh - 58px)}
@media(max-width:900px){main{grid-template-columns:1fr;height:auto}}
.col{overflow-y:auto;padding:16px 20px 40px}
.col+.col{border-left:1px solid var(--line)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;
 padding:14px 16px;margin-bottom:14px}
.card h2{font-size:12px;text-transform:uppercase;letter-spacing:.08em;
 color:var(--muted);margin:0 0 10px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.row+.row{margin-top:8px}
button{font:inherit;font-size:13px;padding:7px 12px;border-radius:7px;
 border:1px solid var(--line);background:var(--panel);color:var(--ink);
 cursor:pointer}
button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
button:disabled{opacity:.45;cursor:default}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
button.primary:hover:not(:disabled){opacity:.9;color:#fff}
button.danger{border-color:#c0392b;color:#c0392b}
button.danger:hover:not(:disabled){background:#c0392b;color:#fff}
input,select{font:inherit;font-size:13px;padding:7px 9px;border-radius:7px;
 border:1px solid var(--line);background:var(--bg);color:var(--ink);width:100%}
.grow{flex:1;min-width:140px}
.kv{display:grid;grid-template-columns:auto 1fr;gap:3px 12px;font-size:13px}
.kv b{font-weight:500;color:var(--muted)}
.mono{font-family:var(--mono);font-size:12.5px;word-break:break-all}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;
 background:var(--muted)}
.dot.ok{background:var(--ok)}.dot.no{background:var(--warn)}
.fs{border:1px solid var(--line);border-radius:8px;max-height:230px;
 overflow-y:auto;margin-top:8px}
.fs div{padding:5px 10px;cursor:pointer;font-size:13px;display:flex;gap:8px}
.fs div:hover{background:var(--accent-soft)}
.fs .up{color:var(--muted)}
.fs .cnt{margin-left:auto;font-family:var(--mono);font-size:11px;
 color:var(--muted)}
pre{background:var(--panel);border:1px solid var(--line);border-radius:8px;
 padding:12px;font-family:var(--mono);font-size:12px;white-space:pre-wrap;
 word-break:break-word;max-height:calc(100vh - 220px);overflow-y:auto;
 margin:0}
.pill{font-family:var(--mono);font-size:11px;padding:1px 7px;border-radius:99px;
 border:1px solid currentColor}
.pill.run{color:var(--accent)} .pill.ok{color:var(--ok)}
.pill.err{color:#c0392b}
.hint{color:var(--muted);font-size:12px;margin:8px 0 0}
.art{border:1px solid var(--line);border-radius:8px;padding:8px 10px;
 margin-bottom:6px;font-size:13px;cursor:pointer}
.art:hover{border-color:var(--accent)}
.art.sel{border-color:var(--accent);background:var(--accent-soft)}
.art .m{color:var(--muted);font-family:var(--mono);font-size:11px}
</style></head><body>
<header>
  <h1>cratedigger <span>control panel</span></h1>
  <div class=sub id=sub>loading...</div>
</header>
<main>
 <div class=col>
  <div class=card id=firstrun style="display:none;border-color:var(--accent)">
  </div>
  <div class=card>
    <h2>1 &middot; library</h2>
    <div class=row>
      <input id=lib class=grow placeholder="path to your music folder">
      <button id=pick>Browse...</button>
    </div>
    <div class=fs id=fs style=display:none></div>
    <div class=row>
      <input id=out class=grow placeholder="output folder (e.g. output-coltrane)">
      <button id=doInit class=primary>Set up</button>
    </div>
    <p class=hint id=libhint></p>
  </div>

  <div class=card>
    <h2>2 &middot; artist profile</h2>
    <div id=artists></div>
    <div class=row style=margin-top:8px>
      <input id=newArtist class=grow placeholder="create profile, e.g. Bill Evans">
      <button id=doArtist>Create</button>
    </div>
    <p class=hint>Life dates and MusicBrainz id are fetched automatically.
      Eras, venues and the discography are yours to fill in &mdash; see
      <span class=mono>vocab/artists/coltrane.json</span> for a worked
      example.</p>
  </div>

  <div class=card data-needs-config>
    <h2>3 &middot; run</h2>
    <div class=row>
      <button data-stage=all class=primary>Run everything</button>
      <button data-stage=scan>Scan</button>
      <button data-stage=build>Build</button>
      <button data-stage=views>Views</button>
      <button data-stage=browse>Browser</button>
      <button data-stage=audit>Audit</button>
    </div>
    <div class=row>
      <button data-stage=enrich-musicbrainz>Enrich: MusicBrainz</button>
      <button data-stage=enrich-wild>Enrich: Wild</button>
      <button data-stage=enrich-all>Enrich: all</button>
    </div>
    <div class=row>
      <button data-stage=fingerprint>Fingerprint</button>
      <button data-stage=fingerprint-lookup>Identify (AcoustID)</button>
      <button data-stage=apply-dry>Score findings</button>
      <button data-stage=apply-write>Apply certain ones</button>
    </div>
    <div class=row>
      <button data-stage=duplicates>Duplicates</button>
      <button data-stage=export>Shareable export</button>
    </div>
    <p class=hint>Scanning is the slow stage. Everything after it takes
      seconds, so rebuild freely once the probe exists.</p>
  </div>

  <div class=card data-needs-config>
    <h2>4 &middot; tags</h2>
    <div class=row>
      <button data-stage=apply-tags>Plan tag changes</button>
      <button data-stage=tags-dry>Preview writes</button>
      <button data-stage=tags-verify>Verify</button>
      <button data-stage=tags-undo class=danger>Undo all writes</button>
    </div>
    <p class=hint>This is the only part of cratedigger that changes your
      files, so the panel will not arm it. Preview and undo live here;
      writing is a deliberate terminal command:
      <span class=mono>cratedigger tags --write --yes</span>. Needs
      <span class=mono>mutagen</span>.</p>
  </div>

  <div class=card data-needs-config>
    <h2>5 &middot; vocabulary</h2>
    <div class=row>
      <select id=vocabPick class=grow></select>
      <button id=vocabLoad>Open</button>
    </div>
    <textarea id=vocabText spellcheck=false
      style="display:none;width:100%;min-height:260px;margin-top:8px;
             font-family:var(--mono);font-size:12px;line-height:1.5;
             background:var(--bg);color:var(--ink);
             border:1px solid var(--line);border-radius:6px;padding:10px;
             box-sizing:border-box"></textarea>
    <div class=row id=vocabActions style=display:none>
      <button id=vocabSave class=primary>Save</button>
      <span class=hint id=vocabMsg></span>
    </div>
    <p class=hint>The curated knowledge &mdash; discography, personnel,
      conductors, ensembles. It is the one thing a rebuild cannot regenerate
      from your files, so the first save of any file keeps a
      <span class=mono>.bak</span> beside it. Invalid JSON is refused rather
      than written.</p>
  </div>

  <div class=card data-needs-config>
    <h2>6 &middot; results &amp; teardown</h2>
    <div class=row>
      <button data-stage=results>What was produced</button>
      <button data-stage=clean-dry>Preview teardown</button>
    </div>
    <div class=row>
      <button id=cleanOut class=danger>Remove output</button>
      <button id=cleanAll class=danger>Remove output + probe</button>
    </div>
    <p class=hint>Teardown never touches your music, and never touches
      <span class=mono>vocab/</span> &mdash; the discography, personnel and
      cached harvests survive, and they are the only things a rebuild cannot
      regenerate. Removing the probe means the next build re-scans.</p>
  </div>

  <div class=card>
    <h2>state</h2>
    <div class=kv id=state></div>
    <div class=row style=margin-top:10px>
      <button id=openBrowser>Open the archive browser</button>
      <button id=openOut>Open output folder</button>
    </div>
  </div>
 </div>

 <div class=col>
   <div class=row style=margin-bottom:8px>
     <strong id=jobname>output</strong>
     <span id=jobpill></span>
     <span class=sub id=jobtime></span>
   </div>
   <pre id=log>Nothing has run yet.

Pick a music folder on the left, choose or create an artist profile,
then press Run everything.</pre>
 </div>
</main>
<script>
const $=s=>document.querySelector(s);
let seen=0, running=false, ST={};

async function api(p,o){const r=await fetch(p,o);return r.json();}

function fmtCounts(c){return c?Object.entries(c)
  .map(([k,v])=>`${v.toLocaleString()} ${k}`).join(' \u00b7 '):'';}

async function refresh(){
  ST=await api('/api/status');
  const cfg=ST.config||{};
  $('#sub').textContent =
    (cfg.library? cfg.library : 'no project yet')
    + (ST.ffprobe?'':'   [ffprobe missing]');
  if(cfg.library && !$('#lib').value) $('#lib').value=cfg.library;
  if(cfg.output && !$('#out').value) $('#out').value=cfg.output;
  $('#libhint').textContent = cfg.library
    ? (ST.library_ok?'':'that folder is not reachable right now')
    : 'Nothing is written into your music folder \u2014 output goes elsewhere.';

  const a=$('#artists'); a.innerHTML='';
  (ST.artists||[]).forEach(p=>{
    const d=document.createElement('div');
    d.className='art'+(cfg.artist===p.slug?' sel':'');
    d.innerHTML=`<div><b>${p.name||p.slug}</b></div>
      <div class=m>${p.from||'?'} \u2192 ${p.to||'?'} \u00b7
      ${p.eras} eras \u00b7 ${p.venues} venues \u00b7
      ${p.sessions||0} sessions${p.mbid?' \u00b7 mbid':''}</div>`;
    d.onclick=async()=>{await api('/api/select-artist',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({slug:p.slug})}); refresh();};
    a.appendChild(d);
  });
  if(!(ST.artists||[]).length) a.innerHTML=
    '<p class=hint>No profiles yet. Create one below.</p>';

  wizard();
  const s=$('#state'); s.innerHTML='';
  const add=(k,v,ok)=>{s.innerHTML+=
    `<b>${k}</b><span><span class="dot ${ok===undefined?'':ok?'ok':'no'}">
     </span> ${v}</span>`;};
  add('ffprobe', ST.ffprobe?'found':'missing \u2014 scanning needs it',
      ST.ffprobe);
  ['probe','manifest','views','browser'].forEach(k=>{
    const b=(ST.build||{})[k]; if(b) add(k,b.detail,b.ok);
  });
  if(ST.counts) add('contents', fmtCounts(ST.counts), true);
}

async function poll(){
  const j=await api('/api/job?since='+seen);
  if(j.lines&&j.lines.length){
    const log=$('#log');
    if(seen===0) log.textContent='';
    log.textContent+=j.lines.join('\n')+'\n';
    log.scrollTop=log.scrollHeight;
    seen=j.total;
  }
  if(j.stage) $('#jobname').textContent=j.stage;
  $('#jobtime').textContent=j.elapsed?`${j.elapsed.toFixed(0)}s`:'';
  const p=$('#jobpill');
  p.className='pill '+(j.running?'run':(j.rc===0?'ok':(j.rc===null?'':'err')));
  p.textContent=j.running?'running':(j.rc===null?'':(j.rc===0?'done':'failed'));
  if(running&&!j.running){ running=false; refresh(); }
  running=j.running;
  document.querySelectorAll('button[data-stage]').forEach(b=>
    b.disabled=j.running);
  ['#doInit','#doArtist','#cleanOut','#cleanAll'].forEach(id=>{
    const el=$(id); if(el) el.disabled=j.running;});
}

async function start(stage){
  seen=0; $('#log').textContent='';
  await api('/api/run',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({stage})});
  running=true; poll();
}
document.querySelectorAll('button[data-stage]').forEach(b=>
  b.onclick=()=>start(b.dataset.stage));

// Destructive actions confirm first, and say exactly what survives.
$('#cleanOut').onclick=()=>{
  if(confirm('Remove generated output?\n\nManifest, playlists, browser and '
    +'reports go. The raw probe stays, so rebuilding takes seconds.\n\n'
    +'Your music and vocab/ are untouched.')) start('clean-outputs');};
$('#cleanAll').onclick=()=>{
  if(confirm('Remove output AND the raw probe?\n\nThe next build will need '
    +'a full re-scan of your library, which takes minutes.\n\n'
    +'Your music and vocab/ are untouched.')) start('clean-all');};

$('#doInit').onclick=async()=>{
  const library=$('#lib').value.trim();
  if(!library){ alert('Pick a music folder first.'); return; }
  seen=0; $('#log').textContent='';
  await api('/api/init',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({library,output:$('#out').value.trim()})});
  running=true; poll();
};
$('#doArtist').onclick=async()=>{
  const name=$('#newArtist').value.trim();
  if(!name) return;
  seen=0; $('#log').textContent='';
  await api('/api/artist',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name})});
  $('#newArtist').value=''; running=true; poll();
};

// ---- server-side folder picker: a page cannot read a real path itself
let fsOpen=false;
$('#pick').onclick=()=>{ fsOpen=!fsOpen;
  $('#fs').style.display=fsOpen?'block':'none';
  if(fsOpen) browse($('#lib').value.trim()||''); };
async function browse(path){
  const d=await api('/api/ls?path='+encodeURIComponent(path));
  const fs=$('#fs'); fs.innerHTML='';
  if(d.parent!==null&&d.path){
    const up=document.createElement('div'); up.className='up';
    up.textContent='\u2191 up'; up.onclick=()=>browse(d.parent); fs.appendChild(up);
  }
  if(d.path){
    const use=document.createElement('div');
    use.innerHTML=`<b>\u2713 use this folder</b>`
      +`<span class=cnt>${d.audio} audio here</span>`;
    use.onclick=()=>{ $('#lib').value=d.path; fsOpen=false;
      $('#fs').style.display='none'; };
    fs.appendChild(use);
  }
  (d.entries||[]).forEach(e=>{
    const el=document.createElement('div');
    el.textContent=(e.path.endsWith('\\')||e.path==='/')?e.name:'\u{1F4C1} '+e.name;
    el.onclick=()=>browse(e.path); fs.appendChild(el);
  });
  if(d.error) fs.innerHTML+=`<div class=up>${d.error}</div>`;
}

$('#openBrowser').onclick=()=>{
  const b=(ST.build||{}).browser;
  if(b&&b.ok&&b.path) api('/api/open?path='+encodeURIComponent(b.path));
  else alert('Build the browser first (press Browser, or Run everything).');
};
$('#openOut').onclick=()=>{
  const m=(ST.build||{}).manifest;
  const p=(m&&m.path)?m.path.replace(/[\\\/][^\\\/]+$/,''):'';
  if(p) api('/api/open?path='+encodeURIComponent(p));
  else alert('Nothing built yet.');
};


// ---------------------------------------------------------------- vocabulary
let vocabName = null;

async function loadVocabList(){
  const v = await api('/api/vocab');
  const sel = $('#vocabPick');
  sel.innerHTML = '';
  (v.files||[]).forEach(f=>{
    const o = document.createElement('option');
    o.value = f.name;
    const kb = (f.bytes/1024).toFixed(0);
    o.textContent = f.name + '  (' +
      (f.entries!==null&&f.entries!==undefined ? f.entries+' entries, ' : '') +
      kb + ' KB)';
    sel.appendChild(o);
  });
  if(!(v.files||[]).length){
    const o=document.createElement('option');
    o.textContent='no vocabulary files'; sel.appendChild(o);
  }
}

$('#vocabLoad').onclick = async()=>{
  const name = $('#vocabPick').value;
  if(!name) return;
  const r = await api('/api/vocab/get?name='+encodeURIComponent(name));
  if(r.error){ $('#vocabMsg').textContent = r.error; return; }
  vocabName = r.name;
  const t = $('#vocabText');
  t.value = r.text;
  t.style.display = 'block';
  $('#vocabActions').style.display = 'flex';
  $('#vocabMsg').textContent = '';
};

$('#vocabSave').onclick = async()=>{
  if(!vocabName) return;
  const msg = $('#vocabMsg');
  // Validate here as well as on the server, so a typo is caught before a
  // request rather than after one.
  try { JSON.parse($('#vocabText').value); }
  catch(e){ msg.textContent = 'not valid JSON: ' + e.message; return; }
  msg.textContent = 'saving...';
  const r = await api('/api/vocab/save', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name: vocabName, text: $('#vocabText').value})});
  msg.textContent = r.message || (r.ok ? 'saved' : 'failed');
  if(r.ok) loadVocabList();
};

// ------------------------------------------------------------- first run
// With no config there is nothing to run and every button below is a dead
// end, so the panel says what to do first instead of showing a wall of
// disabled controls.
function wizard(){
  const configured = !!(ST.config && ST.config.library);
  document.querySelectorAll('[data-needs-config]').forEach(el=>{
    el.style.opacity = configured ? '' : '0.45';
    el.style.pointerEvents = configured ? '' : 'none';
  });
  const banner = $('#firstrun');
  if(!banner) return;
  if(configured){ banner.style.display='none'; return; }
  banner.style.display = 'block';
  banner.innerHTML =
    '<b>Nothing is configured yet.</b> Point step 1 at a music folder and '
    + 'press <b>Set up</b>. That writes a small <span class=mono>'
    + 'cratedigger.json</span> and every other step reads it &mdash; you '
    + 'will not have to repeat the path.';
}

refresh(); poll(); loadVocabList();
setInterval(poll,900);
setInterval(()=>{ if(!running) refresh(); },5000);
</script></body></html>
"""


if __name__ == "__main__":
    serve()
