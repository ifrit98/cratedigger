"""Discography lookup, personnel resolution, and tune normalisation.

Most of these encode a bug that actually happened. Naive substring matching
dated a Copenhagen concert to a Seattle session because the two-letter key
'om' occurs inside 'C-om-plete'; an empty profile list let one artist inherit
another's band. Neither was visible without a case pinning it down.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir))
import coltrane  # noqa: E402

# (folder path, expected album title from the discography, or None)
LOOKUP = [
    # the album title beats a personnel name later in the same folder
    ("16/1957 - The Cats (Tommy Flanagan, John Coltrane, Kenny Burrell, "
     "Idrees Sulieman)", "The Cats"),
    # whole-token matching: 'om' must not match inside 'Complete'
    ("16/1961 - Complete Copenhagen Concert", None),
    ("16/1962 - Complete live at the Sutherland Lounge", None),
    ("16/1965 - Om", "Om"),
    # longest key wins when both genuinely match
    ("24/1966. John Coltrane - Live At The Village Vanguard Again (2016)",
     "Live at the Village Vanguard Again!"),
    # separators normalised: underscores must not defeat the key
    ("16/John_Coltrane-A_Love_Supreme_The_Complete_Masters", "A Love Supreme"),
    ("16/1957 - Blue Train [RVG 2003]", "Blue Train"),
    ("mp3/1961,  November 18, Paris", None),
]

# (iso date, expected lineup name or None)
LINEUP = [
    ("1956-11-30", "Miles Davis Quintet"),
    ("1960-10-21", "Quartet with Steve Davis & Elvin Jones"),
    ("1961-11-02", "Group with Eric Dolphy & Reggie Workman"),
    ("1964-12-09", "Classic Quartet"),
    ("1966-05-28", "Final group"),
    ("1961", "Group with Eric Dolphy & Reggie Workman"),  # year -> mid-year
    (None, None),
]

# (text, expected musicians found -- Coltrane himself is always excluded)
MUSICIANS = [
    ("16/1957 - The Cats (Tommy Flanagan, John Coltrane, Kenny Burrell)",
     ["Tommy Flanagan", "Kenny Burrell"]),
    ("24/1962. Duke Ellington & John Coltrane", ["Duke Ellington"]),
    ("DSD/John Coltrane With The Red Garland Trio", ["Red Garland"]),
    ("mp3/1961,  November 18, Paris", []),
]

# (raw title, expected normalised tune, expected take)
TUNES = [
    ("03 - My Favorite Things", "My Favorite Things", None),
    # display keeps the record's spelling; only the match key normalises
    ("My Favourite Things", "My Favourite Things", None),
    ("07 Naima (Take 2)", "Naima", "2"),
    ("Giant Steps (Alternate Take)", "Giant Steps", "alt"),
    ("12. Impressions [Live]", "Impressions", None),
    ("CD2 - 05 - Blue Train", "Blue Train", None),
    # '26-2' is a real composition. Stripping on a separator alone reduced it
    # to '2'; the stripper now requires a letter after the separator.
    ("26-2", "26-2", None),
    ("Blues to Bechet", "Blues to Bechet", None),
    ("Part 4 - Psalm", "Part 4 - Psalm", None),
    # disc-track prefix; the trailing space is what separates it from '26-2'
    ("1-06 My Favorite Things", "My Favorite Things", None),
    ("2-03 My Favorite Things 2", "My Favorite Things 2", None),
    # takes written without brackets
    ("Naima take 3", "Naima", "3"),
    # ...but 'Mistake 2' is not take 2
    ("Mistake 2", "Mistake 2", None),
]

CASE_COUNT = len(LOOKUP) + len(LINEUP) + len(MUSICIANS) + len(TUNES) + 2


def main():
    fails = []

    for path, want in LOOKUP:
        e = coltrane.lookup_session(path)
        got = e["title"] if e else None
        ok = got == want
        if not ok:
            fails.append(("lookup", path, want, got))
        print("%s  lookup    %-46s -> %s"
              % ("PASS" if ok else "FAIL", path[-46:], got))

    for iso, want in LINEUP:
        lu = coltrane.lineup_for(iso)
        got = lu["name"] if lu else None
        ok = got == want
        if not ok:
            fails.append(("lineup", iso, want, got))
        print("%s  lineup    %-46s -> %s"
              % ("PASS" if ok else "FAIL", str(iso), got))

    for text, want in MUSICIANS:
        got = coltrane.extract_musicians(text)
        ok = got == want
        if not ok:
            fails.append(("musicians", text, want, got))
        print("%s  musician  %-46s -> %s"
              % ("PASS" if ok else "FAIL", text[-46:], got))

    for raw, tune, take in TUNES:
        got_tune, _key = coltrane.normalize_tune(raw)
        got_take = coltrane.extract_take(raw)
        ok = got_tune == tune and got_take == take
        if not ok:
            fails.append(("tune", raw, (tune, take), (got_tune, got_take)))
        print("%s  tune      %-46s -> %s"
              % ("PASS" if ok else "FAIL", raw[:46], (got_tune, got_take)))

    # --- named personnel win outright over the date's band.
    # Merging the two gave 'The Cats' Monk's rhythm section, purely because
    # it falls inside the Five Spot residency window.
    people, _lu, _id, src = coltrane.personnel_for(
        "16/1957 - The Cats (Tommy Flanagan, Kenny Burrell)", None, None,
        "1957-04-18")
    ok = src == "named" and "Thelonious Monk" not in people
    if not ok:
        fails.append(("precedence", "The Cats", "named only", (src, people)))
    print("%s  precedence named personnel beat the date's band -> %s"
          % ("PASS" if ok else "FAIL", src))

    # --- an empty profile list must not fall back to another artist's data
    empty = coltrane._load_profile("__does_not_exist__")
    ok = empty == {}
    if not ok:
        fails.append(("profile", "missing", {}, empty))
    print("%s  profile   a missing profile yields {}, not a fallback"
          % ("PASS" if ok else "FAIL"))

    print("\n%d/%d passed" % (CASE_COUNT - len(fails), CASE_COUNT))
    for kind, text, want, got in fails:
        print("  %s %r: expected %r, got %r" % (kind, text, want, got))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
