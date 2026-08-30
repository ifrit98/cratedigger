# The control panel

```bash
cratedigger serve
```

A single page on `127.0.0.1:8420` that does what the CLI does, for people who
would rather not memorise flags.

## Why this one needs a server

The archive browser (`coltrane-browser.html`) is a static file with the data
baked in — a `file://` page is enough because it only *reads*. The control
panel has to *run* the pipeline and list directories on your disk, and a page
opened from a file can do neither. Hence a small stdlib HTTP server.

**It binds to `127.0.0.1` only and executes local commands by design.** There
is no authentication because there is no listener beyond this machine. Do not
expose it to a network.

## What is on it

**1 · library** — a server-side folder browser. A web page cannot read a real
filesystem path, so the picking happens on the server: walk your drives, see
the audio count in each folder, click *use this folder*.

**2 · artist profile** — every profile with its life span, era and venue
counts, and session total. Click one to make it active; type a name to create
one, and the MusicBrainz id and life dates are fetched for you.

**3 · run** — Run everything, or any single stage: Scan, Build, Views,
Browser, Audit, and the three enrichers. Buttons lock while a job runs.

**state** — ffprobe presence, what is built and how old it is, and the
manifest counts. Buttons to open the archive browser or the output folder in
your file manager.

The right-hand pane streams the job's output live, the same text the CLI
prints, with elapsed time and an exit status.

## Options

```bash
cratedigger serve --port 9000 --no-open
```

## Limits

- One job at a time, deliberately: the stages share an output directory.
- Closing the page does not stop a running job; it reattaches when you
  reload, because the job lives in the server.
- Stopping the server (Ctrl-C) does kill a running job.
- Long scans stream thousands of lines; the log keeps the most recent 4,000.

## First run

With no `cratedigger.json` the panel says so, and dims every step that would
not work yet. Point step 1 at a music folder, press **Set up**, and the rest
of the panel comes alive — the path is written once and every later step
reads it.

## Progress survives a reload

Job state lives on the server, not in the page. Close the tab mid-scan,
reopen it, and the log is still there with the stage and its status; the
client replays from the beginning of the run. Nothing is lost by refreshing,
and nothing is duplicated.

## Editing vocabulary

The vocabulary card lists every file in `vocab/` with its entry count and
opens it in an editor. Invalid JSON is refused on both sides — in the page
before the request, and on the server before the write — so a typo cannot
truncate a discography.

The first save of any file keeps a `.bak` beside it. Vocabulary is the one
thing a rebuild cannot regenerate from your files, which is the whole reason
it is worth editing carefully.

> The endpoint that writes these files never joins a caller-supplied name to
> a path. A name must appear in the listing the server itself produced, so
> `../../cli.py` is not refused by a check that could be outwitted — it
> simply is not in the list.

## Tag writing is not armed here

The tags card can plan, preview, verify and **undo**, but it cannot write.
Arming a filesystem write behind a button in a web page is exactly the
ceremony that phase 3.3 exists to prevent, so the write stays a deliberate
terminal command:

```bash
cratedigger tags --write --yes
```
