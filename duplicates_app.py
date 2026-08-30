"""A page for resolving duplicate clusters.

    python duplicates_app.py --manifest output/library.json \\
                             --out output/duplicates.html \\
                             --root "E:\\Music"

The general pipeline has detected clusters and reclaimable bytes since the
beginning and offered no way to act on them, which made the number decorative.
This shows each cluster side by side -- path, quality, size -- with one copy
preselected to keep.

**It never deletes anything.** The output is a script you read and run
yourself. That is not timidity: the failure mode of an automatic deleter is
unrecoverable, and the reclaimable bytes are not worth it.

Preselection favours quality tier first and size second, because a Redbook
rip and a lossy copy of the same recording are not equivalent, and between
two rips of the same tier the larger is likelier to be the intact one.
"""
import argparse
import json
import os
import sys

from browser_core import TEMPLATE_HEAD

# Best first. Anything unrecognised sorts last, which keeps an unknown tier
# from being preselected over a known-good one.
QUALITY_RANK = ["DSD", "Hi-Res", "Studio", "Redbook", "Unknown", "Lossy"]


def rank(quality, size):
    try:
        q = QUALITY_RANK.index(quality)
    except ValueError:
        q = len(QUALITY_RANK)
    return (q, -(size or 0))


def compact(manifest, root):
    clusters = []
    for c in manifest.get("duplicate_candidates", []):
        paths = c.get("paths") or []
        quality = c.get("quality") or []
        sizes = c.get("sizes") or []
        copies = []
        for i, p in enumerate(paths):
            copies.append({
                "path": p,
                "quality": quality[i] if i < len(quality) else "Unknown",
                "size": sizes[i] if i < len(sizes) else 0,
            })
        if len(copies) < 2:
            continue
        order = sorted(range(len(copies)),
                       key=lambda i: rank(copies[i]["quality"],
                                          copies[i]["size"]))
        conf = c.get("confidence") or ""
        # A `same_title_review` cluster means "these share a title, look at
        # them" -- NOT "these are copies of each other". The first one found
        # in this library was the fourteen discs of a Celibidache box set,
        # which a preselected keep would have offered to reduce to one and
        # called 4.1 GB reclaimed. Low confidence therefore preselects
        # nothing and contributes nothing to the script until a human picks.
        safe = conf == "high" and c.get("kind") == "identical_content"
        clusters.append({
            "key": c.get("key") or "",
            "kind": c.get("kind") or "",
            "confidence": conf,
            "safe": safe,
            "reclaimable": c.get("reclaimable_bytes") or 0,
            "copies": copies,
            "keep": order[0] if safe else -1,
        })
    clusters.sort(key=lambda c: -c["reclaimable"])
    return {"root": os.path.abspath(root).replace("\\", "/"),
            "clusters": clusters}


BODY = r"""
<div class="wrap">
  <header>
    <h1>Duplicate clusters</h1>
    <p class="sub" id="sub"></p>
  </header>

  <div class="bar">
    <label><input type="checkbox" id="onlyHigh" checked> only resolvable clusters</label>
    <span class="spacer"></span>
    <label>script:
      <select id="flavour">
        <option value="ps">PowerShell</option>
        <option value="sh">bash</option>
      </select>
    </label>
    <button id="gen">Build removal script</button>
  </div>

  <div id="list"></div>

  <div id="scriptPane" class="pane" hidden>
    <div class="paneHead">
      <strong>Review this before running it.</strong>
      <button id="copy">Copy</button>
      <button id="close">Close</button>
    </div>
    <pre id="script"></pre>
  </div>
</div>

<style>
.wrap{max-width:1100px;margin:0 auto;padding:24px 20px 80px}
header h1{margin:0 0 4px;font-size:22px}
.sub{color:var(--muted);margin:0 0 18px}
.bar{display:flex;gap:14px;align-items:center;position:sticky;top:0;
     background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);
     z-index:5;flex-wrap:wrap}
.bar .spacer{flex:1}
button,select{font:inherit;background:var(--panel);color:var(--ink);
     border:1px solid var(--line);border-radius:6px;padding:5px 10px;
     cursor:pointer}
button:hover{border-color:var(--accent)}
.cluster{border:1px solid var(--line);border-radius:8px;margin:14px 0;
     background:var(--panel);overflow:hidden}
.ch{display:flex;gap:10px;align-items:baseline;padding:10px 14px;
     border-bottom:1px solid var(--line);flex-wrap:wrap}
.ch .k{font-weight:600}
.tag{font-size:11px;text-transform:uppercase;letter-spacing:.04em;
     border:1px solid var(--line);border-radius:99px;padding:1px 8px;
     color:var(--muted)}
.tag.high{color:var(--accent);border-color:var(--accent)}
.gain{margin-left:auto;color:var(--muted);font-variant-numeric:tabular-nums}
.copy{display:grid;grid-template-columns:auto 1fr auto auto auto;gap:12px;
     align-items:center;padding:8px 14px;border-top:1px solid var(--line)}
.copy:first-of-type{border-top:none}
.copy.keep{background:var(--accent-soft)}
.copy .p{font-family:var(--mono);font-size:12.5px;word-break:break-all}
.copy .q,.copy .s{color:var(--muted);font-size:12.5px;white-space:nowrap;
     font-variant-numeric:tabular-nums}
.copy .verdict{font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.keep .verdict{color:var(--accent)}
.drop .verdict{color:var(--muted)}
.warn{padding:8px 14px;border-top:1px solid var(--line);color:var(--muted);
     font-size:12.5px;line-height:1.5}
.warn b{color:var(--ink)}
.pane{position:fixed;inset:auto 0 0 0;max-height:60vh;background:var(--panel);
     border-top:1px solid var(--accent);display:flex;flex-direction:column;
     z-index:10}
/* display:flex above outranks the UA [hidden] rule, so say it explicitly */
.pane[hidden]{display:none}
.paneHead{display:flex;gap:10px;align-items:center;padding:10px 16px;
     border-bottom:1px solid var(--line)}
.paneHead strong{flex:1;font-weight:600}
#script{margin:0;padding:14px 16px;overflow:auto;font-family:var(--mono);
     font-size:12.5px;line-height:1.5;white-space:pre}
</style>

<script>
const DATA = __PAYLOAD__;
const C = DATA.clusters;
document.title = 'Duplicate clusters — cratedigger';

function bytes(n){
  if(n >= 1e9) return (n/1e9).toFixed(1)+' GB';
  if(n >= 1e6) return (n/1e6).toFixed(0)+' MB';
  return (n/1e3).toFixed(0)+' KB';
}
function esc(s){return String(s).replace(/[&<>"]/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

function visible(){
  return document.getElementById('onlyHigh').checked
    ? C.filter(c=>c.safe) : C;
}

function render(){
  const list = document.getElementById('list');
  const vis = visible();
  list.innerHTML = vis.map((c)=>{
    const i = C.indexOf(c);
    const rows = c.copies.map((cp,j)=>{
      const keep = c.keep===j;
      const none = c.keep < 0;
      return `<label class="copy ${keep?'keep':(none?'':'drop')}">
        <input type="radio" name="c${i}" value="${j}" ${keep?'checked':''}
               onchange="pick(${i},${j})">
        <span class="p">${esc(cp.path)}</span>
        <span class="q">${esc(cp.quality)}</span>
        <span class="s">${bytes(cp.size)}</span>
        <span class="verdict">${none?'':(keep?'keep':'remove')}</span>
      </label>`;
    }).join('');
    const warn = c.safe ? '' : `<div class="warn">
      <b>Nothing preselected.</b> These were grouped because they share a
      title, which is not evidence that they are copies &mdash; they are as
      likely to be separate discs or movements of one release. Choose a copy
      to keep only if you have checked that the others really are redundant.
      Until then this cluster contributes nothing to the script.</div>`;
    return `<div class="cluster">
      <div class="ch">
        <span class="k">${esc(c.key)}</span>
        <span class="tag ${c.safe?'high':''}">${esc(c.confidence)}</span>
        <span class="tag">${esc(c.kind.replace(/_/g,' '))}</span>
        <span class="gain">${c.safe ? bytes(c.reclaimable)+' reclaimable'
                                    : 'unverified'}</span>
      </div>${warn}${rows}</div>`;
  }).join('');

  const safe = C.filter(c=>c.safe);
  const total = safe.reduce((a,c)=>a+c.reclaimable,0);
  const unsafe = C.length - safe.length;
  document.getElementById('sub').textContent =
    `${vis.length} shown · ${bytes(total)} reclaimable across `
    + `${safe.length} verified clusters`
    + (unsafe ? ` · ${unsafe} need checking first` : '')
    + ` · nothing is deleted by this page`;
}

function pick(i,j){ C[i].keep = j; render(); }

function script(){
  const ps = document.getElementById('flavour').value === 'ps';
  const root = DATA.root;
  // Cluster paths are release folders, not single files -- the ones in this
  // library hold ~19 tracks each. A plain delete either prompts or fails on
  // those, so the commands are recursive.
  //
  // Both flavours default to a DRY RUN. Running this script unchanged prints
  // what it would remove and removes nothing; one edit at the top arms it.
  const head = ps
    ? ['# Generated by cratedigger. READ THIS BEFORE RUNNING IT.',
       '# Each block keeps one copy of a release folder and removes the rest.',
       '#',
       '# This is a DRY RUN as written. Change the line below to $false',
       '# to actually delete.',
       '$WhatIfPreference = $true',
       '$ErrorActionPreference = "Stop"',
       '']
    : ['#!/bin/sh',
       '# Generated by cratedigger. READ THIS BEFORE RUNNING IT.',
       '# Each block keeps one copy of a release folder and removes the rest.',
       '#',
       '# This is a DRY RUN as written. Set DRYRUN=0 to actually delete.',
       'DRYRUN=1',
       'run() { if [ "$DRYRUN" = "1" ]; then echo "would remove: $1";'
         + ' else rm -rf -- "$1"; fi; }',
       ''];
  const out = head.slice();
  let freed = 0, n = 0;
  visible().forEach(c=>{
    if(c.keep < 0) return;          // unresolved: contributes nothing
    out.push(`# keep: ${c.copies[c.keep].path}`);
    c.copies.forEach((cp,j)=>{
      if(j===c.keep) return;
      const full = root + '/' + cp.path;
      freed += cp.size; n++;
      out.push(ps
        ? `Remove-Item -LiteralPath ${JSON.stringify(full)} -Recurse -Force`
        : `run ${JSON.stringify(full)}`);
    });
    out.push('');
  });
  out.push(`# ${n} folders, ${bytes(freed)}`);
  return out.join('\n');
}

document.getElementById('gen').onclick = ()=>{
  document.getElementById('script').textContent = script();
  document.getElementById('scriptPane').hidden = false;
};
document.getElementById('close').onclick = ()=>{
  document.getElementById('scriptPane').hidden = true;
};
document.getElementById('copy').onclick = ()=>{
  navigator.clipboard.writeText(document.getElementById('script').textContent);
};
document.getElementById('onlyHigh').onchange = render;
render();
</script>
"""


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default="output/library.json")
    ap.add_argument("--out", default="output/duplicates.html")
    ap.add_argument("--root", required=True,
                    help="library root the manifest paths are relative to")
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)

    data = compact(manifest, args.root)
    if not data["clusters"]:
        print("no duplicate clusters in %s -- nothing to resolve"
              % args.manifest)
        return 0

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    body = BODY.replace("__PAYLOAD__", payload)
    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(TEMPLATE_HEAD + body)

    safe = [c for c in data["clusters"] if c["safe"]]
    total = sum(c["reclaimable"] for c in safe)
    print("wrote %s  (%.0f KB)" % (args.out, os.path.getsize(args.out) / 1024))
    print("  %d clusters, %d verified, %.1f GB reclaimable"
          % (len(data["clusters"]), len(safe), total / 1e9))
    unsafe = len(data["clusters"]) - len(safe)
    if unsafe:
        print("  %d grouped by title only -- shown, but nothing preselected"
              % unsafe)
    print("  open it from disk; it generates a script and deletes nothing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
