"""Guards on the portability claims the README makes.

CI proves the code runs on three platforms, but only after a push. These
cases fail locally and immediately, which is where a syntax slip should be
caught -- a 3.9-only construct imports fine on the developer's 3.11 and
breaks only on the oldest row of the matrix.
"""
import ast
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
PKG = os.path.join(ROOT, "cratedigger")
sys.path.insert(0, ROOT)

OLDEST = (3, 8)          # the floor advertised in README.md and ci.yml


def modules():
    return sorted(glob.glob(os.path.join(PKG, "*.py"))
                  + glob.glob(os.path.join(HERE, "*.py")))


# One case per module for the grammar check, plus one per top-level module
# for the drive-letter check. Computed rather than written down, so adding a
# module cannot silently go untested.
CASE_COUNT = len(modules()) + len(glob.glob(os.path.join(PKG, "*.py")))


def main():
    fails = []
    count = 0

    # 1. Every module must parse under the oldest supported grammar.
    for path in modules():
        count += 1
        name = os.path.relpath(path, ROOT).replace("\\", "/")
        try:
            with open(path, encoding="utf-8") as fh:
                ast.parse(fh.read(), name, feature_version=OLDEST)
            print("PASS  grammar %-46s 3.%d ok" % (name[:46], OLDEST[1]))
        except SyntaxError as e:
            fails.append(("grammar", name, "%s (line %s)" % (e.msg, e.lineno)))
            print("FAIL  grammar %-46s %s" % (name[:46], e.msg))
        except TypeError:
            # feature_version predates this interpreter's ast; skip rather
            # than report a pass we did not actually verify.
            print("SKIP  grammar %-46s no feature_version" % name[:46])

    # 2. A hardcoded drive letter is the failure mode that has actually
    #    happened here twice: build.py joined "D:\\" directly, and the
    #    general path lost its --root flag in a drive swap.
    drive = re.compile(r"""["'][A-Za-z]:[\/]""")
    for path in glob.glob(os.path.join(PKG, "*.py")):
        name = os.path.basename(path)
        count += 1
        with open(path, encoding="utf-8") as fh:
            hits = [(i, ln.strip()) for i, ln in enumerate(fh, 1)
                    if drive.search(ln)
                    and "default=" not in ln       # a documented default
                    and not ln.lstrip().startswith("#")
                    and '"""' not in ln]           # docstring examples
        if hits:
            fails.append(("drive", name, hits[0][1][:60]))
            print("FAIL  drive   %-46s line %d" % (name[:46], hits[0][0]))
        else:
            print("PASS  drive   %-46s no hardcoded root" % name[:46])

    print("\n%d/%d passed" % (count - len(fails), count))
    for kind, name, detail in fails:
        print("  %s %s: %s" % (kind, name, detail))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
