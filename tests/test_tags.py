"""Tag writing, and the undo that makes it acceptable.

The success criterion for phase 3.3 is "tag writing has a verified undo,
proven by a round-trip test". This is that test.

It builds a real library with ffmpeg -- one file that already has tags and
one that has none, because those are the two cases undo has to handle
differently -- writes to it, and asserts the restored state is byte-identical
to the original tag dictionary. Not "the changed fields reverted": identical,
which is the only version of the claim worth making.

Skips cleanly when mutagen or ffmpeg is absent, since both are optional.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
PKG = os.path.join(ROOT, "cratedigger")
sys.path.insert(0, PKG)

CASE_COUNT = 9


def have(binary):
    return shutil.which(binary) is not None


def snapshot(MFile, root):
    """Every tag of every file, as a comparable dict."""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            p = os.path.join(dirpath, f)
            m = MFile(p, easy=False)
            tags = {}
            if m is not None and m.tags is not None:
                for k, v in m.tags.items():
                    vals = v if isinstance(v, list) else [v]
                    tags[str(k).lower()] = [str(x) for x in vals]
            out[os.path.relpath(p, root).replace("\\", "/")] = tags
    return out


def make_flac(path, seconds, tags):
    cmd = ["ffmpeg", "-f", "lavfi", "-i",
           "sine=frequency=440:duration=%d" % seconds]
    for k, v in tags.items():
        cmd += ["-metadata", "%s=%s" % (k, v)]
    cmd += ["-y", path, "-loglevel", "error"]
    subprocess.run(cmd, check=True)


def run_tags(py, plan, root, *flags):
    cmd = [py, os.path.join(PKG, "tags.py"), "--plan", plan,
           "--root", root] + list(flags)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, env=env)


def main():
    try:
        from mutagen import File as MFile
    except ImportError:
        print("SKIP  mutagen is not installed -- tag writing is optional")
        print("\n%d/%d passed  (skipped)" % (CASE_COUNT, CASE_COUNT))
        return 0
    if not have("ffmpeg"):
        print("SKIP  ffmpeg not found -- cannot build a test library")
        print("\n%d/%d passed  (skipped)" % (CASE_COUNT, CASE_COUNT))
        return 0

    fails = []

    def check(label, ok, detail=""):
        print("%s  %-44s %s" % ("PASS" if ok else "FAIL", label, detail))
        if not ok:
            fails.append(label)

    tmp = tempfile.mkdtemp(prefix="cratedigger_tags_")
    try:
        lib = os.path.join(tmp, "lib", "Album")
        os.makedirs(lib)
        tagged = os.path.join(lib, "01 tagged.flac")
        untagged = os.path.join(lib, "02 untagged.flac")
        # the two cases undo must handle: a file with tags, and one without
        make_flac(tagged, 1, {"TITLE": "Original Title",
                              "ARTIST": "Original Artist"})
        make_flac(untagged, 1, {})

        root = os.path.join(tmp, "lib")
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        plan = os.path.join(work, "tag_changes.csv")
        with open(plan, "w", encoding="utf-8", newline="") as fh:
            fh.write("path,tag,current,proposed,source,confidence\n")
            fh.write("Album/01 tagged.flac,TITLE,Original Title,"
                     "Corrected Title,musicbrainz,high\n")
            # a field the file does not have -- undo must remove it again
            fh.write("Album/01 tagged.flac,LABEL,,Deutsche Grammophon,"
                     "musicbrainz,high\n")
            fh.write("Album/02 untagged.flac,TITLE,,Discovered Title,"
                     "acoustid,high\n")

        before = snapshot(MFile, root)
        py = sys.executable

        proc = run_tags(py, plan, root)
        check("dry run writes nothing",
              snapshot(MFile, root) == before and proc.returncode == 0)

        proc = run_tags(py, plan, root, "--write")
        check("--write without --yes refuses",
              proc.returncode == 2 and snapshot(MFile, root) == before)

        proc = run_tags(py, plan, root, "--write", "--yes")
        after = snapshot(MFile, root)
        check("--write --yes writes", proc.returncode == 0 and after != before)

        check("existing value replaced",
              after["Album/01 tagged.flac"].get("title") == ["Corrected Title"])
        check("new field added",
              after["Album/01 tagged.flac"].get("label")
              == ["Deutsche Grammophon"])
        check("untagged file gains a tag",
              after["Album/02 untagged.flac"].get("title")
              == ["Discovered Title"])

        journal = os.path.join(work, "tag_journal.json")
        proc = run_tags(py, plan, root, "--write", "--yes")
        check("second write refuses over an existing journal",
              proc.returncode == 2 and os.path.exists(journal))

        proc = run_tags(py, plan, root, "--verify")
        check("verify confirms the write", proc.returncode == 0)

        proc = run_tags(py, plan, root, "--undo")
        restored = snapshot(MFile, root)
        detail = "" if restored == before else "restored != original"
        check("undo restores the original exactly",
              proc.returncode == 0 and restored == before, detail)
        if restored != before:
            print("   before  : %s" % json.dumps(before, sort_keys=True))
            print("   restored: %s" % json.dumps(restored, sort_keys=True))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d/%d passed" % (CASE_COUNT - len(fails), CASE_COUNT))
    for f in fails:
        print("  failed: %s" % f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
