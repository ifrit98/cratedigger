"""Write tags into audio files. Opt-in, backed up, reversible.

    python tags.py --plan output/tag_changes.csv                 # dry run
    python tags.py --plan output/tag_changes.csv --write --yes
    python tags.py --plan output/tag_changes.csv --undo
    python tags.py --plan output/tag_changes.csv --verify

This is the only code in the toolkit that modifies your files, and it is
built to be the last thing you reach for and the easiest thing to reverse.

It does not decide anything. `apply.py --tags` produces `tag_changes.csv`;
this executes it. That separation is the point: the plan is a plain CSV you
can read, sort, and **delete rows from** before anything is written. Rows you
remove are never written.

Four rules, all mandatory:

1. **Opt-in per run.** `--write` alone is not enough; `--yes` is also
   required. There is no config setting that makes writing the default.
2. **A complete backup precedes any write.** Not just the fields being
   changed -- every tag the file had, so a restore can be exact. The journal
   is written and flushed to disk *before* the first file is opened for
   writing, and the run refuses to start if it cannot be written.
3. **`--undo` restores exactly.** It clears the tag block and rewrites the
   original in full, which also removes tags that were added. A restore that
   only reverts changed fields would leave the additions behind.
4. **Verification is a round trip.** `--verify` re-reads every file and
   compares against the journal, so "it worked" is a measurement.

Needs `mutagen` (`pip install cratedigger[tags]`). Without it, this refuses
to run rather than falling back to rewriting whole files with ffmpeg, which
is a far more dangerous way to change a tag.
"""
import argparse
import csv
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def load_mutagen():
    try:
        import mutagen
        from mutagen import File as MFile
        return mutagen, MFile
    except ImportError:
        return None, None


def read_tags(MFile, path):
    """Every tag on the file, as {KEY: [values]}. None if unreadable."""
    try:
        f = MFile(path, easy=False)
    except Exception:  # noqa: BLE001
        return None
    if f is None or f.tags is None:
        return {}
    out = {}
    try:
        for key, value in f.tags.items():
            if isinstance(value, list):
                out[str(key)] = [str(v) for v in value]
            else:
                out[str(key)] = [str(value)]
    except Exception:  # noqa: BLE001
        return None
    return out


def write_tags(MFile, path, changes):
    """Apply {KEY: value} to one file. Returns None on success, else why."""
    try:
        f = MFile(path, easy=False)
    except Exception as e:  # noqa: BLE001
        return "unreadable: %s" % e
    if f is None:
        return "unrecognised format"
    if f.tags is None:
        try:
            f.add_tags()
        except Exception as e:  # noqa: BLE001
            return "cannot add a tag block: %s" % e
    for key, value in changes.items():
        try:
            f.tags[key] = [value]
        except Exception as e:  # noqa: BLE001
            return "cannot set %s: %s" % (key, e)
    try:
        f.save()
    except Exception as e:  # noqa: BLE001
        return "save failed: %s" % e
    return None


def restore_tags(MFile, path, original):
    """Put the file back exactly: clear the block, rewrite what was there."""
    try:
        f = MFile(path, easy=False)
    except Exception as e:  # noqa: BLE001
        return "unreadable: %s" % e
    if f is None:
        return "unrecognised format"
    if f.tags is None:
        try:
            f.add_tags()
        except Exception as e:  # noqa: BLE001
            return "cannot add a tag block: %s" % e
    try:
        f.tags.clear()
        for key, values in original.items():
            f.tags[key] = list(values)
        f.save()
    except Exception as e:  # noqa: BLE001
        return "restore failed: %s" % e
    return None


def load_plan(path, root):
    """tag_changes.csv -> {abs_path: {TAG: value}}, preserving row order."""
    if not os.path.exists(path):
        sys.exit("no plan at %s\n  produce one with:  apply.py --tags" % path)
    plan, skipped = {}, 0
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            rel = (row.get("path") or "").strip()
            tag = (row.get("tag") or "").strip()
            value = row.get("proposed")
            if not rel or not tag or value is None:
                skipped += 1
                continue
            full = os.path.normpath(os.path.join(root, rel))
            plan.setdefault(full, {})[tag] = value
    return plan, skipped


def journal_path(plan_path):
    return os.path.join(os.path.dirname(os.path.abspath(plan_path)),
                        "tag_journal.json")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", default="output/tag_changes.csv",
                    help="the CSV from apply.py --tags")
    ap.add_argument("--root", required=True,
                    help="library root the plan's paths are relative to")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--yes", action="store_true",
                    help="required alongside --write; there is no config"
                         " setting that makes writing the default")
    ap.add_argument("--undo", action="store_true",
                    help="restore every file in the journal to its original"
                         " tags")
    ap.add_argument("--verify", action="store_true",
                    help="re-read every file and compare with the journal")
    ap.add_argument("--force", action="store_true",
                    help="allow a second write over an existing journal")
    args = ap.parse_args()

    mutagen, MFile = load_mutagen()
    if mutagen is None:
        print("mutagen is not installed, so tags cannot be written.\n")
        print("  pip install cratedigger[tags]")
        print("  pip install mutagen\n")
        print("This refuses rather than falling back to rewriting whole")
        print("files with ffmpeg, which is a more dangerous way to change")
        print("a tag. Nothing else in cratedigger needs it.")
        return 2

    jpath = journal_path(args.plan)

    # ---------------------------------------------------------------- undo
    if args.undo:
        if not os.path.exists(jpath):
            sys.exit("no journal at %s -- nothing to undo" % jpath)
        with open(jpath, encoding="utf-8") as fh:
            journal = json.load(fh)
        files = journal.get("files") or {}
        ok = failed = 0
        for rel, entry in sorted(files.items()):
            full = os.path.normpath(os.path.join(args.root, rel))
            if not os.path.exists(full):
                print("  missing: %s" % rel)
                failed += 1
                continue
            err = restore_tags(MFile, full, entry.get("before") or {})
            if err:
                print("  FAILED %s: %s" % (rel, err))
                failed += 1
            else:
                ok += 1
        print("\nrestored %d files, %d failed" % (ok, failed))
        if not failed:
            done = jpath + ".undone"
            os.replace(jpath, done)
            print("journal moved to %s" % done)
            print("your files are back to their original tags")
        return 1 if failed else 0

    # -------------------------------------------------------------- verify
    if args.verify:
        if not os.path.exists(jpath):
            sys.exit("no journal at %s -- nothing to verify" % jpath)
        with open(jpath, encoding="utf-8") as fh:
            journal = json.load(fh)
        good = bad = 0
        for rel, entry in sorted((journal.get("files") or {}).items()):
            full = os.path.normpath(os.path.join(args.root, rel))
            now = read_tags(MFile, full)
            if now is None:
                print("  unreadable: %s" % rel)
                bad += 1
                continue
            # Vorbis comment keys are case-insensitive by spec, and mutagen
            # stores them lowercased -- writing TITLE reads back as title.
            # Comparing case-sensitively reported every correct write as a
            # mismatch.
            folded = {k.lower(): v for k, v in now.items()}
            for tag, value in (entry.get("wrote") or {}).items():
                got = folded.get(tag.lower())
                if not got or got[0] != value:
                    print("  %s: %s is %r, expected %r"
                          % (rel, tag, got, value))
                    bad += 1
                    break
            else:
                good += 1
        print("\n%d files match the journal, %d do not" % (good, bad))
        return 1 if bad else 0

    # ---------------------------------------------------------------- plan
    plan, skipped = load_plan(args.plan, args.root)
    if skipped:
        print("%d unusable rows skipped" % skipped)
    if not plan:
        print("nothing to do -- the plan is empty")
        return 0

    n_values = sum(len(v) for v in plan.values())
    missing = [p for p in plan if not os.path.exists(p)]
    print("plan: %d tag values across %d files" % (n_values, len(plan)))
    if missing:
        print("  %d files in the plan do not exist and will be skipped"
              % len(missing))

    if not args.write:
        print("\nDRY RUN. Nothing was opened for writing.\n")
        for full in sorted(plan)[:10]:
            rel = os.path.relpath(full, args.root)
            for tag, value in sorted(plan[full].items()):
                print("  %-22s %-18s -> %s" % (rel[-22:], tag, value[:44]))
        if len(plan) > 10:
            print("  ... and %d more files" % (len(plan) - 10))
        print("\nTo write:   --write --yes")
        print("To reverse: --undo")
        return 0

    if not args.yes:
        print("\n--write requires --yes as well.\n")
        print("This is the only part of cratedigger that changes your files.")
        print("Re-run with both flags once you have read the plan:")
        print("  %s" % os.path.abspath(args.plan))
        return 2

    if os.path.exists(jpath) and not args.force:
        print("\nA journal already exists:\n  %s\n" % jpath)
        print("Writing again would overwrite the record of your ORIGINAL")
        print("tags, and the undo would then restore the wrong state.")
        print("Run --undo first, or pass --force if you are certain.")
        return 2

    # Back up everything first. The journal is complete and on disk before
    # any file is opened for writing -- if this loop is interrupted, the
    # files are untouched and the journal is merely unused.
    print("\nreading original tags ...")
    journal = {"written": None, "root": os.path.abspath(args.root),
               "plan": os.path.abspath(args.plan), "files": {}}
    targets = []
    for full in sorted(plan):
        if not os.path.exists(full):
            continue
        before = read_tags(MFile, full)
        if before is None:
            print("  skipping unreadable file: %s" % full)
            continue
        rel = os.path.relpath(full, args.root).replace("\\", "/")
        journal["files"][rel] = {"before": before, "wrote": plan[full]}
        targets.append((full, rel))

    if not targets:
        print("no writable files in the plan")
        return 1
    try:
        with open(jpath, "w", encoding="utf-8") as fh:
            json.dump(journal, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
    except OSError as e:
        sys.exit("cannot write the journal (%s) -- refusing to write tags" % e)
    print("backed up %d files -> %s" % (len(targets), jpath))

    ok = failed = 0
    for full, rel in targets:
        err = write_tags(MFile, full, plan[full])
        if err:
            print("  FAILED %s: %s" % (rel, err))
            failed += 1
        else:
            ok += 1

    journal["written"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(jpath, "w", encoding="utf-8") as fh:
        json.dump(journal, fh, ensure_ascii=False, indent=1)

    print("\nwrote %d files, %d failed" % (ok, failed))
    print("undo with:  --undo")
    print("check with: --verify")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
