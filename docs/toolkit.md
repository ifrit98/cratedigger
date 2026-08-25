# The general library pipeline

Genre-agnostic, composition-centric. Built for mixed collections where
classical, jazz and rock coexist and no single hierarchy fits all of them.

Distinct from the Coltrane project, which is session-centric — see
[coltrane.md](coltrane.md) for why a jazz archive needs a different spine.

## The problem

A folder tree expresses exactly one hierarchy. A real collection needs
several, and folder names give the strain away:

```
BANGERS/            <- a rating
Classical 24/       <- a technical quality tier
Mozart/             <- a composer
Jazz/               <- a genre
```

Four orthogonal facets stacked into one tree. The consequence is duplication:
to find a recording both by "things I love" and by "Mozart", it has to exist
in both places.

## Entity tiers

```
WORK          the composition -- composer, title, catalogue number
              (K.626, BWV 988, Op.111). Null for most jazz and rock,
              where the recording IS the work.
  |  1:N
RECORDING     one audio file. Performers, conductor, movement position.
  |  N:1
RELEASE       one folder. Label, edition, source medium, rating.
```

Modelling all three and letting `work_id` be null is what lets one schema
cover a mixed library. A plain artist→album→track model breaks on the
composer-centric portion; a work-centric model breaks on everything else.

Field names follow **Vorbis Comment as spoken by MusicBrainz Picard**, which
has defined mappings into FLAC, ID3v2.4 and MP4.

## Running it

```bash
python organize.py --root "E:\Music"
```

| flag | |
|---|---|
| `--root DIR` | **required**, the music directory |
| `--out DIR` | default `<root>/_library/output` |
| `--collection NAME=RATING` | treat a top-level folder as a curated set. Repeatable. Default `BANGERS=5`; `--collection ""` for none. |
| `--skip NAME` | directory to ignore. Repeatable. |
| `--workers N` | probe concurrency, default 12 |
| `--stage scan\|build\|views\|all` | run one stage |

`scan` is the expensive stage (~750 files/min). Once `raw_probe.jsonl` exists,
iterating on the model costs seconds:

```bash
python organize.py --root "E:\Music" --stage build
python organize.py --root "E:\Music" --stage views
```

## The fast path

```bash
python playlists.py --root "E:\Music"
```

No `ffprobe`, no manifest, no tag reading. Walks the tree, applies
`credits.py` to each folder path, writes `.m3u8` files grouped by conductor,
ensemble, composer, genre and format. About 30 seconds for 90,000 files.

| flag | |
|---|---|
| `--min-tracks N` | skip playlists smaller than N. Default 8; **use 4** on a smaller curated drive, where 8 silently drops real material. |
| `--relative` | relative paths, for removable media |

On Windows there is no relative path between `C:` and `E:`. Both writers
detect this and fall back to absolute paths automatically.

## Credits recovery

Almost no file carries a `CONDUCTOR` tag, but folder names usually do:

```
Bruckner 7 VPO Kleiber
Bruckner 5 CSO_Barenboim PCM
01. C.Schuricht, Berlin Philharmonic. 1938
```

`credits.py` reads those back out. Three things make it hold up at scale:

**1. The vocabulary is data, not code.** `vocab/conductors.json` and
`vocab/ensembles.json` hold 2,703 conductors and 1,145 ensembles from
MusicBrainz.

```bash
python mbfetch.py --conductors 2400 --ensembles 1500
python mine.py --root "E:\Music" --verify --apply
python tests/test_credits.py
```

**2. Structural rules need no dictionary.** `ENSEMBLE_Conductor`,
`Conductor, Ensemble`, parentheticals, and truncation repair by unique-prefix
match (`SFS_Blomste` → Blomstedt).

> Underscores are word characters, so `\bCSO\b` never matches inside
> `CSO_Barenboim`. Separators are normalised before matching. That single
> issue accounted for 543 of 701 misses on first measurement.

**3. Precision is defended.** A wrong conductor is worse than a missing one:

- **ensemble gate** — a conductor is asserted only when an ensemble is also
  named, so `Beethoven Piano Sonatas Barenboim` stays a recital
- **guarded names** (299) — composer surnames (`Bach`, `Mahler`), ordinary
  words (`Young`, `King`), common given names (`George`, `Terry`) and all
  four-letter surnames need a forename before they may match
- **forename conflict** — `Clark Terry` will not become conductor Andrew Terry
- **ensemble suffix** — `Hagen Quartet` is an ensemble, not a conductor
- **non-classical skip** — the vocabulary is never consulted for jazz or rock

Every value carries `conductor_source` and `conductor_confidence`
(`high` / `medium` / `prefix` / `structural` / `ambiguous`).

```bash
python evalcredits.py --root "E:\Music"
```

Measured on a 90,000-file library: 10,633 folders processed in 5.4 seconds,
55% of classical folders resolved, 163 distinct conductors, ~1% residual
error concentrated in soloist/conductor confusion.

## Reconciling against MusicBrainz

```bash
python general_mb.py --manifest output/library.json      # fetch
python general_mb.py --manifest output/library.json --report
```

The Works view exposes the fragmentation problem: the same piece titled three
ways in three folders becomes three works, because most orchestral repertoire
has no universally-used catalogue number to key on. A MusicBrainz **work id**
is the stable identity that a catalogue number cannot supply, and it comes
back per-recording:

```
inc=recordings+work-rels+recording-level-rels+labels
```

### Matching on durations, not titles

The artist model matches on title overlap. That does not transfer. Measured
on this manifest, of 314 releases:

- **every** track carries a duration from the probe
- only **87** carry an album artist
- exactly **1** carries a MusicBrainz album id

So titles and artist tags are the weak signal here and durations are the
strong one. A sequence of track lengths is close to unique for a particular
performance, which is exactly the distinction that matters: there are
hundreds of recordings of the Brandenburg Concerti and they differ by title
not at all.

A candidate is accepted when **70% of our tracks** pair to a MusicBrainz
track within **5 seconds**. Rips drift a second or two from the catalogue;
five survives that, and a different performance does not pass.

### Why the hit rate is low, and why that is correct

On first measurement roughly a fifth of releases matched. Most refusals are
the validator working:

```
'BACH - Brandenburg Concerti CD1'   ours=19 tracks
   ratio=0.26  mb_tracks=19   The Brandenburg Concerti
```

Right piece, wrong performance — refused. The alternative is a citation that
points at someone else's recording, which is worse than no citation. The
Coltrane pass learned the same lesson from anthologies.

The genuine recall limit is that MusicBrainz ranks search hits by title
score, and for classical the right performance often does not reach the top
five. Three things push against that:

| technique | effect |
|---|---|
| **title cleaning** | `BACH - Brandenburg Concerti CD1` finds nothing; `Brandenburg Concerti` scores 100. Disc markers, bracketed editions and `24-bit/96kHz` noise are stripped. |
| **`tracks:N` filter** | `release:"Brandenburg Concerti"` returns eight plausible releases; the same query with `AND tracks:19` returns one. A track count is a far stronger filter than a title score. |
| **track-count prefilter** | a 67-track anthology cannot be our 4-track release, and the search result says so before any detail fetch. Cut the budget from ~36 calls per release to under 10. |

### Transient failures are not negative results

MusicBrainz throttles hard, and a throttled request looks exactly like an
empty result unless they are kept apart. On a first measurement, **six of
seven apparent misses were 503s** being cached as "no match" — permanently,
since the cache is never revisited. `get()` now returns `(payload,
transient)`, and a release whose lookup hit a server error is left out of the
cache entirely so the next run retries it.

### Output

| file | |
|---|---|
| `vocab/general_mb_works.json` | work ids and titles, with the releases each appears on |
| `mb_conflicts.csv` | one row per matched release: years, labels, catalogue number, how many durations lined up, MBID |

### A MusicBrainz date is a pressing date

The column is named `mb_pressing_year`, not `year`, because that is what it
is: the release date of *that pressing*. A 1962 performance on a 2001
remaster is not a disagreement, and calling it one invites someone to
overwrite a correct recording year with a reissue date. (The artist
reconciler hit the same trap with `first-release-date`; session facts live in
recording relationships, not on the release.)

So rows are classified rather than scored:

| state | meaning |
|---|---|
| `same year` | agreement |
| `mb pressing later` | a reissue — **expected**, not a conflict |
| `REVIEW mb earlier` | our year is later than the pressing, so ours may itself be a reissue date |
| `unknown` | one side has no year |

Only `REVIEW mb earlier` sorts to the top, because it is the only state that
implies something might actually be wrong. **Nothing is applied** — as
everywhere else in this toolkit, the output is a decision sheet with
citations, not a mutation.

## The browser

```bash
python cratedigger.py browse
```

Writes `library-browser.html` -- one self-contained file, opened from disk.
The same client as the artist archive (see `browser_core.py`), driven by a
different payload.

Its spine is the **work**, not the session: the Works view groups every
recording of a piece together, which for classical is the axis a folder tree
cannot express. Facets are work, composer, genre, conductor, ensemble,
quality, source and label, all cross-filtering with live counts.

## Output

| file | |
|---|---|
| `library.json` | nested manifest — works, releases, tracks |
| `library.csv` | one row per track, denormalized |
| `works.csv` | work index with recording counts |
| `duplicates.csv` | clusters by confidence and reclaimable bytes |
| `projection_flat.csv` | flattened tags for simple players — proposed only |
| `views/` | `.m3u8` per facet, including `works-multiple-recordings/` |

`works-multiple-recordings/` is the payoff: every performance of one piece
side by side, regardless of which folder each sits in.

## Projection for simple players

Most DAPs and car head units read only title/artist/album/albumartist/
genre/track/disc. They ignore `WORK` and `MOVEMENT`, so an unprojected
symphony appears as eight fragments called `I. Adagio`.

`projection_flat.csv` folds work into `ALBUM` and movement into `TITLE`, with
`current_*` and `flat_*` columns side by side. **Nothing is written** — it is
a reviewable proposal.

## Known limits

- **Container releases** — `.cue` + image rips and SACD `.iso` have no
  per-track files, so they carry release-level metadata only and cannot appear
  in playlists. No player can open them either.
- **Work resolution has a long tail.** Movement-number-reset segmentation plus
  catalogue keying handles the bulk, but opera and box sets still produce some
  over-broad works.
- **A tag containing a newline** breaks line-oriented formats. The tag reader
  collapses whitespace; this was found in the wild (`'Old Folks\nOld Folks'`).
- **Work resolution fragments across releases.** The same piece titled three
  ways in three folders becomes three works, because most repertoire has no
  universally-used catalogue number to key on. `general_mb.py` addresses this
  where MusicBrainz has the exact performance; for the rest it remains open,
  and the honest fix is acoustic fingerprinting (see the roadmap).
- **No regression suite for work resolution or duplicate detection.** The 130
  cases in `tests/` cover dates, sessions, credits, incremental scan and
  portability.
