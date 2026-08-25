# Install

There is very little to install. The toolkit is **standard library only** —
no `pip install`, no virtualenv required, no services.

| | needed for | required? |
|---|---|---|
| Python 3.8+ | everything | yes |
| FFmpeg (`ffprobe`) | reading tags from your files | for `scan` only |
| Network | MusicBrainz and Wild enrichers | optional |

## Python

```bash
python --version
```

3.8 or newer. If `python` is not found, try `python3`; on Windows try `py`.

<details>
<summary>Windows: the Store stub</summary>

A bare Windows install often ships a `python.exe` stub that opens the
Microsoft Store instead of running anything. If `python --version` opens the
Store, install real Python from [python.org](https://www.python.org/downloads/)
and tick **Add python.exe to PATH** in the installer.
</details>

## FFmpeg

Only `scan` needs it — it shells out to `ffprobe` to read tags and audio
properties. The panel, the model, the playlists and the browser all work
without it, so you can install it later if you only want to look around.

| | |
|---|---|
| Windows | `winget install Gyan.FFmpeg` |
| Windows (Chocolatey) | `choco install ffmpeg` |
| macOS | `brew install ffmpeg` |
| Debian / Ubuntu | `sudo apt install ffmpeg` |
| Fedora | `sudo dnf install ffmpeg` |
| Arch | `sudo pacman -S ffmpeg` |

**Reopen your terminal** afterwards so `PATH` picks it up, then confirm:

```bash
ffprobe -version
```

<details>
<summary>Installed but "not found"</summary>

Almost always a stale `PATH`. Close every terminal and open a fresh one. On
Windows, `where ffprobe` should print a path; if it prints nothing, add the
folder containing `ffprobe.exe` to your PATH and reopen again.

A manual FFmpeg download works too — unzip it anywhere and add its `bin`
folder to `PATH`. Nothing here cares where it lives, only that it is
callable.
</details>

## Get the code

```bash
git clone https://github.com/ifrit98/cratedigger
cd cratedigger
```

Or download the ZIP from the repo page and unpack it. There is no build step.

## Verify

```bash
python doctor.py
```

```
[  ok  ] Python 3.11.0  --  standard library only
[  ok  ] Coltrane toolchain complete  --  6 scripts
[  ok  ] vocab: discography  --  80 sessions
[  ok  ] vocab: personnel  --  9 lineups, 74 musicians
[  ok  ] ffprobe  --  ffprobe version N-117642 ...
```

Every line is `ok`, `warn` or `FAIL`. **`FAIL` blocks the pipeline** and the
line names the fix. `warn` is informational — "no manifest yet" is expected
before your first run.

Point it at your library to also size the job:

```bash
python doctor.py --root "D:\Music"
```

```
[  ok  ] archive  --  3,620 audio files in 546 folders
        full scan estimate: ~5 min at ~750 files/min
```

## Working offline

Everything except the two enrichers works with no network. `artists --create`
takes `--offline` and writes a profile with placeholder dates for you to fill
in by hand.

## Upgrading

```bash
git pull
```

`vocab/` is tracked, so a pull may bring vocabulary improvements. Your own
edits to it will show as a merge — keep yours if you have curated anything.
`cratedigger.json` and `output-*/` are gitignored and never touched by a
pull.

If a pull changes the model, rebuild — it costs seconds and needs no re-scan:

```bash
python cratedigger.py build && python cratedigger.py views
```

## Uninstalling

Delete the clone. Nothing is installed outside it: no packages, no services,
no registry entries. Rescue `vocab/` first if you have curated it — see
[teardown.md](teardown.md).

## Trouble

[troubleshooting.md](troubleshooting.md) covers the common failures by
symptom.
