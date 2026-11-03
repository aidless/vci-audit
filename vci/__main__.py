"""Command line entry point.

    python -m vci audit --families all --out outputs/
    python -m vci list-families
    python -m vci annotate --per-family 2 --out annotations/blind.csv
    python -m vci selfcheck
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
        labels_path=args.labels,
        keep_raw=True, work_dir=args.work,
    )
    report.write_all(payload, args.out)
    s = payload["summary"]
    print(f"families={s['n_families']}  candidates={s['n_candidates']}  "
          f"median VCI={s['vci_median']:.3f} "
          f"[{s['vci_median_ci'][0]:.3f}-{s['vci_median_ci'][1]:.3f}]  "
          f">=0.70: {s['families_ge_0.7']}/{s['n_families']}  "
          f"reliable: {s['families_reliable']}/{s['n_families']} "
          f"(kappa source: {s['kappa_pooled']['source']})")
    if not s["kappa_pooled"]["human"]["n"]:
        print("note: no human annotation sheet found; kappa is measured against the "
              "mutant generator and is therefore an upper bound. Run "
              "'python -m vci annotate' to emit a blind sheet.", file=sys.stderr)
    print(f"wrote {args.out}/results.json, coverage.csv, coverage.md, dashboard.html")
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


def cmd_score(args):
    """Recompute kappa only, from an existing results.json plus a label sheet."""
    import json
    labels = audit._load_labels(args.labels)
    if not labels:
        print(f"no labels found in {args.labels}", file=sys.stderr)
        return 2
    with open(os.path.join(args.out, "results.json"), encoding="utf-8") as fh:
        payload = json.load(fh)
    from . import metrics as M
    scored = []
    for r in payload["families"]:
        fam = registry.by_name(r["family"])
        groups = audit.collect(fam, payload["manifest"]["n_tasks"],
                               audit.family_seed(payload["manifest"]["seed"],
                                                 registry.INDEX[fam.name]))
        scored += [(labels[x["cand_id"]], x["passed"]) for g in groups
                   for x in g["records"] if x["cand_id"] in labels]
    k, po = M.cohen_kappa([a for a, _ in scored], [b for _, b in scored])
    print(f"rows={len(scored)}  kappa={k:.3f}  observed agreement={po:.3f}")
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
    a.set_defaults(fn=cmd_audit)

    l = sub.add_parser("list-families", help="print the registry")
    l.set_defaults(fn=cmd_list)

    n = sub.add_parser("annotate", help="emit a blind human-adjudication sheet")
    _add_common(n)
    n.add_argument("--out", default="annotations/blind.csv")
    n.add_argument("--per-family", type=int, default=2, dest="per_family")
    n.add_argument("--limit", type=int, default=0, help="0 = no limit")
    n.set_defaults(fn=cmd_annotate)

    s = sub.add_parser("selfcheck", help="find mutants that contradict their own label")
    _add_common(s)
    s.set_defaults(fn=cmd_selfcheck)

    c = sub.add_parser("score-annotations", help="recompute kappa from labels")
    c.add_argument("--labels", default="annotations/labels.csv")
    c.add_argument("--out", default="outputs")
    c.set_defaults(fn=cmd_score)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
