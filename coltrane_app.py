"""Generate a self-contained interactive browser for the Coltrane archive.

    python coltrane_app.py --manifest output-coltrane/coltrane.json \\
                           --out output-coltrane/coltrane-browser.html \\
                           --root "D:\\Coltrane"

Writes ONE html file with the whole ontology embedded. Open it from disk and
it works offline, with no server. Because it is a local file it can point an
<audio> element at the archive, so tracks play in place.

The data is compacted before embedding -- repeated strings (era, lineup,
venue, personnel) become indexes into lookup tables, which takes the payload
from ~4.5 MB of JSON to roughly a third of that.
"""
import argparse
import json
import os
import sys

TEMPLATE_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>John Coltrane Archive</title>
<style>
:root{
  --bg:#faf8f5; --panel:#fff; --ink:#1a1714; --muted:#6b625a; --line:#e3ddd4;
  --accent:#9c4221; --accent-soft:#f4e6de; --live:#7b5ea7; --boot:#a8763e;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme=light]){
    --bg:#16130f; --panel:#1f1b16; --ink:#f0e9e0; --muted:#a2968a;
    --line:#332c24; --accent:#e08b5f; --accent-soft:#2e2119;
    --live:#b39ddb; --boot:#d4a45f;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:18px 22px 12px;border-bottom:1px solid var(--line);
  display:flex;gap:18px;align-items:baseline;flex-wrap:wrap}
h1{font-size:19px;margin:0;letter-spacing:-.01em}
h1 span{color:var(--muted);font-weight:400}
.counts{color:var(--muted);font-size:13px;font-family:var(--mono)}
main{display:grid;grid-template-columns:270px 1fr;gap:0;
  height:calc(100vh - 62px)}
@media(max-width:860px){main{grid-template-columns:1fr;height:auto}}
aside{border-right:1px solid var(--line);overflow-y:auto;padding:14px 16px 60px}
section.main{overflow-y:auto;padding:14px 20px 80px}
.fgroup{margin-bottom:16px}
.fgroup h3{font-size:11px;text-transform:uppercase;letter-spacing:.08em;
  color:var(--muted);margin:0 0 6px}
.opt{display:flex;align-items:center;gap:7px;padding:2px 0;cursor:pointer;
  font-size:13px}
.opt input{accent-color:var(--accent);margin:0}
.opt .n{margin-left:auto;color:var(--muted);font-family:var(--mono);
  font-size:11px}
.opt.off{opacity:.4}
input[type=search],select,input[type=range]{width:100%;padding:7px 9px;
  border:1px solid var(--line);border-radius:6px;background:var(--panel);
  color:var(--ink);font:inherit;font-size:13px}
.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;
  margin-bottom:12px}
.toolbar .grow{flex:1;min-width:180px}
button{font:inherit;font-size:13px;padding:7px 12px;border-radius:6px;
  border:1px solid var(--line);background:var(--panel);color:var(--ink);
  cursor:pointer}
button:hover{border-color:var(--accent);color:var(--accent)}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
button.primary:hover{opacity:.9;color:#fff}
.pill{display:inline-block;padding:1px 7px;border-radius:99px;font-size:11px;
  font-family:var(--mono);background:var(--accent-soft);color:var(--accent)}
.pill.live{background:transparent;color:var(--live);
  border:1px solid currentColor}
.pill.boot{background:transparent;color:var(--boot);
  border:1px solid currentColor}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{position:sticky;top:0;background:var(--bg);text-align:left;
  font-size:11px;text-transform:uppercase;letter-spacing:.06em;
  color:var(--muted);padding:6px 8px;border-bottom:1px solid var(--line);
  cursor:pointer;white-space:nowrap}
td{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
tr:hover td{background:var(--accent-soft)}
td.date{font-family:var(--mono);white-space:nowrap;color:var(--muted)}
td.dur{font-family:var(--mono);text-align:right;color:var(--muted)}
.play{border:none;background:none;color:var(--accent);cursor:pointer;
  padding:0 6px 0 0;font-size:14px}
.sess{margin:0 0 4px;padding:10px 12px;border:1px solid var(--line);
  border-radius:8px;background:var(--panel)}
.sess h4{margin:0 0 2px;font-size:14px}
.sess .meta{color:var(--muted);font-size:12px;font-family:var(--mono)}
.sess .tunes{font-size:12.5px;color:var(--muted);margin-top:4px}
.year-head{position:sticky;top:0;background:var(--bg);z-index:2;
  padding:12px 0 4px;font-family:var(--mono);font-size:16px;
  border-bottom:2px solid var(--accent);margin-bottom:8px;color:var(--accent)}
footer{position:fixed;bottom:0;left:0;right:0;background:var(--panel);
  border-top:1px solid var(--line);padding:8px 16px;display:flex;gap:12px;
  align-items:center;font-size:13px}
footer audio{height:32px;flex:1;min-width:120px}
.hint{color:var(--muted);font-size:12px;margin:8px 0 0}
.empty{color:var(--muted);padding:30px;text-align:center}
.rec td{vertical-align:middle}
.rec select{width:auto;max-width:330px;font-size:12.5px;padding:4px 6px}
.conf{font-family:var(--mono);font-size:11px;padding:1px 6px;border-radius:99px;
  border:1px solid currentColor;white-space:nowrap}
.conf.unique{color:#2f7d4f} .conf.corroborated{color:#2f6d8f}
.conf.ambiguous{color:var(--boot)}
.decided{background:var(--accent-soft)}
.chg{color:var(--accent);font-weight:600}
.act{display:flex;gap:4px}
.act button{padding:3px 8px;font-size:12px}
.prog{font-family:var(--mono);font-size:12px;color:var(--muted)}
.sessmeta{font-size:11.5px;color:var(--muted);line-height:1.35}
</style>
</head>
<body>
"""


def compact(manifest):
    """Index repeated strings so the payload stays small."""
    tables = {}
    order = {}

    def idx(table, value):
        if value is None or value == "":
            return -1
        t = tables.setdefault(table, [])
        o = order.setdefault(table, {})
        if value not in o:
            o[value] = len(t)
            t.append(value)
        return o[value]

    rel = {r["release_id"]: r for r in manifest["releases"]}
    rows = []
    for t in manifest["tracks"]:
        r = rel.get(t["release_id"], {})
        rows.append([
            t.get("recording_date") or "",
            idx("era", t.get("era")),
            idx("lineup", t.get("lineup")),
            idx("prov", t.get("provenance")),
            idx("auth", t.get("authority")),
            idx("role", t.get("role")),
            idx("venue", t.get("venue") or t.get("city")),
            idx("fmt", t.get("format_tier")),
            idx("album", t.get("album")),
            t.get("tune") or t.get("title") or "",
            t.get("path") or "",
            int(t.get("duration_seconds") or 0),
            [idx("person", p) for p in (t.get("personnel") or [])],
            idx("dsrc", t.get("date_source")),
            1 if r.get("is_compilation") else 0,
        ])
    rows.sort(key=lambda x: (x[0] or "9999", x[8], x[10]))
    return {"cols": ["date", "era", "lineup", "prov", "auth", "role", "venue",
                     "fmt", "album", "tune", "path", "dur", "people", "dsrc",
                     "comp"],
            "tables": tables, "rows": rows,
            "counts": manifest["counts"]}


def attach_proposals(data, proposals_path):
    """Fold Wild's per-track session candidates into the payload.

    Sessions are stored once and referenced by index; a track carries only
    the indexes of its candidates. Without that, 1,675 tracks with up to six
    candidates each would triple the file size.
    """
    if not os.path.exists(proposals_path):
        return 0
    try:
        with open(proposals_path, encoding="utf-8") as fh:
            src = json.load(fh)["tracks"]
    except (OSError, json.JSONDecodeError, KeyError):
        return 0

    sessions, index = [], {}

    def sidx(c):
        key = c["session"]
        if key not in index:
            index[key] = len(sessions)
            sessions.append([c["session"], c["date"], c.get("group") or "",
                             c.get("location") or "",
                             "; ".join(c.get("personnel") or [])])
        return index[key]

    row_of = {r[10]: i for i, r in enumerate(data["rows"])}
    props = {}
    for path, info in src.items():
        i = row_of.get(path)
        if i is None:
            continue
        cands = info.get("candidates") or []
        if not cands:
            continue
        idxs = [sidx(c) for c in cands]
        cur = data["rows"][i][0]
        exact = [j for j, c in enumerate(cands) if c["date"] == cur]
        if len(cands) == 1:
            conf = "unique"
            best = 0
        elif len(exact) == 1:
            conf = "corroborated"
            best = exact[0]
        else:
            conf = "ambiguous"
            best = 0
        props[str(i)] = {"c": idxs, "b": best, "k": conf}
    data["wild_sessions"] = sessions
    data["proposals"] = props
    return len(props)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default="output-coltrane/coltrane.json")
    ap.add_argument("--out", default="output-coltrane/coltrane-browser.html")
    ap.add_argument("--root", required=True,
                    help="archive root the manifest paths are relative to")
    ap.add_argument("--proposals",
                    default="output-coltrane/wild_track_proposals.json",
                    help="Wild per-track session candidates, if present")
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as fh:
        man = json.load(fh)
    data = compact(man)
    data["root"] = os.path.abspath(args.root).replace("\\", "/")
    n_prop = attach_proposals(data, args.proposals)

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    body = APP_HTML.replace("__PAYLOAD__", payload)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(TEMPLATE_HEAD + body)

    kb = os.path.getsize(args.out) / 1024
    print(f"wrote {args.out}  ({kb:,.0f} KB)")
    print(f"  {len(data['rows']):,} tracks embedded")
    if n_prop:
        print(f"  {n_prop:,} tracks carry Wild session candidates "
              f"({len(data['wild_sessions'])} sessions)")
    print(f"  open it directly from disk -- no server needed")


APP_HTML = r"""
<header>
  <h1>John Coltrane <span>archive browser</span></h1>
  <div class="counts" id="counts"></div>
</header>
<main>
<aside id="facets"></aside>
<section class="main">
  <div class="toolbar">
    <div class="grow"><input type="search" id="q"
      placeholder="Search tune, album, venue, path..."></div>
    <select id="mode" style="width:auto">
      <option value="timeline">Timeline</option>
      <option value="tracks">Track list</option>
      <option value="tunes">Tunes</option>
      <option value="reconcile">Reconcile dates</option>
    </select>
    <select id="confFilter" style="width:auto;display:none">
      <option value="">all confidences</option>
      <option value="unique">unique only</option>
      <option value="corroborated">corroborated only</option>
      <option value="ambiguous">ambiguous only</option>
      <option value="changes">would change the date</option>
      <option value="undecided">undecided only</option>
    </select>
    <button id="acceptAll" style="display:none">Accept all unique</button>
    <button id="exportDec" style="display:none">Export decisions</button>
    <button id="clearDate" style="display:none">✕ date</button>
    <button id="reset">Reset</button>
    <button id="export" class="primary">Export .m3u8</button>
  </div>
  <div id="view"></div>
</section>
</main>
<footer>
  <span id="nowplaying" style="color:var(--muted)">nothing playing</span>
  <audio id="player" controls preload="none"></audio>
</footer>
<script>
const DATA = __PAYLOAD__;
const T = DATA.tables, ROWS = DATA.rows, ROOT = DATA.root;
const C = {}; DATA.cols.forEach((n,i)=>C[n]=i);
const name = (tbl,i)=> i<0 ? null : (T[tbl]||[])[i];

const FACETS = [
  ['era','Era'], ['lineup','Lineup'], ['prov','Recording'],
  ['auth','Issue'], ['role','Coltrane\u2019s role'], ['person','Personnel'],
  ['venue','Venue'], ['fmt','Format'], ['dsrc','Date source']
];
const sel = {};  FACETS.forEach(([k])=>sel[k]=new Set());
let query='', mode='timeline', dateFilter=null;

function rowVals(r,key){
  if(key==='person') return r[C.people];
  return [r[C[key]]];
}
function passes(r, skip){
  if(dateFilter && (r[C.date]||'')!==dateFilter) return false;
  for(const [k] of FACETS){
    if(k===skip) continue;
    const s=sel[k]; if(!s.size) continue;
    const vals=rowVals(r,k);
    if(!vals.some(v=>s.has(v))) return false;
  }
  if(query){
    const hay=(r[C.date]+' '+(name('album',r[C.album])||'')+' '+r[C.tune]+' '+
      (name('venue',r[C.venue])||'')+' '+r[C.path]).toLowerCase();
    if(!hay.includes(query)) return false;
  }
  return true;
}
const filtered = ()=> ROWS.filter(r=>passes(r,null));

function counts(key){
  const m=new Map();
  for(const r of ROWS){ if(!passes(r,key)) continue;
    for(const v of rowVals(r,key)){ if(v<0) continue;
      m.set(v,(m.get(v)||0)+1); } }
  return m;
}
function fmtDur(s){ if(!s) return ''; const m=Math.floor(s/60);
  return m+':'+String(Math.round(s%60)).padStart(2,'0'); }

function renderFacets(){
  const el=document.getElementById('facets'); el.innerHTML='';
  for(const [key,label] of FACETS){
    const cm=counts(key);
    const entries=[...cm.entries()].sort((a,b)=>b[1]-a[1]);
    if(!entries.length) continue;
    const g=document.createElement('div'); g.className='fgroup';
    g.innerHTML=`<h3>${label}</h3>`;
    const limit = key==='person'||key==='venue' ? 12 : 40;
    entries.slice(0,limit).forEach(([v,n])=>{
      const id=key+'_'+v;
      const lab=document.createElement('label');
      lab.className='opt'+(n?'':' off');
      lab.innerHTML=`<input type=checkbox ${sel[key].has(v)?'checked':''}>
        <span>${escapeHtml(name(key,v)||'-')}</span><span class=n>${n}</span>`;
      lab.querySelector('input').addEventListener('change',e=>{
        e.target.checked?sel[key].add(v):sel[key].delete(v); render();
      });
      g.appendChild(lab);
    });
    if(entries.length>limit){
      const more=document.createElement('div');
      more.className='hint';
      more.textContent=`+${entries.length-limit} more (use search)`;
      g.appendChild(more);
    }
    el.appendChild(g);
  }
}

function escapeHtml(s){ return String(s).replace(/[&<>"]/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

function pills(r){
  let out='';
  const p=name('prov',r[C.prov]);
  if(p&&p!=='studio') out+=`<span class="pill live">${p}</span> `;
  if(name('auth',r[C.auth])==='unofficial')
    out+='<span class="pill boot">unofficial</span> ';
  return out;
}

function renderTimeline(rows){
  const byDate=new Map();
  for(const r of rows){ const d=r[C.date]||'undated';
    if(!byDate.has(d)) byDate.set(d,[]); byDate.get(d).push(r); }
  const dates=[...byDate.keys()].sort();
  let html='', curYear=null;
  for(const d of dates){
    const y = d==='undated' ? 'undated' : d.slice(0,4);
    if(y!==curYear){ curYear=y; html+=`<div class="year-head">${y}</div>`; }
    const rs=byDate.get(d);
    const venue=name('venue',rs[0][C.venue])||'';
    const lineup=name('lineup',rs[0][C.lineup])||'';
    const tunes=[...new Set(rs.map(r=>r[C.tune]))].slice(0,7).join(' \u00b7 ');
    html+=`<div class="sess" data-date="${d}">
      <h4>${pills(rs[0])}${d}${venue?' \u2014 '+escapeHtml(venue):''}</h4>
      <div class="meta">${rs.length} track${rs.length>1?'s':''}
        ${lineup?' \u00b7 '+escapeHtml(lineup):''}</div>
      <div class="tunes">${escapeHtml(tunes)}</div></div>`;
  }
  return html||'<div class=empty>No tracks match these filters.</div>';
}

function renderTracks(rows){
  const cols=[['date','Date'],['tune','Tune'],['album','Album'],
    ['venue','Venue'],['dur','Len']];
  let html='<table><thead><tr><th></th>';
  cols.forEach(([k,l])=>html+=`<th data-sort="${k}">${l}</th>`);
  html+='</tr></thead><tbody>';
  const show=rows.slice(0,1200);
  show.forEach((r,i)=>{
    html+=`<tr><td><button class="play" data-i="${ROWS.indexOf(r)}"
      title="play">\u25b6</button></td>
      <td class="date">${r[C.date]||'\u2014'}</td>
      <td>${pills(r)}${escapeHtml(r[C.tune])}</td>
      <td>${escapeHtml(name('album',r[C.album])||'')}</td>
      <td>${escapeHtml(name('venue',r[C.venue])||'')}</td>
      <td class="dur">${fmtDur(r[C.dur])}</td></tr>`;
  });
  html+='</tbody></table>';
  if(rows.length>show.length)
    html+=`<p class=hint>Showing ${show.length.toLocaleString()} of
      ${rows.length.toLocaleString()} \u2014 narrow the filters to see more.</p>`;
  return rows.length?html:'<div class=empty>No tracks match these filters.</div>';
}

function renderTunes(rows){
  const m=new Map();
  for(const r of rows){ const k=r[C.tune].toLowerCase();
    if(!m.has(k)) m.set(k,{title:r[C.tune],n:0,first:null,last:null,live:0});
    if(r[C.tune].length>m.get(k).title.length) m.get(k).title=r[C.tune];
    const e=m.get(k); e.n++;
    if(name('prov',r[C.prov])!=='studio') e.live++;
    const d=r[C.date]; if(d){ if(!e.first||d<e.first) e.first=d;
      if(!e.last||d>e.last) e.last=d; } }
  const list=[...m.values()].sort((a,b)=>b.n-a.n).slice(0,400);
  let html='<table><thead><tr><th>Tune</th><th>Versions</th><th>Live</th>'+
    '<th>First</th><th>Last</th></tr></thead><tbody>';
  list.forEach(e=>{ html+=`<tr><td>${escapeHtml(e.title)}</td>
    <td class="dur">${e.n}</td><td class="dur">${e.live}</td>
    <td class="date">${e.first||'\u2014'}</td>
    <td class="date">${e.last||'\u2014'}</td></tr>`; });
  return html+'</tbody></table>';
}


// ---------------------------------------------------------------- reconcile
const PROP = DATA.proposals || {};
const WSESS = DATA.wild_sessions || [];
const DEC_KEY = 'coltrane.decisions.v1';
let decisions = {};
try { decisions = JSON.parse(localStorage.getItem(DEC_KEY) || '{}'); }
catch(e){ decisions = {}; }
function saveDecisions(){
  try { localStorage.setItem(DEC_KEY, JSON.stringify(decisions)); }
  catch(e){ /* private mode: decisions live for this session only */ }
}
let confFilter = '';

function proposedDate(i){
  const p = PROP[i]; if(!p) return null;
  const d = decisions[i];
  if(d && d.reject) return null;
  const si = (d && typeof d.s === 'number') ? d.s : p.c[p.b];
  return WSESS[si] ? WSESS[si][1] : null;
}

function renderReconcile(rows){
  const idxs = rows.map(r => ROWS.indexOf(r)).filter(i => PROP[i]);
  const keep = idxs.filter(i => {
    const p = PROP[i], d = decisions[i];
    if(confFilter === 'undecided') return !d;
    if(confFilter === 'changes'){
      const pd = proposedDate(i);
      return pd && pd !== ROWS[i][C.date];
    }
    if(confFilter) return p.k === confFilter;
    return true;
  });
  if(!keep.length) return '<div class=empty>No tracks with Wild candidates '+
    'match these filters.</div>';

  const total = keep.length;
  let html = `<p class=hint>${total.toLocaleString()} track`+
    `${total===1?'':'s'} match — `+
    `${keep.filter(i=>decisions[i]).length.toLocaleString()} decided</p>`+
    '<table class="rec"><thead><tr><th></th><th>Current</th>'+
    '<th>Wild session</th><th>Confidence</th><th>Tune</th><th>Album</th>'+
    '<th>Decision</th></tr></thead><tbody>';
  keep.slice(0,600).forEach(i => {
    const r = ROWS[i], p = PROP[i], d = decisions[i];
    const cur = r[C.date] || '\u2014';
    const sel = (d && typeof d.s === 'number') ? d.s : p.c[p.b];
    const pd = proposedDate(i);
    const changes = pd && pd !== r[C.date];
    const opts = p.c.map(si => {
      const w = WSESS[si];
      return `<option value="${si}" ${si===sel?'selected':''}>`+
        `${w[1]} \u00b7 ${escapeHtml((w[3]||w[2]||'').slice(0,44))}</option>`;
    }).join('');
    const w = WSESS[sel];
    html += `<tr class="${d?'decided':''}">
      <td><button class="play" data-i="${i}">\u25b6</button></td>
      <td class="date">${cur}</td>
      <td>${p.c.length>1
            ? `<select data-sel="${i}">${opts}</select>`
            : `<span class="date">${w[1]}</span>`}
          <div class="sessmeta">${escapeHtml((w[2]||'').slice(0,40))}
            ${w[4]?' \u00b7 '+escapeHtml(w[4].slice(0,60)):''}</div></td>
      <td><span class="conf ${p.k}">${p.k}</span>
          ${changes?'<div class="chg">changes</div>':''}</td>
      <td>${escapeHtml(r[C.tune])}</td>
      <td>${escapeHtml(name('album',r[C.album])||'')}</td>
      <td><div class="act">
        <button data-acc="${i}" ${d&&!d.reject?'disabled':''}>Accept</button>
        <button data-rej="${i}" ${d&&d.reject?'disabled':''}>Keep</button>
      </div></td></tr>`;
  });
  html += '</tbody></table>';
  if(keep.length>600) html += `<p class=hint>Showing 600 of
    ${keep.length.toLocaleString()} \u2014 narrow the filters.</p>`;
  return html;
}

function wireReconcile(v){
  v.querySelectorAll('select[data-sel]').forEach(sl=>{
    sl.addEventListener('change',e=>{
      const i=e.target.dataset.sel;
      decisions[i]=Object.assign({},decisions[i],{s:+e.target.value});
      delete decisions[i].reject; saveDecisions(); render();
    });
  });
  v.querySelectorAll('button[data-acc]').forEach(b=>{
    b.addEventListener('click',()=>{
      const i=b.dataset.acc, p=PROP[i];
      const cur=(decisions[i]&&typeof decisions[i].s==='number')
        ? decisions[i].s : p.c[p.b];
      decisions[i]={s:cur}; saveDecisions(); render();
    });
  });
  v.querySelectorAll('button[data-rej]').forEach(b=>{
    b.addEventListener('click',()=>{
      decisions[b.dataset.rej]={reject:true}; saveDecisions(); render();
    });
  });
}

function acceptAllUnique(){
  let n=0;
  for(const i in PROP){
    if(PROP[i].k==='ambiguous') continue;
    if(decisions[i]) continue;
    decisions[i]={s:PROP[i].c[PROP[i].b]}; n++;
  }
  saveDecisions(); render();
  alert(`Accepted ${n} unique / corroborated proposals.\n`+
        `Nothing is written to disk until you Export.`);
}

function exportDecisions(){
  const out={_schema:'coltrane-date-decisions/1',
             _generated:new Date().toISOString().slice(0,10),
             _note:'Per-track date decisions made in the browser. '+
                   'accept => use the Wild session date; keep => leave the '+
                   'existing date untouched.',
             decisions:{}};
  for(const i in decisions){
    const d=decisions[i], r=ROWS[i];
    if(!r) continue;
    if(d.reject){ out.decisions[r[C.path]]={action:'keep',
      current:r[C.date]||null}; continue; }
    const w=WSESS[d.s]; if(!w) continue;
    out.decisions[r[C.path]]={action:'accept',current:r[C.date]||null,
      date:w[1],wild_session:w[0],location:w[3]||null,
      personnel:w[4]?w[4].split('; '):[]};
  }
  const blob=new Blob([JSON.stringify(out,null,1)],{type:'application/json'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='coltrane-date-decisions.json';
  document.body.appendChild(a); a.click(); a.remove();
}

function render(){
  const rows=filtered();
  document.getElementById('counts').textContent =
    `${rows.length.toLocaleString()} of ${ROWS.length.toLocaleString()} tracks`+
    ` \u00b7 ${new Set(rows.map(r=>r[C.date]).filter(Boolean)).size} dates`+
    ` \u00b7 ${new Set(rows.map(r=>r[C.album])).size} albums`
    + (dateFilter ? `  \u2014 ${dateFilter} only` : '')
    + (Object.keys(PROP).length
        ? `  \u00b7 ${Object.keys(decisions).length.toLocaleString()}/`
          + `${Object.keys(PROP).length.toLocaleString()} decided` : '');
  renderFacets();
  document.getElementById('clearDate').style.display =
    dateFilter ? 'inline-block' : 'none';
  const v=document.getElementById('view');
  const recMode = mode==='reconcile';
  ['confFilter','acceptAll','exportDec'].forEach(id=>{
    document.getElementById(id).style.display = recMode?'inline-block':'none';
  });
  v.innerHTML = recMode?renderReconcile(rows)
              : mode==='timeline'?renderTimeline(rows)
              : mode==='tunes'?renderTunes(rows) : renderTracks(rows);
  if(recMode) wireReconcile(v);
  v.querySelectorAll('.play').forEach(b=>b.addEventListener('click',()=>{
    play(ROWS[+b.dataset.i]); }));
  v.querySelectorAll('.sess').forEach(s=>s.addEventListener('click',()=>{
    const d=s.dataset.date; query=''; document.getElementById('q').value='';
    mode='tracks'; document.getElementById('mode').value='tracks';
    dateFilter=d; render();
  }));
}
function play(r){
  const p=document.getElementById('player');
  p.src='file:///'+ROOT+'/'+r[C.path];
  document.getElementById('nowplaying').textContent =
    (r[C.date]||'')+'  '+r[C.tune];
  p.play().catch(()=>{
    document.getElementById('nowplaying').textContent =
      'Cannot play from this location \u2014 path copied instead';
    navigator.clipboard&&navigator.clipboard.writeText(
      ROOT+'/'+r[C.path]);
  });
}

function exportM3U(){
  const rows=filtered();
  let out='#EXTM3U\n#PLAYLIST:Coltrane selection\n';
  for(const r of rows){
    out+=`#EXTINF:${r[C.dur]||-1},${r[C.date]||''} - ${r[C.tune]}\n`;
    out+=(ROOT+'/'+r[C.path]).replace(/\//g,'\\')+'\n';
  }
  const blob=new Blob([out],{type:'audio/x-mpegurl'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='coltrane-selection.m3u8';
  document.body.appendChild(a); a.click(); a.remove();
}

document.getElementById('q').addEventListener('input',e=>{
  query=e.target.value.toLowerCase().trim(); dateFilter=null; render(); });
document.getElementById('mode').addEventListener('change',e=>{
  mode=e.target.value; render(); });
document.getElementById('reset').addEventListener('click',()=>{
  FACETS.forEach(([k])=>sel[k].clear()); query=''; dateFilter=null;
  document.getElementById('q').value=''; render(); });
document.getElementById('export').addEventListener('click',exportM3U);
document.getElementById('confFilter').addEventListener('change',e=>{
  confFilter=e.target.value; render(); });
document.getElementById('acceptAll').addEventListener('click',acceptAllUnique);
document.getElementById('exportDec').addEventListener('click',exportDecisions);
document.getElementById('clearDate').addEventListener('click',()=>{
  dateFilter=null; mode='timeline';
  document.getElementById('mode').value='timeline'; render(); });
render();
</script>
</body></html>
"""


if __name__ == "__main__":
    sys.exit(main())
