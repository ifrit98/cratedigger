"""Coltrane-specific domain layer: dates, sessions, eras, provenance.

The generic model in build.py is composition-centric, which is right for
classical and wrong for a jazz archive. The organizing unit here is the
**session** -- a date, a place, and a personnel -- because that is how jazz
discography actually works, and because bootlegs only make sense in
chronological order next to the studio dates they sit between.

Three sources of date, in priority order:

1. the folder name              '1961, November 18, Paris'  -> exact
2. the discography table        'A Love Supreme'            -> 1964-12-09
3. the DATE tag                 often the reissue year, so trusted last

Nothing here writes to the archive.
"""
import json
import os
import re
import unicodedata

VOCAB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vocab")
ARTISTS_DIR = os.path.join(VOCAB_DIR, "artists")

# Which artist profile to load. Everything artist-specific -- life dates,
# eras, venues, sidemen -- lives in vocab/artists/<slug>.json, so the same
# pipeline serves any artist. The constants further down are the fallback
# used only when no profile file is present.
ARTIST_SLUG = os.environ.get("CRATEDIGGER_ARTIST", "coltrane")


def _load_profile(slug=None):
    path = os.path.join(ARTISTS_DIR, (slug or ARTIST_SLUG) + ".json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


PROFILE = _load_profile()
ARTIST_NAME = PROFILE.get("name", "John Coltrane")
SESSIONS_FILE = os.path.join(
    VOCAB_DIR, PROFILE.get("sessions_file", "coltrane_sessions.json"))

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))


def _flat(s):
    """Lowercase, unaccented, and with rip separators normalised to spaces.

    `A_Love_Supreme_The_Complete_Masters` must match the key 'a love supreme'.
    Underscores and dots are word characters, so without this the key never
    matches -- the same trap that hid half the conductors in credits.py.
    """
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[_·‐-―⁃]+", " ", s)
    return re.sub(r"\s{2,}", " ", s)


# ------------------------------------------------------------------ dates
# Ordered most specific first. Every pattern yields (year, month, day) with
# month/day optional, plus a precision label.

_DATE_PATTERNS = [
    # 1965-07-26  /  1965.07.26
    ("day", re.compile(r"\b(19[3-7]\d)[-.](\d{1,2})[-.](\d{1,2})\b")),
    # 1961, November 18   |   1961,November 18   |   1961,  Nov. 18
    ("day", re.compile(r"\b(19[3-7]\d)\s*,\s*(" + _MONTH_ALT +
                       r")\.?\s+(\d{1,2})\b", re.I)),
    # November 18, 1961
    ("day", re.compile(r"\b(" + _MONTH_ALT + r")\.?\s+(\d{1,2})\s*,?\s*"
                       r"(19[3-7]\d)\b", re.I)),
    # 1961, November      |   1961,November
    ("month", re.compile(r"\b(19[3-7]\d)\s*,\s*(" + _MONTH_ALT + r")\.?\b",
                         re.I)),
    # August '57
    ("month", re.compile(r"\b(" + _MONTH_ALT + r")\.?\s+'(\d{2})\b", re.I)),
    # 1957 - Blue Train    |   1957. Dakar   |   (1957)
    ("year", re.compile(r"\b(19[3-7]\d)\b")),
    # '58 Sessions
    ("year", re.compile(r"'(\d{2})\b")),
]


# Coltrane recorded from the mid-1940s until three months before his death.
# Any "date" outside this window is a release, reissue or compilation year --
# never a recording date. Without this clamp, posthumous compilations date
# themselves to 1972-1979 and poison the chronology.
FIRST_RECORDING = PROFILE.get("active_from", "1945-01-01")
DIED = PROFILE.get("active_to", "1967-07-17")

# Titles that announce a compilation. Their tag year is an issue year and
# must not be read as a recording date.
COMPILATION_RE = re.compile(
    r"\b(best of|greatest|anthology|collection|compilation|retrospective|"
    r"ken burns|the art of|gentle side|mastery of|essential|very best|"
    r"gold\b|priceless jazz|jazz hour|masters?\b|legacy|portrait of|"
    r"introducing the|definitive|ultimate|classics\b|sampler|"
    r"his greatest|their greatest)\b", re.I)


def is_plausible_recording_date(iso):
    """False for anything outside the artist's recording life."""
    if not iso:
        return False
    d = str(iso)[:10]
    if len(d) == 4:
        d += "-06-15"          # bare year: judge by mid-year
    elif len(d) == 7:
        d += "-15"
    return FIRST_RECORDING <= d <= DIED


def is_compilation(text):
    return bool(COMPILATION_RE.search(text or ""))


def _norm_year(y):
    y = int(y)
    if y < 100:                      # '58 -> 1958
        y += 1900
    return y if 1930 <= y <= 1979 else None


def parse_recording_date(text):
    """Extract the earliest plausible recording date from a folder name.

    Returns (iso_string, precision) where precision is 'day' | 'month' |
    'year', or (None, None). The *earliest* year wins: reissue and remaster
    years appear later in a name than the recording year
    ('1963 - ... (1995 Remaster)').
    """
    if not text:
        return None, None

    for precision, rx in _DATE_PATTERNS:
        for m in rx.finditer(text):
            g = m.groups()
            try:
                if precision == "day" and len(g) == 3:
                    # Distinguish on the *second* group: '1965-07-26' has a
                    # number there, '1961, November 18' has a month name.
                    # Testing group 0 alone sends both down the ISO branch,
                    # where int("November") throws and the match is lost.
                    if g[1].isdigit():                           # YYYY-MM-DD
                        y, mo, d = _norm_year(g[0]), int(g[1]), int(g[2])
                    elif g[2].isdigit() and len(g[2]) == 4:      # Month D, YYYY
                        y, mo, d = _norm_year(g[2]), MONTHS[_flat(g[0])], int(g[1])
                    else:                                        # YYYY, Month D
                        y, mo, d = _norm_year(g[0]), MONTHS[_flat(g[1])], int(g[2])
                    if y and 1 <= mo <= 12 and 1 <= d <= 31:
                        return f"{y:04d}-{mo:02d}-{d:02d}", "day"
                elif precision == "month" and len(g) == 2:
                    if g[0].isdigit():
                        y, mo = _norm_year(g[0]), MONTHS[_flat(g[1])]
                    else:
                        y, mo = _norm_year(g[1]), MONTHS[_flat(g[0])]
                    if y and 1 <= mo <= 12:
                        return f"{y:04d}-{mo:02d}", "month"
                elif precision == "year":
                    y = _norm_year(g[0])
                    if y:
                        return f"{y:04d}", "year"
            except (KeyError, ValueError, TypeError):
                continue
    return None, None


# ------------------------------------------------------------------ eras
# The artist's working bands, from the profile. A date is assigned to the last
# era whose start it is on or after.
#
# A loaded profile is authoritative even where a list is empty. Falling back on
# emptiness would hand one artist another artist's bands -- Bill Evans would
# silently acquire Coltrane's Classic Quartet.

ERAS = ([(e["from"], e["name"]) for e in PROFILE["eras"]] if PROFILE else [
    ("1945-01-01", "Navy & apprenticeship"),
    ("1949-01-01", "Dizzy Gillespie / R&B sideman"),
    ("1955-09-01", "Miles Davis Quintet (first)"),
    ("1957-04-01", "Monk & the Prestige years"),
    ("1958-01-01", "Miles Davis Sextet / Prestige leader dates"),
    ("1959-04-01", "Atlantic years"),
    ("1961-05-01", "Impulse! -- Dolphy & the expanding group"),
    ("1962-01-01", "Classic Quartet"),
    ("1965-06-01", "Late period -- Ascension onward"),
    ("1966-01-01", "Final group (Alice Coltrane, Sanders, Ali)"),
])


def band_era(iso_date):
    if not iso_date:
        return None
    d = iso_date[:10]
    name = None
    for start, label in ERAS:
        if d >= start[:len(d)] or d >= start:
            if d >= start:
                name = label
    return name


# ------------------------------------------------------------- provenance

_LIVE_VENUES = ([(v["match"], v.get("venue"), v.get("city"), v.get("country"))
                 for v in PROFILE["venues"]] if PROFILE else [
    ("village vanguard", "Village Vanguard", "New York", "USA"),
    ("birdland", "Birdland", "New York", "USA"),
    ("half note", "Half Note", "New York", "USA"),
    ("five spot", "Five Spot", "New York", "USA"),
    ("cafe bohemia", "Café Bohemia", "New York", "USA"),
    ("newport", "Newport Jazz Festival", "Newport", "USA"),
    ("antibes", "Juan-les-Pins", "Antibes", "France"),
    ("juan les pins", "Juan-les-Pins", "Antibes", "France"),
    ("olatunji", "Olatunji Center", "New York", "USA"),
    ("temple university", "Temple University", "Philadelphia", "USA"),
    ("showboat", "Showboat", "Philadelphia", "USA"),
    ("pep's", "Pep's", "Philadelphia", "USA"),
    ("penthouse", "Penthouse", "Seattle", "USA"),
    ("soldier's field", "Soldier Field", "Chicago", "USA"),
    ("jazz casual", "Jazz Casual (TV)", None, "USA"),
    ("comblain", "Comblain-la-Tour", None, "Belgium"),
    ("konserthuset", "Konserthuset", "Stockholm", "Sweden"),
])

_CITIES = ([(c["match"], c.get("city"), c.get("country"))
            for c in PROFILE["cities"]] if PROFILE else [
    ("paris", "Paris", "France"), ("stockholm", "Stockholm", "Sweden"),
    ("copenhagen", "Copenhagen", "Denmark"), ("berlin", "Berlin", "Germany"),
    ("frankfurt", "Frankfurt", "Germany"), ("stuttgart", "Stuttgart", "Germany"),
    ("hamburg", "Hamburg", "Germany"), ("dusseldorf", "Düsseldorf", "Germany"),
    ("baden-baden", "Baden-Baden", "Germany"), ("graz", "Graz", "Austria"),
    ("vienna", "Vienna", "Austria"), ("helsinki", "Helsinki", "Finland"),
    ("finland", None, "Finland"), ("holland", None, "Netherlands"),
    ("den haag", "The Hague", "Netherlands"),
    ("belguim", None, "Belgium"), ("belgium", None, "Belgium"),
    ("kobe", "Kobe", "Japan"), ("tokyo", "Tokyo", "Japan"),
    ("japan", None, "Japan"), ("seattle", "Seattle", "USA"),
    ("chicago", "Chicago", "USA"), ("philadelphia", "Philadelphia", "USA"),
    ("new york", "New York", "USA"), ("los angeles", "Los Angeles", "USA"),
    ("san francisco", "San Francisco", "USA"),
])

_BROADCAST = re.compile(
    r"\b(tv show|television|broadcast|radio|jazz casual|rai\b|ortf|ndr|wdr|"
    r"sveriges|danmarks|telecast)\b", re.I)
_LIVE_WORD = re.compile(
    r"\b(live|concert|in concert|festival|at the|onstage|on stage|tour\b|"
    r"theatre|theater|hall\b|club\b|jazzhus|konserthuset|set\b|"
    r"first set|second set|2nd set)\b", re.I)
_REHEARSAL = re.compile(r"\b(rehearsal|soundcheck|practice|basement)\b", re.I)
_INTERVIEW = re.compile(r"\b(interview|announcement|speaks|spoken)\b", re.I)


def parse_venue(text):
    """(venue, city, country) from a folder name."""
    flat = _flat(text)
    venue = city = country = None
    for key, v, c, co in _LIVE_VENUES:
        if key in flat:
            venue, city, country = v, c, co
            break
    for key, c, co in _CITIES:
        if key in flat:
            city = city or c
            country = country or co
            break
    return venue, city, country


def classify_provenance(path, tags=None):
    """studio | live | broadcast | rehearsal | interview"""
    text = path.replace("/", " ")
    if _INTERVIEW.search(text):
        return "interview"
    if _REHEARSAL.search(text):
        return "rehearsal"
    if _BROADCAST.search(text):
        return "broadcast"
    venue, _c, _co = parse_venue(text)
    if venue or _LIVE_WORD.search(text):
        return "live"
    return "studio"


# Unofficial material: the mp3 tier is date/venue-named audience and
# broadcast tape, not catalogue releases.
_BOOTLEG_HINT = re.compile(
    r"\b(bootleg|unreleased|audience|soundboard|tape|unofficial|"
    r"private recording)\b", re.I)


def classify_authority(path, has_label=False):
    """official | unofficial

    A folder named as a bare date + place, with no album title, is a
    collector's tape rather than a catalogue release.
    """
    leaf = path.split("/")[-1]
    if _BOOTLEG_HINT.search(path):
        return "unofficial"
    iso, precision = parse_recording_date(leaf)
    if precision == "day":
        # '1961, November 18, Paris' -- date-and-place naming, no album title
        stripped = re.sub(r"\b19[3-7]\d\b|\d{1,2}", "", leaf)
        stripped = re.sub(r"\b(" + _MONTH_ALT + r")\b", "", stripped, flags=re.I)
        stripped = re.sub(r"[,\-\(\)\[\]\.\s]+", " ", stripped).strip()
        venue, city, _co = parse_venue(leaf)
        if venue or city or len(stripped.split()) <= 3:
            return "unofficial"
    return "official"


# ------------------------------------------------------------- discography

def load_sessions(path=SESSIONS_FILE):
    """Album/session -> recording date table. Editable JSON, see vocab/."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    out = {}
    for entry in data.get("sessions", []):
        for key in entry.get("match", []):
            out[_flat(key)] = entry
    return out


SESSIONS = load_sessions()


def _key_pattern(key):
    """Whole-token match. Plain substring matching is a trap here: the two
    letter key 'om' occurs inside 'C-om-plete Copenhagen', which silently
    dated that concert to the Seattle Om session."""
    return re.compile(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])")


_KEY_CACHE = {}


def lookup_session(text, sessions=None):
    """Match a folder name against the discography table.

    Scoring, in order:

    1. position in the *leaf* folder name -- an album title precedes the
       personnel list, so 'The Cats (Tommy Flanagan, ... Kenny Burrell ...)'
       resolves to The Cats and not to the Kenny Burrell album
    2. longer key wins -- 'live at the village vanguard again' beats
       'village vanguard'
    """
    sessions = SESSIONS if sessions is None else sessions
    if not text:
        return None
    flat_full = _flat(text)
    flat_leaf = _flat(text.split("/")[-1])

    best = None
    best_score = None
    for key, entry in sessions.items():
        rx = _KEY_CACHE.get(key)
        if rx is None:
            rx = _KEY_CACHE[key] = _key_pattern(key)
        m_leaf = rx.search(flat_leaf)
        if m_leaf:
            score = (0, m_leaf.start(), -len(key))
        else:
            m_full = rx.search(flat_full)
            if not m_full:
                continue
            score = (1, m_full.start(), -len(key))
        if best_score is None or score < best_score:
            best, best_score = entry, score
    return best


# ------------------------------------------------------------------ role

_LEADER_HINT = re.compile(r"\bjohn\s+coltrane\b|\bcoltrane\b", re.I)
# Names that, when they lead the folder title, mean Coltrane is a sideman.
_OTHER_LEADERS = (PROFILE["other_leaders"] if PROFILE else [
    "miles davis", "thelonious monk", "cannonball adderley", "tadd dameron",
    "hank mobley", "art taylor", "kenny burrell", "milt jackson",
    "duke ellington", "johnny hartman", "red garland", "paul chambers",
    "elmo hope", "gene ammons", "george russell", "ray draper",
    "wilbur harden", "sonny clark", "michel legrand", "don cherry",
    "archie shepp", "mal waldron", "dizzy gillespie", "johnny griffin",
    "zoot sims", "al cohn", "idrees sulieman", "tommy flanagan",
    "quinichette", "alice coltrane", "mccoy tyner",
])


def classify_role(path, album_artist=None):
    """leader | co-leader | sideman -- Coltrane's role on this release."""
    leaf = _flat(path.split("/")[-1])
    text = _flat(path) + " " + _flat(album_artist or "")
    others = [n for n in _OTHER_LEADERS if n in text]
    has_trane = bool(_LEADER_HINT.search(text))

    if not others:
        return "leader" if has_trane else "leader"
    if not has_trane:
        return "sideman"
    # both present: whoever is named first in the leaf title leads
    pos_trane = leaf.find("coltrane")
    pos_other = min((leaf.find(n) for n in others if n in leaf), default=-1)
    if pos_other == -1:
        return "leader"
    if pos_trane == -1:
        return "sideman"
    if abs(pos_trane - pos_other) < 40:
        return "co-leader"
    return "leader" if pos_trane < pos_other else "sideman"


# -------------------------------------------------------------- personnel

PERSONNEL_FILE = os.path.join(
    VOCAB_DIR, PROFILE.get("personnel_file", "coltrane_personnel.json"))


def load_personnel(path=PERSONNEL_FILE):
    """(lineups, musicians, matcher). Empty structures if the file is absent."""
    if not os.path.exists(path):
        return [], {}, None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return [], {}, None

    lineups = data.get("lineups", [])
    musicians, alias_to_name = {}, {}
    for m in data.get("musicians", []):
        musicians[m["name"]] = m
        for a in [m["name"]] + list(m.get("aliases", [])):
            alias_to_name[_flat(a)] = m["name"]

    # One compiled alternation, longest alias first so 'philly joe jones'
    # wins over 'jones' and 'alice coltrane' over 'coltrane'.
    keys = sorted(alias_to_name, key=len, reverse=True)
    matcher = re.compile(
        r"(?<![a-z])(" + "|".join(re.escape(k) for k in keys) + r")(?![a-z])"
    ) if keys else None
    return lineups, musicians, (matcher, alias_to_name)


LINEUPS, MUSICIANS, _MATCHER = load_personnel()


def lineup_for(iso_date, lineups=None):
    """The working band on a given date, or None.

    Year-only dates are judged at mid-year; a bare '1961' therefore lands in
    the Dolphy group rather than being forced into either neighbour.
    """
    lineups = LINEUPS if lineups is None else lineups
    if not iso_date or not lineups:
        return None
    d = str(iso_date)[:10]
    if len(d) == 4:
        d += "-06-15"
    elif len(d) == 7:
        d += "-15"
    for lu in lineups:
        if lu["from"] <= d < lu["to"]:
            return lu
    return None


def extract_musicians(text, matcher=None):
    """Musicians named anywhere in the text, canonicalised and de-duplicated.

    Coltrane himself is dropped -- he is on everything, so recording him adds
    nothing and would swamp the facet.
    """
    pair = _MATCHER if matcher is None else matcher
    if not pair or not text:
        return []
    rx, alias_to_name = pair
    found = []
    for m in rx.finditer(_flat(text)):
        name = alias_to_name.get(m.group(1))
        if name and name != "John Coltrane" and name not in found:
            found.append(name)
    return found


def personnel_for(path, album_artist, artist_tag, iso_date):
    """Combine the two sources into one credited lineup.

    Names written into the folder or tags win, because they describe *this*
    session. The date-ranged working band fills in everything else, which is
    most of the archive.
    """
    named = extract_musicians(" ".join(
        x for x in [path.replace("/", " "), album_artist or "", artist_tag or ""]
        if x))
    lu = lineup_for(iso_date)
    band = [m["name"] for m in (lu or {}).get("members", [])
            if m["name"] != "John Coltrane"]

    # Named musicians win outright. Merging the date-range band on top of
    # them produces nonsense: 'The Cats' (a 1957 Prestige date with Flanagan,
    # Burrell and Sulieman) would otherwise acquire Monk's rhythm section
    # purely because it falls inside the Five Spot residency. An incomplete
    # credit is honest; a wrong one is not.
    if named:
        return named, (lu or {}).get("name"), (lu or {}).get("id"), "named"
    if band:
        return band, lu.get("name"), lu.get("id"), "lineup"
    return [], None, None, None


def instrument_of(name):
    return (MUSICIANS.get(name) or {}).get("instrument")


# ------------------------------------------------------------------ tunes

# A leading track number is only a track number when a *letter* follows.
# Requiring only a separator ate '26-2', a real Coltrane composition, down
# to '2'. Allowing a bare space as separator is what catches '07 Naima'.
# A leading track number is only a track number when a *letter* follows.
# Requiring only a separator ate '26-2', a real Coltrane composition, down
# to '2'. Allowing a bare space as separator is what catches '07 Naima'.
#
# The first alternative handles the disc-track form '1-06 My Favorite
# Things'. It demands whitespace before the title, which is exactly what
# distinguishes it from a tune called '26-2'.
_TRACK_NUM = re.compile(
    r"^\s*(?:"
    r"\d{1,2}-\d{1,3}\s+"                     # 1-06 Title
    r"|(?:cd\s*\d+\s*[-._)]?\s*)?\d{1,3}\s*[-._)\s]\s*"   # 07 Title
    r")(?=[^\d\s])",
    re.I)
# Takes are written every which way: '(Take 2)', 'take 3', '(Alternate
# Take)', '[alt]'. The word boundary on the bare form matters -- without it
# 'Mistake 2' reads as take 2.
_TAKE = re.compile(
    r"\((?:alternate\s+)?take\s*(\d+)\)"    # (Take 2), (Alternate Take 2)
    r"|\btake\s*(\d+)\b"                    # take 3
    r"|\balt(?:ernate)?\s*take\b"            # Alternate Take
    r"|\(alternate\)|\[alt\]",              # (alternate), [alt]
    re.I)


def extract_take(title):
    """'2' | 'alt' | None.

    The single source of truth for take detection. coltrane_build.py used to
    re-derive this with a weaker pattern, so '(Alternate Take)' was stripped
    from the title without ever being recorded as a take.
    """
    if not title:
        return None
    m = _TAKE.search(str(title))
    if not m:
        return None
    return m.group(1) or m.group(2) or "alt"


def normalize_tune(title):
    """A tune title reduced to a comparison key.

    'My Favorite Things', '03 - My Favourite Things (Take 2)' and
    'My Favorite Things [alt]' all collapse to the same key so every
    performance of a tune can be gathered.
    """
    if not title:
        return None, None
    s = _TRACK_NUM.sub("", str(title)).strip()
    take = None
    m = _TAKE.search(s)
    if m:
        take = m.group(1) or m.group(2) or "alt"
    s = _TAKE.sub("", s)
    s = re.sub(r"\[[^\]]*\]|\((?:live|mono|stereo|remaster(?:ed)?|"
               r"alternate|incomplete|part\s*\d+|edit)[^)]*\)", "", s,
               flags=re.I)
    # Removing '(Alternate Take)' leaves an empty '()' behind; strip any
    # bracket pair the removal emptied out.
    s = re.sub(r"[\(\[]\s*[\)\]]", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" -_.")
    key = _flat(s)
    key = re.sub(r"\b(the|a|an)\b", "", key)
    key = re.sub(r"favourite", "favorite", key)
    key = re.sub(r"[^a-z0-9]", "", key)
    return (s or None), (key or None)
