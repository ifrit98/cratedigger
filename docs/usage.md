# Usage

Every command, every flag, and the workflows they combine into.

Two routes do the same work: a control panel, or the terminal. Pick either;
they share the same config and can be mixed freely.

```bash
cratedigger serve       # panel at 127.0.0.1:8420
cratedigger --help      # the commands below
```

---

## Commands

### Setting up

| | |
|---|---|
| `init` | point at a library; writes `cratedigger.json` |
| `status` | config, artist profile, vocabulary, build state |
| `artists` | list artist profiles |
| `artists --create NAME` | create one, fetching id and life dates from MusicBrainz |

```bash
cratedigger init --library "D:\Music" --artist "Bill Evans"
```

| flag | |
|---|---|
| `--library PATH` | the music folder. Prompted for if a terminal is attached |
| `--output DIR` | where results go. Defaults to `output-<artist>` |
| `--artist NAME` | switches to session-centric mode and bootstraps a profile |
| `--mode artist\|library` | force the model. Otherwise inferred from size |
| `--offline` | skip the MusicBrainz lookup |

### Running

| | |
|---|---|
| `all` | scan → build → views → browse |
| `scan` | probe every file. **The slow stage** (~750 files/min) |
| `build` | derive the manifest. Seconds |
| `views` | generate playlists. Seconds |
| `browse` | build the interactive browser |
| `audit` | adversarial data checks; exits with the HIGH count |

```bash
cratedigger scan --workers 16
cratedigger browse --open
```

`--workers` defaults to 12. Raise it on an SSD; **lower** it on a spinning
disk or network share, where seek contention makes more threads slower.

**Scanning is incremental.** A file whose path, size and mtime are unchanged
is reused from the previous probe rather than re-read, so a rescan after
adding a few albums takes seconds rather than minutes. Reuse is refused
whenever it cannot be proved safe — a different root, a corrupt index.

| flag | |
|---|---|
| `--full` | re-probe everything, ignoring the previous scan |
| `--retry-errors` | re-probe only the files that failed last time |

### Enriching

| | |
|---|---|
| `enrich --source musicbrainz` | session dates, venues and credits from MusicBrainz |
| `enrich --source wild` | David Wild's discography (Coltrane only) |
| `enrich --source all` | both, then the three-way consensus |

**Nothing is ever auto-applied.** Each produces a decision sheet; you rule on
it in the browser's Reconcile mode; the ruling is stored with its citation.
See [coltrane.md](coltrane.md).

### Looking and cleaning

| | |
|---|---|
| `results` | every artifact, its size, and what it is for |
| `clean [what]` | remove generated output. `--dry-run`, `--yes` |
| `serve` | the control panel. `--port`, `--no-open` |

`clean` targets: `views`, `browser`, `reports`, `manifest`, `probe`,
`outputs` (default — keeps the probe), `all`.

---

## Workflows

### First run

```bash
python doctor.py
cratedigger init --library "D:\Coltrane" --artist "John Coltrane"
cratedigger all
cratedigger results
cratedigger audit
```

### You added music

Re-scan, then everything downstream. Only the new files are probed:

```bash
cratedigger all
```

### You changed the model or a vocabulary

No re-scan needed — the probe is unchanged:

```bash
cratedigger build && cratedigger views && cratedigger browse
```

This is the loop to iterate in. It costs seconds, so edit
`vocab/*_sessions.json` freely and watch the coverage numbers move.

### Reconciling dates

```bash
cratedigger enrich --source all
```

Then open the browser, switch to **Reconcile dates**, adjudicate, Export, and:

```bash
python coltrane_decisions.py --in ~/Downloads/coltrane-date-decisions.json
cratedigger build
```

Decisions become the highest-precedence source, above folder names, the
discography and tags.

### Two libraries side by side

Give each its own output directory. Run commands from the directory holding
that project's `cratedigger.json`, or re-run `init` to switch:

```bash
cratedigger init --library "D:\Coltrane" --output out-coltrane --artist "John Coltrane"
cratedigger all

cratedigger init --library "L:\Music" --output out-library --mode library
cratedigger all
```

### Starting over

```bash
cratedigger clean all --yes
cratedigger all
```

---

## Scripting

Commands exit non-zero on failure, so they chain:

```bash
cratedigger build && cratedigger views
```

`audit` exits with its **HIGH finding count**, which makes it a usable gate:

```bash
cratedigger audit || echo "structural problems found"
```

Prompts are skipped when stdin is not a terminal. `clean` **cancels** rather
than proceeding in that case — pass `--yes` if a script genuinely means it.

`CRATEDIGGER_ARTIST` overrides the active profile for one invocation:

```bash
CRATEDIGGER_ARTIST=bill-evans cratedigger build
```

---

## Running the stages by hand

`cratedigger.py` is a convenience wrapper. Every stage is a standalone script
that takes explicit paths, which is what you want for odd layouts or one-off
experiments:

```bash
python scan.py --root "D:\Coltrane" --out out/raw_probe.jsonl --workers 16
python coltrane_build.py --raw out/raw_probe.jsonl --out out --root "D:\Coltrane"
python coltrane_views.py --manifest out/coltrane.json --out out/views --root "D:\Coltrane"
python coltrane_app.py --manifest out/coltrane.json --out out/browser.html --root "D:\Coltrane"
```

Each takes `--help`. [toolkit.md](toolkit.md) documents the general
composition-centric pipeline, which has its own `organize.py` runner and a
fast playlist path needing no scan at all.
