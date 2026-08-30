"""Date parsing and the lifetime clamp.

Every case is a real folder name from the archive, or a bug that was found in
it. The negatives matter most: a wrong date corrupts the chronology and the
tune index, and it does so silently.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "cratedigger"))
import coltrane  # noqa: E402

# (text, expected_iso_or_None, expected_precision_or_None)
PARSE = [
    # --- the bootleg tier: 'YYYY, Month DD, Venue', with its many spacings
    ("1961,  November 18, Paris", "1961-11-18", "day"),
    ("1958, September 25, Joe Brazil's Basement", "1958-09-25", "day"),
    ("1960, April 4,Dusseldorf, West Germany", "1960-04-04", "day"),
    ("1961,December 2, Berlin", "1961-12-02", "day"),
    ("1965,     March 19, Half Note", "1965-03-19", "day"),
    ("1966, November 11, Temple University", "1966-11-11", "day"),
    ("1967, April 23 (The Olatunji Concert)", "1967-04-23", "day"),

    # This one is why the day patterns test their *second* group. Testing the
    # first sent 'YYYY, Month DD' down the ISO branch, where int("November")
    # threw and the match was silently discarded -- it degraded to month
    # precision across the whole bootleg tier.
    ("1963,  July 7, Newport", "1963-07-07", "day"),

    # --- ISO
    ("1965-07-26 - Antibes, Fr-Juan-Les-Pins Jazz Fest", "1965-07-26", "day"),

    # --- month only
    ("1961, October, Chicago", "1961-10", "month"),

    # --- year only
    ("1957 - Blue Train [RVG 2003]", "1957", "year"),
    ("(1957) John Coltrane - Coltrane [Prestige 24-44.1]", "1957", "year"),
    ("'58 Sessions", "1958", "year"),

    # the earliest year wins: a reissue year appears later in the name than
    # the recording year
    ("1963 - John Coltrane And Johnny Hartman (1995 Remaster 24-96)",
     "1963", "year"),
    ("Beethoven 7 VPO Kleiber", None, None),      # no date at all
    ("", None, None),
    (None, None, None),
]

# (iso, plausible?)  -- Coltrane recorded 1945-01-01 .. 1967-07-17
CLAMP = [
    ("1957-09-15", True),
    ("1945-01-01", True),
    ("1967-07-17", True),
    ("1967", True),            # bare year judged at mid-year
    ("1972", False),           # posthumous compilation issue year
    ("1979", False),
    ("1944", False),
    ("2011", False),
    (None, False),
    ("", False),
]

COMPILATION = [
    ("Ken Burns Jazz", True),
    ("The Art of John Coltrane", True),
    ("John Coltrane - The Gentle Side Of John Coltrane", True),
    ("The Mastery of John Coltrane, Volume 3", True),
    ("The Very Best of John Coltrane", True),
    ("1957 - Blue Train", False),
    ("1964 - A Love Supreme", False),
    ("1961, November 18, Paris", False),
]

CASE_COUNT = len(PARSE) + len(CLAMP) + len(COMPILATION)


def main():
    fails = []

    for text, iso, prec in PARSE:
        got_iso, got_prec = coltrane.parse_recording_date(text)
        ok = got_iso == iso and got_prec == prec
        if not ok:
            fails.append(("parse", text, (iso, prec), (got_iso, got_prec)))
        print("%s  parse   %-52s -> %s"
              % ("PASS" if ok else "FAIL", str(text)[:52],
                 (got_iso, got_prec)))

    for iso, want in CLAMP:
        got = coltrane.is_plausible_recording_date(iso)
        ok = got == want
        if not ok:
            fails.append(("clamp", iso, want, got))
        print("%s  clamp   %-52s -> %s"
              % ("PASS" if ok else "FAIL", str(iso)[:52], got))

    for text, want in COMPILATION:
        got = coltrane.is_compilation(text)
        ok = got == want
        if not ok:
            fails.append(("compilation", text, want, got))
        print("%s  compil  %-52s -> %s"
              % ("PASS" if ok else "FAIL", text[:52], got))

    print("\n%d/%d passed" % (CASE_COUNT - len(fails), CASE_COUNT))
    for kind, text, want, got in fails:
        print("  %s %r: expected %r, got %r" % (kind, text, want, got))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
