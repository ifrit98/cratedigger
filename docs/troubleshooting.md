# Troubleshooting

Start with `python doctor.py`. It catches most of this.

## Setup

**`ffprobe not on PATH`**
Install FFmpeg (see [getting-started.md](getting-started.md)) and reopen the
terminal. Only the scan needs it — the panel, playlists and browser work
without.

**`ModuleNotFoundError: No module named 'coltrane'`**
You are running a script from the wrong directory. `cd` into the repo first.
The toolkit is standard-library only, so this is never a missing package.

**Unicode errors in the console on Windows**
`set PYTHONIOENCODING=utf-8`. Files written are always UTF-8; this only
affects terminal display.

**`No cratedigger.json here`**
Run `cratedigger init`, or `cd` to the directory where you ran it.

## The panel

**Port already in use**
`cratedigger serve --port 9000`

**A job seems stuck**
It is still running — the pane streams output only as the stage produces it,
and the scan prints every 250 files. Elapsed time keeps counting. Closing the
page does not stop a job; reopening reattaches, because the job lives in the
server. Ctrl-C in the terminal does stop it.

**Buttons are all disabled**
One job at a time, deliberately — the stages share an output directory. Wait
for the pill to read `done`.

**The folder browser shows nothing**
Permissions. It skips what it cannot read rather than failing; try a
different starting point, or type the path directly.

## Scanning

**"N errors" at the end**
Usually benign, and categorised. macOS `._*` AppleDouble files are resource
forks, not audio. WavPack-compressed SACD images (`.iso.wv`) are disc images
reclassified as containers. To see yours:

```bash
python - <<'PY'
import json, os, collections
c = collections.Counter()
for line in open("output-coltrane/raw_probe.jsonl", encoding="utf-8"):
    r = json.loads(line)
    if r.get("error"):
        c[os.path.splitext(r["path"])[1].lower()] += 1
print(c)
PY
```

**Very slow**
Expect ~750 files/min. Raise `--workers` on an SSD; **lower** it on a
spinning disk or network share, where seek contention makes more threads
slower. USB 2 enclosures are usually the real bottleneck.

**It rescans unchanged files**
There is no incremental mode. But the probe is the expensive artifact: keep
it and re-run only `build` and `views`, which take seconds.

## Results look wrong

**Coverage dropped after adding music**
Check per genre before concluding anything. Composer, conductor and catalogue
fields legitimately do not apply to jazz, so adding jazz dilutes the
library-wide number while the classical figures are unchanged or better.
There is a snippet for this in [toolkit.md](toolkit.md).

**A date is wrong**
Check `date_source` in `tracks.csv`. `folder` means it came from the folder
name; `discography` from `vocab/*_sessions.json`; `tag` from the file, which
on a reissue is usually the reissue year. Fix the discography entry, or
adjudicate in the browser's Reconcile mode.

**Dates after the artist died**
Should be impossible — the lifetime clamp rejects anything outside
`active_from`/`active_to` in the profile. If you see one, that profile's
dates are wrong. Check `vocab/artists/<slug>.json`.

**A whole album has one date but spans several sessions**
Expected, and marked: `confidence: "first"` in the discography means the
first of several. Track-level assignment is the fix — see the Reconcile
section of [coltrane.md](coltrane.md).

**A conductor is wrong** (general mode)
Check the confidence first; `ambiguous` and `structural` are flagged as
uncertain by design. If a `high` value is wrong, add `"guarded": true` to
that entry in `vocab/conductors.json`, which forces a forename match. Then
`python tests/test_credits.py`.

**A new artist inherited another artist's bands**
Should be impossible — a loaded profile is authoritative even where a list is
empty. If it happens, the profile failed to load; check the JSON parses.

## Playlists

**Paths do not resolve**
A removable drive changed letter. Regenerate. When output and music are on
different drives the writers use absolute paths automatically, because
Windows has no relative path between `C:` and `E:`.

**Playlists are empty or missing**
`--min-tracks` defaults to 8 in the general fast path; on a small library try
4. In artist mode there is no floor.

**Some albums never appear**
Container releases — `.cue` + single-image rips and SACD `.iso` — have no
per-track files, so they cannot be in a playlist. No player can open them
either; that is a format limit, not a toolkit one.

## MusicBrainz

**Nothing returned, or HTTP 503**
Rate limiting. The client paces at 1 request/second and retries; wait a few
minutes. Existing `vocab/*.json` is untouched on failure.

**It matched the wrong release**
It should not — every candidate is validated against your tracklist, and
session facts are computed only from overlapping tracks. If you find one that
slipped through, the MBID is in `mb_conflicts.csv` so it can be checked.

**`mine.py --verify` rejects a real conductor**
Verification uses the MusicBrainz `disambiguation` field, which is
incomplete. It errs toward rejecting rather than inventing. Add the name to
`vocab/conductors.json` by hand; a refetch merges rather than overwrites.

## Starting over

Everything generated is regenerable — see [teardown.md](teardown.md).
`vocab/` is the only thing worth backing up.
