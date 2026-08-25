# Where this could go

> The detailed version is [docs/PRD.md](docs/PRD.md) — phase-by-phase build
> steps, completion criteria, success metrics, and the database question
> answered from measurement.

An honest assessment of cratedigger as a product, and what stands between
here and "point it at a folder, get clean results."

## Is it brandable?

Yes, and the name is doing useful work. *cratedigger* signals **collector**,
not consumer. That matters, because the collector is the only user for whom
this beats what already exists.

The visual language is already consistent — the archive browser and the
control panel share a palette, and it reads as a tool for someone who cares
about provenance. That is the right register.

## The honest competitive position

"Point at a directory, get clean tags from MusicBrainz" is **solved**:

| | |
|---|---|
| **beets** | CLI library manager, MusicBrainz autotagger, AcoustID fingerprinting, moves and retags files, large plugin ecosystem. The incumbent. |
| **MusicBrainz Picard** | the official tagger. GUI, fingerprinting, writes tags. |
| **Roon** | commercial, polished, rich metadata — but a whole playback ecosystem, priced accordingly. |

Rebuilding any of those is a losing move. The question is what they are bad
at.

## The wedge

Four things cratedigger does that the incumbents structurally do not:

**1. It never writes to your music.** beets moves and retags by default;
Picard writes tags. A large number of serious collectors will not let
software touch a 400 GB archive, and that objection has no answer inside
those tools. Read-only is not a limitation here, it is the product.

**2. It is archive-shaped, not catalogue-shaped.** The incumbents assume your
files correspond to releases in a catalogue. Bootlegs, broadcasts, alternate
takes, seventeen versions of *My Favorite Things*, and classical works with
many recordings are exactly where they degrade. The session model and the
work model were built for that.

**3. Provenance and confidence on every derived field.** The incumbents pick
a match. cratedigger records what each source says, grades where they
disagree, and hands you a decision sheet. For anyone doing serious
cataloguing that difference is the whole game.

**4. Faceted views over a fixed hierarchy.** A folder tree has one dimension.
The generated splines — date, work, lineup, personnel, venue, provenance —
are a query language expressed as playlists any player can open.

**The target user:** the classical or jazz collector with a large, messy,
partly-unofficial archive who does not trust automatic tools. Small, but
underserved and vocal.

## What blocks the general case today

Grounded in the current code, not aspiration:

| blocker | detail |
|---|---|
| **Artist mode does not scale** | 80 hand-written sessions, 9 lineups, 74 musicians — per artist. Excellent for Coltrane, unusable as a general path. |
| **General mode is the weaker half** | mixed-library mode has no browser (`browse` refuses), no reconciliation, and only recently got docs. It is the actual product path and it is behind. |
| **Identification depends on filenames** | dates and works come from folder names and tags. A library with poor names or no tags gets little. |
| **No incremental scan** | every scan re-probes everything. Fine at 3k files, painful at 90k, unacceptable as a routine. |
| **Thin tests** | 33 cases, all `credits.py`. Nothing covers date parsing, work resolution, personnel or the reconcilers. |
| **Windows-shaped** | developed and tested on Windows. Nothing is obviously non-portable, but nothing is *verified* elsewhere. |

## The plan

### Phase 1 — make the general path first-class

The mixed library is the general case; artist mode is the specialism. Today
that is backwards.

- bring the browser to general mode (works, composers, quality, duplicates)
- reconciliation for the general path: release-level MusicBrainz matching
  with the same validation the artist path uses
- incremental scan keyed on path + mtime + size; re-probe only what changed
- widen the test suite to date parsing, work resolution and personnel, and
  run it on macOS and Linux in CI

### Phase 2 — identify files by content

This is the unlock, and the one thing that would genuinely deliver "point at
a folder and it works."

**AcoustID / Chromaprint fingerprinting.** Identify a track by its audio, not
its filename. That is how a library with garbage names becomes tractable, and
it is what beets and Picard already use.

It costs the project's cleanest property: fingerprinting needs the `fpcalc`
binary and an API key, so "standard library only, nothing to install" ends.
Worth it, but it should be **optional** — a plugin, not a dependency, so the
zero-install path survives for people who only want the faceted views.

With fingerprints, the flow becomes:

```
fingerprint -> MusicBrainz recording id -> release, date, personnel, work
            -> confidence score
            -> high confidence: apply automatically
            -> low or conflicting: decision sheet, as now
```

The decision-sheet architecture already handles the hard half. Fingerprinting
just shrinks how often a human is needed.

### Phase 3 — product surface

- packaged install (`pipx install cratedigger`, or a signed binary) so there
  is no clone step
- the panel becomes the primary interface, the CLI the power path
- **opt-in tag writing**, with a full backup and a one-command undo. This is
  the most-requested thing such tools do, and the most dangerous; it should
  be last, loudest, and reversible.
- a shareable read-only export of a collection

### Phase 4 — the commercial question

Worth being blunt: **the direct path to revenue is poor.** beets is free and
entrenched; Picard is free and official. Charging for a better tagger is
competing with zero.

Plausible directions, roughly in order of realism:

1. **Stay open source.** The value is the artifact and the reputation. This
   is the honest default.
2. **Services around it.** Archive cataloguing for labels, radio stations,
   estates and private collections is real work that people pay for; the tool
   makes one person able to do it. The product is the service.
3. **Hosted vocabulary.** A curated, versioned discography layer worth paying
   a little for, with the engine free. Narrow, but it is the part that is
   genuinely expensive to produce.
4. **A polished consumer app.** Competes with Roon on presentation and loses
   on ecosystem. Least realistic.

## What to do next, concretely

In dependency order, smallest first:

1. **Incremental scan.** Contained, immediately useful, unblocks routine use
   on large libraries.
2. **Widen the tests.** Everything after this is a refactor, and refactors
   need a net. The date parser and work resolution are where regressions
   would hurt most, and where behaviour was already provably preserved once
   by hashing — that technique generalises into fixtures.
3. **General-mode browser.** Reuses the existing app almost wholly; the
   payoff is that the general path stops feeling like the poor relation.
4. **AcoustID behind a flag.** Prove it on a deliberately messy folder before
   committing to it.
5. **CI on three platforms.** Cheap, and it converts "should be portable"
   into "is portable".

Only after those does packaging make sense. Shipping an installer for
something that still needs hand-written session tables would set the wrong
expectation.
