"""Deliverable writers: results.json, coverage table, static dashboard."""
import csv
import json
import os

DEFECT_ORDER = ["correct", "semantic_equivalent", "boundary", "off_by_one",
                "type_mismatch", "order", "missing", "extra", "semantic_wrong",
                "partial"]

DEFECT_LABEL = {
    "correct": "canonical",
    "semantic_equivalent": "paraphrase",
    "boundary": "boundary",
    "off_by_one": "off-by-one",
    "type_mismatch": "type",
    "order": "order",
    "missing": "missing",
    "extra": "extra",
    "semantic_wrong": "semantic",
    "partial": "partial",
}


def _f(x, nd=3):
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "-"


def write_csv(payload, path):
    rows = payload["families"]
    cols = ["family", "domain", "n_tasks", "n_candidates", "vci", "vci_ci_lo", "vci_ci_hi",
            "cheapness", "trust", "density", "tpr", "tnr", "far90", "tpr_equiv",
            "kappa", "kappa_source", "p95_ms", "reliable", "unreliable_reasons"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            m = r["metrics"]
            w.writerow({
                "family": r["family"],
                "domain": r["domain"],
                "n_tasks": r["n_tasks"],
                "n_candidates": r["n_candidates"],
                "vci": _f(r["vci"]),
                "vci_ci_lo": _f(r["vci_ci"][0]),
                "vci_ci_hi": _f(r["vci_ci"][1]),
                "cheapness": _f(r["cheapness"]),
                "trust": _f(r["trust"]),
                "density": _f(r["density"]),
                "tpr": _f(m["tpr"]),
                "tnr": _f(m["tnr"]),
                "far90": _f(m["far90"]),
                "tpr_equiv": _f(m["tpr_equiv"]),
                "kappa": _f(r["kappa"]["value"]),
                "kappa_source": r["kappa"]["source"],
                "p95_ms": _f(r["latency_ms"]["p95"], 1),
                "reliable": "yes" if r["reliable"] else "no",
                "unreliable_reasons": " | ".join(r["unreliable_reasons"]),
            })


def write_markdown(payload, path):
    s = payload["summary"]
    lines = [
        "# VCI coverage table",
        "",
        f"seed=`{payload['manifest']['seed']}`  tasks/family=`{payload['manifest']['n_tasks']}`  "
        f"families=`{s['n_families']}`  candidates=`{s['n_candidates']}`",
        "",
        f"**Median VCI {_f(s['vci_median'])}** "
        f"(95% bootstrap CI {_f(s['vci_median_ci'][0])}-{_f(s['vci_median_ci'][1])}), "
        f"**{s['families_ge_0.7']}/{s['n_families']} families >= 0.70**, "
        f"**{s['families_reliable']}/{s['n_families']} pass the reliability gate** "
        f"(kappa source: `{s['kappa_pooled']['source']}`).",
        "",
        "| family | domain | VCI | 95% CI | C | T | D | TPR | TNR | FAR90 | TPR-paraphrase | kappa | kappa src | p95 ms | reliable |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(payload["families"], key=lambda x: -x["vci"]):
        m = r["metrics"]
        lines.append(
            f"| {r['family']} | {r['domain']} | {_f(r['vci'])} | "
            f"{_f(r['vci_ci'][0])}-{_f(r['vci_ci'][1])} | {_f(r['cheapness'],2)} | "
            f"{_f(r['trust'],2)} | {_f(r['density'],2)} | {_f(m['tpr'],2)} | "
            f"{_f(m['tnr'],2)} | {_f(m['far90'],2)} | {_f(m['tpr_equiv'],2)} | "
            f"{_f(r['kappa']['value'],2)} | {r['kappa']['source']} | "
            f"{_f(r['latency_ms']['p95'],1)} | "
            f"{'yes' if r['reliable'] else 'NO'} |")
    lines += ["", "## Why a family is marked unreliable", ""]
    any_bad = False
    for r in payload["families"]:
        if not r["reliable"]:
            any_bad = True
            lines.append(f"- **{r['family']}**: " + "; ".join(r["unreliable_reasons"]))
    if not any_bad:
        lines.append("All families pass the gate.")
    lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>VCI audit dashboard</title>
<style>
:root{--bg:#f7f8fa;--panel:#fff;--ink:#16181d;--mut:#5d6470;--line:#e3e6eb;
--ok:#177245;--warn:#a1590b;--bad:#a12c2c;--accent:#2f5fd0;--soft:#eef1f6;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:32px 20px 60px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}
.sub{color:var(--mut);margin:0 0 24px;font-size:13px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:28px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.card .k{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut)}
.card .v{font-size:30px;font-weight:650;margin-top:6px;letter-spacing:-.02em}
.card .n{font-size:12px;color:var(--mut);margin-top:4px}
h2{font-size:16px;margin:34px 0 10px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;overflow-x:auto}
.bar-row{display:grid;grid-template-columns:170px 1fr 58px;align-items:center;gap:10px;padding:4px 0}
.bar-row .nm{font-size:12.5px;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-row .num{text-align:right;font-variant-numeric:tabular-nums;font-size:12.5px;color:var(--mut)}
.track{position:relative;height:15px;background:var(--soft);border-radius:4px;overflow:hidden}
.fill{position:absolute;left:0;top:0;bottom:0;border-radius:4px}
.tick{position:absolute;left:70%;top:0;bottom:0;border-left:1px dashed #9aa2ad}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th{font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--mut);text-align:right}
td.f,th.f{text-align:left}
td.mono{font-variant-numeric:tabular-nums}
.heat{display:inline-block;min-width:44px;padding:2px 6px;border-radius:4px;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11px;font-weight:600}
.pill.ok{background:#e4f3ea;color:var(--ok)}.pill.bad{background:#fae6e6;color:var(--bad)}
.legend{font-size:12px;color:var(--mut);margin-top:10px}
.note{font-size:12.5px;color:var(--mut);margin-top:26px;border-top:1px solid var(--line);padding-top:14px}
</style></head><body><div class="wrap">
<h1>Verification Coverage Index &mdash; first run</h1>
<p class="sub" id="sub"></p>
<div class="cards" id="cards"></div>
<h2>VCI by family</h2><div class="panel" id="bars"></div>
<p class="legend">Dashed line = 0.70 continuation threshold. Red bar = fails the reliability gate.</p>
<h2>Components</h2><div class="panel" id="comp"></div>
<h2>Per-family detail</h2><div class="panel" id="table"></div>
<h2>Which defect classes slip through</h2><div class="panel" id="heat"></div>
<p class="legend">Cell = fraction of that defect class the verifier accepted (0 = good, 1 = the class is invisible to the verifier). Blank = class not present in this family.</p>
<p class="note" id="note"></p>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const f3=x=>(x==null?'-':Number(x).toFixed(3));
const f2=x=>(x==null?'-':Number(x).toFixed(2));
document.getElementById('sub').textContent=
 `${D.manifest.n_tasks} seed tasks per family &middot; ${D.summary.n_candidates} graded candidates &middot; seed ${D.manifest.seed} &middot; generated ${D.manifest.generated_at_utc}`;
const cards=[
 ['Median VCI',f3(D.summary.vci_median),`95% CI ${f3(D.summary.vci_median_ci[0])}-${f3(D.summary.vci_median_ci[1])}`],
 ['Families >= 0.70',`${D.summary.families_ge_0.7} / ${D.summary.n_families}`,'continuation threshold'],
 ['Reliable verifiers',`${D.summary.families_reliable} / ${D.summary.n_families}`,'TPR,TNR>=.90 FAR90<=.20 kappa>=.60'],
 ['Pooled kappa',f3(D.summary.kappa_pooled.value),`${D.summary.kappa_pooled.n} rows &middot; source: ${D.summary.kappa_pooled.source}`]
];
document.getElementById('cards').innerHTML=cards.map(c=>
 `<div class="card"><div class="k">${c[0]}</div><div class="v">${c[1]}</div><div class="n">${c[2]}</div></div>`).join('');
const sorted=[...D.families].sort((a,b)=>b.vci-a.vci);
document.getElementById('bars').innerHTML=sorted.map(r=>{
 const col=r.reliable?'var(--accent)':'var(--bad)';
 return `<div class="bar-row"><div class="nm" title="${r.family}">${r.family}</div>
 <div class="track"><div class="fill" style="width:${(r.vci*100).toFixed(1)}%;background:${col}"></div>
 <div class="tick"></div></div><div class="num">${f3(r.vci)}</div></div>`}).join('');
const comp=['cheapness','trust','density'];
document.getElementById('comp').innerHTML=
 `<div style="display:grid;grid-template-columns:170px 1fr;gap:8px 10px;align-items:center">`+
 sorted.map(r=>`<div style="font-size:12.5px;color:var(--mut)">${r.family}</div>
 <div style="display:flex;height:16px;gap:4px">`+comp.map((k,i)=>{
   const cols=['#2f5fd0','#177245','#a1590b'];
   return `<div title="${k} ${f2(r[k])}" style="width:${Math.max(1,r[k]*100)}%;background:${cols[i]};border-radius:3px;opacity:.85"></div>`
 }).join('')+`</div>`).join('')+`</div>
 <div class="legend"><span style="color:#2f5fd0">&#9632;</span> cheapness &nbsp;
 <span style="color:#177245">&#9632;</span> trust &nbsp;
 <span style="color:#a1590b">&#9632;</span> density</div>`;
document.getElementById('table').innerHTML=
 `<table><thead><tr><th class="f">family</th><th class="f">domain</th><th>VCI</th><th>CI</th>
 <th>C</th><th>T</th><th>D</th><th>TPR</th><th>TNR</th><th>FAR90</th><th>TPR&nbsp;paraphr.</th>
 <th>kappa</th><th>src</th><th>p95&nbsp;ms</th><th>gate</th></tr></thead><tbody>`+
 sorted.map(r=>`<tr><td class="f">${r.family}</td><td class="f" style="color:var(--mut)">${r.domain}</td>
 <td class="mono">${f3(r.vci)}</td><td class="mono" style="color:var(--mut)">${f2(r.vci_ci[0])}-${f2(r.vci_ci[1])}</td>
 <td class="mono">${f2(r.cheapness)}</td><td class="mono">${f2(r.trust)}</td><td class="mono">${f2(r.density)}</td>
 <td class="mono">${f2(r.metrics.tpr)}</td><td class="mono">${f2(r.metrics.tnr)}</td>
 <td class="mono">${f2(r.metrics.far90)}</td><td class="mono">${f2(r.metrics.tpr_equiv)}</td>
 <td class="mono">${f2(r.kappa.value)}</td><td class="mono" style="color:var(--mut)">${r.kappa.source}</td><td class="mono">${Number(r.latency_ms.p95).toFixed(1)}</td>
 <td>${r.reliable?'<span class="pill ok">pass</span>':'<span class="pill bad">fail</span>'}</td></tr>`).join('')+
 `</tbody></table>`;
const defects=['boundary','off_by_one','type_mismatch','order','missing','extra','semantic_wrong','semantic_equivalent','partial'];
document.getElementById('heat').innerHTML=
 `<table><thead><tr><th class="f">family</th>`+defects.map(d=>`<th>${d.replace('_','-')}</th>`).join('')+`</tr></thead><tbody>`+
 sorted.map(r=>`<tr><td class="f">${r.family}</td>`+defects.map(d=>{
   const cell=r.per_defect[d];
   if(!cell||!cell.n) return `<td style="color:#c3c8d0">-</td>`;
   const a=cell.accept_rate;
   const bg=a<0.05?'#e6f4ec':a<0.2?'#fdf3df':'#fae6e6';
   const fg=a<0.05?'#177245':a<0.2?'#8a5a00':'#a12c2c';
   return `<td><span class="heat" style="background:${bg};color:${fg}">${a.toFixed(2)}</span></td>`;
 }).join('')+`</tr>`).join('')+`</tbody></table>`;
document.getElementById('note').textContent=
 `VCI = (C * T^2 * D)^0.25. C = cheapness from p95 latency (1.0 at <=20 ms, 0 at >=500 ms). `+
 `T = min(TPR, TNR, 1-FAR90) at full-credit acceptance. D = granularity x partial-credit fidelity. `+
 `All mutants are generated programmatically; labels are synthetic. kappa is measured against those `+
 `synthetic labels unless annotations/labels.csv exists, in which case the blind human sheet takes over. `+
 `Because selfcheck forces verifier/mutant agreement to be perfect, every synthetic kappa is an upper bound. `+
 `Latency is the only hardware-dependent number. `+
 `Self-contained page: no network requests.`;
</script></body></html>"""


def write_html(payload, path):
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(HTML.replace("__DATA__", data))


def write_all(payload, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    write_csv(payload, os.path.join(out_dir, "coverage.csv"))
    write_markdown(payload, os.path.join(out_dir, "coverage.md"))
    write_html(payload, os.path.join(out_dir, "dashboard.html"))
