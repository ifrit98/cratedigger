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
| **Tests** | 76 cases, 4 suites: dates, sessions, credits, incremental scan |
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

**1.3 General-mode browser — NEXT**

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

**1.4 Reconciliation for the general path**

Reuse the validated-match machinery already proven in `coltrane_mb.py`: a
candidate release must overlap our tracklist in **both** directions, and
session facts are computed only from overlapping tracks.

- match on (album artist, album title, track count, durations)
- populate recording date, label, catalogue number, work identity
- emit `mb_conflicts.csv` in the same decision-sheet shape
- durations are the strongest signal available without fingerprinting and
  are already captured by the probe

**Done when:** a classical release with useless tags gets its work identity
and recording date from MusicBrainz, with citations, and nothing is applied
automatically.

**1.5 Cross-platform CI**
GitHub Actions: Python 3.8–3.12 on Windows, macOS and Linux, running
`tests/run_tests.py`. Converts "should be portable" into "is".

### Phase 2 — identify files by content

The unlock for "point at a folder and it works".

**2.1 AcoustID / Chromaprint, behind a flag**

Identify a track by its audio rather than its filename. This is what makes a
library with garbage names tractable, and it is what beets and Picard already
use.

- costs the zero-install property: needs the `fpcalc` binary and an API key
- therefore **strictly optional** — a plugin, never a hard dependency, and it
  degrades to current behaviour when absent
- `cratedigger fingerprint` populates a cache keyed by path + size + mtime,
  the same reuse discipline as the scan

**Done when:** a folder of files named `track01.mp3` with no tags yields
correct artist, album, date and work.

**2.2 Confidence-scored auto-apply**

With fingerprints most matches become unambiguous.

- high confidence *and* corroboration → apply automatically, still recording
  the source and confidence
- anything contested → the existing decision sheet
- the threshold is configurable and defaults conservative

**Done when:** a human is needed for the genuinely ambiguous minority rather
than for everything.

**2.3 Duplicate resolution UI**

The general path already detects clusters and reclaimable bytes and has no
interface for them. Show clusters side by side with quality, provenance and
size, with a keep-this action. **Never deletes** — emits a script the user
reads and runs.

### Phase 3 — product surface

**3.1 Packaging** — `pipx install cratedigger`, console entry point, so there
is no clone step. Vocabulary ships as package data.

**3.2 Panel as primary** — first-run wizard, progress surviving a reload,
vocabulary editing in the UI instead of raw JSON.

**3.3 Opt-in tag writing** — the most requested and most dangerous feature.
Requirements, all mandatory: explicit opt-in per run; a full backup of
original tags before any write; `cratedigger tags --undo` restoring exactly;
a dry-run listing every field that would change. Last, loudest, reversible.

**3.4 Shareable export** — a read-only static site of a collection, no audio,
for showing a catalogue to someone else.

### Phase 4 — sustainability

The direct revenue path is poor: beets is free and entrenched, Picard is free
and official. In descending order of realism:

1. **Open source.** The value is the artifact and the reputation. Default.
2. **Services.** Archive cataloguing for labels, stations, estates.
3. **Hosted vocabulary.** A curated, versioned discography layer; engine free.
4. **Consumer app.** Loses to Roon on ecosystem. Least realistic.

---

## 8. Success criteria

| phase | measurable |
|---|---|
| 1 | a 90k mixed library goes scan → browser in under 30 min; browser interactive in under 3 s |
| 1 | audit reports 0 HIGH on both paths |
| 1 | CI green on three platforms and three Python versions |
| 2 | ≥80% of an untagged, badly-named test folder identified correctly |
| 2 | human decisions needed for <20% of tracks |
| 3 | install to first browser under 5 minutes for a non-developer |
| 3 | tag writing has a verified undo, proven by a round-trip test |

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
