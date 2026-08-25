"""Regression suite for credits.py. Run after any vocabulary refetch.

    python test_credits.py

Every case is a real folder name from the library. The negative cases matter
more than the positive ones: a wrong conductor is worse than a missing one.
"""
import sys

import credits

# (path, is_classical, expected_surname_or_None)
CASES = [
    # --- the underscore convention: ENSEMBLE_Conductor
    ("Orchestra PCM/Bruckner 5 CSO_Barenboim PCM", True, "Barenboim"),
    ("Orchestra PCM/Mozart Adagio and Fugue C minor K 546 BPO_HvK PCM",
     True, "Karajan"),                                  # HvK alias
    ("Orchestra PCM/Bruckner 8 VPO_Furt PCM", True, "Furtwängler"),
    ("Orchestra PCM/Hindemith Trauermusik SFS_Blomstedt PCM", True,
     "Blomstedt"),
    ("Orchestra PCM/Bruckner 7 Bavarian State_Nagano PCM", True, "Nagano"),
    ("Orchestra PCM/Franck Symphony RSOB_Maazel PCM", True, "Maazel"),
    ("Orchestra PCM/Beethoven 7 Munich_Celibidache PCM", True, "Celibidache"),
    ("Orchestra PCM/Beethoven 7 SB_Barenboim PCM", True, "Barenboim"),

    # --- 'Conductor, Ensemble' and 'Ensemble, Conductor'
    ("Classical/Bruckner 7/01. C.Schuricht, Berlin Philharmonic. 1938",
     True, "Schuricht"),
    ("Classical/Bruckner 7/18. C. von Dohnanyi, Cleveland Orchestra. 1990",
     True, "Dohnányi"),
    ("Classical/Bruckner 7/22. G.Tintner, Royal Scottish National Orchestra. 1997",
     True, "Tintner"),
    ("Conductors/Philharmonia Orchestra, Klemperer", True, "Klemperer"),
    ("Conductors/Philharmoniker Hamburg, Simone Young", True, "Young"),
    ("Conductors/Wiener Philharmoniker, Wilhelm Furtwängler", True,
     "Furtwängler"),

    # --- parenthetical credits
    ("Classical/Bach Concertos [Box] (The English Concert, Trevor Pinnock) [FLAC]",
     True, "Pinnock"),
    ("Classical/Bruckner - Symphony No.9 (SWF SO Baden-Baden - Gielen) - 1997",
     True, "Gielen"),
    ("Classical/Bach - Brandenburg Concertos - Otto Klemperer - Philharmonia - EMI",
     True, "Klemperer"),

    # --- guarded names: a composer surname alone is NEVER the conductor
    ("Classical/Bach - Brandenburg Concertos - Philharmonia", True, None),
    ("Classical/Mahler - Symphony No 5 - Wiener Philharmoniker", True, None),
    ("Classical/Wagner - Tristan und Isolde - Berlin Philharmonic", True, None),
    ("Classical/Strauss - Four Last Songs - Philharmonia Orchestra",
     True, None),
    ("Classical/Schubert - Symphony No 9 - Berliner Philharmoniker",
     True, None),

    # --- performer-conductors need an ensemble before the role is asserted
    ("Classical/Bach The Well-Tempered Clavier (Barenboim) [FLAC]", True, None),
    ("Classical/Barenboim - On My New Piano", True, None),
    ("Classical/Daniel Barenboim, LV Beethoven - Complete piano sonatas",
     True, None),
    ("Classical/Beethoven Piano Sonata 32 Richter Live 1963", True, None),

    # --- chamber / solo works have no conductor
    ("Classical/Beethoven - Complete Violin Sonatas - Oistrakh, Oborin",
     True, None),
    ("Classical/Bartok - Violin Sonatas - Faust, Kupiec", True, None),
    ("Classical/Bach - The Art of Fugue - Emerson", True, None),

    # --- non-classical must never reach the conductor vocabulary
    ("Jazz/Miles Davis Quintet - Workin'", False, None),
    ("Jazz/Bill Evans Trio - Waltz For Debby", False, None),
    ("Jazz/Wayne Shorter - The Soothsayer", False, None),
    ("Rock/Allan Holdsworth - Metal Fatigue", False, None),
]


def main():
    credits.reload_vocab()
    n_cond, n_ens = credits.VOCAB.size
    print(f"vocabulary: {n_cond} conductors, {n_ens} ensembles\n")

    failed = []
    for path, classical, want in CASES:
        got, conf, _ens = credits.extract_credits(
            path, None, (), is_classical=classical)
        if want is None:
            ok = got is None
        else:
            ok = bool(got) and want.split()[-1].lower() in got.lower()
        if not ok:
            failed.append((path, want, got, conf))
        print(f"{'PASS' if ok else 'FAIL'}  {path[-56:]:58s} -> "
              f"{str(got)[:26]:28s} [{conf}]")

    print(f"\n{len(CASES) - len(failed)}/{len(CASES)} passed")
    if failed:
        print("\nfailures:")
        for path, want, got, conf in failed:
            print(f"  {path}\n    expected {want!r}, got {got!r} [{conf}]")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
