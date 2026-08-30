"""Score findings by confidence and, when they are certain, apply them.

    python apply.py --manifest output/library.json                # dry run
    python apply.py --manifest output/library.json --apply
    python apply.py --manifest output/library.json --tags         # dry run

Everything before this module produces *candidates*. This one decides which
are certain enough to stop asking a human about, and writes those into the
manifest with their source and confidence recorded beside them.

Three rules govern the whole thing:

1. **A contested field is never applied.** If two sources disagree it goes to
   the decision sheet, however strong either one is.
2. **Corroboration outranks strength.** Two independent sources agreeing at
   0.8 is better evidence than one source at 0.99, because the failure modes
   of a duration match and an acoustic fingerprint are unrelated.
3. **Nothing touches your audio files.** `--apply` writes the manifest, which
   is regenerable from the files at any time. Tag writing is dry-run only and
   has no enabled write path -- see the note at `stage_tags`.

Field naming follows the convention credits.py established: a value applied
to `label` records `label_source` and `label_confidence` beside it.
"""
import argparse
import collections
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VOCAB = os.path.join(HERE, "vocab")

# Auto-apply needs this much strength from a single uncorroborated source.
# Deliberately high: the cost of a wrong value is that it looks authoritative
# and stops being questioned, which is worse than a blank field.
DEFAULT_THRESHOLD = 0.95

# Corroboration from two independent sources is accepted lower, because the
# ways a duration match and a fingerprint fail have nothing in common.
CORROBORATED_THRESHOLD = 0.75


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


class Proposal(object):
    """Every value any source suggested for one (entity, field)."""

    def __init__(self, key, field):
        self.key = key
        self.field = field
        self.claims = []          # (value, source, strength)

    def add(self, value, source, strength):
        if value in (None, "", []):
            return
        self.claims.append((value, source, float(strength)))

    def verdict(self, threshold):
        """(value, confidence_label, source_string, state)."""
        if not self.claims:
            return None, None, None, "none"
        by_value = collections.defaultdict(list)
        for value, source, strength in self.claims:
            by_value[str(value)].append((value, source, strength))

        ranked = sorted(
            by_value.items(),
            key=lambda kv: (len({s for _v, s, _st in kv[1]}),
                            max(st for _v, _s, st in kv[1])),
            reverse=True)
        top_key, top_claims = ranked[0]
        value = top_claims[0][0]
        sources = sorted({s for _v, s, _st in top_claims})
        best = max(st for _v, _s, st in top_claims)

        if len(ranked) > 1:
            # Somebody disagrees. No score rescues this; a human decides.
            return value, "contested", "+".join(sources), "contested"

        if len(sources) > 1:
            state = "apply" if best >= CORROBORATED_THRESHOLD else "review"
            return value, "corroborated", "+".join(sources), state
        state = "apply" if best >= threshold else "review"
        label = "high" if best >= threshold else "medium" if best >= 0.7 \
            else "low"
        return value, label, sources[0], state


# --------------------------------------------------------------------------
# gathering what the enrichers found


def from_musicbrainz(props, manifest):
    """Accepted release matches from general_mb.py.

    Note what is deliberately absent: the release date. A MusicBrainz release
    date is that pressing's date, not the recording's, so applying it would
    overwrite a correct recording year with a reissue year. That distinction
    cost a wrong report earlier; it is not repeated here.
    """
    cache = load_json(os.path.join(VOCAB, "general_mb_cache.json"), {})
    by_path = {r["path"]: r for r in manifest.get("releases", [])}
    n = 0
    for path, entry in cache.items():
        acc = entry.get("accepted")
        if not acc or path not in by_path:
            continue
        rel = by_path[path]
        strength = float(acc.get("ratio") or 0)
        rid = rel["release_id"]
        for field, value in (("label", acc.get("label")),
                             ("catalog_number", acc.get("catalog_number")),
                             ("barcode", acc.get("barcode")),
                             ("musicbrainz_albumid", acc.get("mbid"))):
            if value:
                props[(rid, field)].add(value, "musicbrainz", strength)
                n += 1

        # Per-recording work ids: the point of the exercise. A work id is the
        # stable identity that catalogue numbers cannot supply, so the same
        # piece in three differently-named folders finally collapses to one.
        ours = sorted(rel.get("tracks", []),
                      key=lambda t: (t.get("disc_number") or 0,
                                     t.get("track_number") or 0))
        theirs = acc.get("tracks") or []
        if len(ours) == len(theirs):
            for track, mb in zip(ours, theirs):
                if mb.get("work_id"):
                    # Deliberately NOT `work_id`. That field is our own
                    # locally-derived grouping key, and every track already
                    # has one -- proposing a replacement would put 954 rows
                    # into "would overwrite" and the guard would refuse them
                    # all, which is the guard working correctly and the
                    # fragmentation fix never landing.
                    #
                    # They are two different identities and deserve two
                    # fields. MUSICBRAINZ_WORKID is also what Picard writes,
                    # so the name is not invented here.
                    props[(track["track_id"], "musicbrainz_workid")].add(
                        mb["work_id"], "musicbrainz", strength)
                    props[(track["track_id"], "musicbrainz_worktitle")].add(
                        mb.get("work_title"), "musicbrainz", strength)
                    n += 1
    return n


def from_acoustid(props, manifest, ids_path):
    """Fingerprint identifications, keyed by track path."""
    ident = load_json(ids_path, {})
    if not ident:
        return 0
    by_path = {}
    for rel in manifest.get("releases", []):
        for t in rel.get("tracks", []):
            if t.get("path"):
                by_path[t["path"].replace("\\", "/")] = t
    n = 0
    for path, best in ident.items():
        t = by_path.get(path.replace("\\", "/"))
        if not t or not best or not best.get("recording_id"):
            continue
        strength = float(best.get("score") or 0)
        props[(t["track_id"], "musicbrainz_recordingid")].add(
            best["recording_id"], "acoustid", strength)
        if best.get("title"):
            props[(t["track_id"], "title")].add(best["title"], "acoustid",
                                                strength)
        n += 1
    return n


# --------------------------------------------------------------------------


def index_entities(manifest):
    ent = {}
    for rel in manifest.get("releases", []):
        ent[rel["release_id"]] = rel
        for t in rel.get("tracks", []):
            ent[t["track_id"]] = t
    return ent


def stage_score(args, manifest):
    class Bag(dict):
        def __missing__(self, key):
            self[key] = Proposal(key[0], key[1])
            return self[key]

    props = Bag()
    n_mb = from_musicbrainz(props, manifest)
    ids_path = args.ids or os.path.join(
        os.path.dirname(os.path.abspath(args.manifest)),
        "fingerprints_ids.json")
    n_ac = from_acoustid(props, manifest, ids_path)
    print("claims gathered:  musicbrainz %d, acoustid %d" % (n_mb, n_ac))
    if not n_ac:
        print("  (no fingerprint identifications -- see fingerprint.py)")

    entities = index_entities(manifest)
    rows, counts = [], collections.Counter()
    for (key, field), p in sorted(props.items()):
        ent = entities.get(key)
        if ent is None:
            continue
        value, label, source, state = p.verdict(args.threshold)
        if value is None:
            continue
        current = ent.get(field)
        if current not in (None, "", []) and str(current) == str(value):
            counts["already correct"] += 1
            continue
        if current not in (None, "", []) and not args.overwrite:
            # We have a value already and no source disagreement was found;
            # replacing it silently is exactly the behaviour this project
            # exists to avoid.
            state = "review"
            label = "would overwrite"
        counts[state] += 1
        rows.append({"state": state, "confidence": label, "field": field,
                     "current": "" if current is None else str(current)[:60],
                     "proposed": str(value)[:60], "source": source,
                     "entity": key,
                     "path": (ent.get("path") or "")[:70],
                     # The display columns above are truncated for the CSV.
                     # Applying must use the real value -- writing the
                     # 60-character form into the manifest silently corrupted
                     # every work title longer than that.
                     "_value": value})
    return rows, counts


def write_sheet(rows, out_dir):
    path = os.path.join(out_dir, "apply_decisions.csv")
    if not rows:
        return path
    order = {"contested": 0, "review": 1, "apply": 2}
    cols = [c for c in rows[0].keys() if not c.startswith("_")]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: (order.get(x["state"], 9),
                                             x["field"], x["path"])):
            w.writerow(r)
    return path


def stage_apply(args, manifest, rows):
    entities = index_entities(manifest)
    applied = 0
    for r in rows:
        if r["state"] != "apply":
            continue
        ent = entities.get(r["entity"])
        if ent is None:
            continue
        ent[r["field"]] = r["_value"]
        ent[r["field"] + "_source"] = r["source"]
        ent[r["field"] + "_confidence"] = r["confidence"]
        applied += 1

    backup = args.manifest + ".before-apply"
    if not os.path.exists(backup):
        with open(args.manifest, encoding="utf-8") as fh:
            original = fh.read()
        with open(backup, "w", encoding="utf-8") as fh:
            fh.write(original)
    with open(args.manifest, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print("\napplied %d fields to %s" % (applied, args.manifest))
    print("previous manifest kept at %s" % backup)
    return applied


# --------------------------------------------------------------------------
# tag writing -- dry run only


# Manifest field -> the Vorbis Comment name Picard uses. Only fields whose
# mapping is unambiguous appear here; a guess in this table would be written
# into somebody's files.
TAG_MAP = {
    "title": "TITLE",
    "label": "LABEL",
    "catalog_number": "CATALOGNUMBER",
    "barcode": "BARCODE",
    "musicbrainz_albumid": "MUSICBRAINZ_ALBUMID",
    "musicbrainz_recordingid": "MUSICBRAINZ_TRACKID",
    "musicbrainz_workid": "MUSICBRAINZ_WORKID",
    "conductor": "CONDUCTOR",
}


def stage_tags(args, manifest, rows):
    """Show every tag write that would happen, and back up what it would
    replace. There is no code path here that writes to an audio file, and
    that is deliberate: tag writing is phase 3.3, and its requirements --
    per-run opt-in, a verified undo, a round-trip test -- are not met yet.
    Producing the plan and the backup now is what makes those testable.
    """
    probe = os.path.join(os.path.dirname(os.path.abspath(args.manifest)),
                         "raw_probe.jsonl")
    current = {}
    if os.path.exists(probe):
        with open(probe, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("tags"):
                    current[rec["path"].replace("\\", "/")] = rec["tags"]

    entities = index_entities(manifest)
    changes, backup = [], {}
    for r in rows:
        if r["state"] != "apply" or r["field"] not in TAG_MAP:
            continue
        ent = entities.get(r["entity"]) or {}
        path = (ent.get("path") or "").replace("\\", "/")
        if not path:
            continue
        tag = TAG_MAP[r["field"]]
        have = (current.get(path) or {}).get(tag)
        if have is not None and str(have) == str(r["_value"]):
            continue
        changes.append({"path": path, "tag": tag,
                        "current": "" if have is None else str(have)[:60],
                        "proposed": str(r["_value"]), "source": r["source"],
                        "confidence": r["confidence"]})
        if path in current:
            backup[path] = current[path]

    out_dir = os.path.dirname(os.path.abspath(args.manifest))
    plan = os.path.join(out_dir, "tag_changes.csv")
    if changes:
        with open(plan, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(changes[0].keys()))
            w.writeheader()
            for c in sorted(changes, key=lambda x: (x["path"], x["tag"])):
                w.writerow(c)
    bpath = os.path.join(out_dir, "tag_backup.json")
    with open(bpath, "w", encoding="utf-8") as fh:
        json.dump({"_comment": "Original tags for every file the tag plan "
                               "would touch. Written before any write path "
                               "exists, so an undo can be tested against it.",
                   "files": backup}, fh, ensure_ascii=False, indent=1)

    files = len({c["path"] for c in changes})
    print("\ntag plan (DRY RUN -- no file was opened for writing)")
    print("  %d tag values across %d files" % (len(changes), files))
    print("  -> %s" % plan)
    print("  -> %s   (%d files backed up)" % (bpath, len(backup)))
    print("\nNo write path exists yet. Tag writing is phase 3.3 and needs a")
    print("verified undo first; this plan and backup are what make that")
    print("testable.")
    return len(changes)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default="output/library.json")
    ap.add_argument("--ids", default=None,
                    help="fingerprints_ids.json from fingerprint.py --lookup")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--apply", action="store_true",
                    help="write high-confidence values into the manifest")
    ap.add_argument("--overwrite", action="store_true",
                    help="also replace values we already have")
    ap.add_argument("--tags", action="store_true",
                    help="show the tag writes this would imply (dry run)")
    args = ap.parse_args()

    manifest = load_json(args.manifest, None)
    if manifest is None:
        sys.exit("cannot read %s" % args.manifest)

    rows, counts = stage_score(args, manifest)
    out_dir = os.path.dirname(os.path.abspath(args.manifest))

    print("\n%-16s %s" % ("apply", counts.get("apply", 0)))
    print("%-16s %s" % ("review", counts.get("review", 0)))
    print("%-16s %s" % ("contested", counts.get("contested", 0)))
    print("%-16s %s" % ("already correct", counts.get("already correct", 0)))

    sheet = write_sheet(rows, out_dir)
    if rows:
        print("\n-> %s" % sheet)

    if args.apply:
        stage_apply(args, manifest, rows)
    else:
        print("\nDry run. Nothing was written. Add --apply to write the")
        print("%d 'apply' rows into the manifest." % counts.get("apply", 0))

    if args.tags:
        stage_tags(args, manifest, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
