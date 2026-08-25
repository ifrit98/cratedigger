# Tests

```bash
python tests/run_tests.py            # everything
python tests/run_tests.py dates      # one suite
```

Stdlib only -- no pytest, no runner to install. The toolkit's zero-install
property applies to its tests.

| suite | covers |
|---|---|
| `test_dates` | date parsing, the lifetime clamp, compilation detection |
| `test_sessions` | discography lookup, personnel precedence, tune normalisation |
| `test_credits` | conductor and ensemble recovery, and its precision guards |
| `test_scan` | incremental scan, on a real library built with ffmpeg |

Most cases encode a bug that actually happened, which is why several read
oddly. `26-2` is a Coltrane composition that a track-number stripper reduced
to `2`; the two-letter key `om` matched inside `C-om-plete Copenhagen` and
dated that concert to a Seattle session. The negatives matter more than the
positives -- a wrong answer is worse than a missing one.

## artist_browser_baseline.txt

A hash of the artist browser payload content -- `DATA.rows`, `DATA.tables`
and `DATA.proposals`. The browser core is shared between the artist and
library models, so refactoring it risks silently changing what the artist
archive shows. Regenerate deliberately, never to make a failure go away:

```bash
python - <<'EOF'
import re, json, hashlib
h = open("output-coltrane/coltrane-browser.html", encoding="utf-8").read()
d = json.loads(re.search(r"const DATA = (\{.*?\});
", h, re.S).group(1))
c = {k: d[k] for k in ("cols", "tables", "rows", "proposals", "wild_sessions")
     if k in d}
print(hashlib.sha1(json.dumps(c, sort_keys=True,
                              separators=(",", ":")).encode()).hexdigest()[:16])
EOF
```

It legitimately changes when the manifest changes -- new music, a vocabulary
edit, a parser fix. It must **not** change when only the browser code moves.
