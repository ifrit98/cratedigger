"""Run every test module.

    python tests/run_tests.py            all suites
    python tests/run_tests.py credits    just one

Plain stdlib, no pytest, no runner to install -- the toolkit's zero-install
property applies to its tests too.
"""
import importlib
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, "cratedigger"))
sys.path.insert(0, os.path.join(HERE, os.pardir))
sys.path.insert(0, HERE)

SUITES = ["test_credits", "test_dates", "test_sessions", "test_scan",
          "test_portability", "test_tags", "test_export"]


def main():
    wanted = sys.argv[1:]
    suites = [s for s in SUITES
              if not wanted or any(w in s for w in wanted)]
    if not suites:
        print("no suite matched %s\n  available: %s"
              % (wanted, ", ".join(SUITES)))
        return 1

    failed, total_cases = [], 0
    t0 = time.time()
    for name in suites:
        print("=" * 62)
        print(name)
        print("=" * 62)
        try:
            mod = importlib.import_module(name)
        except Exception as e:  # noqa: BLE001
            print("  !! could not import: %s: %s" % (type(e).__name__, e))
            failed.append(name)
            continue
        rc = mod.main()
        total_cases += getattr(mod, "CASE_COUNT", 0)
        if rc:
            failed.append(name)
        print()

    print("=" * 62)
    dur = time.time() - t0
    if failed:
        print("FAILED: %s   (%.1fs)" % (", ".join(failed), dur))
        return 1
    print("all suites passed  --  %d suites, %s cases, %.1fs"
          % (len(suites), total_cases or "?", dur))
    return 0


if __name__ == "__main__":
    sys.exit(main())
