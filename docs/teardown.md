# Teardown and reset

What is safe to delete, what is not, and how to start over.

## The one rule

**Your music is never touched.** No command in this repo writes to, moves,
renames or deletes anything in your library. The audit verifies every path it
claims exists; it never modifies one.

Beyond that, exactly one directory matters:

| | |
|---|---|
| `vocab/` | **irreplaceable.** The discography, personnel tables, artist profiles, and the cached MusicBrainz and Wild harvests — roughly forty minutes of rate-limited fetching plus hand curation. Back this up. |
| everything else generated | disposable. Rebuilds from your audio in minutes. |

`clean` never touches `vocab/`, at any level.

## Preview first

```bash
cratedigger clean --dry-run
```

Lists what would go, with a total size, and removes nothing.

## Remove generated output

```bash
cratedigger clean
```

Removes the manifest, CSVs, playlists, browser and reconciliation reports.
**Keeps the raw probe**, so rebuilding is seconds rather than a re-scan:

```bash
cratedigger build && cratedigger views
```

## Remove everything generated

```bash
cratedigger clean all
```

Adds the probe. The next build needs a full re-scan of your library — minutes,
not seconds. The command warns before doing it.

## Remove one thing

```bash
cratedigger clean views       # just the playlists
cratedigger clean browser     # just the html
cratedigger clean reports     # just the reconciliation CSVs
cratedigger clean manifest    # manifest + its CSVs
cratedigger clean probe       # just the probe
```

## Confirmation

`clean` asks before removing. `--yes` skips the prompt, for scripts. When
stdin is not a terminal and `--yes` is absent it **cancels**, so a piped or
scheduled invocation cannot delete by accident.

In the panel, both red buttons confirm in a dialog that states what survives.

## Starting over on the same library

```bash
cratedigger clean all --yes
cratedigger all
```

## Pointing at a different library

Re-run init. It overwrites the config; nothing else moves.

```bash
cratedigger init --library "E:\Other Music" --output output-other
```

Use a separate `--output` per library, and both sets of results coexist.

## Removing an artist profile

There is deliberately no command for this — profiles are hand-curated
knowledge, and a stray flag should not be able to delete an evening's work.
Delete the files yourself:

```bash
rm vocab/artists/bill-evans.json
rm vocab/bill-evans_sessions.json vocab/bill-evans_personnel.json
```

If that artist is the active one, re-run init or pick another in the panel.

## Uninstalling

Delete the clone. Nothing is installed elsewhere: no packages, no services,
no registry entries, no files outside the repo and its output directory.

The one thing to rescue first is `vocab/`.

```bash
cp -r cratedigger/vocab ~/cratedigger-vocab-backup
rm -rf cratedigger
```

## What is in git

`cratedigger.json` and `output-*/` are gitignored — your config and your
generated artifacts are yours, not the repo's. `vocab/` **is** tracked,
because it is the curated knowledge the project is largely made of.
