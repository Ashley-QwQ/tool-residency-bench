"""Command line entry point.

    python -m trb run                      # everything, writes results/summary.md
    python -m trb run -w burst -p ttl-5
    python -m trb sweep -w late_reuse      # where does eviction stop paying?
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import policies as pol
from .model import CostModel, load_all, load_catalog, load_workload
from .report import curve, table, workload_section
from .simulator import run

ROOT = Path(__file__).resolve().parent.parent
WORKLOADS = ROOT / "workloads"
RESULTS = ROOT / "results"

# `static` is deliberately left out of the curves: it is a flat line at the
# full catalog size and rescales the plot so hard that everything else becomes
# unreadable. Its number is in the table.
CURVE_POLICIES = ["search-only", "ttl-20", "ttl-5", "rent-optimal"]


def _load(names: list[str] | None):
    catalog = load_catalog(WORKLOADS / "catalog.json")
    if not names:
        return load_all(WORKLOADS)
    return [load_workload(WORKLOADS / f"{n}.json", catalog) for n in names]


def _policies(specs: list[str] | None):
    if not specs:
        return pol.default_policies()
    return [pol.build(s) for s in specs]


def cmd_run(args) -> None:
    workloads = _load(args.workload)
    cost = CostModel(discovery_tokens=args.discovery, search_turn=not args.no_search_turn)

    sections = [
        "# Results",
        "",
        f"Cost model: {cost.label()}. "
        "`token-turns` is the sum, over every turn, of the schema tokens "
        "resident on that turn. `total tokens` adds the one-off discovery and "
        "re-search costs on top.",
        "",
    ]
    for wl in workloads:
        results = [run(wl, p, cost) for p in _policies(args.policy)]
        section = workload_section(wl, results, CURVE_POLICIES)
        sections.append(section)
        print(section)

    if args.out:
        RESULTS.mkdir(exist_ok=True)
        path = RESULTS / args.out
        path.write_text("\n".join(sections), encoding="utf-8")
        print(f"\nwrote {path.relative_to(ROOT)}")


def cmd_sweep(args) -> None:
    """Sweep the discovery cost and watch the ranking change.

    The point: whether eviction pays is not a property of the policy, it is a
    property of the ratio between schema size and re-search cost. A benchmark
    that reports one number for that ratio is hiding the interesting part.
    """
    workloads = _load(args.workload)
    costs = [int(x) for x in args.discovery_range.split(",")]

    for wl in workloads:
        print(f"\n### {wl.name} - total tool tokens vs. cost of one re-search\n")
        specs = args.policy or [
            "search-only", "ttl-20", "no-cache", "min-loads", "rent-optimal",
        ]
        header = "| discovery cost | " + " | ".join(specs) + " | best |"
        print(header)
        print("|" + "|".join("---" for _ in range(len(specs) + 2)) + "|")
        for d in costs:
            cost = CostModel(discovery_tokens=d, search_turn=not args.no_search_turn)
            totals = {s: run(wl, pol.build(s), cost).total_tokens for s in specs}
            best = min(totals, key=totals.get)
            cells = " | ".join(f"{totals[s]:,}" for s in specs)
            print(f"| {d:,} | {cells} | **{best}** |")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="trb", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-w", "--workload", action="append",
                        help="workload name; repeatable; default all")
    common.add_argument("-p", "--policy", action="append",
                        help="policy spec e.g. ttl-5, lru-8, oracle-16; default all")
    common.add_argument("--no-search-turn", action="store_true",
                        help="do not charge an extra request for a re-search")

    r = sub.add_parser("run", parents=[common], help="run the matrix")
    r.add_argument("--discovery", type=int, default=150,
                   help="tokens charged per search round trip (default 150)")
    r.add_argument("--out", default="summary.md", help="file under results/, or '' to skip")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("sweep", parents=[common], help="sweep the discovery cost")
    s.add_argument("--discovery-range", default="0,150,1000,5000,20000,100000")
    s.set_defaults(func=cmd_sweep)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
