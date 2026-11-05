"""Command line entry point.

    python -m vci audit --families all --out outputs/
    python -m vci list-families
    python -m vci annotate --per-family 3 --out annotations/blind.csv
    python -m vci label --sheet annotations/blind.csv --out annotations/labels.csv \
        --qualification --group-by-family
    python -m vci label --sheet annotations/blind.csv \
        --out annotations/labels_retest.csv --round 2 --shuffle-seed 99
    python -m vci selfcheck
    python -m vci score-annotations
"""
import argparse
import csv
import os
import sys

from . import audit, registry, report


def _add_common(p):
    p.add_argument("--families", default="all",
                   help="'all' or a comma separated list, e.g. arith_expression,sql_result")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--tasks", type=int, default=25, help="seed tasks per family (20-40)")


def cmd_audit(args):
    fams = registry.resolve(args.families)
    payload = audit.run_audit(
        families=fams, n_tasks=args.tasks, seed=args.seed, n_boot=args.bootstrap,
        labels_path=args.labels, labels_retest_path=args.labels_retest,
        keep_raw=True, work_dir=args.work,
    )
    report.write_all(payload, args.out)
    s = payload["summary"]
    print(f"families={s['n_families']}  aligned candidates={s['n_candidates']}  "
          f"probes={s['n_probes']} ({s['n_probes_scored']} scored)")
    print(f"median VCI={s['vci_median']:.3f} "
          f"[{s['vci_median_ci'][0]:.3f}-{s['vci_median_ci'][1]:.3f}]  "
          f"(aligned-only {s['vci_median_aligned']:.3f} "
          f"[{s['vci_median_aligned_ci'][0]:.3f}-{s['vci_median_aligned_ci'][1]:.3f}])  "
          f">=0.70: {s['families_ge_0.7']}/{s['n_families']}")
    print(f"median trust aligned={s['trust_median_aligned']:.3f}  "
          f"non-aligned={s['trust_median_non_aligned']:.3f}  "
          f"reliable(aligned gate)={s['families_reliable']}/{s['n_families']}  "
          f"core(provisional)={len(s['core_provisional'])}  "
          f"core(human-backed)={len(s['core_human_backed'])}")
    print(f"kappa source: {s['kappa_pooled']['source']}  "
          f"human rows={s['kappa_pooled']['human']['n']} "
          f"undecidable={s['kappa_pooled']['human']['n_undecidable']}  "
          f"synthetic upper bound={s['kappa_pooled']['synthetic']['value']:.3f} "
          f"(n={s['kappa_pooled']['synthetic']['n']})")
    if not s["kappa_pooled"]["human"]["n"]:
        print("note: no human labels found, so kappa is measured against the mutant "
              "generator and is an upper bound. Run 'python3 -m vci label' on "
              "annotations/blind.csv to obtain a human kappa.", file=sys.stderr)
    print("wrote " + ", ".join(os.path.join(args.out, n) for n in
                               ("results.json", "coverage.csv", "coverage.md",
                                "attribution.csv", "dashboard.html")))
    return 0


def cmd_list(args):
    for meta in registry.registry_metadata():
        print(f"{meta['family']:22s} {meta['domain']:14s} units={meta['item_unit']:12s} "
              f"{meta['task_shape']}")
    return 0


def cmd_annotate(args):
    fams = registry.resolve(args.families)
    rows = audit.annotation_sample(n_tasks=args.tasks, seed=args.seed, families=fams,
                                   per_family=args.per_family)
    if args.limit:
        rows = rows[:args.limit]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["row_id", "family", "task_prompt",
                                           "reference_answer", "candidate",
                                           "human_label"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} blind rows to {args.out}")
    print("Fill the human_label column with 1 (valid) or 0 (invalid). The defect class "
          "is deliberately not shown.")
    return 0


def cmd_harness_diff(args):
    from . import harness_diff
    result = harness_diff.run_differential(n_tasks=args.tasks, seed=args.seed,
                                           n_seeds=args.seeds)
    harness_diff.write_report(result, args.out)
    p = result["pooled"]
    print(f"harness differential on {result['family']}: "
          f"{result['n_tasks']} tasks x {len(result['seeds'])} seeds, "
          f"{p['A']['n']} scored probes per strategy")
    print(f"trust non-aligned: A={p['A']['trust']:.3f} -> B={p['B']['trust']:.3f}  "
          f"(TNR {p['A']['tnr']:.3f} -> {p['B']['tnr']:.3f})")
    x = p["x02"]
    print(f"x02 leak: A accepted {x['A']['accepted']}/{x['A']['n']}, "
          f"B accepted {x['B']['accepted']}/{x['B']['n']}")
    ag = result["aligned_agreement_seed0"]
    print(f"aligned agreement (seed {args.seed}): {ag['n_disagree']}/{ag['n']} flips")
    d = result["trust_delta_B_minus_A"]
    sd = f"{d['sd']:.4f}" if d["sd"] is not None else "n/a"
    print(f"trust delta B-A: mean={d['mean']:.4f} sd={sd} over {len(d['per_seed'])} seeds")
    print("wrote " + args.out)
    return 0


def cmd_realfail(args):
    import json
    from . import realfail
    fams = registry.resolve(args.families) if args.families != "default" else \
        [registry.by_name(n) for n in realfail.DEFAULT_FAMILIES]
    payload = realfail.run(fams, n_tasks=args.tasks, seed=args.seed,
                           model=args.model, host=args.host,
                           max_tokens=args.max_tokens, timeout_s=args.timeout)
    import os
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    n_err = sum(1 for r in payload["records"] if "error" in r)
    n_scored = sum(1 for r in payload["records"] if "verdict" in r)
    n_pass = sum(1 for r in payload["records"]
                 if r.get("verdict", {}).get("passed"))
    print(f"realfail: {len(payload['records'])} tasks "
          f"({n_scored} scored, {n_err} transport errors), "
          f"verifier accepted {n_pass}")
    print("wrote " + args.out)
    return 0


def cmd_realfail_sheet(args):
    import json
    from . import realfail
    with open(args.run, encoding="utf-8") as fh:
        payload = json.load(fh)
    fams = {f.name: f for f in registry.FAMILIES}
    rows = realfail.emit_sheet(payload, fams)
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    print(f"wrote {len(rows)} sheet rows to {args.out}")
    return 0


def cmd_realfail_tolerant(args):
    import json
    from . import realfail
    with open(args.run, encoding="utf-8") as fh:
        payload = json.load(fh)
    labels = realfail.load_human_labels(args.labels)
    fams = {f.name: f for f in registry.FAMILIES}
    rep = realfail.analyze_tolerant(payload, labels, fams)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=1)
    print(f"faithful families: {', '.join(rep['faithful_families'])}")
    for fam, why in rep["excluded_families"].items():
        print(f"  EXCLUDED {fam}: {why['mismatched_units']} replay mismatches")

    def _fmt(x):
        return "n/a" if x is None else f"{x:.3f}"

    modes = list(rep["rule_variants"])
    for fam, c in rep["per_family"].items():
        s = c["strict"]
        for m in modes:
            v = c["variants"][m]
            print(f"  {fam:22s} {m} TPR {_fmt(s['tpr'])} -> {_fmt(v['tpr'])} "
                  f"TNR {_fmt(s['tnr'])} -> {_fmt(v['tnr'])} "
                  f"repairs={len(v['repairs'])} "
                  f"(correct={len(v['repaired_correct'])}, "
                  f"new FA={len(v['new_false_accepts'])})")
    s = rep["pooled"]["strict"]
    for m in modes:
        v = rep["pooled"]["variants"][m]
        print(f"  {'POOLED':22s} {m} TPR {_fmt(s['tpr'])} -> {_fmt(v['tpr'])} "
              f"TNR {_fmt(s['tnr'])} -> {_fmt(v['tnr'])} "
              f"kappa {_fmt(s['kappa'])} -> {_fmt(v['kappa'])} "
              f"repairs={len(v['repairs'])} "
              f"(correct={len(v['repaired_correct'])}, "
              f"new FA={len(v['new_false_accepts'])})")
    print("wrote " + args.out)
    return 0


def cmd_realfail_analyze(args):
    import json
    from . import realfail
    with open(args.run, encoding="utf-8") as fh:
        payload = json.load(fh)
    labels = realfail.load_human_labels(args.labels)
    fams = {f.name: f for f in registry.FAMILIES}
    rep = realfail.analyze(payload, labels, fams)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=1)
    rs = rep["run_stats"]
    print(f"run: {rs['n_tasks_run']} tasks, {rs['n_errors']} errors, "
          f"{rs['parse_fail']} parse failures, "
          f"verifier passed {rs['verifier_passed_tasks']} tasks")
    print(f"labels: {rep['n_labeled']}/{rep['n_sheet_rows']} units labeled "
          f"({rep['n_undecidable']} undecidable, {len(rep['unlabeled'])} missing)")
    for fam, c in rep["per_family"].items():
        k = f"{c['kappa']:.3f}" if c["kappa"] is not None else "n/a"
        tpr = f"{c['tpr']:.3f}" if c["tpr"] is not None else "n/a"
        tnr = f"{c['tnr']:.3f}" if c["tnr"] is not None else "n/a"
        print(f"  {fam:22s} n={c['n']:3d} pos={c['pos']:3d} neg={c['neg']:3d} "
              f"TPR={tpr} TNR={tnr} kappa={k} "
              f"FA={len(c['false_accepts'])} FR={len(c['false_rejects'])}")
    p = rep["pooled"]
    k = f"{p['kappa']:.3f}" if p["kappa"] is not None else "n/a"
    print(f"  {'POOLED':22s} n={p['n']:3d} pos={p['pos']:3d} neg={p['neg']:3d} "
          f"TPR={p['tpr']:.3f} TNR={p['tnr']:.3f} kappa={k} "
          f"FA={len(p['false_accepts'])} FR={len(p['false_rejects'])}")
    print("wrote " + args.out)
    return 0


def cmd_harness_decomp(args):
    from . import harness_decomp
    result = harness_decomp.decompose_file(args.input, args.b, top_n=args.top_n)
    harness_decomp.write_report(result, args.out)
    print(harness_decomp.format_summary(result))
    print("wrote " + args.out)
    return 0 if result.get("ok") else 2


def cmd_passk(args):
    from . import passk
    result = passk.compute_file(args.input, k_max=args.k_max, n_boot=args.bootstrap,
                                seed=args.seed)
    passk.write_report(result, args.out)
    print(passk.format_summary(result))
    print("wrote " + args.out)
    return 0 if result.get("ok") else 2


def cmd_selfcheck(args):
    problems = audit.selfcheck(families=registry.resolve(args.families),
                               n_tasks=args.tasks, seed=args.seed)
    if not problems:
        print("selfcheck clean: every correct mutant passed and every wrong mutant failed")
        return 0
    print(f"{len(problems)} contradictory mutants:")
    for p in problems[:40]:
        print("  ", p)
    return 1


def cmd_label(args):
    from .labeler import run

    stats = run(args.sheet, args.out, round_no=args.round, annotator=args.user,
                shuffle_seed=args.shuffle_seed, limit=args.limit, redo=args.redo,
                group_by_family=args.group_by_family,
                qualification=args.qualification)
    qual = stats.get("qualification")
    if qual:
        print(f"qualification: {qual['correct']}/{qual['total']} correct"
              + (f" (wrong: {', '.join(qual['wrong'])})" if qual["wrong"] else ""))
    return 0 if stats["quit"] or stats["total"] else 2


def cmd_score(args):
    """Recompute agreement only, from an existing results.json plus label sheets."""
    import json

    labels = audit._load_label_rows(args.labels)
    retest = audit._load_label_rows(args.labels_retest)
    if not labels:
        print(f"no labels found in {args.labels}", file=sys.stderr)
        return 2
    with open(os.path.join(args.out, "results.json"), encoding="utf-8") as fh:
        payload = json.load(fh)
    recs, probes = [], []
    for r in payload["families"]:
        fam = registry.by_name(r["family"])
        groups = audit.collect(fam, payload["manifest"]["n_tasks"],
                               audit.family_seed(payload["manifest"]["seed"],
                                                 registry.INDEX[fam.name]))
        recs += [x for g in groups for x in g["records"]]
        probes += [x for g in groups for x in g["probes"]]
    info = audit._family_kappa(recs, probes, labels, retest,
                               n_boot=args.bootstrap, seed=0)
    human, synth = info["human"], info["synthetic"]
    oracle, stab = info["oracle_non_aligned"], info["stability"]
    stab_txt = f"{stab['value']:.3f}" if stab["value"] is not None else "n/a"
    print(f"sheet rows: {len(labels)} (undecidable {human['n_undecidable']})  "
          f"retest rows: {len(retest)}")
    print(f"human vs verifier      : n={human['n']:4d}  kappa={human['value']:.3f}  "
          f"CI[{human['ci'][0]:.3f}-{human['ci'][1]:.3f}]  po={human['po']:.3f}")
    print(f"human test-retest      : n={stab['n']:4d}  kappa={stab_txt}")
    print(f"synthetic upper bound  : n={synth['n']:4d}  kappa={synth['value']:.3f}  "
          f"(NOT a substitute for human)")
    print(f"independent probe judge: n={oracle['n']:4d}  kappa={oracle['value']:.3f}  "
          f"CI[{oracle['ci'][0]:.3f}-{oracle['ci'][1]:.3f}]")
    print(f"effective source       : {info['source']}")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="python -m vci", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="run the full audit and write deliverables")
    _add_common(a)
    a.add_argument("--out", default="outputs")
    a.add_argument("--work", default="work")
    a.add_argument("--bootstrap", type=int, default=500)
    a.add_argument("--labels", default="annotations/labels.csv")
    a.add_argument("--labels-retest", default="annotations/labels_retest.csv",
                   dest="labels_retest", help="second-pass sheet for annotator stability")
    a.set_defaults(fn=cmd_audit)

    l = sub.add_parser("list-families", help="print the registry")
    l.set_defaults(fn=cmd_list)

    n = sub.add_parser("annotate", help="emit a blind human-adjudication sheet")
    _add_common(n)
    n.add_argument("--out", default="annotations/blind.csv")
    n.add_argument("--per-family", type=int, default=3, dest="per_family")
    n.add_argument("--limit", type=int, default=0, help="0 = no limit")
    n.set_defaults(fn=cmd_annotate)

    b = sub.add_parser("label", help="blind-label the sheet from the terminal")
    b.add_argument("--sheet", default="annotations/blind.csv")
    b.add_argument("--out", default="annotations/labels.csv")
    b.add_argument("--round", type=int, default=1,
                   help="1 = first pass, 2 = test-retest pass")
    b.add_argument("--user", default="anon")
    b.add_argument("--shuffle-seed", type=int, default=None, dest="shuffle_seed",
                   help="shuffle pending rows deterministically (use a fresh seed for the retest)")
    b.add_argument("--limit", type=int, default=0, help="0 = no limit")
    b.add_argument("--redo", action="store_true", help="ignore existing answers")
    b.add_argument("--group-by-family", action="store_true", dest="group_by_family",
                   help="present one family at a time, shuffled within the family")
    b.add_argument("--qualification", action="store_true",
                   help="ask 3 calibration items first (wrong answers warn, never block)")
    b.set_defaults(fn=cmd_label)

    s = sub.add_parser("selfcheck", help="find mutants that contradict their own label")
    _add_common(s)
    s.set_defaults(fn=cmd_selfcheck)

    hd = sub.add_parser("harness-decomp",
                        help="decompose a two-harness score difference into "
                             "state / compaction / tool / retry")
    hd.add_argument("--input", required=True,
                    help="combined JSON/CSV (both harnesses per task) or harness A")
    hd.add_argument("--b", default=None, help="optional second file (harness B)")
    hd.add_argument("--out", default="work/harness_decomp.json")
    hd.add_argument("--top-n", type=int, default=10, dest="top_n")
    hd.set_defaults(fn=cmd_harness_decomp)

    pk = sub.add_parser("passk",
                        help="pass@1, pass@k and pass^k curves with bootstrap CI")
    pk.add_argument("--input", required=True)
    pk.add_argument("--out", default="work/passk.json")
    pk.add_argument("--k-max", type=int, default=None, dest="k_max")
    pk.add_argument("--bootstrap", type=int, default=1000)
    pk.add_argument("--seed", type=int, default=0)
    pk.set_defaults(fn=cmd_passk)

    h = sub.add_parser("harness-diff",
                       help="compare harness strategies A (single pass) and B "
                            "(repeat run) on the code_patch probe set")
    h.add_argument("--seed", type=int, default=0)
    h.add_argument("--tasks", type=int, default=25, help="seed tasks (20-40)")
    h.add_argument("--seeds", type=int, default=5,
                   help="number of task seeds for the delta spread")
    h.add_argument("--out", default="work/harness_diff.json")
    h.set_defaults(fn=cmd_harness_diff)

    rf = sub.add_parser("realfail",
                        help="sample real model outputs via local ollama and "
                             "verify them (round-6 real-failure study)")
    rf.add_argument("--families", default="default",
                    help="'default' = the six round-6 families, 'all', or a list")
    rf.add_argument("--seed", type=int, default=20261104,
                    help="task seed (disjoint from the audit seed 0)")
    rf.add_argument("--tasks", type=int, default=25)
    rf.add_argument("--model", default="evalsft-qwen25-05b:latest")
    rf.add_argument("--host", default="http://localhost:11434")
    rf.add_argument("--max-tokens", type=int, default=1024, dest="max_tokens")
    rf.add_argument("--timeout", type=float, default=120.0)
    rf.add_argument("--out", default="work/realfail.json")
    rf.set_defaults(fn=cmd_realfail)

    rs = sub.add_parser("realfail-sheet",
                        help="emit the per-unit human-adjudication sheet")
    rs.add_argument("--run", default="work/realfail.json")
    rs.add_argument("--out", default="work/realfail_sheet.jsonl")
    rs.set_defaults(fn=cmd_realfail_sheet)

    ra = sub.add_parser("realfail-analyze",
                        help="merge human labels and compute verifier "
                             "TPR/TNR/kappa against human truth")
    ra.add_argument("--run", default="work/realfail.json")
    ra.add_argument("--labels", default="work/realfail_human.csv")
    ra.add_argument("--out", default="work/realfail_analysis.json")
    ra.set_defaults(fn=cmd_realfail_analyze)

    rt = sub.add_parser("realfail-tolerant",
                        help="counterfactual: re-grade the archived run with "
                             "schema-tolerant extraction (round 8)")
    rt.add_argument("--run", default="work/realfail.json")
    rt.add_argument("--labels", default="work/realfail_human.csv")
    rt.add_argument("--out", default="work/realfail_tolerant.json")
    rt.set_defaults(fn=cmd_realfail_tolerant)

    c = sub.add_parser("score-annotations", help="recompute kappa from labels")
    c.add_argument("--labels", default="annotations/labels.csv")
    c.add_argument("--labels-retest", default="annotations/labels_retest.csv",
                   dest="labels_retest")
    c.add_argument("--out", default="outputs")
    c.add_argument("--bootstrap", type=int, default=500)
    c.set_defaults(fn=cmd_score)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
