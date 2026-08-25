"""Recover conductor and ensemble credits from folder paths.

Most classical rips carry no CONDUCTOR tag but name the conductor and
orchestra in the directory. This module reads those names back out.

Design for durability on a large library:

* **Vocabulary lives in data files**, not in code. `vocab/conductors.json`
  and `vocab/ensembles.json` are loaded at import; `mbfetch.py` grows them
  from MusicBrainz and `mine.py` proposes additions found in your own
  folder names. The seed below is only a fallback when the files are absent.
* **Structural rules work without any dictionary.** `CSO_Barenboim`,
  `Berlin Philharmonic, C.Schuricht` and `(… Orchestra, Litton - BIS)` are
  recognised by shape, so a conductor nobody has ever added still resolves.
* **Matching is compiled once** into single alternations. Scanning 43k
  folders against a 1,000-name vocabulary stays linear in the text, not in
  the size of the vocabulary.

Gating rule that keeps this honest: a conductor is only asserted when an
ensemble is also present. Barenboim, Bernstein, Ashkenazy and Richter are
performers as often as conductors, so 'Beethoven Piano Sonatas Barenboim'
is a recital, not a conducted work.
"""
import json
import os
import re
import unicodedata

VOCAB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vocab")

# Separators that rips use between an ensemble and a conductor. Underscore is
# a word character, so 'CSO_Barenboim' defeats \b matching unless normalised.
_SEPARATORS = re.compile(r"[_·•∙/\\|~]+")
_PUNCT_RUN = re.compile(r"\s{2,}")


def _flat(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()


def normalize(text):
    """Folder text -> matchable text. Separators become spaces so word
    boundaries work; initials are spaced out ('C.Schuricht' -> 'C Schuricht')."""
    s = _SEPARATORS.sub(" ", text or "")
    s = re.sub(r"\b([A-Z])\.\s*(?=[A-Z][a-z])", r"\1 ", s)   # C.Schuricht
    s = re.sub(r"(?<=[a-z])\.(?=[A-Z])", ". ", s)            # Suite.Karajan
    return _PUNCT_RUN.sub(" ", s).strip()


# --------------------------------------------------------------- seed vocab
# Fallback only. The shipped vocab/*.json supersedes these.

SEED_CONDUCTORS = {
    "karajan": ("Herbert von Karajan", ["hvk", "h v k", "von karajan"]),
    "furtwangler": ("Wilhelm Furtwängler", ["furt", "furtw"]),
    "bohm": ("Karl Böhm", ["boehm"]),
    "walter": ("Bruno Walter", []),
    "celibidache": ("Sergiu Celibidache", ["celi"]),
    "barenboim": ("Daniel Barenboim", []),
    "ozawa": ("Seiji Ozawa", []),
    "reiner": ("Fritz Reiner", []),
    "giulini": ("Carlo Maria Giulini", []),
    "boulez": ("Pierre Boulez", []),
    "mackerras": ("Charles Mackerras", []),
    "jochum": ("Eugen Jochum", []),
    "toscanini": ("Arturo Toscanini", []),
    "bernstein": ("Leonard Bernstein", []),
    "klemperer": ("Otto Klemperer", []),
    "krips": ("Josef Krips", []),
    "dorati": ("Antal Doráti", []),
    "muti": ("Riccardo Muti", []),
    "rattle": ("Simon Rattle", []),
    "thielemann": ("Christian Thielemann", []),
    "honeck": ("Manfred Honeck", []),
    "haitink": ("Bernard Haitink", []),
    "solti": ("Georg Solti", []),
    "abbado": ("Claudio Abbado", []),
    "szell": ("George Szell", []),
    "monteux": ("Pierre Monteux", []),
    "munch": ("Charles Munch", []),
    "ormandy": ("Eugene Ormandy", []),
    "stokowski": ("Leopold Stokowski", []),
    "mravinsky": ("Evgeny Mravinsky", []),
    "kondrashin": ("Kirill Kondrashin", []),
    "svetlanov": ("Evgeny Svetlanov", []),
    "gergiev": ("Valery Gergiev", []),
    "jansons": ("Mariss Jansons", []),
    "chailly": ("Riccardo Chailly", []),
    "harnoncourt": ("Nikolaus Harnoncourt", []),
    "hogwood": ("Christopher Hogwood", []),
    "pinnock": ("Trevor Pinnock", []),
    "norrington": ("Roger Norrington", []),
    "herreweghe": ("Philippe Herreweghe", []),
    "koopman": ("Ton Koopman", []),
    "suitner": ("Otmar Suitner", []),
    "sanderling": ("Kurt Sanderling", []),
    "wand": ("Günter Wand", []),
    "skrowaczewski": ("Stanisław Skrowaczewski", ["skrowaczewsk"]),
    "tennstedt": ("Klaus Tennstedt", []),
    "maazel": ("Lorin Maazel", []),
    "previn": ("André Previn", []),
    "levine": ("James Levine", []),
    "mehta": ("Zubin Mehta", []),
    "dutoit": ("Charles Dutoit", []),
    "marriner": ("Neville Marriner", []),
    "cluytens": ("André Cluytens", []),
    "knappertsbusch": ("Hans Knappertsbusch", []),
    "keilberth": ("Joseph Keilberth", []),
    "konwitschny": ("Franz Konwitschny", []),
    "horenstein": ("Jascha Horenstein", []),
    "scherchen": ("Hermann Scherchen", []),
    "ancerl": ("Karel Ančerl", []),
    "kubelik": ("Rafael Kubelík", []),
    "fricsay": ("Ferenc Fricsay", []),
    "leinsdorf": ("Erich Leinsdorf", []),
    "steinberg": ("William Steinberg", []),
    "paray": ("Paul Paray", []),
    "beecham": ("Thomas Beecham", []),
    "barbirolli": ("John Barbirolli", []),
    "boult": ("Adrian Boult", []),
    "sargent": ("Malcolm Sargent", []),
    "nelsons": ("Andris Nelsons", []),
    "dudamel": ("Gustavo Dudamel", []),
    "salonen": ("Esa-Pekka Salonen", []),
    "blomstedt": ("Herbert Blomstedt", []),
    "minkowski": ("Marc Minkowski", []),
    "christie": ("William Christie", []),
    "rousset": ("Christophe Rousset", []),
    "antonini": ("Giovanni Antonini", []),
    "currentzis": ("Teodor Currentzis", []),
    "gardiner": ("John Eliot Gardiner", []),
    "savall": ("Jordi Savall", []),
    "egarr": ("Richard Egarr", []),
    "kuijken": ("Sigiswald Kuijken", []),
    "schmidt-isserstedt": ("Hans Schmidt-Isserstedt", []),
    "shaw": ("Robert Shaw", []),
    "matacic": ("Lovro von Matačić", []),
    "gielen": ("Michael Gielen", []),
    "nagano": ("Kent Nagano", []),
    "masur": ("Kurt Masur", []),
    "schuricht": ("Carl Schuricht", []),
    "dohnanyi": ("Christoph von Dohnányi", []),
    "tintner": ("Georg Tintner", []),
    "litton": ("Andrew Litton", []),
    "young": ("Simone Young", []),
    "haenchen": ("Hartmut Haenchen", []),
    "inbal": ("Eliahu Inbal", []),
    "chelibidache": ("Sergiu Celibidache", []),
    "walcha": ("Helmut Walcha", []),
    "willens": ("Michael Alexander Willens", []),
    "chauvin": ("Julien Chauvin", []),
    "gonzales-monjas": ("Roberto González-Monjas", []),
    "widmann": ("Jörg Widmann", []),
}

SEED_AMBIGUOUS = {
    "kleiber": ("Kleiber (Carlos or Erich)",
                {"carlos": "Carlos Kleiber", "erich": "Erich Kleiber"}),
    "davis": ("Davis (Colin or Andrew)",
              {"colin": "Colin Davis", "andrew": "Andrew Davis"}),
    "richter": ("Richter (Karl, conductor — or Sviatoslav, pianist)",
                {"karl": "Karl Richter"}),
    "fischer": ("Fischer (Iván or Ádám)",
                {"ivan": "Iván Fischer", "adam": "Ádám Fischer"}),
    "jarvi": ("Järvi (Neeme, Paavo or Kristjan)",
              {"neeme": "Neeme Järvi", "paavo": "Paavo Järvi",
               "kristjan": "Kristjan Järvi"}),
    "petrenko": ("Petrenko (Kirill or Vasily)",
                 {"kirill": "Kirill Petrenko", "vasily": "Vasily Petrenko"}),
    "kempe": ("Rudolf Kempe", {"rudolf": "Rudolf Kempe"}),
    "jansen": ("Jansen (Janine, violinist — or conductor)", {}),
}

# Conductors equally famous as instrumentalists: require a named ensemble.
SEED_NEEDS_ENSEMBLE = [
    "barenboim", "bernstein", "richter", "previn", "koopman", "egarr",
    "pinnock", "hogwood", "rousset", "christie", "antonini", "widmann",
    "savall", "gardiner", "harnoncourt", "fischer", "jarvi", "kuijken",
    "walcha", "ashkenazy", "perahia", "eschenbach", "zukerman", "young",
]

SEED_ABBREV = {
    "VPO": "Wiener Philharmoniker", "WPO": "Wiener Philharmoniker",
    "BPO": "Berliner Philharmoniker", "BPH": "Berliner Philharmoniker",
    "CSO": "Chicago Symphony Orchestra",
    "LSO": "London Symphony Orchestra",
    "LPO": "London Philharmonic Orchestra",
    "NYPO": "New York Philharmonic", "NYP": "New York Philharmonic",
    "BSO": "Boston Symphony Orchestra",
    "RCO": "Royal Concertgebouw Orchestra", "COA": "Royal Concertgebouw Orchestra",
    "SB": "Staatskapelle Berlin", "SKB": "Staatskapelle Berlin",
    "SKD": "Staatskapelle Dresden",
    "ECO": "English Chamber Orchestra",
    "COE": "Chamber Orchestra of Europe",
    "OSR": "Orchestre de la Suisse Romande",
    "ASMF": "Academy of St Martin in the Fields",
    "SFS": "San Francisco Symphony",
    "CBSO": "City of Birmingham Symphony Orchestra",
    "RPO": "Royal Philharmonic Orchestra",
    "MPO": "Munich Philharmonic Orchestra",
    "BRSO": "Bavarian Radio Symphony Orchestra",
    "ONF": "Orchestre National de France",
    "PO": "Philharmonia Orchestra",
    "RSOB": "Radio-Symphonie-Orchester Berlin",
    "SWF": "SWF Sinfonieorchester Baden-Baden",
    "SWR": "SWR Sinfonieorchester",
    "WDR": "WDR Sinfonieorchester Köln",
    "NDR": "NDR Elbphilharmonie Orchester",
    "ORF": "ORF Radio-Symphonieorchester Wien",
    "LAPO": "Los Angeles Philharmonic",
    "RSNO": "Royal Scottish National Orchestra",
    "OAE": "Orchestra of the Age of Enlightenment",
    "SCO": "Scottish Chamber Orchestra",
    "MCO": "Mahler Chamber Orchestra",
    "AAM": "Academy of Ancient Music",
    "DSO": "Deutsches Symphonie-Orchester Berlin",
    "HSO": "Houston Symphony Orchestra",
    "PSO": "Pittsburgh Symphony Orchestra",
    "SFSO": "San Francisco Symphony",
    "TSO": "Toronto Symphony Orchestra",
}

SEED_PATTERNS = [
    ["wiener philharmoniker|vienna philharmonic", "Wiener Philharmoniker"],
    ["berliner philharmoniker|berlin philharmonic", "Berliner Philharmoniker"],
    ["staatskapelle dresden", "Staatskapelle Dresden"],
    ["staatskapelle berlin", "Staatskapelle Berlin"],
    ["concertgebouw", "Royal Concertgebouw Orchestra"],
    ["chicago s(?:ymphony|o\\b)", "Chicago Symphony Orchestra"],
    ["boston s(?:ymphony|o\\b)", "Boston Symphony Orchestra"],
    ["pittsburgh s(?:ymphony|o\\b)", "Pittsburgh Symphony Orchestra"],
    ["cleveland orchestra", "Cleveland Orchestra"],
    ["philadelphia orchestra", "Philadelphia Orchestra"],
    ["new york phil", "New York Philharmonic"],
    ["london symphony", "London Symphony Orchestra"],
    ["london philharmonic", "London Philharmonic Orchestra"],
    ["philharmonia\\b", "Philharmonia Orchestra"],
    ["english chamber orchestra", "English Chamber Orchestra"],
    ["english concert", "The English Concert"],
    ["bamberger symphoniker", "Bamberger Symphoniker"],
    ["royal philharmonic", "Royal Philharmonic Orchestra"],
    ["mozarteumorchester", "Mozarteumorchester Salzburg"],
    ["academy of ancient music", "Academy of Ancient Music"],
    ["wiener singverein", "Wiener Singverein"],
    ["gewandhaus", "Gewandhausorchester Leipzig"],
    ["suisse romande", "Orchestre de la Suisse Romande"],
    ["munchner philharmoniker|munich phil", "Münchner Philharmoniker"],
    ["czech philharmonic", "Czech Philharmonic"],
    ["leningrad phil", "Leningrad Philharmonic"],
    ["nbc symphony", "NBC Symphony Orchestra"],
    ["orchestre de paris", "Orchestre de Paris"],
    ["bergen philharmonic", "Bergen Philharmonic Orchestra"],
    ["royal scottish national", "Royal Scottish National Orchestra"],
    ["saarland radio symphony", "Saarland Radio Symphony Orchestra"],
    ["bavarian (?:radio|state)", "Bavarian Radio Symphony Orchestra"],
    ["israel philharmonic", "Israel Philharmonic Orchestra"],
    ["los angeles phil", "Los Angeles Philharmonic"],
    ["dresdner staatskapelle", "Staatskapelle Dresden"],
    ["philharmoniker hamburg", "Philharmoniker Hamburg"],
]

# Words that mark a token group as an ensemble even when unknown by name.
GENERIC_ENSEMBLE = re.compile(
    r"\b(orchestra\w*|orchestre|orchester\w*|orkest|philharmoni\w*|"
    r"symphoni\w*|symphony|sinfoni\w*|staatskapelle|kapelle|singverein|"
    r"chorus|choir|chor\b|kamerkoor|quartet|quintet|ensemble|akademie|"
    r"academy|camerata|collegium|consort|capella|cappella|concert\b|"
    r"concerto grosso|orkiestra|filarmonica|tonhalle|gewandhaus)\b", re.I)

# Composers whose surnames appear constantly in folder titles. The structural
# rules must never mistake the composer being played for the conductor.
COMPOSER_BLOCK = {
    "bach", "mozart", "beethoven", "brahms", "mahler", "wagner", "strauss",
    "schubert", "schumann", "liszt", "chopin", "haydn", "handel", "bruckner",
    "britten", "berg", "franck", "stravinsky", "debussy", "ravel", "vivaldi",
    "tchaikovsky", "dvorak", "sibelius", "faure", "bartok", "ligeti",
    "shostakovich", "rachmaninov", "berlioz", "schoenberg", "webern",
    "hindemith", "janacek", "elgar", "copland", "gershwin", "scarlatti",
    "telemann", "purcell", "monteverdi", "prokofiev", "mendelssohn",
    "messiaen", "barber", "ives", "respighi", "verdi", "puccini", "rossini",
    "borodin", "mussorgsky", "rimsky-korsakov", "glazunov", "scriabin",
    "poulenc", "milhaud", "satie", "nielsen", "grieg", "smetana", "weber",
}

_CAP = r"[A-ZÄÖÜÅÉÈÁÀÍÓÚŠŽČŁ][\w'’\-]+"
# 'Litton', 'Simone Young', 'Christoph von Dohnányi'
_NAME = (_CAP + r"(?:\s+(?:von|van|de|di|del|der|den|ten)\s+" + _CAP + r"|"
         r"\s+" + _CAP + r")?")


# --------------------------------------------------------------- vocabulary

class Vocab:
    """Compiled matcher set. Build once, reuse across the whole scan."""

    def __init__(self, conductors, ambiguous, needs_ensemble, abbrev,
                 patterns):
        self.conductors = conductors          # key -> {"name":..,"aliases":[]}
        self.ambiguous = ambiguous            # key -> {"label":..,"variants":{}}
        self.needs_ensemble = set(needs_ensemble)
        self.abbrev = abbrev                  # "VPO" -> canonical
        self.patterns = patterns              # [[regex, canonical], ...]

        # alias -> canonical key, so 'HvK' resolves to karajan
        self.alias_to_key = {}
        for key, entry in conductors.items():
            self.alias_to_key[key] = key
            for a in entry.get("aliases", []):
                self.alias_to_key[_flat(a)] = key

        keys = sorted(self.alias_to_key, key=len, reverse=True)
        self._cond_re = self._alt(keys)
        amb = sorted(ambiguous, key=len, reverse=True)
        self._amb_re = self._alt(amb)
        self._pat_re = [(re.compile(p, re.I), n) for p, n in patterns]
        self._abbrev_re = re.compile(
            r"\b(" + "|".join(sorted(map(re.escape, abbrev), key=len,
                                     reverse=True)) + r")\b") if abbrev else None

    @staticmethod
    def _alt(keys):
        if not keys:
            return None
        return re.compile(r"\b(" + "|".join(re.escape(k) for k in keys)
                          + r")\b")

    @property
    def size(self):
        return len(self.conductors), len(self.abbrev) + len(self.patterns)


def _seed_vocab():
    return Vocab(
        {k: {"name": v[0], "aliases": v[1]}
         for k, (v) in SEED_CONDUCTORS.items()},
        {k: {"label": v[0], "variants": v[1]}
         for k, v in SEED_AMBIGUOUS.items()},
        SEED_NEEDS_ENSEMBLE, dict(SEED_ABBREV), [list(p) for p in SEED_PATTERNS],
    )


def load_vocab(vocab_dir=VOCAB_DIR):
    """Load vocab/*.json, falling back to the built-in seed."""
    cpath = os.path.join(vocab_dir, "conductors.json")
    epath = os.path.join(vocab_dir, "ensembles.json")
    if not (os.path.exists(cpath) and os.path.exists(epath)):
        return _seed_vocab()
    try:
        with open(cpath, encoding="utf-8") as fh:
            c = json.load(fh)
        with open(epath, encoding="utf-8") as fh:
            e = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return _seed_vocab()

    return Vocab(
        c.get("entries", {}),
        {k: v for k, v in c.get("ambiguous", {}).items()},
        c.get("needs_ensemble", SEED_NEEDS_ENSEMBLE),
        e.get("abbreviations", {}),
        e.get("patterns", []),
    )


VOCAB = load_vocab()


def reload_vocab(vocab_dir=VOCAB_DIR):
    global VOCAB
    VOCAB = load_vocab(vocab_dir)
    return VOCAB


# --------------------------------------------------------------- extraction

def find_ensembles(text, vocab=None):
    """Canonical ensembles named anywhere in the text."""
    vocab = vocab or VOCAB
    norm = normalize(text)
    flat = _flat(norm)
    found, seen = [], set()

    def add(name):
        k = re.sub(r"[^a-z]", "", _flat(name))
        if not k:
            return
        for existing in list(seen):
            if k in existing or existing in k:
                return
        seen.add(k)
        found.append(name)

    for rx, canon in vocab._pat_re:
        m = rx.search(flat)
        if m:
            add(canon or m.group(0).title())
    if vocab._abbrev_re:
        for tok in vocab._abbrev_re.findall(norm):
            add(vocab.abbrev[tok])
    return found


def _resolve(key, text_flat, vocab):
    """Turn a matched key into (name, confidence)."""
    if key in vocab.ambiguous:
        entry = vocab.ambiguous[key]
        for fore, full in (entry.get("variants") or {}).items():
            if re.search(r"\b" + re.escape(_flat(fore)) + r"\b", text_flat):
                return full, "high"
        return entry.get("label", key), "ambiguous"
    real = vocab.alias_to_key.get(key, key)
    return vocab.conductors[real]["name"], "high"


def _forename_present(entry, flat):
    """Does a forename from the canonical name also appear in the text?

    This is what licenses a guarded surname: 'Mahler' alone is the composer,
    but 'Gustav Mahler' next to an orchestra is the conductor.
    """
    parts = (entry.get("name") or "").split()
    for p in parts[:-1]:
        p = re.sub(r"[^\w'-]", "", p)
        if len(p) > 2 and re.search(r"\b" + re.escape(_flat(p)) + r"\b", flat):
            return True
    return False


_PARTICLES = {"von", "van", "de", "di", "del", "der", "den", "ten", "la",
              "le", "du", "da", "dos", "el"}

# Format, edition and packaging words. Never a person's surname.
_NOISE_TOKENS = {
    "pcm", "flac", "dsd", "sacd", "iso", "cd", "dvd", "sad", "wav", "ape",
    "live", "mono", "stereo", "remaster", "remastered", "box", "set",
    "complete", "edition", "recordings", "recording", "vol", "volume",
    "disc", "disk", "part", "excerpts", "selections", "highlights",
    "symphony", "concerto", "sonata", "suite", "overture", "quartet",
}


def _preceding_token(norm, start):
    """The word immediately before a match, in original casing."""
    before = norm[:start].rstrip()
    m = re.search(r"([\w'’\-\.]+)$", before)
    return m.group(1) if m else ""


def _forename_conflict(entry, norm, start):
    """True when the name in front of the surname belongs to someone else.

    'Clark Terry' must not resolve to conductor Andrew Terry, and
    'Herbie Hancock' must not resolve to Gareth Hancock. A preceding token
    that is neither an ensemble word, an initial, nor one of this person's
    own forenames means we have the wrong person entirely.
    """
    prev = _preceding_token(norm, start)
    if not prev or not prev[:1].isupper():
        return False                      # nothing, or lowercase filler
    flat_prev = _flat(prev).strip(".")
    if flat_prev in _PARTICLES:
        return False
    if GENERIC_ENSEMBLE.search(prev) or prev.isupper():
        return False                      # 'VPO_Kleiber', 'CSO Reiner'
    forenames = [_flat(re.sub(r"[^\w'-]", "", p))
                 for p in (entry.get("name") or "").split()[:-1]]
    forenames = [f for f in forenames if f]
    if not forenames:
        return False
    if len(flat_prev) == 1:               # initial: 'G Szell', 'C Schuricht'
        return not any(f.startswith(flat_prev) for f in forenames)
    return flat_prev not in forenames


def _is_forename_of_other(entry, norm, end):
    """True when the match is really the first name of somebody else.

    'Peter Altenberg' matches conductor Sandra Peter on the surname 'peter',
    but Peter is followed by a different surname, so it is a forename here.
    """
    after = norm[end:end + 30].lstrip()
    m = re.match(r"([A-ZÄÖÜÅÉÈÁÀÍÓÚŠŽČŁ][\w'’\-]+)", after)
    if not m:
        return False
    nxt = m.group(1)
    if _flat(nxt) in _PARTICLES or GENERIC_ENSEMBLE.match(nxt):
        return False
    # format and edition noise is not a surname: 'BPO_HvK PCM', 'VPO_Furt PCM'
    if nxt.isupper() or _flat(nxt) in _NOISE_TOKENS:
        return False
    own_surname = _flat((entry.get("name") or "").split()[-1])         if entry.get("name") else ""
    return _flat(nxt) != own_surname


def find_conductor(text, composer_surnames=(), vocab=None):
    """Dictionary lookup. Returns (name, confidence, key).

    Matching runs over case-preserving text so that a capitalised surname can
    be told apart from an ordinary word ('guest' vs the conductor Guest).
    """
    vocab = vocab or VOCAB
    norm = normalize(text)
    flat = _flat(norm)
    blocked = {_flat(s).split(",")[0].strip() for s in composer_surnames}

    def scan(rx, ambiguous):
        if not rx:
            return None
        spans = [(m.start(), m.end(), m.group(1)) for m in rx.finditer(flat)]
        # a key immediately followed by another key is a forename, not the
        # surname: in 'Trevor Pinnock' both match, only Pinnock is meant
        spans = [(s, e, k) for (s, e, k) in spans
                 if not any(0 < s2 - e <= 2 for (s2, _, _) in spans)] or spans
        for s, e, key in spans:
            real = key if ambiguous else vocab.alias_to_key.get(key, key)
            if real in blocked or key in blocked:
                continue
            # a real name is capitalised in the source text
            if not norm[s:s + 1].isupper():
                continue
            entry = ({} if ambiguous
                     else (vocab.conductors.get(real) or {}))
            if not ambiguous:
                if entry.get("guarded") and not _forename_present(entry, flat):
                    continue
                if _forename_conflict(entry, norm, s):
                    continue
                if _is_forename_of_other(entry, norm, e):
                    continue
                if re.match(r"\s(?:" + GENERIC_ENSEMBLE.pattern + r")",
                            norm[e:e + 24], re.I):
                    continue          # 'Hagen Quartet' is the ensemble's name
            name, conf = _resolve(key, flat, vocab)
            return name, conf, real
        return None

    return scan(vocab._cond_re, False) or scan(vocab._amb_re, True) \
        or (None, None, None)


def find_conductor_structural(text, composer_surnames=()):
    """Dictionary-free extraction from shape alone.

    Catches names no vocabulary has yet: 'CSO_Barenboim',
    'Berlin Philharmonic, C.Schuricht', '(… Orchestra, Litton - BIS)'.
    Returns (name, rule) or (None, None).
    """
    norm = normalize(text)
    blocked = {_flat(s).split(",")[0].strip() for s in composer_surnames}
    segment = norm.split("/")[-1] if "/" in norm else norm

    def ok(cand, end=None):
        cand = cand.strip(" .,-–—")
        if not cand or len(cand) < 3:
            return None
        if GENERIC_ENSEMBLE.search(cand):
            return None
        if re.search(r"\d", cand):
            return None
        flat = _flat(cand)
        if flat in blocked or flat.split()[-1] in blocked:
            return None
        # a composer named in the title is not the conductor
        if flat in COMPOSER_BLOCK or flat.split()[-1] in COMPOSER_BLOCK:
            return None
        # 'Hagen Quartet' names an ensemble, not a conductor called Hagen
        if end is not None and re.match(
                r"\s(?:" + GENERIC_ENSEMBLE.pattern + r")",
                segment[end:end + 24], re.I):
            return None               # 'Hagen Quartet' is the ensemble's name
        # reject format/edition noise
        if re.match(r"^(pcm|flac|live|mono|stereo|remaster|sacd|iso|dsd|cd|"
                    r"disc|vol|box|complete|the|and|with)\b", flat):
            return None
        return cand

    # Rule 1: '<ENSEMBLE>_<Name>' -- the 'Bruckner 5 CSO_Barenboim PCM'
    # convention. Underscores are normalised away for matching, so the split
    # is recovered from the raw text.
    raw = text.split("/")[-1]
    if "_" in raw:
        left, _, right = raw.partition("_")
        cand = ok(re.split(r"\s+(?:PCM|FLAC|DSD|SACD|ISO|Live|\d{4})\b",
                           right, flags=re.I)[0])
        if cand:
            left_tokens = normalize(left).split()
            tail = left_tokens[-1] if left_tokens else ""
            strong = bool(GENERIC_ENSEMBLE.search(normalize(left))) or \
                bool(re.fullmatch(r"[A-Z]{2,6}", tail))
            return cand, "underscore" if strong else "underscore_weak"

    # Rule 2: '<ensemble words>, <Name>'  e.g. 'Philharmonia Orchestra, Klemperer'
    for m in re.finditer(r"(" + GENERIC_ENSEMBLE.pattern + r"[^,()]{0,30}),\s*("
                         + _NAME + r")", segment, re.I):
        cand = ok(m.group(m.lastindex), m.end())
        if cand:
            return cand, "ensemble_comma"

    # Rule 3: '<Name>, <ensemble words>'  e.g. 'C Schuricht, Berlin Philharmonic'
    # Two tokens required -- an initial or forename plus a surname. A single
    # bare word before ', <ensemble>' is far more often the work being played
    # ('Inventions, Academy of Ancient Music') than a conductor.
    for m in re.finditer(r"\b(" + _NAME + r"),\s*[^,]{0,20}?"
                         + GENERIC_ENSEMBLE.pattern, segment, re.I):
        cand = ok(m.group(1), m.end(1))
        if cand and not _work_like(cand):
            return cand, "comma_ensemble"

    return None, None


# Words that never appear in a person's name. Checked per token, so
# 'Egmont Overture' and 'Funeral Music' are both rejected.
_NOT_A_NAME = {
    "piano", "violin", "cello", "viola", "organ", "flute", "horn", "solo",
    "duo", "live", "suite", "suites", "works", "work", "music", "musik",
    "concert", "concerto", "concertos", "opera", "orchestra", "sonata",
    "sonatas", "symphony", "symphonies", "sinfonia", "edition", "recording",
    "recordings", "complete", "selection", "selections", "highlights",
    "excerpts", "disc", "disk", "part", "volume", "vol", "chor", "choir",
    "chorus", "the", "and", "with", "overture", "overtures", "egmont",
    "leonore", "fidelio", "eroica", "prelude", "preludes", "fugue",
    "variation", "variations", "mass", "requiem", "cantata", "cantatas",
    "motet", "motets", "nocturne", "nocturnes", "scherzo", "rhapsody",
    "fantasia", "serenade", "divertimento", "funeral", "masonic", "sacred",
    "quartet", "quintet", "trio", "octet", "minor", "major", "op", "no",
    "pcm", "flac", "dsd", "sacd", "iso", "box", "set", "cycle", "variants",
}


# Fragments of work titles that survive the token filter because every word
# is capitalised: 'Des Knaben Wunderhorn', 'Ein Deutsches Requiem'.
_WORK_WORDS = {
    "knaben", "wunderhorn", "klagende", "lied", "lieder", "deutsches",
    "kindertotenlieder", "gesange", "gesänge", "stucke", "stücke", "tanze",
    "tänze", "walzer", "marsch", "messe", "passion", "oratorium", "singspiel",
    "inventions", "invention", "sinfonien", "konzert", "konzerte", "quatuor",
    "sonate", "sonaten", "praeludium", "toccata", "chaconne", "passacaglia",
    "capriccio", "impromptu", "ballade", "etudes", "etuden", "bagatelles",
    "goldberg", "brandenburg", "jeux", "images", "estampes", "preludes",
}


def _work_like(cand):
    """True when a capitalised phrase is really a piece, not a person."""
    return any(_flat(t.strip("'’-")) in _WORK_WORDS
               for t in re.split(r"[\s\.]+", cand) if t)


def _looks_like_person(cand):
    """Reject work titles and format noise masquerading as a name."""
    tokens = [t for t in re.split(r"[\s\.]+", cand.strip()) if t]
    if not tokens or len(cand) < 5:
        return False
    if _flat(tokens[-1]) in _PARTICLES:      # 'Jaqueline du' -- truncated
        return False
    for t in tokens:
        if _flat(t.strip("'’-")) in _NOT_A_NAME:
            return False
        # every token of a person's name is capitalised; 'Das klagende Lied'
        # gives itself away on the lowercase word
        if t[:1].islower() and _flat(t) not in _PARTICLES:
            return False
    return True


def resolve_prefix(candidate, vocab=None):
    """Repair a truncated folder name against the vocabulary.

    Long paths get cut off mid-word by rippers and filesystems, leaving
    'SFS_Blomste' or 'CSO_Barenboi'. If exactly one known surname starts with
    the fragment, that is almost certainly who was meant.
    """
    vocab = vocab or VOCAB
    cand = candidate or ""
    # 'H. von Karajan' -> 'Karajan'; the particle is not part of the key
    parts = [p for p in re.split(r"\s+", cand.strip()) if p]
    while parts and (_flat(parts[0]) in _PARTICLES or len(parts[0].strip(".")) <= 1):
        parts.pop(0)
    frag = _flat(re.sub(r"[^\w'\-]", "", " ".join(parts).split(" ")[-1]
                        if parts else ""))
    if len(frag) < 5:
        return None, None
    if frag in vocab.conductors:
        return vocab.conductors[frag]["name"], "high"
    matches = [k for k in vocab.conductors if k.startswith(frag)]
    if len(matches) == 1:
        entry = vocab.conductors[matches[0]]
        if entry.get("guarded"):
            return None, None
        return entry["name"], "prefix"
    return None, None


def extract_credits(path, album, composers=(), tag_ensembles=(),
                    is_classical=True, vocab=None, allow_structural=True):
    """Recover (conductor, confidence, ensembles) for one release.

    `path` should be the full relative path so box-set parents are seen.
    Skipped entirely for non-classical releases, so 'Miles Davis Quintet'
    cannot match a Davis on the conductor list.
    """
    vocab = vocab or VOCAB
    # Semicolons keep the fields apart: a name ending one path component must
    # not be read as adjacent to whatever begins the next one.
    parts = [p for p in path.split("/") if p]
    if album:
        parts.append(album)
    text = " ; ".join(parts)
    ensembles = find_ensembles(text, vocab)
    if not is_classical:
        return None, None, ensembles

    has_ensemble = bool(ensembles) or bool(tag_ensembles) or \
        bool(GENERIC_ENSEMBLE.search(normalize(text)))

    name, conf, key = find_conductor(text, composers, vocab)
    if name:
        if key in vocab.needs_ensemble and not has_ensemble:
            return None, None, ensembles
        if not has_ensemble and conf != "ambiguous":
            # With no orchestra named anywhere, assert only a well-established
            # conductor, or one whose *full* name is written out. A bare
            # surname here is usually the soloist ('Stern & Perlman',
            # 'Amoyal - Violin Concerto'); 'Geoffrey Simon - Respighi
            # Orchestral Works' names the person outright.
            entry = vocab.conductors.get(key) or {}
            if not entry.get("trusted") and not _forename_present(
                    entry, _flat(normalize(text))):
                return None, None, ensembles
            conf = "medium"
        return name, conf, ensembles

    if allow_structural:
        cand, rule = find_conductor_structural(path, composers)
        strong = rule in ("underscore", "ensemble_comma", "comma_ensemble")
        if cand and (has_ensemble or strong):
            # first try to repair a truncated fragment against the vocabulary
            fixed, fconf = resolve_prefix(cand, vocab)
            if fixed:
                return fixed, fconf, ensembles
            # otherwise accept only a plausible, unambiguous surname
            if (strong and len(cand) >= 5
                    and not cand.isupper()
                    and _looks_like_person(cand)
                    and re.fullmatch(r"[A-Za-zÀ-ÿ'’\-]+(?:\s+[A-Za-zÀ-ÿ'’\-]+)?",
                                     cand)):
                return cand, "structural", ensembles

    return None, None, ensembles
