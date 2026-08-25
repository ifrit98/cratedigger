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

## Requirements

Python 3.8+ (**standard library only** — nothing to `pip install`) and
**FFmpeg**, for `ffprobe`. Network access is needed only by the two
reconcilers.

```bash
winget install Gyan.FFmpeg          # or: brew install ffmpeg
```

## First run

```bash
python doctor.py --root "D:\Coltrane"
```

Checks Python, FFmpeg, the vocabularies, any existing manifest, and your
archive — then estimates how long a scan will take. It names the install
command for anything missing.

## Coltrane pipeline

```bash
python scan.py --root "D:\Coltrane" --out output-coltrane/raw_probe.jsonl --workers 16
python coltrane_build.py --raw output-coltrane/raw_probe.jsonl --out output-coltrane --root "D:\Coltrane"
python coltrane_views.py --manifest output-coltrane/coltrane.json --out output-coltrane/views --root "D:\Coltrane"
python coltrane_app.py --manifest output-coltrane/coltrane.json --out output-coltrane/coltrane-browser.html --root "D:\Coltrane"
```

The scan takes ~5 minutes for 3,400 files; everything downstream is seconds.
Re-run `build` and the generators freely after editing any vocabulary.

**Open `output-coltrane/coltrane-browser.html` straight from disk.** It is the
main way in: the whole ontology in one file, filtering on every axis at once,
tracks playing in place, and a Reconcile mode for adjudicating dates.

## Verifying

```bash
python coltrane_audit.py --manifest output-coltrane/coltrane.json --root "D:\Coltrane"
python tests/test_credits.py
```

The audit is adversarial — it hunts for what is *wrong* and prints examples so
any claim can be checked. It exits with the count of HIGH-severity findings.
Current state: **0 HIGH**, 54 MED, every MED explained in the docs.

## Reconciling dates against external sources

```bash
python coltrane_wild.py --fetch --tracks     # David Wild discography
python coltrane_mb.py                        # MusicBrainz
python coltrane_mb.py --report
python coltrane_consensus.py                 # three-way agreement
```

Then adjudicate in the browser's **Reconcile dates** mode and apply:

```bash
python coltrane_decisions.py --in ~/Downloads/coltrane-date-decisions.json
python coltrane_build.py --raw output-coltrane/raw_probe.jsonl --out output-coltrane --root "D:\Coltrane"
```

Nothing external is ever auto-applied. Every reconciler produces a decision
sheet; a human rules on it; the ruling is stored with its citation.

## Layout

```
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
docs/                   coltrane.md, toolkit.md
tests/                  credits regression suite
output-coltrane/        GENERATED -- gitignored, rebuilt from your files
```

## What is worth backing up

`vocab/` and nothing else. It holds the hand-written discography and personnel
tables, plus the cached MusicBrainz and Wild harvests — roughly forty minutes
of rate-limited fetching and a lot of hand curation. Everything under
`output-coltrane/` rebuilds from your audio in about five minutes.

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
