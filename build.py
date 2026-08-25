"""Phases 1-3: derive / normalize / emit the faceted library manifest.

Consumes raw_probe.jsonl, writes library.json + library.csv + works.csv +
duplicates.csv into the output directory. Never touches the music
files.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict

import credits

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw_probe.jsonl")
# No drive letters: every path comes from the CLI.
OUTDIR = os.path.join(os.getcwd(), "output")
MUSIC_ROOT = os.getcwd()

# Populated from CLI flags in main(); see --collection.
CONFIG = {
    "collections": {"BANGERS": 5},
    "genre_keywords": {},
}

# ---------------------------------------------------------------- vocabulary

DISC_DIR_RE = re.compile(r"^(cd|disc|disk)\s*\.?\s*(\d+)\b", re.I)

# Composer catalogue systems. Order matters: specific before generic Op.
CATALOG_RES = [
    ("K",    re.compile(r"\bK\.?\s?V?\.?\s?(\d+[a-z]?)\b")),
    ("BWV",  re.compile(r"\bBWV\.?\s?(\d+[a-z]?)\b", re.I)),
    ("D",    re.compile(r"\bD\.?\s?(\d{3,4})\b")),
    ("Hob",  re.compile(r"\bHob\.?\s?([IVXL]+)[:\.]?\s?(\d+)\b", re.I)),
    ("HWV",  re.compile(r"\bHWV\.?\s?(\d+)\b", re.I)),
    ("RV",   re.compile(r"\bRV\.?\s?(\d+)\b", re.I)),
    ("WoO",  re.compile(r"\bWoO\.?\s?(\d+)\b", re.I)),
    ("Sz",   re.compile(r"\bSz\.?\s?(\d+)\b", re.I)),
    ("BB",   re.compile(r"\bBB\.?\s?(\d+)\b", re.I)),
    ("Op",   re.compile(r"\bOp{1,2}\.?\s?(\d+)(?:\s*,?\s*No\.?\s?(\d+))?", re.I)),
]

# Composer strings that carry no composer information.
COMPOSER_JUNK = {
    "various composers", "various", "composer information unavailable",
    "blue note hdtracks", "unknown", "n/a", "none", "traditional",
    "various artists", "hdtracks", "-", "",
}

# Canonical surname -> "Surname, Forenames". Covers the classical core;
# anything unmatched falls through to the structural normalizer.
CANON = {
    "mozart": "Mozart, Wolfgang Amadeus",
    "beethoven": "Beethoven, Ludwig van",
    "bach": "Bach, Johann Sebastian",
    "bruckner": "Bruckner, Anton",
    "handel": "Handel, George Frideric",
    "haendel": "Handel, George Frideric",
    "händel": "Handel, George Frideric",
    "schubert": "Schubert, Franz",
    "brahms": "Brahms, Johannes",
    "mahler": "Mahler, Gustav",
    "prokofiev": "Prokofiev, Sergei",
    "stravinsky": "Stravinsky, Igor",
    "mendelssohn": "Mendelssohn, Felix",
    "mendelsohn": "Mendelssohn, Felix",
    "schumann": "Schumann, Robert",
    "debussy": "Debussy, Claude",
    "ravel": "Ravel, Maurice",
    "chopin": "Chopin, Frederic",
    "liszt": "Liszt, Franz",
    "haydn": "Haydn, Joseph",
    "vivaldi": "Vivaldi, Antonio",
    "tchaikovsky": "Tchaikovsky, Pyotr Ilyich",
    "dvorak": "Dvorak, Antonin",
    "dvořák": "Dvorak, Antonin",
    "sibelius": "Sibelius, Jean",
    "faure": "Faure, Gabriel",
    "fauré": "Faure, Gabriel",
    "franck": "Franck, Cesar",
    "bartok": "Bartok, Bela",
    "bartók": "Bartok, Bela",
    "ligeti": "Ligeti, Gyorgy",
    "shostakovich": "Shostakovich, Dmitri",
    "rachmaninov": "Rachmaninov, Sergei",
    "rachmaninoff": "Rachmaninov, Sergei",
    "berlioz": "Berlioz, Hector",
    "wagner": "Wagner, Richard",
    "strauss": "Strauss, Richard",
    "schoenberg": "Schoenberg, Arnold",
    "webern": "Webern, Anton",
    "berg": "Berg, Alban",
    "hindemith": "Hindemith, Paul",
    "janacek": "Janacek, Leos",
    "elgar": "Elgar, Edward",
    "britten": "Britten, Benjamin",
    "copland": "Copland, Aaron",
    "gershwin": "Gershwin, George",
    "scarlatti": "Scarlatti, Domenico",
    "telemann": "Telemann, Georg Philipp",
    "purcell": "Purcell, Henry",
    "monteverdi": "Monteverdi, Claudio",
}

ENSEMBLE_RE = re.compile(
    r"\b(orchestra|orchestre|orkest|philharmoni|symphon|sinfoni|quartet|quartett|"
    r"quintet|trio|ensemble|chorus|choir|chor\b|singverein|academy|camerata|"
    r"consort|band|collegium|capella|kapelle|staatskapelle|concertgebouw|"
    r"players|soloists|group|septet|octet|sextet)", re.I)

# Source-medium markers found in release folder names.
MEDIUM_MARKERS = [
    ("SACD",        re.compile(r"\bSACD\b|\bDSD\d*\b|\bDSF\b|\bISO\b", re.I)),
    ("Vinyl",       re.compile(r"\bvinyl\b|\bLP\b|\b45\s?RPM\b|\bMFSL\b|"
                               r"\banalogue productions\b|\b180g\b", re.I)),
    ("Blu-ray",     re.compile(r"\bblu-?ray\b|\bBDA\b|\bblu-?spec\b", re.I)),
    ("Web",         re.compile(r"\bHDTracks\b|\bQobuz\b|\bTidal\b|\bWEB\b|"
                               r"\bhi-?res\b", re.I)),
    ("CD",          re.compile(r"\bCD\b|\bEAC\b|\bredbook\b", re.I)),
]

ROMAN = {"i":1,"ii":2,"iii":3,"iv":4,"v":5,"vi":6,"vii":7,"viii":8,"ix":9,
         "x":10,"xi":11,"xii":12,"xiii":13,"xiv":14,"xv":15}

MOVEMENT_RE = re.compile(
    r"^\s*(?:(\d{1,2})|([IVXivx]{1,5}))\s*[\.\)]\s*(.*)$")

# Sung sections of the mass/requiem: movement names, never work names.
LITURGICAL = {
    "introitus", "introit", "kyrie", "gloria", "credo", "sanctus",
    "benedictus", "agnus dei", "dies irae", "tuba mirum", "rex tremendae",
    "recordare", "confutatis", "lacrimosa", "lacrymosa", "domine jesu",
    "hostias", "communio", "offertorium", "sequenz", "sequentia",
    "requiem aeternam", "lux aeterna", "libera me", "in paradisum",
    "quam olim abrahae", "te decet hymnus", "et incarnatus est",
}

TEMPO_ALT = (
    r"allegro|adagio|andante|largo|presto|vivace|moderato|lento|grave|"
    r"scherzo|menuett?o|minuet|rondo|finale|fuga|fugue|aria|recitativ|"
    r"prelude|preludio|introduction|variation|thema|theme|coda|"
    r"langsam|schnell|zart|bewegt|nicht|sehr|ruhig|feierlich")
TEMPO_WORDS = re.compile(r"\b(" + TEMPO_ALT + r")", re.I)


# ---------------------------------------------------------------- helpers

def sid(prefix, s):
    return prefix + "_" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def tget(tags, *names):
    """Case-insensitive tag lookup, first non-empty wins."""
    low = {k.lower().strip(): v for k, v in (tags or {}).items()}
    for n in names:
        v = low.get(n)
        if v and str(v).strip():
            # Embedded newlines are real -- some rips write
            # 'Old Folks\nOld Folks' into TITLE -- and they break every
            # line-oriented format downstream (m3u8, CSV).
            return re.sub(r"\s+", " ", str(v)).strip()
    return None


def norm_composer(raw):
    """190 messy strings -> canonical 'Surname, Forenames'."""
    if not raw:
        return None
    s = str(raw).strip()
    if s.lower() in COMPOSER_JUNK:
        return None
    # drop life-dates and trailing parentheticals: "Beethoven (1770 - 1827)"
    s = re.sub(r"\((?:\s*\d{4}\s*[-–]\s*\d{4}\s*)\)", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" ,;")
    if not s or s.lower() in COMPOSER_JUNK:
        return None
    # a multi-composer field is not a composer
    if len(re.split(r"[;/]|,\s*(?=[A-Z][a-z]+\s+[A-Z])", s)) > 2:
        pass  # still try surname match below

    flat = strip_accents(s).lower()
    for surname, canon in CANON.items():
        key = strip_accents(surname)
        if re.search(r"\b" + re.escape(key) + r"\b", flat):
            return canon
    # structural fallback
    if "," in s:
        return s  # already "Last, First"
    parts = s.split()
    if len(parts) >= 2:
        return parts[-1] + ", " + " ".join(parts[:-1])
    return s


def parse_catalog(text):
    """Return (system, number) for the first catalogue marker found."""
    if not text:
        return None, None
    for name, rx in CATALOG_RES:
        m = rx.search(text)
        if not m:
            continue
        groups = [g for g in m.groups() if g]
        if name == "Hob":
            return name, f"{groups[0].upper()}:{groups[1]}"
        if name == "Op" and len(groups) == 2:
            return name, f"{groups[0]} No.{groups[1]}"
        return name, groups[0]
    return None, None


def split_work_movement(title):
    """Both observed grammars:
         'Work in Key, Op.77 - 1. Allegro'
         'Composer: Work No. 6, Op. 82: I. Allegro moderato'
       -> (work_title, movement_no, movement_name)
    """
    if not title:
        return None, None, None
    parts = re.split(r"\s+[-–—]\s+|\s*:\s+", title)
    if len(parts) < 2:
        return title.strip(), None, None

    for i in range(len(parts) - 1, 0, -1):
        cand = parts[i].strip()
        m = MOVEMENT_RE.match(cand)
        if m:
            num = int(m.group(1)) if m.group(1) else ROMAN.get(
                (m.group(2) or "").lower())
            return " - ".join(p.strip() for p in parts[:i]).strip(), num, \
                m.group(3).strip()
        # unnumbered but clearly a tempo marking
        if TEMPO_WORDS.search(cand) and len(cand) < 70:
            return " - ".join(p.strip() for p in parts[:i]).strip(), None, cand

    return title.strip(), None, None


def is_bare_movement(title):
    """True when the whole TITLE is just a movement, so the work name lives
    in the album tag: 'I. Adagio', '3.Allegretto', 'Agnus Dei'."""
    if not title:
        return False
    s = title.strip()
    m = MOVEMENT_RE.match(s)
    if m and (m.group(3) or "").strip():
        # 'I. Adagio' but not 'No. 6 Piano Sonata' (a work with a number)
        rest = m.group(3).strip()
        if TEMPO_WORDS.search(rest) or len(rest.split()) <= 4:
            return True
    flat = strip_accents(s).lower().strip(" .-")
    if flat in LITURGICAL:
        return True
    if TEMPO_WORDS.match(flat) and len(s.split()) <= 5:
        return True
    return False


def extract_works_from_album(album):
    """Split an album title into its constituent works using catalogue
    markers as anchors: 'Mozart - Requiem K.626, Adagio & Fugue K.546'
    -> [('Requiem', 'K', '626'), ('Adagio & Fugue', 'K', '546')]"""
    if not album:
        return []
    hits = []
    for name, rx in CATALOG_RES:
        for m in rx.finditer(album):
            groups = [g for g in m.groups() if g]
            if name == "Hob":
                num = f"{groups[0].upper()}:{groups[1]}"
            elif name == "Op" and len(groups) == 2:
                num = f"{groups[0]} No.{groups[1]}"
            else:
                num = groups[0]
            hits.append((m.start(), m.end(), name, num))
    if not hits:
        return []
    # keep the leftmost match at each position, drop overlaps
    hits.sort()
    kept = []
    for h in hits:
        if kept and h[0] < kept[-1][1]:
            continue
        kept.append(h)

    works, prev_end = [], 0
    for start, end, name, num in kept:
        seg = album[prev_end:start]
        seg = re.split(r"\s*[-–—,;:]\s*", seg)
        title = next((p.strip() for p in reversed(seg) if p.strip()), None)
        works.append((title, name, num))
        prev_end = end
    return works


def clean_album_as_work(album, folder_name):
    """Fallback work title when the album carries no catalogue marker."""
    src = album or folder_name or ""
    src = re.sub(r"\s*[\[\({].*?[\]\)}]\s*", " ", src)
    src = re.sub(r"\b(19|20)\d{2}\b", " ", src)
    src = re.sub(r"\b(FLAC|SACD|ISO|DSD|24|16|96|192|88\.2|44\.1|"
                 r"remaster(ed)?|hi-?res|HDTracks)\b", " ", src, flags=re.I)
    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", src) if p.strip()]
    if parts:
        # drop a leading composer surname: 'Mozart - Requiem' -> 'Requiem'
        if len(parts) > 1 and strip_accents(parts[0]).lower() in CANON:
            parts = parts[1:]
        return re.sub(r"\s{2,}", " ", parts[0]).strip(" -–—,")
    return re.sub(r"\s{2,}", " ", src).strip() or None


def polish_work_title(title, csys, cnum):
    """Strip movement residue, edition noise and the catalogue marker from a
    work title; the catalogue lives in its own fields."""
    if not title:
        return None
    s = title.strip()
    s = re.sub(r"\s*\((?:remaster(?:ed)?|live|mono|stereo)[^)]*\)\s*$", "",
               s, flags=re.I)
    # trailing movement: ' - I. Adagio', ': Allegro', ' - 1. Allegro'
    s = re.sub(r"\s*[-–—:]\s*(?:[IVXivx]{1,5}|\d{1,2})\s*[\.\)]\s*\S.*$", "", s)
    s = re.sub(r"\s*:\s*(?:" + TEMPO_ALT + r")\b.*$", "", s,
               flags=re.I)
    # trailing catalogue marker, now redundant
    if csys and cnum:
        base = re.escape(str(cnum).split(" No.")[0])
        s = re.sub(r"\s*[,;]?\s*\b" + re.escape(csys) + r"\.?\s?V?\.?\s?"
                   + base + r"\b.*$", "", s, flags=re.I)
    s = re.sub(r"^\s*[A-Z][a-zA-Z\.]{1,20}\s*[-–—]\s+", "", s)  # 'Mozart - '
    s = re.sub(r"\s{2,}", " ", s).strip(" -–—,;:")
    return s or title.strip()


def norm_title_key(title):
    if not title:
        return ""
    s = strip_accents(title).lower()
    for _, rx in CATALOG_RES:
        s = rx.sub(" ", s)
    s = re.sub(r"\((?:[^)]*)\)", " ", s)
    s = re.sub(r"\b(no|nr|op|the|a|an|in|for|and|major|minor|flat|sharp)\b",
               " ", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def finalize_works(works, all_tracks):
    """Polish titles, then merge same-composer works whose titles agree and
    where exactly one catalogue number is known."""
    for w in works.values():
        w["title"] = polish_work_title(w["title"], w["catalog_system"],
                                       w["catalog_number"])

    buckets = defaultdict(list)
    for w in works.values():
        buckets[(w["composer"] or "?", norm_title_key(w["title"]))].append(w)

    remap = {}
    for (comp, key), group in buckets.items():
        if len(group) < 2 or not key:
            continue
        cats = {(g["catalog_system"], g["catalog_number"]) for g in group
                if g["catalog_system"]}
        if len(cats) > 1:
            continue  # genuinely different works sharing a title
        target = max(group, key=lambda g: (bool(g["catalog_system"]),
                                           g["movement_count"]))
        if cats:
            target["catalog_system"], target["catalog_number"] = \
                next(iter(cats))
        for g in group:
            if g["work_id"] == target["work_id"]:
                continue
            remap[g["work_id"]] = target["work_id"]
            target["movement_count"] += g["movement_count"]
            for rid in g["release_ids"]:
                if rid not in target["release_ids"]:
                    target["release_ids"].append(rid)
            works.pop(g["work_id"], None)
        target["recording_count"] = len(target["release_ids"])

    for t in all_tracks:
        wid = t.get("work_id")
        if wid in remap:
            wid = remap[wid]
            t["work_id"] = wid
        w = works.get(wid)
        if w:
            t["work_title"] = w["title"]
            if not t["catalog_system"] and w["catalog_system"]:
                t["catalog_system"] = w["catalog_system"]
                t["catalog_number"] = w["catalog_number"]
    return works


GENRE_KEYWORDS = {
    "Classical": ["classical", "opera", "orchestral", "chamber", "baroque",
                  "romantic", "symphon", "concerto", "lieder", "choral",
                  "早期音楽", "klassik"],
    "Jazz": ["jazz", "bebop", "fusion", "bigband", "big band", "swing",
             "blue note"],
    "Rock": ["rock", "metal", "prog", "punk", "grunge", "indie", "alt"],
    "Electronic": ["electronic", "techno", "ambient", "house", "idm", "edm"],
    "Hip-Hop": ["hip-hop", "hiphop", "hip hop", "rap"],
    "Folk": ["folk", "country", "bluegrass", "americana", "singer-songwriter"],
    "Blues": ["blues", "r&b", "soul", "funk"],
    "World": ["world", "latin", "afro", "reggae", "flamenco"],
    "Pop": ["pop"],
}


def infer_genre(folder, genre_tag, has_composer, config):
    """Genre from the path first, then the tag, then the composer signal.

    Path segments win because a top-level 'Jazz' or 'Mozart' folder is a
    deliberate statement by the collector; GENRE tags are frequently junk.
    """
    segments = [s.lower() for s in folder.split("/")]
    for seg in segments:
        stripped = strip_accents(seg)
        for genre, keys in config["genre_keywords"].items():
            for k in keys:
                if re.search(r"\b" + re.escape(k), stripped):
                    return genre
        # a top-level folder named for a composer is a classical shelf
        if strip_accents(seg).strip() in CANON:
            return "Classical"

    if genre_tag:
        flat = strip_accents(genre_tag).lower()
        for genre, keys in config["genre_keywords"].items():
            for k in keys:
                if k in flat:
                    return genre
        return genre_tag
    return "Classical" if has_composer else None


def infer_collections(folder, config):
    """Top-level folders the user has flagged as curated sets."""
    segments = folder.split("/")
    out = []
    for name in config["collections"]:
        if any(s.lower() == name.lower() for s in segments):
            out.append(name)
    return out


def surname_of(composer):
    return (composer or "").split(",")[0].strip() or None


def flat_projection(track, release, work):
    """Project the rich model onto the six tags a simple player understands.

    Players like the FiiO Music app read only title/artist/album/albumartist/
    genre/track/disc. They ignore WORK and MOVEMENT entirely, so the work name
    has to be folded into ALBUM and the movement into TITLE, or a symphony
    shows up as eight untitled fragments.

    Returns proposed values only. Nothing is written to any file.
    """
    is_classical = bool(track.get("composer")) and \
        release.get("genre_primary") == "Classical"

    performers = []
    if track.get("conductor") and track["conductor_confidence"] != "ambiguous":
        performers.append(track["conductor"])
    performers.extend(track.get("ensembles") or [])
    performers.extend((track.get("soloists") or [])[:2])
    seen, perf = set(), []
    for p in performers:
        if p and p not in seen:
            seen.add(p)
            perf.append(p)
    performer_str = ", ".join(perf[:3]) or release.get("album_artist") or ""

    year = release.get("recording_year") or release.get("release_year")

    if is_classical:
        album_artist = surname_of(track["composer"]) or "Various"
        cat = ""
        if track.get("catalog_system") and track.get("catalog_number"):
            cat = f" {track['catalog_system']}.{track['catalog_number']}"
        work_label = (track.get("work_title") or release.get("title") or "")
        bits = [f"{work_label}{cat}".strip()]
        short_perf = ", ".join(perf[:2])
        if short_perf:
            bits.append(short_perf)
        if year:
            bits.append(f"({year})")
        album = " - ".join(b for b in bits[:2] if b)
        if year:
            album = f"{album} ({year})"

        if track.get("movement_name"):
            mv = track["movement_name"]
            title = (f"{track['movement_number']}. {mv}"
                     if track.get("movement_number") else mv)
        else:
            title = track.get("title") or track.get("filename")
        artist = performer_str or album_artist
    else:
        album_artist = release.get("album_artist") or \
            (track.get("soloists") or [None])[0] or "Unknown Artist"
        album = release.get("title") or release.get("folder_name")
        if year and album and f"({year})" not in album:
            album = f"{album} ({year})"
        title = track.get("title") or track.get("filename")
        artist = track.get("artist_raw") or album_artist

    return {
        "flat_albumartist": album_artist,
        "flat_album": (album or "")[:120],
        "flat_title": (title or "")[:120],
        "flat_artist": (artist or "")[:120],
        "flat_genre": release.get("genre_primary") or
                      release.get("genre_tag_raw") or "Unknown",
        "flat_track": track.get("track_number"),
        "flat_disc": track.get("disc_number"),
        "flat_date": year,
        "flat_grouping": track.get("work_title") or "",
    }


def work_sort_key(csys, cnum):
    """Numeric-aware sort so K.9 precedes K.626."""
    if not cnum:
        return (csys or "", 0, "")
    m = re.match(r"(\d+)", str(cnum))
    return (csys or "", int(m.group(1)) if m else 0, str(cnum))


def segment_into_works(tracks):
    """Group an ordered track list into work segments. A new work starts
    when an explicit work title changes, or when movement numbering
    restarts (I, II, III, I, II -> two works)."""
    segments, cur = [], []
    prev_mv, prev_work = None, None
    for t in tracks:
        explicit = t.get("_work_part")
        new = False
        if cur:
            if explicit and prev_work and explicit != prev_work:
                new = True
            elif explicit and not prev_work:
                new = True
            elif not explicit and prev_work:
                new = True
            elif (t.get("movement_number") and prev_mv
                  and t["movement_number"] <= prev_mv):
                new = True
        if new:
            segments.append(cur)
            cur = []
        cur.append(t)
        prev_work = explicit
        if t.get("movement_number"):
            prev_mv = t["movement_number"]
        elif new:
            prev_mv = None
    if cur:
        segments.append(cur)
    return segments


CONDUCTED_BY = re.compile(
    r"\s*[,;]?\s*\b(?:cond(?:\.|ucted by|uctor)?|dir(?:\.|ected by)?)\s*[:.]?\s+",
    re.I)


def split_artists(raw):
    """Split a packed artist field and classify person vs ensemble.

    Returns (people, ensembles, conductor_hint). Rips routinely write
    'English Chamber Orchestra cond. Daniel Barenboim' into one ARTIST field;
    left unsplit that string ends up displayed as an ensemble name.
    """
    if not raw:
        return [], [], None

    conductor_hint = None
    text = str(raw)
    m = CONDUCTED_BY.search(text)
    if m:
        tail = text[m.end():].strip(" ,;")
        tail = re.split(r"\s*[;/]\s*", tail)[0].strip()
        if tail and not ENSEMBLE_RE.search(tail) and len(tail.split()) <= 5:
            conductor_hint = tail
            text = text[:m.start()].strip(" ,;")

    chunks = [c.strip() for c in re.split(r"\s*[;/]\s*|\s+&\s+|\s+feat\.?\s+",
                                          text) if c.strip()]
    expanded = []
    for c in chunks:
        # "Staatskapelle Dresden, Christian Thielemann" -> two entities
        if "," in c and ENSEMBLE_RE.search(c):
            expanded.extend(p.strip() for p in c.split(",") if p.strip())
        else:
            expanded.append(c)
    people, ensembles = [], []
    for e in expanded:
        (ensembles if ENSEMBLE_RE.search(e) else people).append(e)
    return people, ensembles, conductor_hint


def detect_medium(folder_name, codecs):
    if any(c in ("dsd_lsbf_planar", "dsd_msbf", "dsd_lsbf", "dsd_msbf_planar")
           for c in codecs):
        return "SACD"
    for name, rx in MEDIUM_MARKERS:
        if rx.search(folder_name):
            return name
    return "Unknown"


def quality_tier(codec, bits, rate):
    if codec and codec.startswith("dsd"):
        return "DSD"
    if codec in ("mp3", "aac", "vorbis", "opus"):
        return "Lossy"
    b = bits or 0
    r = rate or 0
    if b > 16 or r > 48000:
        return "Hi-Res"
    if b and r:
        return "Redbook"
    return "Unknown"


def parse_folder_year(name):
    m = re.findall(r"(?<!\d)(1[89]\d{2}|20[0-4]\d)(?!\d)", name)
    return int(m[0]) if m else None


def parse_cue(path):
    """Extract TRACK/TITLE/PERFORMER entries from a cue sheet."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as fh:
                text = fh.read()
            break
        except (UnicodeDecodeError, OSError):
            continue
    else:
        return []
    tracks, cur = [], None
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^TRACK\s+(\d+)\s+AUDIO", s, re.I)
        if m:
            if cur:
                tracks.append(cur)
            cur = {"track_number": int(m.group(1))}
            continue
        if cur is None:
            continue
        m = re.match(r'^TITLE\s+"?(.*?)"?$', s, re.I)
        if m:
            cur["title"] = m.group(1).strip()
        m = re.match(r'^PERFORMER\s+"?(.*?)"?$', s, re.I)
        if m:
            cur["performer"] = m.group(1).strip()
        m = re.match(r"^INDEX\s+01\s+(\d+):(\d+):(\d+)", s, re.I)
        if m:
            a, b, c = (int(x) for x in m.groups())
            cur["start_seconds"] = a * 60 + b + c / 75.0
    if cur:
        tracks.append(cur)
    return tracks


def majority(values):
    vals = [v for v in values if v]
    return Counter(vals).most_common(1)[0][0] if vals else None


# ---------------------------------------------------------------- load

def load():
    audio, containers, sidecars = [], [], []
    with open(RAW, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            base = os.path.basename(r["path"])
            if base.startswith("._"):          # macOS AppleDouble junk
                continue
            kind = r.get("kind")
            if kind == "audio":
                if r.get("error"):
                    # .iso.wv = WavPack-compressed SACD image, not a track
                    if r["path"].lower().endswith(".iso.wv"):
                        containers.append(r)
                    continue
                audio.append(r)
            elif kind == "container":
                containers.append(r)
            else:
                sidecars.append(r)
    return audio, containers, sidecars


def release_key(relpath):
    """Folder holding the file, rolled up past CD1/Disc 2/... subfolders."""
    d = os.path.dirname(relpath)
    parts = d.split("/")
    disc_no, disc_sub = None, None
    if len(parts) > 1:
        m = DISC_DIR_RE.match(parts[-1])
        if m:
            disc_no = int(m.group(2))
            rest = parts[-1][m.end():].strip(" -–—")
            disc_sub = rest or None
            parts = parts[:-1]
    return "/".join(parts), disc_no, disc_sub


# ---------------------------------------------------------------- build

def parse_args():
    ap = argparse.ArgumentParser(
        description="Derive the faceted music manifest from a raw probe.")
    ap.add_argument("--raw", default=RAW, help="raw_probe.jsonl from scan.py")
    ap.add_argument("--out", default=OUTDIR, help="output directory")
    ap.add_argument("--root", default=MUSIC_ROOT,
                    help="music root the probe paths are relative to; "
                         "needed to read .cue sheets")
    ap.add_argument("--collection", action="append", default=None,
                    metavar="NAME[=RATING]",
                    help="top-level folder to treat as a curated set, "
                         "e.g. --collection BANGERS=5 (repeatable)")
    return ap.parse_args()


def main():
    global RAW, OUTDIR, MUSIC_ROOT
    args = parse_args()
    RAW, OUTDIR, MUSIC_ROOT = args.raw, args.out, args.root

    colls = {}
    for spec in (args.collection if args.collection is not None
                 else ["BANGERS=5"]):
        name, _, rating = spec.partition("=")
        colls[name.strip()] = int(rating) if rating.strip().isdigit() else None
    CONFIG["collections"] = colls
    CONFIG["genre_keywords"] = GENRE_KEYWORDS

    os.makedirs(OUTDIR, exist_ok=True)
    audio, containers, sidecars = load()

    # ---- sidecars indexed by folder, for release-level provenance
    side_by_dir = defaultdict(list)
    for s in sidecars:
        side_by_dir[os.path.dirname(s["path"])].append(
            os.path.basename(s["path"]))

    # ---- group tracks into releases
    groups = defaultdict(list)
    for r in audio:
        key, disc_no, disc_sub = release_key(r["path"])
        r["_disc_dir_no"] = disc_no
        r["_disc_dir_sub"] = disc_sub
        groups[key].append(r)
    for c in containers:
        key, _, _ = release_key(c["path"])
        groups.setdefault(key, [])

    works = {}
    releases = []
    all_tracks = []

    for folder, items in sorted(groups.items()):
        folder_name = folder.split("/")[-1] if folder else "(root)"
        top = folder.split("/")[0] if folder else ""
        rel_id = sid("rel", folder)

        # -------- release-level facets from the path
        colls = infer_collections(folder, CONFIG)

        cont = [c for c in containers
                if release_key(c["path"])[0] == folder]
        sides = []
        for d, names in side_by_dir.items():
            if d == folder or d.startswith(folder + "/"):
                sides.extend(names)
        side_lower = [s.lower() for s in sides]

        codecs = [i.get("codec") for i in items if i.get("codec")]
        bits = [int(i["bits_per_raw_sample"]) for i in items
                if i.get("bits_per_raw_sample")
                and str(i["bits_per_raw_sample"]).isdigit()]
        rates = [int(i["sample_rate"]) for i in items
                 if i.get("sample_rate") and str(i["sample_rate"]).isdigit()]
        max_bits = max(bits) if bits else None
        max_rate = max(rates) if rates else None

        tag_list = [i.get("tags") or {} for i in items]
        album = majority([tget(t, "album") for t in tag_list])
        album_artist = majority([tget(t, "album_artist", "albumartist",
                                      "album artist") for t in tag_list])
        label = majority([tget(t, "label", "organization", "publisher")
                          for t in tag_list])
        catalog = majority([tget(t, "catalognumber", "catalogue_no",
                                 "catalog_no") for t in tag_list])
        date = majority([tget(t, "date", "year") for t in tag_list])
        origdate = majority([tget(t, "originaldate", "origdate")
                             for t in tag_list])
        genre_tag = majority([tget(t, "genre") for t in tag_list])
        upc = majority([tget(t, "upc", "barcode") for t in tag_list])
        mb_album = majority([tget(t, "musicbrainz_albumid") for t in tag_list])

        def year_of(v):
            if not v:
                return None
            m = re.search(r"(1[89]\d{2}|20[0-4]\d)", str(v))
            return int(m.group(1)) if m else None

        release_year = year_of(date) or parse_folder_year(folder_name)
        recording_year = year_of(origdate)
        # folder names often carry "1961, 2001" = recorded, reissued
        fy = re.findall(r"(?<!\d)(1[89]\d{2}|20[0-4]\d)(?!\d)", folder_name)
        if len(fy) >= 2 and not recording_year:
            recording_year = int(min(fy))

        is_container = bool(cont) or (
            len(items) <= 2 and any(s.endswith(".cue") for s in side_lower))

        primary_codec = majority(codecs)
        release = {
            "release_id": rel_id,
            "path": folder,
            "folder_name": folder_name,
            "title": album or re.sub(r"\s*[\[\({].*?[\]\)}]\s*", " ",
                                     folder_name).strip(" -–—"),
            "album_artist": album_artist,
            "genre_primary": infer_genre(
                folder, genre_tag,
                any(norm_composer(tget(tt, "composer")) for tt in tag_list),
                CONFIG),
            "genre_tag_raw": genre_tag,
            "release_year": release_year,
            "recording_year": recording_year,
            "label": label,
            "catalog_number": catalog,
            "barcode": upc,
            "musicbrainz_albumid": mb_album,
            "source_medium": detect_medium(folder_name, codecs),
            "codec": primary_codec,
            "bit_depth": max_bits,
            "sample_rate": max_rate,
            "quality_tier": quality_tier(primary_codec, max_bits, max_rate),
            "channels": majority([i.get("channels") for i in items]),
            "rating": max((CONFIG["collections"][c] for c in colls),
                          default=None),
            "collections": colls,
            "is_container_release": is_container,
            "container_files": [c["path"] for c in cont],
            "track_count": len(items),
            "duration_seconds": round(sum(
                float(i["duration"]) for i in items if i.get("duration")), 1),
            "size_bytes": sum(i.get("size") or 0 for i in items)
                          + sum(c.get("size") or 0 for c in cont),
            "has_rip_log": any(s.endswith(".log") for s in side_lower),
            "has_accurip": any(s.endswith(".accurip") for s in side_lower),
            "has_cue": any(s.endswith(".cue") for s in side_lower),
            "has_booklet": any(s.endswith(".pdf") for s in side_lower),
            "has_cover_art": any(s.endswith((".jpg", ".jpeg", ".png", ".webp"))
                                 for s in side_lower),
            "has_dr_analysis": any("dr" in s and s.endswith(".txt")
                                   for s in side_lower),
        }

        # -------- cue expansion for image releases
        cue_tracks = []
        if is_container:
            for d, names in side_by_dir.items():
                if d != folder and not d.startswith(folder + "/"):
                    continue
                for n in names:
                    if n.lower().endswith(".cue"):
                        cue_tracks.extend(parse_cue(
                            os.path.join(MUSIC_ROOT, d, n)))
        release["cue_track_count"] = len(cue_tracks)

        # -------- tracks
        tracks = []
        for i in items:
            t = i.get("tags") or {}
            title = tget(t, "title")
            composer = norm_composer(tget(t, "composer"))

            # A title that is *only* a movement leaves the work to the album;
            # resolution happens in the per-release post-pass below.
            if is_bare_movement(title):
                m = MOVEMENT_RE.match(title.strip())
                if m and (m.group(3) or "").strip():
                    mv_no = int(m.group(1)) if m.group(1) else ROMAN.get(
                        (m.group(2) or "").lower())
                    mv_name = m.group(3).strip()
                else:
                    mv_no, mv_name = None, title.strip()
                work_part = None
            else:
                work_part, mv_no, mv_name = split_work_movement(title)

            csys, cnum = parse_catalog(title)

            artist_raw = tget(t, "artist")
            people, ensembles, cond_hint = split_artists(artist_raw)
            conductor = tget(t, "conductor") or cond_hint
            # a person named alongside an ensemble is a conductor *candidate*
            cond_cand = None
            if not conductor and ensembles and people:
                cond_cand = people[-1]

            def as_int(v):
                if v is None:
                    return None
                m = re.match(r"\s*(\d+)", str(v))
                return int(m.group(1)) if m else None

            bd = i.get("bits_per_raw_sample") or i.get("bits_per_sample")
            tr = {
                "track_id": sid("trk", i["path"]),
                "release_id": rel_id,
                "path": i["path"],
                "filename": os.path.basename(i["path"]),
                "disc_number": i.get("_disc_dir_no")
                               or as_int(tget(t, "disc", "discnumber")),
                "disc_subtitle": i.get("_disc_dir_sub"),
                "track_number": as_int(tget(t, "track", "tracknumber")),
                "title": title,
                "work_id": None,
                "work_title": None,
                "_work_part": work_part,
                "movement_number": mv_no,
                "movement_name": mv_name,
                "composer": composer,
                "composer_raw": tget(t, "composer"),
                "artist_raw": artist_raw,
                "soloists": people,
                "ensembles": ensembles,
                "conductor": conductor,
                "conductor_candidate": cond_cand,
                "catalog_system": csys,
                "catalog_number": cnum,
                "date": tget(t, "date", "year"),
                "original_date": tget(t, "originaldate", "origdate"),
                "isrc": tget(t, "isrc"),
                "musicbrainz_recordingid": tget(t, "musicbrainz_trackid",
                                                "musicbrainz_recordingid"),
                "duration_seconds": round(float(i["duration"]), 1)
                                    if i.get("duration") else None,
                "codec": i.get("codec"),
                "bit_depth": int(bd) if bd and str(bd).isdigit() else None,
                "sample_rate": int(i["sample_rate"])
                               if i.get("sample_rate") else None,
                "channels": i.get("channels"),
                "size_bytes": i.get("size"),
                "quality_tier": quality_tier(
                    i.get("codec"),
                    int(bd) if bd and str(bd).isdigit() else None,
                    int(i["sample_rate"]) if i.get("sample_rate") else None),
                "has_embedded_art": i.get("has_embedded_art", False),
            }
            tracks.append(tr)
            all_tracks.append(tr)

        tracks.sort(key=lambda x: (x["disc_number"] or 0,
                                   x["track_number"] or 0,
                                   x["filename"]))

        # ---- work resolution (per release, in playing order)
        album_works = extract_works_from_album(album or folder_name)
        release_composer = majority([t["composer"] for t in tracks])

        segments = []
        for disc in sorted({t["disc_number"] or 0 for t in tracks}):
            dtracks = [t for t in tracks if (t["disc_number"] or 0) == disc]
            segments.extend(segment_into_works(dtracks))

        # Only zip album works onto segments when the counts line up exactly;
        # a mismatch means we cannot trust positional assignment.
        zipped = album_works if len(album_works) == len(segments) else None

        for idx, seg in enumerate(segments):
            wt = majority([t.get("_work_part") for t in seg])
            csys = majority([t["catalog_system"] for t in seg])
            cnum = majority([t["catalog_number"] for t in seg])

            if zipped:
                a_title, a_sys, a_num = zipped[idx]
                wt = wt or a_title
                if not csys:
                    csys, cnum = a_sys, a_num
            elif len(album_works) == 1:
                a_title, a_sys, a_num = album_works[0]
                wt = wt or a_title
                if not csys:
                    csys, cnum = a_sys, a_num

            if not wt:
                wt = clean_album_as_work(album, folder_name)
            if wt:
                wt = re.sub(r"^\s*[^:]{2,30}:\s+", "", wt).strip() or wt

            comp = majority([t["composer"] for t in seg]) or release_composer
            if not comp and not wt:
                continue

            if csys and cnum:
                wkey = f"{comp or '?'}|{csys}.{cnum}"
            else:
                wkey = f"{comp or '?'}|{strip_accents((wt or '').lower())}"
            work_id = sid("work", wkey)

            w = works.setdefault(work_id, {
                "work_id": work_id,
                "composer": comp,
                "title": wt,
                "catalog_system": csys,
                "catalog_number": cnum,
                "movement_count": 0,
                "recording_count": 0,
                "release_ids": [],
            })
            if not w["title"] and wt:
                w["title"] = wt
            w["movement_count"] += len(seg)
            if rel_id not in w["release_ids"]:
                w["release_ids"].append(rel_id)
                w["recording_count"] += 1

            for t in seg:
                t["work_id"] = work_id
                t["work_title"] = wt
                if not t["catalog_system"]:
                    t["catalog_system"], t["catalog_number"] = csys, cnum
                if not t["composer"]:
                    t["composer"] = comp

        for t in tracks:
            t.pop("_work_part", None)

        release["composers"] = sorted({t["composer"] for t in tracks
                                       if t["composer"]})

        # ---- credits recovered from the folder path (conductor / ensemble)
        tagged_cond = majority([t["conductor"] for t in tracks])
        tag_ens_pre = sorted({e for t in tracks for e in t["ensembles"]})
        path_cond, cond_conf, path_ens = credits.extract_credits(
            folder, album, release["composers"],
            tag_ensembles=tag_ens_pre,
            is_classical=(release["genre_primary"] == "Classical"))

        if tagged_cond:
            release["conductor"] = tagged_cond
            release["conductor_source"] = "tag"
            release["conductor_confidence"] = "high"
        elif path_cond:
            release["conductor"] = path_cond
            release["conductor_source"] = "folder_path"
            release["conductor_confidence"] = cond_conf
        else:
            release["conductor"] = None
            release["conductor_source"] = None
            release["conductor_confidence"] = None

        tag_ens = sorted({e for t in tracks for e in t["ensembles"]})
        release["ensembles"] = sorted(set(path_ens) | set(tag_ens))

        for t in tracks:
            if not t["conductor"] and release["conductor"]:
                t["conductor"] = release["conductor"]
                t["conductor_source"] = release["conductor_source"]
                t["conductor_confidence"] = release["conductor_confidence"]
            else:
                t.setdefault("conductor_source",
                             "tag" if t["conductor"] else None)
                t.setdefault("conductor_confidence",
                             "high" if t["conductor"] else None)
            if not t["ensembles"] and path_ens:
                t["ensembles"] = list(path_ens)
        release["work_ids"] = sorted({t["work_id"] for t in tracks
                                      if t["work_id"]})
        release["tracks"] = tracks
        releases.append(release)

    works = finalize_works(works, all_tracks)
    for r in releases:
        r["work_ids"] = sorted({t["work_id"] for t in r["tracks"]
                                if t["work_id"]})

    # ---- duplicate detection: same work+composer across releases,
    #      and near-identical release titles
    dupes = []
    seen_pairs = set()

    def emit(kind, confidence, rs, key):
        ids = tuple(sorted(r["release_id"] for r in rs))
        if ids in seen_pairs:
            return
        seen_pairs.add(ids)
        sizes = [r["size_bytes"] for r in rs]
        dupes.append({
            "kind": kind,
            "confidence": confidence,
            "key": key,
            "count": len(rs),
            "paths": [r["path"] for r in rs],
            "quality": [r["quality_tier"] for r in rs],
            "sizes": sizes,
            "reclaimable_bytes": sum(sizes) - max(sizes) if sizes else 0,
        })

    # exact: identical content fingerprint (same filenames and byte sizes)
    by_content = defaultdict(list)
    for r in releases:
        fp = tuple(sorted((t["filename"], t["size_bytes"])
                          for t in r["tracks"]))
        if fp and r["track_count"]:
            by_content[fp].append(r)
    for fp, rs in by_content.items():
        if len(rs) > 1:
            emit("identical_content", "high", rs, rs[0]["title"])

    # strong: same folder name in two locations, same total size
    by_folder = defaultdict(list)
    for r in releases:
        key = (strip_accents(r["folder_name"].lower()), r["size_bytes"])
        by_folder[key].append(r)
    for key, rs in by_folder.items():
        if len(rs) > 1:
            emit("same_folder_and_size", "high", rs, rs[0]["folder_name"])

    # weak: same album title but different content -> needs human review
    by_title = defaultdict(list)
    for r in releases:
        k = re.sub(r"[^a-z0-9]", "",
                   strip_accents((r["title"] or "").lower()))[:40]
        if k and k not in ("unknowntitle", "untitled", "variousartists"):
            by_title[k].append(r)
    for k, rs in by_title.items():
        if len(rs) > 1:
            emit("same_title_review", "low", rs, rs[0]["title"])

    # ---- emit
    manifest = {
        "schema": "faceted-music-library/1.0",
        "generated_from": MUSIC_ROOT,
        "field_vocabulary": "Vorbis Comment / MusicBrainz Picard names",
        "entity_tiers": ["work", "recording(track)", "release"],
        "counts": {
            "releases": len(releases),
            "tracks": len(all_tracks),
            "works": len(works),
            "container_releases": sum(1 for r in releases
                                      if r["is_container_release"]),
        },
        "facet_vocabulary": {
            "quality_tier": ["DSD", "Hi-Res", "Redbook", "Lossy", "Unknown"],
            "source_medium": ["SACD", "Vinyl", "Blu-ray", "Web", "CD",
                              "Unknown"],
            "genre_primary": ["Classical", "Jazz", "Rock"],
            "rating": "1-5, 5 = BANGERS",
            "collections": ["BANGERS"],
        },
        "works": sorted(works.values(),
                        key=lambda w: (w["composer"] or "~",)
                        + work_sort_key(w["catalog_system"],
                                        w["catalog_number"])
                        + (w["title"] or "",)),
        "releases": releases,
        "duplicate_candidates": dupes,
    }

    with open(os.path.join(OUTDIR, "library.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    # flat CSV: one row per track, denormalized with release context
    cols = ["track_id", "release_id", "path", "genre_primary", "rating",
            "collections", "composer", "work_title", "catalog_system",
            "catalog_number", "movement_number", "movement_name", "title",
            "artist_raw", "soloists", "ensembles", "conductor",
            "conductor_source", "conductor_confidence", "conductor_candidate", "album", "album_artist", "disc_number",
            "disc_subtitle", "track_number", "release_year",
            "recording_year", "label", "catalog_number_release",
            "source_medium", "quality_tier", "codec", "bit_depth",
            "sample_rate", "channels", "duration_seconds", "size_bytes",
            "isrc", "is_container_release"]
    relmap = {r["release_id"]: r for r in releases}
    with open(os.path.join(OUTDIR, "library.csv"), "w", encoding="utf-8-sig",
              newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for t in sorted(all_tracks, key=lambda x: x["path"]):
            r = relmap[t["release_id"]]
            row = dict(t)
            row["soloists"] = "; ".join(t["soloists"])
            row["ensembles"] = "; ".join(t["ensembles"])
            row["album"] = r["title"]
            row["album_artist"] = r["album_artist"]
            row["genre_primary"] = r["genre_primary"]
            row["rating"] = r["rating"]
            row["collections"] = "; ".join(r["collections"])
            row["release_year"] = r["release_year"]
            row["recording_year"] = r["recording_year"]
            row["label"] = r["label"]
            row["catalog_number_release"] = r["catalog_number"]
            row["source_medium"] = r["source_medium"]
            row["is_container_release"] = r["is_container_release"]
            w.writerow(row)

    # flattened projection for simple players: current vs proposed, no writes
    workmap = {w["work_id"]: w for w in works.values()}
    proj_cols = ["path", "genre_primary",
                 "current_albumartist", "current_album", "current_title",
                 "current_artist", "current_track", "current_disc",
                 "flat_albumartist", "flat_album", "flat_title", "flat_artist",
                 "flat_genre", "flat_track", "flat_disc", "flat_date",
                 "flat_grouping", "changed"]
    changed = 0
    with open(os.path.join(OUTDIR, "projection_flat.csv"), "w",
              encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=proj_cols, extrasaction="ignore")
        w.writeheader()
        for t in sorted(all_tracks, key=lambda x: x["path"]):
            r = relmap[t["release_id"]]
            if r["is_container_release"]:
                continue          # no per-track file to retag
            p = flat_projection(t, r, workmap.get(t.get("work_id")))
            row = {
                "path": t["path"],
                "genre_primary": r["genre_primary"],
                "current_albumartist": r["album_artist"],
                "current_album": r["title"],
                "current_title": t["title"],
                "current_artist": t["artist_raw"],
                "current_track": t["track_number"],
                "current_disc": t["disc_number"],
            }
            row.update(p)
            diff = (row["current_title"] != p["flat_title"]
                    or row["current_album"] != p["flat_album"]
                    or row["current_albumartist"] != p["flat_albumartist"])
            row["changed"] = "yes" if diff else "no"
            changed += 1 if diff else 0
            w.writerow(row)

    with open(os.path.join(OUTDIR, "works.csv"), "w", encoding="utf-8-sig",
              newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["work_id", "composer", "title",
                                           "catalog_system", "catalog_number",
                                           "recording_count"],
                           extrasaction="ignore")
        w.writeheader()
        for wk in manifest["works"]:
            w.writerow(wk)

    with open(os.path.join(OUTDIR, "duplicates.csv"), "w", encoding="utf-8-sig",
              newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["confidence", "kind", "key", "count", "reclaimable_gb",
                    "quality_tiers", "paths"])
        for d in sorted(dupes, key=lambda x: (x["confidence"] != "high",
                                              -x["reclaimable_bytes"])):
            w.writerow([d["confidence"], d["kind"], d["key"], d["count"],
                        f"{d['reclaimable_bytes'] / 2**30:.2f}",
                        " | ".join(str(q) for q in d["quality"]),
                        " | ".join(d["paths"])])

    print(json.dumps(manifest["counts"], indent=2))
    print("\ncoverage:")
    n = len(all_tracks)
    for f in ("composer", "work_title", "movement_name", "title",
              "track_number", "catalog_system", "conductor", "ensembles"):
        c = sum(1 for t in all_tracks if t.get(f))
        print(f"  {f:20s} {c*100//n:3d}%  ({c}/{n})")
    n_high = sum(1 for d in dupes if d["confidence"] == "high")
    print(f"\nduplicate clusters: {len(dupes)} ({n_high} high-confidence)")
    print(f"wrote -> {OUTDIR}")


if __name__ == "__main__":
    main()
