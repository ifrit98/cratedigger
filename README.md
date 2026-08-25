# cratedigger

*Finding the order in a pile of records.*

Builds queryable metadata ontologies for music collections, then projects them
into things you can actually use: playlists, spreadsheets, and a
self-contained interactive browser.

A folder tree has exactly one dimension. Real collections have five — composer,
rating, quality tier, provenance, chronology — so this stops trying to encode
them as directories and makes the metadata authoritative instead. Every
hierarchy, including your existing folders, becomes a generated view.

**Read-only with respect to your music.** Nothing is moved, renamed or
retagged. Everything produced goes to a separate output directory, and the
audit verifies every path before claiming anything.

Two projects share the codebase:

| | |
|---|---|
| **Coltrane archive** | a single-artist, session-centric ontology reconciled against David Wild's discography and MusicBrainz. Complete — see [docs/coltrane.md](docs/coltrane.md). |
| **General library** | a genre-agnostic, composition-centric pipeline for mixed collections. Working; see [docs/toolkit.md](docs/toolkit.md). |

---

## Install

**Standard library only** — nothing to `pip install`, no virtualenv, no
services. Three things, one of them optional:

| | needed for | required? |
|---|---|---|
| Python 3.8+ | everything | yes |
| FFmpeg (`ffprobe`) | reading tags from your files | for `scan` only |
| Network | the MusicBrainz and Wild enrichers | optional |

```bash
winget install Gyan.FFmpeg     # Windows
brew install ffmpeg            # macOS
sudo apt install ffmpeg        # Debian/Ubuntu
```

Reopen your terminal so `PATH` updates, then:

```bash
git clone https://github.com/ifrit98/cratedigger
cd cratedigger
python doctor.py
```

`doctor.py` checks Python, FFmpeg and the vocabularies, and names the fix for
anything missing. Add `--root "D:\Music"` and it also sizes the scan.

FFmpeg is only needed by `scan` — the panel, the model, the playlists and the
browser all work without it, so you can look around first and install it
later.

→ **[docs/install.md](docs/install.md)** — per-platform detail, PATH
problems, the Windows Store Python stub, working offline, upgrading,
uninstalling.

## Usage

Two routes, same work, freely mixed.

### The panel

```bash
python cratedigger.py serve
```

A local control panel at `127.0.0.1:8420`: browse to your music folder, pick
or create an artist profile, run any stage with live output, see what was
produced, and tear it down again. Bound to localhost only.

→ **[docs/panel.md](docs/panel.md)**

### The terminal

```bash
python cratedigger.py init --library "D:\Music" --artist "John Coltrane"
python cratedigger.py all
```

`init` surveys the folder, estimates the scan, and writes `cratedigger.json`
so nothing afterwards needs paths again. `all` runs scan → build → views →
browser.

| command | |
|---|---|
| `init` | point at a library; writes the project config |
| `status` | config, artist profile, vocabulary, build state |
| `all` | scan → build → views → browse |
| `scan` `build` `views` `browse` | the stages individually |
| `audit` | adversarial data checks; exits with the HIGH count |
| `enrich` | pull session data from MusicBrainz or Wild |
| `artists` | list or create artist profiles |
| `results` | what was produced, where, and what each file is for |
| `clean` | remove generated output; never your music or `vocab/` |
| `serve` | the control panel |

Only `scan` is slow (~750 files/min). Everything downstream rebuilds in
seconds, so the loop to iterate in is:

```bash
python cratedigger.py build && python cratedigger.py views
```

→ **[docs/usage.md](docs/usage.md)** — every flag, plus workflows for adding
music, reconciling dates, running two libraries side by side, scripting, and
calling the stages by hand.

### Then look at it

```bash
python cratedigger.py results
```

Lists every artifact with its size and purpose, ending at the one to open
first — `output-*/coltrane-browser.html`, a single self-contained file with
the whole ontology in it.

→ **[docs/outputs.md](docs/outputs.md)** — what every file and every command
output means.

### And clean up

```bash
python cratedigger.py clean --dry-run
```

**Your music is never touched, and `vocab/` is never touched** at any level —
the discography, personnel and cached harvests are the only things a rebuild
cannot regenerate.

→ **[docs/teardown.md](docs/teardown.md)**

## Using it for a different artist

Everything artist-specific is **data, not code** — life dates, eras, venues,
sidemen and the discography all live in `vocab/artists/<slug>.json`.

```bash
python cratedigger.py artists --create "Bill Evans"
python cratedigger.py artists
```

That fetches the MusicBrainz id and life span, then seeds empty session and
personnel tables for you to fill. The lifetime clamp, era assignment, venue
detection and MusicBrainz reconciliation all follow the profile from then on.
`vocab/artists/coltrane.json` is the worked example — 10 eras, 17 venues,
31 other leaders.

A loaded profile is authoritative even where a list is empty, so a new artist
never inherits Coltrane's bands.

## Verifying

```bash
python cratedigger.py audit
python tests/run_tests.py
```

The audit is adversarial — it hunts for what is *wrong* and prints examples
so any claim can be checked, exiting with the count of HIGH-severity
findings so it works as a gate in a script.

Current state on the reference archive: **0 HIGH**, 54 MED, with every MED
explained in [coltrane.md](docs/coltrane.md).

## Reconciling dates against external sources

```bash
python cratedigger.py enrich --source all
```

Fetches session data from **MusicBrainz** and **David Wild's discography**,
then grades every release on where the two agree: `adopt` (both agree and we
differ), `contested` (the sources disagree), `confirmed`, `unsourced`.

Adjudicate in the browser's **Reconcile dates** mode, then apply:

```bash
python coltrane_decisions.py --in ~/Downloads/coltrane-date-decisions.json
python cratedigger.py build
```

**Nothing external is ever auto-applied.** Every reconciler produces a
decision sheet; a person rules on it; the ruling is stored with its citation
and outranks every inferred source.

→ **[docs/coltrane.md](docs/coltrane.md)** — the sources, their coverage
gaps, and the matching traps that cost real accuracy before they were
caught.

## Documentation

| doc | |
|---|---|
| [install.md](docs/install.md) | prerequisites, platforms, upgrading, uninstalling |
| [usage.md](docs/usage.md) | every command and flag, plus workflows |
| [getting-started.md](docs/getting-started.md) | the guided first run, end to end |
| [outputs.md](docs/outputs.md) | what every file and command output means |
| [panel.md](docs/panel.md) | the control panel |
| [teardown.md](docs/teardown.md) | what is safe to delete, resetting, uninstalling |
| [troubleshooting.md](docs/troubleshooting.md) | symptom → cause → fix |
| [coltrane.md](docs/coltrane.md) | the Coltrane archive: model, sources, reconciliation |
| [toolkit.md](docs/toolkit.md) | the general mixed-library pipeline |

## Layout

```
cratedigger.py          one CLI: init / status / run stages / serve
cratedigger_ui.py       the local control panel served by `serve`
doctor.py               environment check -- run first
scan.py                 shared: ffprobe every file -> raw_probe.jsonl

coltrane.py             domain layer: dates, eras, personnel, tunes, provenance
coltrane_build.py       -> coltrane.json + chronology/sessions/tunes/tracks CSV
coltrane_views.py       -> 1,113 .m3u8 playlists across 11 splines
coltrane_app.py         -> the interactive browser, one HTML file
coltrane_audit.py       adversarial data checks
coltrane_wild.py        mine + reconcile David Wild's discography
coltrane_mb.py          mine + reconcile MusicBrainz
coltrane_consensus.py   grade agreement between the sources
coltrane_decisions.py   apply browser decisions as date overrides

build.py views.py       general pipeline (composition-centric)
organize.py             general pipeline runner
playlists.py            general fast-path playlists, no scan needed
credits.py              conductor/ensemble recovery from folder paths
mbfetch.py mine.py      grow the credits vocabulary
evalcredits.py          measure credit coverage

vocab/                  curated knowledge -- see LICENSE for provenance
docs/                   coltrane.md, toolkit.md, panel.md
tests/                  credits regression suite
output-coltrane/        GENERATED -- gitignored, rebuilt from your files
```

## What is worth backing up

`vocab/` and nothing else. It holds the hand-written discography and personnel
tables, plus the cached MusicBrainz and Wild harvests — roughly forty minutes
of rate-limited fetching and a lot of hand curation. Everything under
`output-coltrane/` rebuilds from your audio in about five minutes.

## Where this is going

[ROADMAP.md](ROADMAP.md) — an honest read on what this competes with (beets,
Picard, Roon), the wedge it actually has, what blocks the general case today,
and the order to fix it in.

## Design commitments

- **Read-only.** The manifest is the source of truth; every hierarchy,
  including your existing folders, is a generated view.
- **A wrong answer is worse than none.** Extraction declines rather than
  guesses, and anything uncertain carries its confidence level and source.
- **No silent overwrites.** External sources produce decision sheets, never
  direct edits.
- **The album topology is structural.** `release_id` is a hash of the folder
  path, never of a date — so per-track session dates can never fragment the
  album view.

## Data, sources and attribution

No audio is included, redistributed, or referenced by content. The code is
**MIT**. The curated data in `vocab/` has mixed provenance and is not all the
author's to relicense:

**MusicBrainz** — `conductors.json`, `ensembles.json`, `coltrane_mb_cache.json`,
`coltrane_mb_sessions.json`. Core data is released under
[CC0](https://musicbrainz.org/doc/About/Data_License). Fetched politely, at the
documented 1 request/second.

**David Wild** — `coltrane_wild_sessions.json` holds 101 session records
(dates, personnel, locations, tune listings) extracted from the web edition of
David Wild, *The Recordings of John Coltrane: A Discography*, 2nd ed.,
Wildmusic 1979, at [wildmusic-jazz.com](http://www.wildmusic-jazz.com/).

> Wild's discography is the authoritative work on these recordings and this
> project would be guessing without it. Individual facts are not
> copyrightable; the compilation is his. This extract exists to catalogue a
> private collection. **If you use it, credit Wild. If you are doing anything
> commercial, ask him first.** `coltrane_wild.py --fetch` rebuilds it from
> source, so you need not take this copy on trust.

**Hand-written** — `coltrane_sessions.json`, `coltrane_personnel.json`. Written
from general knowledge, then reconciled against the above. Every entry carries
`confidence` and `source` fields recording how far it has actually been
verified. Several were wrong until the reconcilers caught them, and the docs
say which.

See [LICENSE](LICENSE) for the full terms.
