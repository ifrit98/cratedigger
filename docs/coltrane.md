# The Coltrane archive

A single-artist ontology for `D:\Coltrane` (403 GB, 3,398 audio files).
**The archive is read-only. Nothing is ever written into it** — the manifest
and all playlists live under `output-coltrane/` on C:.

## Why this is not the generic model

The general toolkit is composition-centric: Work → Recording → Release. That
is right for classical and wrong here. A Coltrane archive is mostly *not the
catalogue* — it is bootlegs, broadcasts, alternate takes and European tour
tapes, and those only make sense next to the studio dates they sit between.

So the organizing unit is the **session**: a date, a place, a band. That is
how jazz discography actually works.

```
TUNE                the composition -- 'My Favorite Things', 'Naima'
  |  N performances
PERFORMANCE         one recorded take = one audio file
  |  grouped into
SESSION             date + venue + personnel   <- the chronological spine
  |  issued on
RELEASE             album, bootleg or compilation  <- the album spine
```

## Dating: three sources, in strict precedence

Only 83% of files carry a DATE tag, and on reissues that tag is the *reissue*
year. Dates are resolved in this order:

1. **A day or month date in the folder name.** The bootleg tier is named
   `1961, November 18, Paris` — specific to that recording, and the most
   trustworthy signal in the archive.
2. **The discography table** (`vocab/coltrane_sessions.json`). `1957 - Blue
   Train` gives only a year, but the session is documented as 15 September
   1957. This is what dates the SACD/DSD transfers, which are titled by album
   alone.
3. **A year-only folder name**, then the DATE tag last.

### The lifetime clamp

Coltrane died **17 July 1967**. Any date outside 1945–1967 is a release or
compilation year, never a recording date. Without this rule, posthumous
compilations date themselves to 1972–1979 and corrupt the chronology — and
worse, corrupt the tune index. Before the clamp, *My Favorite Things* claimed
a first recording of 1956; it is October 1960, and the 1956 came from a
compilation's arbitrary tag year.

Compilation titles (`Best of`, `Ken Burns Jazz`, `The Art of`, `Mastery of`…)
are detected and their tag year is never read as a session date.

### Coverage

| date precision | releases |
|---|---|
| day | 323 |
| year | 135 |
| month | 11 |
| none | 77 |

| source | releases |
|---|---|
| discography table | 262 |
| folder name | 187 |
| tag | 20 |
| unresolved | 77 |

The 77 unresolved are mostly compilations and `CD1`/`CD2` subfolders whose
parents carry no date either. They are collected in
`by-date/_UNDATED.m3u8` rather than being given a false date.

## The interactive browser

`output-coltrane/coltrane-browser.html` — one self-contained file, ~670 KB,
the whole ontology embedded. **Open it directly from disk.** No server, no
network, works offline.

Because it is a local file it can point an `<audio>` element at the archive,
so tracks play in place. If the browser blocks `file://` media, the path is
copied to the clipboard instead and the footer says so.

| | |
|---|---|
| **Timeline** | sessions grouped under year headers, in true date order. Click a session to drill into its tracks. |
| **Track list** | flat, sortable, with a play button per row |
| **Tunes** | every tune with version count, live count, and first/last recorded |
| **Facets** | era, lineup, recording type, issue, role, personnel, venue, format, date source — all cross-filtering, with live counts |
| **Search** | tune, album, venue, or path |
| **Export** | writes the current selection as `.m3u8` |

Facet counts update against the *other* active filters, so you can see how
many Half Note dates remain once you have already selected the Classic
Quartet. Selecting a lineup and then a musician who is in it will still
reduce the count — that is not a bug, it means those releases had personnel
read from folder text rather than inferred from the date.

The payload is compacted before embedding: repeated strings (era, lineup,
venue, personnel) become indexes into lookup tables, taking 4.5 MB of JSON
down to about 525 KB, before the reconciliation data is added.

Regenerate after any rebuild:

```bash
python coltrane_app.py --manifest output-coltrane/coltrane.json --out output-coltrane/coltrane-browser.html --root "D:\Coltrane"
```

## Ten slices worth starting from

| what you want | how |
|---|---|
| the whole career in order | `by-date/_ALL - complete chronology.m3u8` |
| one year, everything | `by-date/_years/1965.m3u8` |
| one night | `by-date/1961-11-02 - Village Vanguard.m3u8` (68 tracks) |
| an album as issued | `by-release/1964 - A Love Supreme.m3u8` |
| how a tune evolved | `by-tune/117 - My Favorite Things.m3u8` — 1960 to 1967 |
| one band's whole output | `by-lineup/06 - Classic Quartet.m3u8` |
| everyone Coltrane played with | `by-personnel/0227 - Eric Dolphy (as, bcl, fl).m3u8` |
| studio only, no concerts | `by-provenance/studio.m3u8` |
| catalogue only, no tapes | `by-authority/official.m3u8` |
| where he was a sideman | `by-role/sideman.m3u8` |

Anything crossing two axes is a browser filter or a `tracks.csv` query rather
than a prebuilt playlist — there are too many combinations to enumerate.
`Classic Quartet` + `1963` is 325 tracks across 15 dates.

## Verifying the data

```bash
python coltrane_audit.py --manifest output-coltrane/coltrane.json --root "D:\Coltrane"
```

Adversarial by design — it looks for what is *wrong*, prints examples so any
claim can be checked, and exits with the count of HIGH findings.

Current state: **0 HIGH, 54 MED.**

HIGH covers structural integrity: impossible dates, zero-track releases,
orphaned tracks, duplicate ids, and manifest paths missing from disk. All
3,398 paths verified present.

The MED findings are known and explained:

| finding | count | why |
|---|---|---|
| same album dated differently across tiers | 19 | mostly genuinely different albums sharing a title — there are two records simply called *Coltrane* (Prestige 1957, Impulse 1962) |
| junk tune titles | 20 | `Unknown Title`, `Untitled Original 11386` — the last is a real Coltrane original, not a bug |
| marked studio but venue is not a studio | 15 | venue inherited from the discography table where the folder named no place |

Two bugs the audit caught and that are now fixed, both from naive substring
matching in the discography lookup:

- the two-letter key `om` matched inside **C-om-plete** Copenhagen, dating
  that concert to the Seattle *Om* session and giving it a Seattle venue
- `kenny burrell` (13 chars) beat `the cats` (8) under longest-key-first,
  because the personnel are listed in the folder name

Matching is now whole-token and scored by position in the leaf folder name,
so an album title beats a personnel mention. Venue false positives dropped
from 49 to 15.

## The view splines

1,113 playlists in `output-coltrane/views/`.

### by-date — the chronological spine

One playlist per session date, named to sort chronologically in any file
browser, with the character of the date in the filename:

```
1961-11-02 - Village Vanguard.m3u8
1961-11-18 - Paris [unofficial].m3u8
1963-10-08 - Birdland [live].m3u8
1963-12-07 - Jazz Casual (TV) [broadcast unofficial].m3u8
1964-12-09 - Van Gelder Studio, Englewood Cliffs.m3u8
```

Plus `_years/1961.m3u8` rollups, and `_ALL - complete chronology.m3u8`:
the entire archive in true date order, studio and stage and bootleg
interleaved. That is the view a folder tree structurally cannot produce.

### by-release — the album spine

One playlist per release folder, prefixed with the recording year:
`1957 - Blue Train.m3u8`, `1964 - A Love Supreme.m3u8`.

546 of them. Names collide constantly in this archive — a dozen folders
called `CD1`, and the same album held at 16-bit, 24-bit and DSD — so
colliding names are disambiguated by archive tier rather than silently
overwriting each other.

### The rest

| spline | |
|---|---|
| `by-tune` | 337 tunes with 3+ versions. *My Favorite Things* has 117 dated performances spanning 1960–1967. |
| `by-era` | the working bands in sequence, `00`–`09` prefixed |
| `by-provenance` | studio (368) / live (171) / broadcast (4) / rehearsal (3) |
| `by-authority` | official (479) vs unofficial (67) |
| `by-venue` | 27 venues — Van Gelder, Birdland, Half Note, Village Vanguard, Newport … |
| `by-role` | leader (489) / co-leader (32) / sideman (25) |
| `by-personnel` | 36 musicians with 5+ tracks — every date Coltrane and they shared |
| `by-lineup` | the 9 working bands as playable sets |
| `by-format` | Lossless, Lossless Hi-Res, DSD, Lossy |

## Personnel

Two sources, and named musicians always win.

**1. Date-ranged working bands** (`vocab/coltrane_personnel.json` → `lineups`).
Nine non-overlapping ranges covering 1955–1967. This resolves the bulk of the
archive — 404 of 546 releases — because most folders name no one at all.

**2. Names written into the folder or tags.** `The Cats (Tommy Flanagan, John
Coltrane, Kenny Burrell, Idrees Sulieman)` says exactly who played. 72
releases resolve this way.

The precedence is the important part. An early version merged the two, and
*The Cats* — a 1957 Prestige date — acquired Monk's rhythm section purely
because it falls inside the Five Spot residency window. **Named musicians now
win outright**, and the date-range band fills in only when nothing is named.
An incomplete credit is honest; a wrong one is not. `personnel_source` records
which applied: `named`, `lineup`, or empty.

| source | releases |
|---|---|
| lineup (by date) | 404 |
| named in folder/tags | 72 |
| unresolved | 70 |

Most-recorded associates, by track count:

| | | | |
|---|---|---|---|
| McCoy Tyner (p) | 1,692 | Miles Davis (tp) | 375 |
| Elvin Jones (d) | 1,487 | Paul Chambers (b) | 327 |
| Jimmy Garrison (b) | 1,371 | Jimmy Cobb (d) | 256 |
| Rashied Ali (d) | 674 | Eric Dolphy (as, bcl, fl) | 227 |
| Pharoah Sanders (ts) | 674 | Reggie Workman (b) | 222 |

Sanders and Ali share an identical count because they appear in exactly the
same two lineups — an artifact of date-range inference, not a coincidence in
the music.

### Crossing the axes

The splines compose. "Every Tyner/Garrison/Jones date in 1963" is
`by-lineup/06 - Classic Quartet` intersected with `by-date/_years/1963`, or
one filter on `tracks.csv`:

```
lineup = "Classic Quartet" AND recording_date LIKE "1963%"
```

### Editing personnel

`lineups` entries take `from`/`to` (inclusive/exclusive), a member list with
instruments, and a `caveat` for transitional months. Ranges are deliberately
non-overlapping — Sanders joined mid-1965 and Ali in November while Elvin
Jones was still present, and rather than model that as overlap the
`expanded-1965` entry carries a caveat.

`musicians` entries take a canonical `name`, an `instrument`, and `aliases`.
Matching is longest-alias-first, so `philly joe jones` wins over `jones` and
`alice coltrane` over `coltrane`. Coltrane himself is excluded from the
output — he is on everything.

## External sources

Dates were originally mine alone, uncited. Two independent sources are now
mined and reconciled. **Neither is auto-applied** -- both produce decision
sheets.

### David Wild (`coltrane_wild.py`)

<http://www.wildmusic-jazz.com/> -- the web edition of David Wild, *The
Recordings of John Coltrane: A Discography*, 2nd ed., Wildmusic 1979.

The best source available, because Wild keys each session **YYMMDD**: the
date is stated, not inferred. **101 sessions** mined, every one with
personnel-and-instruments, location, engineer and full tune listing (471
tunes) -- exactly the tier this model calls a session.

```
611102  JOHN COLTRANE GROUP
   Village Vanguard, New York City NY
   Coltrane [ss, ts]; Eric Dolphy [as, bcl]; Garvin Bushell [oboe,
   contrabassoon]; Ahmed Abdul-Malik [tamboura]; McCoy Tyner [p]
```

**Coverage gap:** the web edition has 1956-57 and 1960-67, but **1958 and
1959 are absent entirely**, and 1957 has one session. Blue Train, Giant
Steps, Soultrane and Lush Life -- the Prestige/Atlantic core -- are therefore
not covered online. The print 2nd edition has them.

### MusicBrainz (`coltrane_mb.py`)

Session data lives in recording *relationships* (`recorded at` with a begin
date, plus per-musician `instrument` credits), not in `first-release-date`,
which is the release. **82 albums** validated, 46 of them shown to span more
than one session.

### The repertoire trap

Matching a release to a session by shared tune titles fails badly for this
artist. Coltrane played the same repertoire nightly, so any three-tune live
set overlaps a dozen sessions at 100%. An early pass claimed **75** date
corrections including `1963, July 7, Newport` -> 1961-11-18 (Paris).

Three guards fixed it, taking corrections to 18:

- require **at least 4 shared tunes**, not merely a high ratio
- let the **venue corroborate** the match
- treat a **folder's own day-precision date as primary** -- Wild's web
  edition does not cover the bootleg tier, so a "correction" there is a
  mis-match by definition

The same trap applies to MusicBrainz: searching "Blue Train" returns both the
Elmo Hope session and a 70-track anthology. Candidates are validated against
our tracklist, and session facts are computed from the **overlapping tracks
only** -- which turns an anthology from a hazard into a useful source, since
MusicBrainz dates each recording individually.

### Consensus (`coltrane_consensus.py`)

Grades all 546 releases on where the sources agree:

| verdict | releases | meaning |
|---|---|---|
| confirmed | 149 | sources agree, and so do we |
| unsourced | 244 | neither source has it |
| single-source | 115 | only one external source |
| **adopt** | 20 | both sources agree, we differ -- change these |
| **contested** | 18 | the sources disagree -- needs a person |

The `adopt` rows cover 7 distinct albums, mostly multi-session records where
my table had picked an arbitrary first date: *Ballads* -> 1962-11-13,
*Coltrane Plays the Blues* -> 1960-10-24, *The Avant-Garde* -> 1960-07-08.

`contested` is almost entirely live compilations, and that is informative
rather than embarrassing: for an anthology drawn from six European concerts,
"the album date" is an ill-posed question. The answer is track-level
assignment, not a better album date.

### Reconcile mode in the browser

`coltrane-browser.html` now has a **Reconcile dates** mode, so the granular
state is reachable without leaving the tool. It carries all 1,675 tracks that
Wild knows, with every candidate session embedded (97 sessions, 655 KB total).

Each row shows the current date, the proposed Wild session with its venue and
personnel, and a confidence badge. For an ambiguous track the proposal is a
**dropdown of the actual candidate sessions** -- *Peace on Earth* offers four,
distinguished by venue and group -- so the choice is made against the
evidence rather than in the abstract.

| control | |
|---|---|
| confidence filter | unique / corroborated / ambiguous / would-change / undecided |
| Accept, Keep | per row; `Keep` records a deliberate decision to leave the date alone |
| Accept all unique | bulk-accepts the 997 unambiguous proposals |
| Export decisions | downloads a JSON of every decision made |

Decisions persist in `localStorage`, so the work survives closing the tab.
Nothing touches the manifest until you export and apply.

### Closing the loop

```bash
python coltrane_decisions.py --in ~/Downloads/coltrane-date-decisions.json
python coltrane_build.py --raw output-coltrane/raw_probe.jsonl --out output-coltrane --root "D:\Coltrane"
```

`coltrane_decisions.py` writes `vocab/coltrane_date_overrides.json`, which
`coltrane_build.py` treats as the **highest-precedence source** -- above
folder names, the discography table and tags -- because it records a human
decision with a citation. It merges rather than replaces, so adjudication can
happen in several sittings.

A verified round trip: `Early Trane/CD1/09. Airegin.mp3` went from
`1955-01-01 / year / discography` with no venue, to `1956-07-21 / day /
decision` at Peacock Alley, St. Louis -- with the era corrected from "Dizzy
Gillespie / R&B sideman" to "Miles Davis Quintet" and Wild's personnel
attached. One decision, and the date, venue, era and personnel all follow.

### Track-level assignment

```bash
python coltrane_wild.py --tracks
```

A tune appearing in exactly one Wild session dates that track outright,
whatever album it sits on -- so *Ballads* stops pretending to a single date.

| | tracks |
|---|---|
| tune known to Wild | 1,675 |
| unique or corroborated session | **997** |
| ambiguous (tune played at many sessions) | 678 |
| would change the current date | 345 |
| no Wild tune match | 1,723 |

The 678 ambiguous are genuinely ambiguous, not a parser weakness: the tune
really does appear at many sessions. Wild lists durations, so timing-based
disambiguation is the obvious next step.

## Eras

Assigned from the recording date:

```
00  Navy & apprenticeship              1945-
01  Dizzy Gillespie / R&B sideman      1949-
02  Miles Davis Quintet (first)        1955-09
03  Monk & the Prestige years          1957-04
04  Miles Davis Sextet / Prestige      1958-01
05  Atlantic years                     1959-04
06  Impulse! -- Dolphy & expansion     1961-05
07  Classic Quartet                    1962-01
08  Late period -- Ascension onward    1965-06
09  Final group (Alice, Sanders, Ali)  1966-01
```

## Running it

```bash
python scan.py --root "D:\Coltrane" --out output-coltrane/raw_probe.jsonl --workers 16
```
```bash
python coltrane_build.py --raw output-coltrane/raw_probe.jsonl --out output-coltrane --root "D:\Coltrane"
```
```bash
python coltrane_views.py --manifest output-coltrane/coltrane.json --out output-coltrane/views --root "D:\Coltrane"
```

The scan takes about 5 minutes; build and views are seconds. Re-run build and
views freely after editing the discography table.

Paths in the playlists are **absolute**, because the archive is on D: and the
output on C: — Windows has no relative path between drives.

## Output

| file | |
|---|---|
| `coltrane.json` | full manifest: sessions, tunes, releases, tracks |
| `chronology.csv` | releases in date order — the spreadsheet view of the spine |
| `sessions.csv` | 112 sessions: date, venue, provenance, tunes played |
| `tunes.csv` | 1,042 tunes with first/last recorded and studio/live counts |
| `tracks.csv` | every file, date-sorted, with all facets including personnel |

## Editing the discography

`vocab/coltrane_sessions.json` is the domain knowledge and the one file worth
curating by hand. Each entry:

```json
{
  "match": ["a love supreme"],
  "title": "A Love Supreme",
  "recorded": "1964-12-09",
  "precision": "day",
  "confidence": "exact",
  "venue": "Van Gelder Studio, Englewood Cliffs",
  "label": "Impulse!",
  "provenance": "studio",
  "leader": "coltrane"
}
```

`match` holds lowercase substrings tested against the folder path, longest
first — so `live at the village vanguard again` wins over `village vanguard`.
`confidence` is `exact` (one documented session), `first` (the first of
several dates for that album), or `approx`.

Adding an entry immediately upgrades every folder that matches it from
year-precision to a real session date. That is the highest-leverage way to
improve the chronology.

## Known limits

- **Multi-session albums are dated to their first session.** *Giant Steps*
  spans May and December 1959; the table records 1959-05-04 with
  `confidence: "first"`. Track-level session assignment would need a much
  finer discography.
- **Personnel below the session level are not modelled.** A lineup applies to
  a whole release; guests on individual tracks are not distinguished.
- **Year-only dates take a mid-year lineup.** A bare `1960` resolves to
  15 June 1960 for the purpose of band lookup, which places it in the first
  quartet rather than the Steve Davis/Elvin Jones group formed that October.
- **`by-tune` matches on normalized titles**, so a mis-tagged or untitled
  track lands in its own group. 1,042 tunes is more than Coltrane's real
  repertoire; the 337 with 3+ versions are the reliable ones.
- Six files failed to probe (4 `.wv`, 2 `.m4a`) out of 3,404.
- **1,039 tunes is more than Coltrane's repertoire.** 515 have a single
  performance, inflated by inconsistent tagging. The 337 with three or more
  versions are the reliable ones, and those are what `by-tune` builds.
- **No regression suite for the date parser or personnel resolution.**
  `coltrane_audit.py` covers some of that ground but is not a unit test.
