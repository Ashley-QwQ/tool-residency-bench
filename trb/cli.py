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
    """Sweep the reactivation cost and watch the policies change places.

    Reported as an **optimality gap** - each policy's cost divided by the
    rent-optimal cost at that same reactivation price. That normalisation is
    what makes the structure visible: the policies are not rivals scattered
    across a table, they are points on one continuum with two limits.

        D -> 0    the optimum is no-cache      (any idle turn costs more
                  than getting the tool back)
        D -> inf  the optimum is min-loads     (never pay to fetch twice)

    Everything in between is selective residency, and real agents live there.
    Classical miss minimisation is not a competing theory; it is the D -> inf
    regime of this one.
    """
    workloads = _load(args.workload)
    costs = [int(x) for x in args.discovery_range.split(",")]
    specs = args.policy or [
        "search-only", "ttl-20", "lru-8", "no-cache", "min-loads",
    ]

    for wl in workloads:
        print(f"\n### {wl.name} - optimality gap vs. cost of one reactivation\n")
        print("| D | rent-optimal | " + " | ".join(specs) + " |")
        print("|" + "|".join("---" for _ in range(len(specs) + 2)) + "|")
        for d in costs:
            cost = CostModel(discovery_tokens=d, search_turn=not args.no_search_turn)
            opt = run(wl, pol.RentOptimal(), cost).total_tokens
            cells = []
            for s in specs:
                total = run(wl, pol.build(s), cost).total_tokens
                ratio = total / opt if opt else float("inf")
                cells.append(f"**{ratio:.2f}x**" if ratio < 1.005 else f"{ratio:.2f}x")
            print(f"| {d:,} | {opt:,} | " + " | ".join(cells) + " |")
        print("\nBold = matches the optimum at that reactivation price.")


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
