"""Mine session data from David Wild's online Coltrane discography.

    python coltrane_wild.py --fetch      # download + parse -> vocab/
    python coltrane_wild.py --report     # reconcile against our manifest

Source: http://www.wildmusic-jazz.com/  -- the web edition of David Wild,
*The Recordings of John Coltrane: A Discography* (2nd ed., Wildmusic, 1979).

Why this source beats the alternatives: Wild keys every session by a
**YYMMDD session number**, so the date is explicit rather than inferred, and
each entry carries full personnel with instruments, the studio or venue, the
engineer, and every tune with composer and issue. That is precisely the
tier our model calls a session.

We extract factual session data for local cataloguing and cite the session
number and source URL on every record. Requests are rate limited and the
whole discography is ten pages.
"""
import argparse
import collections
import csv
import html as htmllib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
VOCAB = os.path.join(HERE, "vocab")
OUT_JSON = os.path.join(VOCAB, "coltrane_wild_sessions.json")
BASE = "http://www.wildmusic-jazz.com/"
UA = "Mozilla/5.0 (compatible; personal-library-cataloging/1.0)"
RATE = 1.5
_last = [0.0]

# Shared tunes required before a Wild session may be matched to a release.
# Ratio alone is not enough: a three-tune live set overlaps a dozen sessions
# at 100% because the repertoire barely changed between 1961 and 1965.
MIN_TUNE_OVERLAP = 4

YEAR_PAGES = [f"jcdisc{yy}.htm" for yy in
              ("53", "54", "55", "56", "57", "58", "59",
               "60", "61", "62", "63", "64", "65", "66", "67")]

INSTRUMENTS = {
    "ts": "tenor sax", "ss": "soprano sax", "as": "alto sax",
    "bs": "baritone sax", "cl": "clarinet", "bcl": "bass clarinet",
    "fl": "flute", "tp": "trumpet", "tb": "trombone", "frh": "french horn",
    "p": "piano", "b": "bass", "dr": "drums", "d": "drums",
    "perc": "percussion", "g": "guitar", "vib": "vibraphone",
    "vcl": "vocal", "org": "organ", "tuba": "tuba", "euphonium": "euphonium",
    "arr": "arranger", "cond": "conductor", "harp": "harp", "vln": "violin",
}


def get(url, retries=3):
    for attempt in range(retries):
        wait = RATE - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as fh:
                raw = fh.read()
                enc = fh.headers.get_content_charset() or "utf-8"
                return raw.decode(enc, errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (attempt + 1))
        except Exception:  # noqa: BLE001
            time.sleep(2 * (attempt + 1))
    return None


def flatten(h):
    """HTML -> newline-preserving text, so field labels stay separable."""
    h = re.sub(r"<br\s*/?>", "\n", h, flags=re.I)
    h = re.sub(r"</?(p|tr|div|table|td|li)[^>]*>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", "", h)
    h = htmllib.unescape(h)
    h = h.replace("’", "'").replace("“", '"').replace("”", '"')
    h = re.sub(r"[ \t\xa0]+", " ", h)
    return re.sub(r"\n{3,}", "\n\n", h)


def session_date(num):
    """YYMMDD -> ISO. Coltrane's career makes the century unambiguous."""
    if not re.fullmatch(r"\d{6}", num):
        return None
    yy, mm, dd = int(num[:2]), int(num[2:4]), int(num[4:6])
    year = 1900 + yy
    if not (1940 <= year <= 1975 and 1 <= mm <= 12 and 1 <= dd <= 31):
        return None
    return f"{year:04d}-{mm:02d}-{dd:02d}"


def parse_personnel(text):
    """'Miles Davis, tp; Hank Mobley, John Coltrane, ts; ...' -> records.

    Instruments are shared across a run of names: 'Hank Mobley, John
    Coltrane, ts' credits both men on tenor.
    """
    out = []
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(",") if p.strip()]
        names, instrs = [], []
        for p in parts:
            key = p.lower().strip(". ")
            # Wild capitalises people and leaves instruments lowercase, which
            # is the only reliable separator: the abbreviation list alone
            # misses spelled-out entries like 'oboe', 'contrabassoon' and
            # 'tenor saxophone', which then get credited as band members.
            is_instr = (key in INSTRUMENTS
                        or not re.search(r"[A-Z]", p)
                        or key in ("bells", "percussion", "drums"))
            if is_instr:
                instrs.append(INSTRUMENTS.get(key, key))
            else:
                names.append(p)
        for n in names:
            n = re.sub(r"\s+", " ", n).strip(" .")
            if len(n) > 2 and not n.lower().startswith(("same", "add ",
                                                        "omit")):
                out.append({"name": n,
                            "instrument": ", ".join(instrs) or None})
    return out


TUNE_RE = re.compile(
    r"^\s*([a-z]{1,2})\.\s*\"([^\"]+)\"\s*(?:\(([^)]*)\))?\s*"
    r"(\d{1,2}:\d{2})?\s*(.*)$", re.I)


def parse_session(num, block):
    """One session block -> a structured record."""
    date = session_date(num)
    if not date:
        return None
    lines = [l.rstrip() for l in block.split("\n")]

    group = None
    for l in lines[:10]:
        cand = l.strip()
        if not cand or cand.lower().startswith(
                ("personnel", "location", "date", "engineer", "note")):
            continue
        # the band line is the shouted one: 'JOHN COLTRANE QUARTET:'
        letters = re.sub(r"[^A-Za-z]", "", cand)
        if letters and cand.rstrip(":").isupper() and len(letters) > 3:
            group = cand.rstrip(":").strip()
            break

    def field(label, stop):
        m = re.search(label + r"\s*:(.*?)(?=" + stop + r"|$)",
                      block, re.I | re.S)
        return re.sub(r"\s+", " ", m.group(1)).strip(" .") if m else None

    personnel_raw = field("Personnel", r"Location\s*:|Date\s*:|Engineer\s*:")
    location = field("Location", r"Date\s*:|Engineer\s*:|^\s*[a-z]\.")
    engineer = field("Engineer", r"^\s*[a-z]{1,2}\.|NOTE|$")

    tunes = []
    for l in lines:
        m = TUNE_RE.match(l)
        if m:
            letter, title, composer, dur, tail = m.groups()
            tunes.append({
                "index": letter.lower(),
                "title": re.sub(r"\s+", " ", title).strip(),
                "composer": re.sub(r"\s+", " ", composer).strip()
                            if composer else None,
                "duration": dur,
                "issue": re.sub(r"\s+", " ", tail).strip() or None,
            })

    note = None
    m = re.search(r"NOTE\s*:?(.*?)(?=\n\s*\n|$)", block, re.I | re.S)
    if m:
        note = re.sub(r"\s+", " ", m.group(1)).strip()[:300]

    if location:
        location = location.replace("' '", "'")
        location = re.sub(r"^[\s']+|[\s']+$", "", location)
        location = location.replace("',", ",")
    return {
        "session": num,
        "date": date,
        "group": group,
        "personnel": parse_personnel(personnel_raw) if personnel_raw else [],
        "location": location,
        "engineer": engineer or None,
        "tunes": tunes,
        "note": note,
        "source": "David Wild, The Recordings of John Coltrane: "
                  "A Discography (2nd ed., Wildmusic 1979), web edition",
    }


def fetch_all():
    os.makedirs(VOCAB, exist_ok=True)
    sessions, pages_ok = {}, []
    for page in YEAR_PAGES:
        h = get(BASE + page)
        if not h:
            print(f"  {page}: not present")
            continue
        anchors = re.findall(r'<a\s+name\s*=\s*"?(\d{6})"?', h, re.I)
        text = flatten(h)
        # split the flattened text on session numbers appearing alone
        marks = [(m.start(), m.group(1)) for m in
                 re.finditer(r"(?m)^\s*(\d{6})\s*$", text)]
        got = 0
        for i, (pos, num) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
            block = text[pos:end]
            if len(block) < 60:          # summary-table row, not an entry
                continue
            rec = parse_session(num, block)
            if rec and (rec["personnel"] or rec["tunes"]):
                rec["source_url"] = BASE + page + "#" + num
                sessions[num] = rec
                got += 1
        pages_ok.append(page)
        print(f"  {page}: {len(anchors)} anchors, {got} sessions parsed")

    out = {
        "_comment": "Session data mined from David Wild's online Coltrane "
                    "discography. Facts only (dates, personnel, locations, "
                    "tune listings), each citing its session number and "
                    "source URL. Wild's session number is YYMMDD.",
        "_source": "http://www.wildmusic-jazz.com/",
        "_citation": "David Wild, The Recordings of John Coltrane: A "
                     "Discography, 2nd ed., Wildmusic, 1979 (web edition)",
        "_fetched": time.strftime("%Y-%m-%d"),
        "_pages": pages_ok,
        "sessions": [sessions[k] for k in sorted(sessions)],
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

    s = out["sessions"]
    print(f"\n{len(s)} sessions parsed from {len(pages_ok)} pages")
    if s:
        print(f"  range: {s[0]['date']} .. {s[-1]['date']}")
        print(f"  with personnel : {sum(1 for x in s if x['personnel'])}")
        print(f"  with location  : {sum(1 for x in s if x['location'])}")
        print(f"  total tunes    : {sum(len(x['tunes']) for x in s)}")
    print(f"-> {OUT_JSON}")


def norm_tune(s):
    s = (s or "").lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"\b(take|alt|alternate|the|a|an)\b", " ", s)
    s = s.replace("favourite", "favorite")
    return re.sub(r"[^a-z0-9]", "", s)


def report(manifest_path):
    wild = json.load(open(OUT_JSON, encoding="utf-8"))["sessions"]
    if not os.path.exists(manifest_path):
        sys.exit(f"no manifest at {manifest_path}")
    man = json.load(open(manifest_path, encoding="utf-8"))

    by_date = {w["date"]: w for w in wild}
    tune_index = collections.defaultdict(list)
    for w in wild:
        for t in w["tunes"]:
            tune_index[norm_tune(t["title"])].append(w)

    # our tracks per release, so a release can be matched to Wild by tunes
    tracks_by_rel = collections.defaultdict(set)
    for t in man["tracks"]:
        if t.get("tune"):
            tracks_by_rel[t["release_id"]].add(norm_tune(t["tune"]))

    rows = []
    confirmed = corrected = supplied = nomatch = 0
    for r in man["releases"]:
        d = r.get("recording_date")
        ours = tracks_by_rel.get(r["release_id"], set())

        # Score every Wild session by how much of our tracklist it explains.
        #
        # Tune overlap alone is a weak signal for this artist: Coltrane
        # played the same repertoire nightly, so any three-tune live set
        # matches a dozen sessions at 100%. Require a substantial number of
        # shared tunes, not merely a high ratio, and let the venue vote.
        our_place = norm_tune((r.get("venue") or "") + (r.get("city") or ""))
        best, best_rank, best_score, best_ov = None, 0.0, 0.0, 0
        for w in wild:
            wt = {norm_tune(t["title"]) for t in w["tunes"]}
            wt.discard("")
            if not wt or not ours:
                continue
            ov = len(wt & ours)
            if ov < MIN_TUNE_OVERLAP:
                continue
            score = ov / max(1, len(ours))
            venue_ok = bool(our_place and w.get("location")
                            and our_place[:6]
                            and our_place[:6] in norm_tune(w["location"]))
            ranked = score + (0.5 if venue_ok else 0)
            if ranked > best_rank:
                best, best_rank, best_score, best_ov = w, ranked, score, ov

        matched = best is not None and best_ov >= MIN_TUNE_OVERLAP \
            and best_score >= 0.4
        # A folder that states its own day-precision date is primary
        # evidence about that specific tape. Wild's web edition does not
        # cover the bootleg tier, so a "correction" there is a mis-match.
        folder_asserted = (r.get("date_source") == "folder"
                           and r.get("date_precision") == "day")

        if not matched:
            state = "no Wild match"
            nomatch += 1
        elif d and len(d) == 10 and d == best["date"]:
            state = "confirmed"
            confirmed += 1
        elif folder_asserted and d != best["date"]:
            state = "folder date kept"
            nomatch += 1
        elif d and len(d) == 10:
            state = "CORRECTED"
            corrected += 1
        else:
            state = "date supplied"
            supplied += 1

        rows.append({
            "state": state,
            "our_date": d or "",
            "wild_date": best["date"] if state != "no Wild match" else "",
            "wild_session": best["session"] if state != "no Wild match" else "",
            "tune_overlap": f"{min(best_score,1.0):.0%}" if best else "",
            "tunes_shared": best_ov if best else "",
            "precision": r.get("date_precision") or "",
            "our_source": r.get("date_source") or "",
            "wild_group": (best or {}).get("group") or "",
            "wild_location": (best or {}).get("location") or "",
            "wild_personnel": "; ".join(
                p["name"] for p in (best or {}).get("personnel", [])[:8]),
            "album": r.get("title", "")[:60],
            "path": r.get("path", ""),
        })
    agree, differ, absent = confirmed, corrected, nomatch

    out = os.path.join(HERE, "output-coltrane", "wild_reconciliation.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for row in sorted(rows, key=lambda x: (x["state"], x["our_date"])):
            w.writerow(row)

    print(f"Wild sessions loaded : {len(wild)}")
    print(f"  confirmed     : {confirmed:4d}  our date matches Wild's session")
    print(f"  CORRECTED     : {corrected:4d}  Wild disagrees with our date")
    print(f"  date supplied : {supplied:4d}  we had none, Wild has one")
    print(f"  no Wild match : {nomatch:4d}  not in the web edition, or "
          f"folder date kept")
    kept = sum(1 for r in rows if r["state"] == "folder date kept")
    print(f"     of which folder-asserted dates preserved: {kept}")
    print(f"\ndistinct tunes in Wild: {len(tune_index)}")
    print(f"-> {out}")


def tracks(manifest_path):
    """Propose a Wild session for each individual track.

    This is where Wild pays off. A tune that appears in exactly one Wild
    session can be dated outright; the album it sits on is irrelevant, so a
    multi-session record like Ballads stops pretending to one date.

    Nothing is applied. The output is a proposal with a confidence column.
    """
    wild = json.load(open(OUT_JSON, encoding="utf-8"))["sessions"]
    man = json.load(open(manifest_path, encoding="utf-8"))

    # tune -> the Wild sessions that contain it
    where = collections.defaultdict(list)
    for w in wild:
        for t in w["tunes"]:
            k = norm_tune(t["title"])
            if k and w not in where[k]:
                where[k].append(w)

    rel = {r["release_id"]: r for r in man["releases"]}
    rows = []
    unique = ambiguous = absent = 0
    for t in man["tracks"]:
        k = norm_tune(t.get("tune"))
        r = rel.get(t["release_id"], {})
        cands = where.get(k, [])
        if not k or not cands:
            absent += 1
            continue
        if len(cands) == 1:
            w = cands[0]
            conf, note = "unique", ""
            unique += 1
        else:
            # several sessions played this tune; prefer one whose date the
            # release already points at, otherwise leave it ambiguous
            same = [c for c in cands if c["date"] == t.get("recording_date")]
            if len(same) == 1:
                w, conf, note = same[0], "corroborated", \
                    f"{len(cands)} sessions play this tune"
                unique += 1
            else:
                w, conf = cands[0], "ambiguous"
                note = f"{len(cands)} sessions play this tune"
                ambiguous += 1
        rows.append({
            "confidence": conf,
            "current_date": t.get("recording_date") or "",
            "wild_date": w["date"],
            "changes": "yes" if t.get("recording_date") != w["date"] else "no",
            "tune": t.get("tune") or "",
            "wild_session": w["session"],
            "wild_group": w.get("group") or "",
            "wild_location": w.get("location") or "",
            "wild_personnel": "; ".join(p["name"] for p in w["personnel"][:8]),
            "note": note,
            "album": r.get("title", "")[:50],
            "path": t.get("path", ""),
        })

    out = os.path.join(HERE, "output-coltrane", "wild_track_proposals.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w_.writeheader()
        for row in sorted(rows, key=lambda x: (x["confidence"], x["path"])):
            w_.writerow(row)

    # JSON alongside the CSV, carrying every candidate session for the
    # ambiguous tracks so the browser can offer a real choice rather than
    # just reporting that a choice exists.
    jrows = {}
    for t in man["tracks"]:
        k = norm_tune(t.get("tune"))
        cands = where.get(k, [])
        if not k or not cands:
            continue
        jrows[t["path"]] = {
            "candidates": [{
                "session": c["session"], "date": c["date"],
                "group": c.get("group"), "location": c.get("location"),
                "personnel": [p["name"] for p in c["personnel"]],
                "url": c.get("source_url"),
            } for c in sorted(cands, key=lambda x: x["date"])],
        }
    jout = os.path.join(HERE, "output-coltrane", "wild_track_proposals.json")
    with open(jout, "w", encoding="utf-8") as fh:
        json.dump({"_source": "David Wild discography, web edition",
                   "tracks": jrows}, fh, ensure_ascii=False)
    print(f"-> {jout}")

    changed = sum(1 for r in rows if r["changes"] == "yes"
                  and r["confidence"] != "ambiguous")
    print(f"tracks with a Wild-known tune : {len(rows):,}")
    print(f"  unique / corroborated match : {unique:,}")
    print(f"  ambiguous (tune played at several sessions): {ambiguous:,}")
    print(f"  tracks whose date would change: {changed:,}")
    print(f"tracks with no Wild tune match  : {absent:,}")
    print(f"\n-> {out}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--tracks", action="store_true",
                    help="propose a Wild session per track")
    ap.add_argument("--manifest", default="output-coltrane/coltrane.json")
    args = ap.parse_args()
    if args.fetch:
        fetch_all()
    elif args.report:
        report(args.manifest)
    elif args.tracks:
        tracks(args.manifest)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
