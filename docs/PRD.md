# cratedigger — product requirements

*Finding the order in a pile of records.*

Status: working tool. The single-artist path is complete; the general path is
behind. This document is the plan to close that gap, and what "done" means at
each step.

---

## 1. The problem

A folder tree expresses exactly one hierarchy. A serious music collection
needs several at once — composer, work, session date, rating, quality tier,
provenance — and the folder names give the strain away:

```
BANGERS/            a rating
Classical 24/       a technical quality tier
Mozart/             a composer
Jazz/               a genre
```

The consequence is duplication: to find a recording both by "things I love"
and by "Mozart", it has to exist twice. On the reference drive that accounted
for **65.7 GB** of byte-identical copies.

Existing tools do not solve this. They solve a different problem — making
files match a catalogue — and they solve it by **writing to your files**.

## 2. Who this is for

**Primary: the archivist-collector.** A large, messy, partly-unofficial
classical or jazz collection. Bootlegs, broadcasts, alternate takes, seven
recordings of the same symphony. They have opinions about provenance and will
not let an automatic tool loose on a 400 GB archive.

**Secondary: the professional cataloguer.** Labels, radio stations, estates,
private collections. Cataloguing is billable work; the tool makes one person
able to do it.

**Explicitly not:** the listener who wants tidy tags on a 2,000-file pop
library. beets and Picard serve them well and this will not do it better.

## 3. Jobs to be done

| | |
|---|---|
| J1 | "Show me my collection in an order the folders cannot express." |
| J2 | "Tell me what I actually have, and where it disagrees with itself." |
| J3 | "Reconcile it against authoritative sources without trusting them blindly." |
| J4 | "Do not touch my files." |
| J5 | "Let me hear it — put a playlist in the player I already use." |

## 4. Non-goals

Stated because each is a plausible-sounding trap:

- **Not a player.** Playlists go to foobar2000, VLC, a DAP. Roon owns this.
- **Not a tagger by default.** Tag writing is a Phase 3 opt-in with backup
  and undo, never the default posture.
- **Not a downloader or acquirer.**
- **Not a beets competitor** on catalogue matching. Different problem.
- **Not cloud.** Local-first; the panel binds to localhost by design.
- **Not a general database front-end.** The facets are opinionated because
  the domain is.

## 5. Principles

Load-bearing, not decorative — several have already caught real bugs.

1. **Read-only with respect to your music.** Nothing is moved, renamed or
   retagged. The audit verifies every path it claims; it never modifies one.
2. **A wrong answer is worse than none.** Extraction declines rather than
   guesses. Anything uncertain carries a confidence and a source.
3. **No silent overwrites.** External sources produce decision sheets. A
   person rules; the ruling is stored with its citation and outranks
   inference.
4. **Everything generated is disposable.** Only `vocab/` is irreplaceable.
5. **Inspectable by default.** Artifacts are text a human can read, diff and
   grep.
6. **Zero install.** Standard library only. Anything needing a binary or an
   API key is optional and behind a flag.

## 6. Current state

| | |
|---|---|
| **Artist path** | complete: session model, 11 view splines, browser with reconciliation, audit at 0 HIGH, reconciled against David Wild and MusicBrainz |
| **General path** | model and playlists work; **no browser**, no reconciliation, no duplicate UI |
| **Scale proven** | 3,398 tracks end to end; 90,159 walked and playlisted via the fast path |
| **Tests** | 130 cases, 5 suites: dates, sessions, credits, incremental scan, portability |
| **Docs** | 9 documents, ~1,900 lines |

Measured on the reference archive of 3,398 tracks:

```
manifest    4.33 MB    1,338 B/track       json load  0.03 s
probe       2.76 MB      852 B/track       in memory  3,184 B/track
browser     0.64 MB      198 B/track
scan          64 s full   ->   0.3 s incremental
```

---

## 7. Roadmap

### Phase 1 — make the general path first-class

The mixed library is the general case; artist mode is the specialism. Today
that is backwards.

**1.1 Incremental scan — DONE**
Reuse a file whose path, size and mtime are unchanged. 64 s → 0.3 s, output
byte-identical to a full scan, reuse refused across roots.

**1.2 Widen the tests — DONE**
76 cases. Found four real bugs on the first run, including a track-number
stripper that reduced the composition `26-2` to `2`.

**1.3 General-mode browser — DONE**

`coltrane_app.py` is roughly 90% artist-agnostic; the compaction step and the
facet list are the artist-specific parts.

- extract a shared browser core: facet engine, timeline, table, search,
  m3u8 export, decision storage
- artist mode contributes: session date, lineup, personnel, provenance,
  authority
- general mode contributes: work, composer, catalogue number, quality tier,
  source medium, duplicate cluster
- add a `by-work` view: every recording of a piece side by side, which is the
  general-path equivalent of the chronology spine
- `cratedigger browse` stops refusing general mode

**Done when:** a mixed library opens in the browser, `by-work` shows all
recordings of a piece together, and the artist browser is unchanged in
behaviour (verified by hashing its payload before and after).

**1.4 Reconciliation for the general path — DONE**

Reuse the validated-match machinery already proven in `coltrane_mb.py`: a
candidate release must overlap our tracklist in **both** directions, and
session facts are computed only from overlapping tracks.

Shipped as `general_mb.py`. One assumption from the plan above did not
survive contact with the data: **album artist is not usable as a match key.**
Measured on the manifest, all 314 releases have complete durations, 87 have
an album artist, and 1 has a MusicBrainz album id. So matching validates on
the **duration sequence** alone — 70% of tracks pairing within 5 seconds —
and treats title and artist purely as search terms.

- populates recording date, label, catalogue number and **per-recording work
  ids**, which is the stable identity fragmentation actually needs
- emits `mb_conflicts.csv` in the decision-sheet shape, nothing applied
- `vocab/general_mb_works.json` records which releases share a work

Three lessons came out of measuring rather than assuming:

1. **A throttle is not a negative result.** Six of seven early "misses" were
   503s cached permanently as "no match". Transient failures are now kept out
   of the cache so the next run retries them.
2. **Folder titles need cleaning before they are queries.** `BACH -
   Brandenburg Concerti CD1` returns nothing; `Brandenburg Concerti` scores
   100.
3. **A track count out-filters a title score.** `tracks:19` reduced eight
   plausible candidates to one, and prefiltering on the count reported in
   search results cut the call budget per release from ~36 to under 10.

**Done:** a classical release with useless tags gets work identity and a
recording date with citations, and a wrong performance is refused rather than
guessed — which is why the hit rate is a fifth rather than everything.

**1.5 Cross-platform CI — DONE**
`.github/workflows/ci.yml`: Python 3.8–3.12 on Windows, macOS and Linux with
`ffmpeg` installed, running `tests/run_tests.py`, plus a Linux job that
imports every module and `--help`s every entry point — because the failures
most likely to hit a non-Windows user are import-time.

A `test_portability` suite makes the same guarantee locally: every module is
parsed against the 3.8 grammar, and no module may carry a hardcoded drive
letter (a regression that has happened twice here).

**The platform question is open, and deliberately notated rather than
answered** — see [platform.md](platform.md). CI proves the code *runs* on
three platforms; it does not prove the tool is *good* on them. The folder
picker is modelled on drive letters, and no non-Windows playlist consumer has
been tested. The honest claim is "runs everywhere, proven on Windows."

### Phase 2 — identify files by content

The unlock for "point at a folder and it works".

**2.1 AcoustID / Chromaprint, behind a flag — DONE (lookup unverified)**

Identify a track by its audio rather than its filename. This is what makes a
library with garbage names tractable, and it is what beets and Picard already
use.

- costs the zero-install property: needs the `fpcalc` binary and an API key
- therefore **strictly optional** — a plugin, never a hard dependency, and it
  degrades to current behaviour when absent
- `cratedigger fingerprint` populates a cache keyed by path + size + mtime,
  the same reuse discipline as the scan

Shipped as `fingerprint.py`, wired in as `cratedigger fingerprint`. Stage 1
(`fpcalc`, local, no key, no network) is verified end to end: Chromaprint
1.6.1 installed, real files fingerprinted, cache reuse confirmed.

**Stage 2 was exercised against the live service on 30 Aug 2026** with a key
supplied by the owner, and the service rejected it: `{"code": 4, "message":
"invalid API key"}`. That is still not a measurement of the identification
rate, but it was worth far more than one, because reaching the network
uncovered four defects that no amount of local testing had:

1. **A rejected key was reported as a busy server.** The 400 was treated like
   a throttle and retried three times per file; the message that explained
   everything was discarded. The run printed "0 identified, 12 deferred after
   server errors", which reads like AcoustID was having a bad day. On a full
   library that is 10,000 pointless requests to arrive at one sentence.
2. **The join to the manifest silently matched nothing.** `apply.py` assumed
   tracks are nested under their release; the artist archive keeps them in a
   flat top-level list. Every identification was dropped and the run printed
   `acoustid 0` — indistinguishable from a lookup that genuinely found
   nothing. This alone would have made a *valid* key look useless.
3. **Five CLI subcommands never dispatched.** `fingerprint`, `apply`,
   `duplicates`, `tags` and `export` set `func=` where the dispatcher reads
   `fn`. Every one of them parsed `--help` perfectly, which is why a
   help-only smoke test passed them all.
4. **`apply --tags` only wrote the plan when it had rows**, leaving the
   previous run's plan on disk looking current — in the one file that
   `tags.py --write` executes against real audio.

With those fixed the chain is verified end to end apart from the network
call itself: real fingerprints from `D:\Coltrane`, through a synthesised
AcoustID response shaped like the live one, into scored proposals, into a
tag plan whose paths all resolve to real files. `tests/test_fingerprint.py`
holds the regressions.

**What is still needed is an *application* key.** AcoustID issues two
different strings: a user API key on the account page, and a per-application
key at <https://acoustid.org/my-applications>. Only the second works here,
and the error for the wrong one is simply "invalid API key". The tool now
says so when it is refused.

One bug worth recording: `--limit` rewrote the output file from only the
records processed before the break, silently discarding every fingerprint
past that point and turning a resume flag into a way to lose work.

**2.2 Confidence-scored auto-apply — DONE**

With fingerprints most matches become unambiguous.

- high confidence *and* corroboration → apply automatically, still recording
  the source and confidence
- anything contested → the existing decision sheet
- the threshold is configurable and defaults conservative

Shipped as `apply.py`. Measured on the classical manifest: **1,022 fields
applied, 75 held for review, 0 contested**, of which 452 are MusicBrainz work
ids. Idempotent — a second run finds nothing to do.

Two things the build taught:

- **MusicBrainz work ids needed their own field.** Proposed onto `work_id`
  they were 954 "would overwrite" rows that the guard correctly refused,
  which meant the fragmentation fix never landed. `musicbrainz_workid` is a
  different identity from our local grouping key, and is what Picard writes.
- **Display truncation reached the write path.** Values were stored from the
  60-character CSV column rather than the real value, silently truncating
  every work title longer than that. Caught by re-running apply and finding
  280 of 1,022 no longer matching what had just been written; idempotence is
  now a check, not an assumption.

Tag writing is planned but **not enabled**: `--tags` emits the full change
list and a backup of the current tags, and no code path opens an audio file
for writing. That belongs to 3.3.

**2.3 Duplicate resolution UI — DONE**

Shipped as `duplicates_app.py` / `cratedigger duplicates`. Clusters side by
side with path, quality and size, one copy preselected. Never deletes: it
emits a script, and the script is a dry run as written
(`$WhatIfPreference = $true` / `DRYRUN=1`) — verified by round-tripping an
actual folder through both states.

**The feature nearly shipped a catastrophe.** The largest cluster was
`Celibidache Volume 1: Symphonies` — 14 entries, 4.1 GB "reclaimable" —
which turned out to be the fourteen discs of one box set, grouped only
because they share a title. The page would have generated a script reducing
it to a single disc and called that a saving.

`same_title_review` means *"these share a title, look at them"*, never
*"these are copies"*. Low-confidence clusters now preselect nothing,
contribute nothing to the script, and say why. The honest figure for this
library is **9.0 GB across 25 verified clusters**, not the 20.8 GB the raw
list implies — the difference was entirely false positives, and it is the
strongest argument in the project for never wiring a deleter to a heuristic.

### Phase 3 — product surface

**3.1 Packaging — DONE** — `pipx install cratedigger`, console entry point, so there
is no clone step. Vocabulary ships as package data.

**3.2 Panel as primary — DONE** — first-run wizard, progress surviving a
reload, vocabulary editing in the UI instead of raw JSON.

All three are in place, and the second turned out to be already true: job
state lives on the server and the client replays from the start of the run,
so a reload never lost anything. It is now verified rather than assumed.

The vocabulary editor is an HTTP endpoint that writes files, so the name is
never joined to a path. A name must appear in the listing the server itself
produced, which makes traversal impossible rather than merely unlikely —
`../../cli.py`, `..%2f..%2fcli.py` and `C:/Windows/win.ini` are all refused
because they are not in the list, not because a check caught them.

Tag writing is deliberately **not** armed from the panel. It can plan,
preview, verify and undo; writing stays a terminal command, because putting
a filesystem write behind a button in a web page is the ceremony 3.3 exists
to prevent.

The 3.1 package move had broken the panel outright — its stage table still
shelled out to `cratedigger.py` at the repo root, so every button would have
failed. Two further bugs surfaced only by driving it: the stage runner joined
`argv[0]` to the package directory, turning `-m` into a nonexistent path; and
saving vocabulary wrote CRLF on Windows, rewriting an LF file wholesale and
producing a diff of the entire discography for a one-line edit.

**3.3 Opt-in tag writing — DONE** — the most requested and most dangerous
feature. All four requirements are met and tested: opt-in per run (`--write`
is refused without `--yes`); a complete backup of *every* tag before any
write, flushed before the first file is opened; `--undo` restoring exactly;
and a dry run listing every field.

Shipped as `tags.py` / `cratedigger tags`, with `mutagen` as an optional
extra. It refuses to run without it rather than falling back to rewriting
whole files with ffmpeg.

Two design choices worth recording:

- **It decides nothing.** `apply --tags` writes the plan; `tags` executes it.
  The CSV is reviewable and row-deletable, so a human filter sits between
  inference and the filesystem by construction rather than by discipline.
- **A second write over an existing journal is refused.** It would overwrite
  the record of the original tags and leave undo restoring the wrong state —
  the failure mode where the safety net is what breaks.

`tests/test_tags.py` proves the round trip: a real ffmpeg-built library, one
tagged file and one untagged, restored state asserted **identical** to the
original. CI installs mutagen so it runs rather than skips.

**3.4 Shareable export — DONE** — a read-only static site of a collection,
no audio, for showing a catalogue to someone else. Shipped as `export.py` /
`cratedigger export`.

The design rule is *absent, not hidden*: the path column is overwritten, the
root key deleted, and the `<audio>` element cut from the file rather than
hidden by script, so "no audio" describes the bytes rather than the runtime.
The payload is audited before writing and the export refuses itself if a
drive letter, home directory or surviving path is found.

That audit paid for itself immediately. The first export **refused**, and not
over the path column — 28 *album titles* in the test library are rip paths
(`E:\APE\rip\Bareboim Bruckner CSO\CD01`), because whoever ripped those
discs tagged the album with the directory they ripped into. Blanking the path
column would have published every one. Path-shaped metadata is now reduced to
its last component; `AC/DC Live` survives, which is the case a naive
slash-split gets wrong.

`tests/test_export.py` covers it as a privacy guarantee rather than a code
review.

### Phase 4 — sustainability

The direct revenue path is poor: beets is free and entrenched, Picard is free
and official. In descending order of realism:

1. **Open source.** The value is the artifact and the reputation. Default.
2. **Services.** Archive cataloguing for labels, stations, estates.
3. **Hosted vocabulary.** A curated, versioned discography layer; engine free.
4. **Consumer app.** Loses to Roon on ecosystem. Least realistic.

---

## 8. Success criteria

| phase | measurable | status |
|---|---|---|
| 1 | a 90k mixed library goes scan → browser in under 30 min; browser interactive in under 3 s | met |
| 1 | audit reports 0 HIGH on both paths | met |
| 1 | CI green on three platforms and three Python versions | met — 9 jobs, 3.8–3.12 |
| 2 | ≥80% of an untagged, badly-named test folder identified correctly | **unverified** — key supplied 30 Aug was refused as invalid |
| 2 | human decisions needed for <20% of tracks | **not met** — depends on the above |
| 3 | install to first browser under 5 minutes for a non-developer | met — `pipx install cratedigger`, verified from a clean venv |
| 3 | tag writing has a verified undo, proven by a round-trip test | met — `tests/test_tags.py`, run in CI |

The two open rows are both phase 2 and both the same dependency. The key
supplied on 30 Aug 2026 was refused by AcoustID as invalid — an *application*
key from <https://acoustid.org/my-applications> is what this needs, not the
user API key on the account page. The attempt was still worth making: it
exposed four defects, two of which (a silent join failure and five
undispatchable CLI commands) would have made a valid key look like a broken
feature. Those are fixed and covered by tests. The identification rate itself
remains unmeasured, so the honest reading is unchanged: the phase-2 unlock
("point at a folder and it works") is built, wired, and unproven.

Duration-based MusicBrainz matching, which *is* measured, reaches 16% on
classical. That is the ceiling without fingerprinting, and it is why 2.1
matters rather than being a nice-to-have.

## 9. Risks

| risk | mitigation |
|---|---|
| scope creep into a player | non-goals are explicit; playlists are the integration point |
| AcoustID breaks zero-install | strictly optional, flagged, degrades cleanly |
| vocabulary rot | it is data, versioned in git, with `confidence` and `source` per entry |
| Wild extract licensing | attributed in README and LICENSE; `--fetch` rebuilds from source |
| the general path stays second-class | Phase 1 exists entirely to prevent this |
| tag writing destroys someone's tags | backup, undo and dry-run are requirements, not features |

## 10. Open questions

- Does the artist path stay a specialism, or become a *profile* over the
  general model? The session tier has no general equivalent; forcing one may
  be worse than maintaining two shapes.
- Is the panel or the CLI primary for the target user? The archivist may well
  prefer the CLI, in which case the panel is an onboarding surface only.
- Where is the line between "curated vocabulary" and "redistributing someone
  else's discography"? Currently drawn at attribution plus a rebuild path.

---

## 11. Storage: does this need a database?

Asked at the right time, and the answer is **not yet, and then only as a
derived index** — never as the source of truth.

### Measured

| tracks | manifest | in memory | browser payload | JSON load |
|---|---|---|---|---|
| 3,398 (reference) | 4.3 MB | 10 MB | 0.64 MB | 0.03 s |
| 90,159 (measured library) | ~115 MB | ~0.27 GB | ~17 MB | ~0.7 s |
| 250,000 | ~319 MB | ~0.74 GB | ~47 MB | ~2.0 s |
| 1,000,000 | ~1.3 GB | ~2.97 GB | ~188 MB | ~8.1 s |

### What the numbers say

The **build is not the constraint**. Parsing 115 MB of JSON takes 0.7 s and
0.27 GB — unremarkable. Even a million tracks loads in 8 s, and that stage
runs once per change.

**The browser is the constraint.** It embeds the whole payload in one HTML
file. At 17 MB (90k tracks) that is sluggish; at 47 MB it is untenable. The
wall is roughly **50,000 tracks**, and it arrives in the general path — which
is exactly what Phase 1.3 is about.

So the trigger is specific and near: the general-mode browser on a large
mixed library.

### Recommendation

**Keep JSON and JSONL as the source of truth. Add SQLite as a derived,
regenerable index — the same status as `views/`.**

Reasons:

- **SQLite is in the standard library.** A database costs nothing against the
  zero-install principle. This is the decisive fact.
- **Inspectability survives.** The manifest stays greppable, diffable text.
  The database is an index, and like the playlists it can be deleted and
  rebuilt.
- **It answers the real question.** A server-backed browser can page and
  filter without shipping the collection to the client — and the panel is
  already a server, so the machinery exists.
- **JSONL is genuinely right for the probe.** Append-only, streamable,
  line-diffable, survives a partial write. Replacing it would be a
  regression.

### What it does *not* solve

Being honest about the parts a database is often assumed to fix:

- it does not make the model better; the facets are the value
- it does not help reconciliation, which is bounded by source quality
- it does not help the scan, which is bounded by ffprobe
- it adds schema migration as a maintenance burden the JSON does not have

### Trigger and plan

Build it when **any** of these is true — not before:

1. a target library exceeds ~50,000 tracks, or
2. the general-mode browser cannot ship its payload to the client, or
3. two processes need concurrent access (panel and CLI writing at once)

When triggered:

```
build  ->  library.json      (source of truth, unchanged)
       ->  library.db        (derived index, gitignored, rebuildable)
```

- one table per tier — track, release, work/session, plus a facet join
- indices on the facets the browser filters: date, composer, work, lineup,
  quality, provenance
- `cratedigger index` builds it; `cratedigger clean` removes it like any
  other artifact
- the browser gains a server-backed mode for large libraries and keeps the
  static single-file mode for small ones, because a self-contained file you
  can email is worth preserving

**Decision for now: do not build it.** The reference archive is 3,398 tracks
and the static browser is 0.64 MB. Adding a database today would be
infrastructure ahead of need, and would dilute the inspectability that is
currently a selling point. Revisit at Phase 1.3, with a real 90k mixed
library in front of us, where the question answers itself.
