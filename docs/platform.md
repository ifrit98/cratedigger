# Platform support

**Status: developed and tested on Windows 11 / Python 3.11. Everything else
is now covered by CI but has not been used in anger against a real library.**

This page records what is actually known, what is merely believed, and where
to look first when something breaks on a platform that isn't Windows.

## What CI covers

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs the 130-case
suite on Linux, macOS and Windows across Python 3.8–3.12, with `ffmpeg`
installed so `test_scan.py` exercises real probing rather than skipping.

A second job imports every module and calls `--help` on every entry point on
Linux. That job exists because the failures most likely to hit a non-Windows
user are **import-time**: a malformed regex or a bad `os.name` assumption
fails before any test gets a chance to run.

What CI does **not** cover: a real music library. The runners have no
40,000-file tree, so the scale-dependent behaviour — incremental scan over a
slow USB volume, playlist generation across drives — is verified only on
Windows.

## Known platform-dependent code

There are exactly three places that branch on the operating system, all in
the control panel and all with a working non-Windows path:

| location | Windows | elsewhere |
|---|---|---|
| `cratedigger_ui.py:106` | enumerates drive letters `C:`–`Z:` as picker roots | offers `/` |
| `cratedigger_ui.py:263` | `os.startfile` | `open` (macOS) / `xdg-open` |
| `views.py`, `playlists.py` | falls back to absolute paths when no relative path exists between two drives | not reachable — one root |

The third is worth explaining: on Windows there is **no relative path**
between `C:` and `L:`, and `os.path.relpath` raises `ValueError` rather than
returning something useless. Both playlist writers catch it and emit absolute
paths. On a single-root filesystem the exception cannot occur, so the
fallback is dead code there rather than wrong code.

## Things that are portable by construction

- **Extensions are matched case-folded** (`os.path.splitext(f)[1].lower()`),
  so `.FLAC` is found on a case-sensitive filesystem.
- **Manifest paths are stored with forward slashes**, normalised on write.
- **Playlists are written UTF-8 as `.m3u8`**, which is the encoding the
  extension denotes; `.m3u` has no defined encoding and is avoided.
- **No compiled dependencies.** Standard library only, plus `ffprobe` as an
  external binary.

## Things to check first on a non-Windows library

1. **Case-colliding folders.** `Bach/` and `bach/` are one directory on
   Windows and two on Linux. The manifest keys on path, so they become two
   releases. Not wrong, but it will look surprising.
2. **`ffprobe` on `PATH`.** Run `python doctor.py` first; it checks this
   explicitly rather than failing 4,000 files into a scan.
3. **Paths over 260 characters** are a Windows problem the other platforms
   do not have — so a tree built on Linux may not scan on Windows. The
   reverse is safe.
4. **Symlinks.** The scanner follows the tree as `os.walk` presents it and
   does not detect symlink loops. Rare on a music drive, but Linux users are
   likelier to have them.

## The open question: what "supported" should mean

CI proves the code *runs* on three platforms. It does not prove the tool is
*good* on them, and the gap matters for anything shipped as a product:

- The control panel's folder picker is modelled on drive letters. On Linux
  the useful starting points are `~`, `/mnt` and `/media`, not `/`.
- Playlist consumers differ. foobar2000 on Windows is the reference target;
  Rhythmbox, Quod Libet and Swinsian have not been tested against the
  generated `.m3u8` files.
- File-manager integration (`open` / `xdg-open`) is best-effort and silently
  does nothing in a headless session.

Until someone runs this against a real library on macOS or Linux, the honest
claim is **"runs everywhere, proven on Windows."**
