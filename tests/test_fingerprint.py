"""The AcoustID path, which for a long time had never run against the
service at all.

When it finally did, three things were wrong and none of them announced
itself:

- a **rejected API key** came back as a 400, was treated as a throttle, and
  was retried three times per file. The one sentence that mattered --
  "invalid API key" -- was discarded, and the run reported "0 identified,
  12 deferred after server errors", which reads like the service was busy.
- the **join to the manifest** assumed tracks are nested under releases.
  The artist archive keeps them in a flat top-level list, so every
  identification was silently dropped and the run printed "acoustid 0",
  indistinguishable from a lookup that genuinely found nothing.
- the **tag plan was only written when it had rows**, leaving a previous
  run's plan on disk looking current.

Each of those gets a case here. No network: the transport is stubbed, since
what is being tested is how the response is interpreted.
"""
import io
import json
import os
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, os.pardir, "cratedigger")
sys.path.insert(0, PKG)

import apply as A          # noqa: E402
import fingerprint as F    # noqa: E402

CASE_COUNT = 18


class FakeResponse(object):
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, payload):
    body = io.BytesIO(json.dumps(payload).encode("utf-8"))
    return urllib.error.HTTPError("http://x", code, "err", {}, body)


def stub(monkey):
    """Replace the transport with something that never touches a network."""
    F.urllib.request.urlopen = monkey
    F._last[0] = 0.0


def main():
    fails = []

    def check(label, ok, detail=""):
        print("%s  %-52s %s" % ("PASS" if ok else "FAIL", label, detail))
        if not ok:
            fails.append(label)

    real = F.urllib.request.urlopen
    F.ACOUSTID_RATE = 0.0          # no need to be polite to a stub
    try:
        # ---- a refused key is fatal, not transient ----------------------
        calls = []

        def refuse(req, timeout=None):
            calls.append(1)
            raise http_error(400, {"status": "error",
                                   "error": {"code": 4,
                                             "message": "invalid API key"}})
        stub(refuse)
        try:
            F.acoustid_lookup("bad", 100, "fp")
            check("a 400 'invalid API key' raises Fatal", False, "no raise")
        except F.Fatal as e:
            check("a 400 'invalid API key' raises Fatal", True)
            check("the server's own words survive", "invalid API key" in str(e),
                  str(e))
        check("a refused key is not retried", len(calls) == 1,
              "%d attempts" % len(calls))

        # the same error, reported in the body of a 200
        def refuse_200(req, timeout=None):
            return FakeResponse({"status": "error",
                                 "error": {"code": 4, "message": "invalid"}})
        stub(refuse_200)
        try:
            F.acoustid_lookup("bad", 100, "fp")
            check("a code-4 body is fatal even with HTTP 200", False)
        except F.Fatal:
            check("a code-4 body is fatal even with HTTP 200", True)

        # ---- a throttle is transient, and never cached ------------------
        def throttle(req, timeout=None):
            raise http_error(503, {})
        stub(throttle)
        results, transient, err = F.acoustid_lookup("k", 100, "fp", retries=2)
        check("503 is transient", results is None and transient is True)
        check("503 explains itself", "503" in (err or ""), repr(err))

        # ---- a bad fingerprint is a real, cacheable refusal -------------
        def bad_fp(req, timeout=None):
            raise http_error(400, {"status": "error",
                                   "error": {"code": 3,
                                             "message": "invalid fingerprint"}})
        stub(bad_fp)
        results, transient, err = F.acoustid_lookup("k", 100, "fp")
        check("a bad fingerprint is cacheable, not transient",
              results is None and transient is False and "invalid" in (err or ""))

        # ---- a good answer ---------------------------------------------
        payload = {"status": "ok", "results": [
            {"id": "ac-1", "score": 0.6, "recordings": []},
            {"id": "ac-2", "score": 0.98, "recordings": [
                {"id": "rec-2", "title": "Naima",
                 "artists": [{"name": "John Coltrane"}],
                 "releasegroups": [{"id": "rg-2", "title": "Giant Steps"}]}]},
        ]}
        stub(lambda req, timeout=None: FakeResponse(payload))
        results, transient, err = F.acoustid_lookup("k", 100, "fp")
        best = F.best_result(results)
        check("the best scoring result with a recording wins",
              best and best["recording_id"] == "rec-2", json.dumps(best))
        check("a high score with no recording is not chosen",
              best and best["acoustid"] == "ac-2")
    finally:
        F.urllib.request.urlopen = real

    # ---- the join works for BOTH manifest shapes ------------------------
    nested = {"releases": [{"release_id": "rel1", "path": "A",
                            "tracks": [{"track_id": "t1", "release_id": "rel1",
                                        "path": "A/01.flac"}]}]}
    flat = {"releases": [{"release_id": "rel1", "path": "A"}],
            "tracks": [{"track_id": "t1", "release_id": "rel1",
                        "path": "A/01.flac"}]}
    check("iter_tracks reads the nested shape",
          [t["track_id"] for t in A.iter_tracks(nested)] == ["t1"])
    check("iter_tracks reads the flat shape",
          [t["track_id"] for t in A.iter_tracks(flat)] == ["t1"])

    ident = {"A/01.flac": {"recording_id": "rec-9", "score": 0.95,
                           "title": "Naima", "n_candidates": 1}}
    tmp = tempfile.mkdtemp(prefix="cratedigger_fp_")
    ids_path = os.path.join(tmp, "fingerprints_ids.json")
    with io.open(ids_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(ident))

    joined = []
    for manifest, name in ((nested, "nested"), (flat, "flat")):
        class Bag(dict):
            def __missing__(self, key):
                self[key] = A.Proposal(key[0], key[1])
                return self[key]
        props = Bag()
        joined.append(A.from_acoustid(props, manifest, ids_path))
    check("identifications join to a flat manifest", joined[1] == 1,
          "matched %d" % joined[1])
    check("and still join to a nested one", joined[0] == 1)
    check("index_entities finds flat tracks",
          "t1" in A.index_entities(flat))

    # ---- an empty plan must overwrite a previous one --------------------
    class Args(object):
        pass

    args = Args()
    args.manifest = os.path.join(tmp, "manifest.json")
    with io.open(args.manifest, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(flat))
    plan_path = os.path.join(tmp, "tag_changes.csv")

    row = {"state": "apply", "field": "title", "entity": "t1",
           "_value": "Naima", "source": "acoustid", "confidence": "high"}
    A.stage_tags(args, flat, [row])
    first = io.open(plan_path, encoding="utf-8-sig").read()
    check("a plan with changes is written", "Naima" in first)

    A.stage_tags(args, flat, [])
    second = io.open(plan_path, encoding="utf-8-sig").read()
    check("an empty run overwrites the previous plan",
          "Naima" not in second and second.strip().startswith("path,tag"),
          repr(second[:40]))

    # ---- every subcommand is actually dispatchable ----------------------
    import cli                                          # noqa: E402
    ap = cli.build_parser()
    choices = {}
    for action in ap._actions:
        if getattr(action, "choices", None) and action.dest == "cmd":
            choices = action.choices
    unwired = [name for name, sp in sorted(choices.items())
               if not callable(sp.get_default("fn"))]
    check("every subcommand dispatches to a callable", not unwired,
          "unwired: %s" % ", ".join(unwired))
    check("the CLI surface is not empty", len(choices) >= 15,
          "%d subcommands" % len(choices))

    print("\n%d/%d passed" % (CASE_COUNT - len(fails), CASE_COUNT))
    for f in fails:
        print("  failed: %s" % f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
