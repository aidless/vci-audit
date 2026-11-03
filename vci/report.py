"""Deliverable writers: results.json, coverage table, static dashboard."""
import csv
import json
import os

DEFECT_ORDER = ["correct", "semantic_equivalent", "boundary", "off_by_one",
                "type_mismatch", "order", "missing", "extra", "semantic_wrong",
                "partial"]

FAILURE_ORDER = ["semantic_equivalent", "spec_ambiguity", "hardcoded_expected",
                 "overfit_to_tests", "silent_partial", "resource"]


def _f(x, nd=3):
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "-"


def write_csv(payload, path):
    rows = payload["families"]
    cols = ["family", "domain", "n_tasks", "n_candidates", "n_probes",
            "vci", "vci_ci_lo", "vci_ci_hi", "vci_aligned", "vci_non_aligned",
            "cheapness", "trust", "trust_aligned", "trust_non_aligned", "density",
            "tpr", "tnr", "far90", "tpr_equiv",
            "tpr_na", "tnr_na", "far90_na", "n_probe_pos", "n_probe_neg",
            "kappa", "kappa_source", "kappa_human", "kappa_human_n",
            "kappa_stability", "kappa_stability_n",
            "p95_ms", "probe_p95_ms", "reliable", "reliable_non_aligned",
            "core", "core_human_backed", "unreliable_reasons",
            "unreliable_reasons_non_aligned"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            m = r["metrics_aligned"]
            na = r["metrics_non_aligned"]
            k = r["kappa"]
            w.writerow({
                "family": r["family"],
                "domain": r["domain"],
                "n_tasks": r["n_tasks"],
                "n_candidates": r["n_candidates"],
                "n_probes": r["n_probes"],
                "vci": _f(r["vci"]),
                "vci_ci_lo": _f(r["vci_ci"][0]),
                "vci_ci_hi": _f(r["vci_ci"][1]),
                "vci_aligned": _f(r["vci_aligned"]),
                "vci_non_aligned": _f(r["vci_non_aligned"]),
                "cheapness": _f(r["cheapness"]),
                "trust": _f(r["trust"]),
                "trust_aligned": _f(r["trust_aligned"]),
                "trust_non_aligned": _f(r["trust_non_aligned"]),
                "density": _f(r["density"]),
                "tpr": _f(m["tpr"]),
                "tnr": _f(m["tnr"]),
                "far90": _f(m["far90"]),
                "tpr_equiv": _f(m["tpr_equiv"]),
                "tpr_na": _f(na["tpr"]),
                "tnr_na": _f(na["tnr"]),
                "far90_na": _f(na["far90"]),
                "n_probe_pos": int(na["n_pos"]),
                "n_probe_neg": int(na["n_neg"]),
                "kappa": _f(k["value"]),
                "kappa_source": k["source"],
                "kappa_human": _f(k["human"]["value"]) if k["human"]["n"] else "-",
                "kappa_human_n": k["human"]["n"],
                "kappa_stability": (_f(k["stability"]["value"])
                                    if k["stability"]["value"] is not None else "-"),
                "kappa_stability_n": k["stability"]["n"],
                "p95_ms": _f(r["latency_ms"]["p95"], 1),
                "probe_p95_ms": _f(r["probe_latency_ms"]["p95"], 1),
                "reliable": "yes" if r["reliable"] else "no",
                "reliable_non_aligned": ("yes" if r["reliable_non_aligned"] else "no"
                                         if r["reliable_non_aligned"] is False else "-"),
                "core": "yes" if r["core_eligible"] else "no",
                "core_human_backed": "yes" if r["core_human_backed"] else "no",
                "unreliable_reasons": " | ".join(r["unreliable_reasons"]),
                "unreliable_reasons_non_aligned": " | ".join(
                    r["unreliable_reasons_non_aligned"]),
            })


def write_markdown(payload, path):
    s = payload["summary"]
    kp = s["kappa_pooled"]
    lines = [
        "# VCI coverage table (round 2)",
        "",
        f"seed=`{payload['manifest']['seed']}`  tasks/family=`{payload['manifest']['n_tasks']}`  "
        f"families=`{s['n_families']}`  aligned candidates=`{s['n_candidates']}`  "
        f"non-aligned probes=`{s['n_probes']}`",
        "",
        f"**Median VCI {_f(s['vci_median'])}** "
        f"(95% bootstrap CI {_f(s['vci_median_ci'][0])}-{_f(s['vci_median_ci'][1])}); "
        f"aligned-only median {_f(s['vci_median_aligned'])} "
        f"({_f(s['vci_median_aligned_ci'][0])}-{_f(s['vci_median_aligned_ci'][1])}). "
        f"**{s['families_ge_0.7']}/{s['n_families']} families >= 0.70**.",
        "",
        f"Median trust: aligned `{_f(s['trust_median_aligned'])}`, "
        f"non-aligned `{_f(s['trust_median_non_aligned'])}`. "
        f"kappa in use: `{kp['source']}` (human rows n={kp['human']['n']}, "
        f"undecidable {kp['human']['n_undecidable']}; synthetic upper bound "
        f"{_f(kp['synthetic']['value'])} is reported separately and is not a human value).",
        "",
        "## Per family: VCI, components, aligned vs non-aligned trust",
        "",
        "| family | VCI | 95% CI | C | D | K | T | T-aligned | T-non-aligned | "
        "TPR al | TNR al | FAR90 al | TPR na | TNR na | FAR90 na | kappa (src) | "
        "gate al | gate na |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(payload["families"], key=lambda x: -x["vci"]):
        m, na, k = r["metrics_aligned"], r["metrics_non_aligned"], r["kappa"]
        gate_na = ("yes" if r["reliable_non_aligned"] else "NO"
                   if r["reliable_non_aligned"] is False else "-")
        lines.append(
            f"| {r['family']} | {_f(r['vci'])} | "
            f"{_f(r['vci_ci'][0])}-{_f(r['vci_ci'][1])} | {_f(r['cheapness'],2)} | "
            f"{_f(r['density'],2)} | {_f(r['units_per_task'],1)} | {_f(r['trust'],2)} | "
            f"{_f(r['trust_aligned'],2)} | {_f(r['trust_non_aligned'],2)} | "
            f"{_f(m['tpr'],2)} | {_f(m['tnr'],2)} | {_f(m['far90'],2)} | "
            f"{_f(na['tpr'],2)} | {_f(na['tnr'],2)} | {_f(na['far90'],2)} | "
            f"{_f(k['value'],2)} ({k['source']}) | "
            f"{'yes' if r['reliable'] else 'NO'} | {gate_na} |")
    lines += ["", "## Non-aligned acceptance by failure class", "",
              "Cell = share of that class the verifier accepted. `n` is the number of "
              "probes in the class. `-` means the class was not sampled for the family.",
              "",
              "| family | " + " | ".join(FAILURE_ORDER) + " |",
              "|---|" + "---|" * len(FAILURE_ORDER)]
    for r in sorted(payload["families"], key=lambda x: -x["trust_non_aligned"]):
        cells = []
        for cls in FAILURE_ORDER:
            c = r["per_failure_class"].get(cls)
            cells.append(f"{_f(c['accept_rate'],2)} (n={c['n']})" if c else "-")
        lines.append(f"| {r['family']} | " + " | ".join(cells) + " |")
    lines += ["", "## Why a family is marked unreliable", ""]
    any_bad = False
    for r in payload["families"]:
        if not r["reliable"]:
            any_bad = True
            lines.append(f"- **{r['family']}** (aligned gate): "
                         + "; ".join(r["unreliable_reasons"]))
        if r["reliable_non_aligned"] is False:
            any_bad = True
            lines.append(f"- **{r['family']}** (non-aligned gate): "
                         + "; ".join(r["unreliable_reasons_non_aligned"]))
    if not any_bad:
        lines.append("All families pass both gates.")
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
.wrap{max-width:1320px;margin:0 auto;padding:32px 20px 60px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}
.sub{color:var(--mut);margin:0 0 24px;font-size:13px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:28px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.card .k{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut)}
.card .v{font-size:28px;font-weight:650;margin-top:6px;letter-spacing:-.02em}
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
.pill.warn{background:#fdf3df;color:var(--warn)}
.legend{font-size:12px;color:var(--mut);margin-top:10px}
.note{font-size:12.5px;color:var(--mut);margin-top:26px;border-top:1px solid var(--line);padding-top:14px}
</style></head><body><div class="wrap">
<h1>Verification Coverage Index &mdash; round 2</h1>
<p class="sub" id="sub"></p>
<div class="cards" id="cards"></div>
<h2>VCI by family (aligned vs non-aligned marked)</h2><div class="panel" id="bars"></div>
<p class="legend">Solid bar = round-2 VCI (trust limited by non-aligned probes). Dashed line = 0.70 threshold. Red = fails the aligned reliability gate.</p>
<h2>Components</h2><div class="panel" id="comp"></div>
<h2>Per-family detail</h2><div class="panel" id="table"></div>
<h2>Aligned mutants: which defect classes slip through</h2><div class="panel" id="heat"></div>
<p class="legend">Cell = fraction of that defect class the verifier accepted (0 = good, 1 = invisible to the verifier).</p>
<h2>Non-aligned probes: acceptance by failure class</h2><div class="panel" id="heat2"></div>
<p class="legend">Cell = share of probes the verifier accepted. Green = correctly rejected, red = accepted a candidate that should have been rejected (or rejected one that should have passed). Hover shows class and n.</p>
<p class="note" id="note"></p>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const f3=x=>(x==null?'-':Number(x).toFixed(3));
const f2=x=>(x==null?'-':Number(x).toFixed(2));
const S=D.summary, K=S.kappa_pooled;
document.getElementById('sub').textContent=
 `${D.manifest.n_tasks} seed tasks per family &middot; ${S.n_candidates} aligned mutants + ${S.n_probes} non-aligned probes &middot; seed ${D.manifest.seed} &middot; generated ${D.manifest.generated_at_utc}`;
const cards=[
 ['Median VCI (round 2)',f3(S.vci_median),`95% CI ${f3(S.vci_median_ci[0])}-${f3(S.vci_median_ci[1])} &middot; aligned-only ${f3(S.vci_median_aligned)}`],
 ['Families >= 0.70',`${S.families_ge_0.7} / ${S.n_families}`,`aligned-only: ${S.families_ge_0.7_aligned}`],
 ['Median trust',f3(S.trust_median_non_aligned),`aligned ${f3(S.trust_median_aligned)} &middot; non-aligned shown`],
 ['Core families',`${S.core_provisional.length}`,`human-backed: ${S.core_human_backed.length}`],
 ['kappa in use',K.human.n?f3(K.human.value):'n/a',`source ${K.source} &middot; human n=${K.human.n} &middot; synthetic ${f3(K.synthetic.value)}`]
];
document.getElementById('cards').innerHTML=cards.map(c=>
 `<div class="card"><div class="k">${c[0]}</div><div class="v">${c[1]}</div><div class="n">${c[2]}</div></div>`).join('');
const sorted=[...D.families].sort((a,b)=>b.vci-a.vci);
document.getElementById('bars').innerHTML=sorted.map(r=>{
 const col=r.reliable?'var(--accent)':'var(--bad)';
 return `<div class="bar-row" title="aligned-only ${f3(r.vci_aligned)} | non-aligned T ${f2(r.trust_non_aligned)}"><div class="nm">${r.family}</div>
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
 <span style="color:#177245">&#9632;</span> trust (min of aligned / non-aligned) &nbsp;
 <span style="color:#a1590b">&#9632;</span> density</div>`;
document.getElementById('table').innerHTML=
 `<table><thead><tr><th class="f">family</th><th class="f">domain</th><th>VCI</th><th>CI</th>
 <th>C</th><th>D</th><th>K</th><th>T</th><th>T al</th><th>T na</th>
 <th>TPR al</th><th>TNR al</th><th>FAR90 al</th><th>TPR na</th><th>TNR na</th><th>FAR90 na</th>
 <th>kappa</th><th>src</th><th>p95&nbsp;ms</th><th>gate al / na</th></tr></thead><tbody>`+
 sorted.map(r=>{const m=r.metrics_aligned,na=r.metrics_non_aligned;return `<tr><td class="f">${r.family}</td><td class="f" style="color:var(--mut)">${r.domain}</td>
 <td class="mono">${f3(r.vci)}</td><td class="mono" style="color:var(--mut)">${f2(r.vci_ci[0])}-${f2(r.vci_ci[1])}</td>
 <td class="mono">${f2(r.cheapness)}</td><td class="mono">${f2(r.density)}</td><td class="mono">${Number(r.units_per_task).toFixed(1)}</td>
 <td class="mono">${f2(r.trust)}</td><td class="mono">${f2(r.trust_aligned)}</td><td class="mono">${f2(r.trust_non_aligned)}</td>
 <td class="mono">${f2(m.tpr)}</td><td class="mono">${f2(m.tnr)}</td><td class="mono">${f2(m.far90)}</td>
 <td class="mono">${f2(na.tpr)}</td><td class="mono">${f2(na.tnr)}</td><td class="mono">${f2(na.far90)}</td>
 <td class="mono">${f2(r.kappa.value)}</td><td class="mono" style="color:var(--mut)">${r.kappa.source}</td>
 <td class="mono">${Number(r.latency_ms.p95).toFixed(1)}</td>
 <td>${r.reliable?'<span class="pill ok">al</span>':'<span class="pill bad">al</span>'} ${r.reliable_non_aligned===false?'<span class="pill bad">na</span>':r.reliable_non_aligned?'<span class="pill ok">na</span>':'<span class="pill warn">na ?</span>'}${r.core_eligible?' <span class="pill warn">core*</span>':''}</td></tr>`}).join('')+
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
const fclasses=['semantic_equivalent','spec_ambiguity','hardcoded_expected','overfit_to_tests','silent_partial','resource'];
document.getElementById('heat2').innerHTML=
 `<table><thead><tr><th class="f">family</th>`+fclasses.map(d=>`<th>${d.replace(/_/g,'-')}</th>`).join('')+`</tr></thead><tbody>`+
 sorted.map(r=>`<tr><td class="f">${r.family}</td>`+fclasses.map(d=>{
   const cell=r.per_failure_class[d];
   if(!cell) return `<td style="color:#c3c8d0">-</td>`;
   const a=cell.accept_rate;
   const bg=a<0.05?'#e6f4ec':a<0.2?'#fdf3df':'#fae6e6';
   const fg=a<0.05?'#177245':a<0.2?'#8a5a00':'#a12c2c';
   return `<td title="${d}: n=${cell.n} pos=${cell.n_pos} neg=${cell.n_neg} tpr=${f2(cell.tpr)} tnr=${f2(cell.tnr)}"><span class="heat" style="background:${bg};color:${fg}">${a.toFixed(2)}</span></td>`;
 }).join('')+`</tr>`).join('')+`</tbody></table>`;
document.getElementById('note').textContent=
 `VCI = (C * T^2 * D)^0.25. C = cheapness from aligned p95 latency (1.0 at <=20 ms, 0 at >=500 ms). `+
 `T = min(T_aligned, T_non_aligned); each T is min(TPR, TNR, 1-FAR90). `+
 `Aligned mutants are generated by the family's own generator, so their labels and the verifier share `+
 `code. Non-aligned probes live in vci/adversarial.py and never call the verifier to decide their label. `+
 `kappa: ${K.source}; human rows n=${K.human.n}, undecidable ${K.human.n_undecidable}; `+
 `synthetic upper bound ${f3(K.synthetic.value)} is never used in place of a human value; `+
 `human test-retest stability ${K.stability.value==null?'n/a':f3(K.stability.value)} (n=${K.stability.n}). `+
 `core* = VCI>=0.70 and T>=0.90 and D>0, but the kappa behind it is synthetic, so the list is provisional. `+
 `Latency is the only hardware-dependent number. Self-contained page: no network requests.`;
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
