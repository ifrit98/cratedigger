# Reading the output

What every command prints, what every file is for, and which one to open
first.

```bash
python cratedigger.py results
```

Lists what exists, with sizes and a one-line explanation of each.

## Open this first

```
output-*/coltrane-browser.html
```

One self-contained file, opened from disk. The whole ontology: timeline,
track list, tune index, nine cross-filtering facets, search, `.m3u8` export,
and a Reconcile mode for adjudicating dates. Tracks play in place.

Everything below is the same data in other shapes, for when you want a
spreadsheet or a playlist instead.

## The manifest

| file | |
|---|---|
| `coltrane.json` | the authoritative record: sessions, tunes, releases, tracks, with every facet and its provenance |
| `raw_probe.jsonl` | one line per file, straight from `ffprobe`. **The expensive artifact** — keep it and every rebuild is seconds |

Field-by-field detail is in [coltrane.md](coltrane.md) and
[toolkit.md](toolkit.md).

## Spreadsheets

Open in Excel, Numbers, or `pandas`. All UTF-8 with a BOM so Excel gets the
encoding right.

| file | one row per | reach for it when |
|---|---|---|
| `tracks.csv` | audio file | you want to filter on anything — date, era, lineup, venue, provenance, format |
| `chronology.csv` | release, date-ordered | you want the career as a spreadsheet |
| `sessions.csv` | session | you want dates, venues, lineups and what was played |
| `tunes.csv` | tune | you want version counts and first/last recorded |
| `duplicates.csv` | duplicate cluster | you are reclaiming disk (general mode) |
| `projection_flat.csv` | track | you are considering retagging for a simple player |

### Reconciliation reports

| file | |
|---|---|
| `date_consensus.csv` | **start here.** Every release graded `adopt` / `contested` / `single-source` / `confirmed` / `unsourced`. Sort by verdict: `adopt` is where two sources agree and we differ, `contested` is where the sources disagree and a person must rule |
| `mb_conflicts.csv` | where MusicBrainz disagrees, with MBID citations |
| `wild_reconciliation.csv` | where David Wild disagrees, with session numbers |
| `wild_track_proposals.csv` | per-track session candidates and their confidence |

**Nothing in these is applied.** They are decision sheets. Adjudicate in the
browser's Reconcile mode, then:

```bash
python coltrane_decisions.py --in ~/Downloads/coltrane-date-decisions.json
```

## Playlists

`output-*/views/`, one directory per facet. Plain UTF-8 M3U8 with `#EXTINF`,
so foobar2000, VLC, MusicBee, Kodi and most DAPs read them.

| facet | |
|---|---|
| `by-date/` | one playlist per session date, named to sort chronologically. Plus `_years/` rollups and `_ALL - complete chronology.m3u8` |
| `by-release/` | the album spine, year-prefixed |
| `by-tune/` | every version of a tune, oldest first |
| `by-lineup/`, `by-personnel/` | a band's whole output; everyone who played |
| `by-era/`, `by-venue/`, `by-provenance/`, `by-authority/`, `by-role/`, `by-format/` | the remaining axes |

Load them with **File → Load Playlist**, or drag them in. Multi-select opens
each as its own tab.

> Playlists named `_review ...` are cases the tooling flagged as uncertain —
> an ambiguous conductor, a contested date. They are honest uncertainty, not
> errors.

## What the commands print

**`status`** — config, artist profile with vocabulary sizes, and build state
with file ages. The quickest "where am I".

**`results`** — every artifact, its size, and what it is for.

**`audit`** — findings by severity, with examples:

```
[HIGH]  dates outside the artist's life: 0
[MED ]! junk tune titles: 20  -- unnamed track titles becoming pseudo-tunes
```

`HIGH` is structural and should be zero. `MED` is worth understanding but
usually explainable — the current ones are catalogued in
[coltrane.md](coltrane.md). Exit code is the HIGH count, so it works in a
script.

**`scan`** — a progress line every 250 files, then a count of any that failed
to probe. Failures are normal and categorised: macOS `._*` junk and
WavPack-compressed SACD images are handled, not lost.

**`build`** — counts, then coverage per field, then the facet distributions.
Read the coverage lines per genre, not library-wide: composer and conductor
legitimately do not apply to jazz, so adding jazz dilutes the overall number
while the classical figures are unchanged.

**`enrich`** — what each source returned and how it compares. Never applies
anything.

## In the panel

The right-hand pane streams the same text live, with elapsed time and an exit
status. **What was produced** runs `results` into it. Buttons at the bottom
open the browser or the output folder in your file manager.
