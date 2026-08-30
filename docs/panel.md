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
