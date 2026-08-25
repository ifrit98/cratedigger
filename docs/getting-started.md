# Getting started

From nothing to a browsable archive. Two routes — a control panel, or the
terminal. They do the same work.

## 1. Install

**Python 3.8+.** Check with `python --version`. There is nothing to
`pip install`; the toolkit is standard library only.

**FFmpeg**, for `ffprobe`. Only the scan needs it — the panel, playlists and
browser all work without.

| | |
|---|---|
| Windows | `winget install Gyan.FFmpeg` |
| macOS | `brew install ffmpeg` |
| Debian/Ubuntu | `sudo apt install ffmpeg` |
| Fedora | `sudo dnf install ffmpeg` |

Reopen your terminal afterwards so `PATH` picks it up, then:

```bash
ffprobe -version
```

**Get the toolkit:**

```bash
git clone https://github.com/ifrit98/cratedigger
cd cratedigger
```

**Check everything:**

```bash
python doctor.py
```

Every line is `ok`, `warn` or `FAIL`. A `FAIL` blocks the pipeline and names
the fix. A `warn` is informational — no network only disables the enrichers.

## 2. Point it at your music

### The panel

```bash
python cratedigger.py serve
```

Opens `127.0.0.1:8420`. Press **Browse...**, walk to your music folder — the
audio count for each folder is shown as you go — and click **use this
folder**. Then **Set up**.

### The terminal

```bash
python cratedigger.py init --library "D:\Music"
```

Either way it surveys the folder, reports what it found, estimates the scan
time, and writes `cratedigger.json` so nothing afterwards needs paths again.

> **Your music is never written to.** Not now, not by any later command.
> Everything produced goes to the output directory.

## 3. Pick an artist, if it is one artist

For a single-artist archive, the session-centric model is the right one:

```bash
python cratedigger.py artists --create "Bill Evans"
```

MusicBrainz supplies the id and life dates; the eras, venues and discography
are yours to fill in as you learn them. `vocab/artists/coltrane.json` is the
worked example.

For a mixed library, skip this — it runs in general mode, which is
composition-centric. See [toolkit.md](toolkit.md).

## 4. Run it

```bash
python cratedigger.py all
```

Or press **Run everything** in the panel. Four stages:

| stage | what it does | how long |
|---|---|---|
| scan | `ffprobe` every file | ~750 files/min |
| build | derive the manifest | seconds |
| views | generate playlists | seconds |
| browse | build the browser | seconds |

Only the scan is slow, and it only needs redoing when files change.
Everything downstream rebuilds in seconds, so iterate freely.

## 5. Look at what you got

```bash
python cratedigger.py results
```

Lists every artifact with its size and what it is for. The one to open first
is the browser:

```
output-coltrane/coltrane-browser.html
```

Open it from disk. No server. See [outputs.md](outputs.md) for what
everything else is.

## 6. Check it is right

```bash
python tests/run_tests.py
```

130 cases across five suites — date parsing, discography lookup, personnel,
tune normalisation and incremental scan. Stdlib only; nothing to install.


```bash
python cratedigger.py audit
```

Adversarial by design: it hunts for what is *wrong* and prints examples so
you can check any claim. HIGH findings are structural — impossible dates,
missing files, orphaned records. It exits with that count.

## A first session, end to end

```bash
python doctor.py
python cratedigger.py init --library "D:\Coltrane" --artist "John Coltrane"
python cratedigger.py all
python cratedigger.py results
python cratedigger.py audit
```

## Where things live

```
cratedigger.json      your project: library path, output dir, artist
vocab/                curated knowledge -- back this up
output-*/             everything generated -- disposable
```

Only `vocab/` is irreplaceable. See [teardown.md](teardown.md).
