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
              "generator and is an upper bound. Run 'python -m vci label' on "
              "annotations/blind.csv to obtain a human kappa.", file=sys.stderr)
    print("wrote " + ", ".join(os.path.join(args.out, n) for n in
                               ("results.json", "coverage.csv", "coverage.md",
                                "dashboard.html")))
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
