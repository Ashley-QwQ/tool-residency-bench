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
from .report import curve, pareto_front, scatter, table, workload_section
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


def cmd_pareto(args) -> None:
    """The trade-off itself, before any exchange rate is chosen.

    `run` and `sweep` both reduce two quantities to one by picking a price for
    a reactivation. That is a modelling choice, and a reader is entitled to
    disagree with it. This command declines to make it: it plots residency
    rent against reactivations directly and marks the Pareto frontier.

    `D` then has no role except to say *where on the frontier* a given
    deployment wants to sit. The claim the repo actually needs - that rent and
    reactivations trade off against each other measurably, and that
    `search-only` is not on the frontier at all on long traces - survives any
    disagreement about the price.
    """
    workloads = _load(args.workload)
    cost = CostModel(discovery_tokens=args.discovery,
                     search_turn=not args.no_search_turn)
    specs = args.policy or [
        "static", "search-only", "ttl-20", "ttl-5", "lru-8", "no-cache",
        "min-loads", "rent-optimal",
    ]
    trace = [int(x) for x in args.trace_discovery.split(",")] if args.trace_discovery else []

    for wl in workloads:
        points = []
        for s in specs:
            r = run(wl, pol.build(s), cost)
            points.append((s, r.reloads, r.resident_token_rent))
        # The optimum at a range of prices is one curve, sampled - it traces
        # out the frontier rather than contributing separate policies.
        curve_pts = []
        for d in trace:
            r = run(wl, pol.RentOptimal(),
                    CostModel(discovery_tokens=d, search_turn=not args.no_search_turn))
            curve_pts.append((f"opt@D={d:,}", r.reloads, r.resident_token_rent))

        front = pareto_front(points + curve_pts)
        print(f"\n### {wl.name} - residency rent vs. reactivations\n")
        print("| policy | reactivations | rent (token-turns) | on frontier |")
        print("|---|---|---|---|")
        for name, x, y in points + curve_pts:
            print(f"| {name} | {x:,} | {y:,} | {'**yes**' if name in front else 'dominated'} |")
        dominated = [n for n, _, _ in points if n not in front]
        print(f"\nDominated outright: {', '.join(dominated) if dominated else 'none'}. "
              "A dominated policy cannot be rescued by any exchange rate between "
              "the two axes - something else is cheaper on both.")
        print()
        print("```text")
        print(scatter(points, curve_pts))
        print("```")


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

    p = sub.add_parser("pareto", parents=[common],
                       help="rent vs. reactivations, with no exchange rate assumed")
    p.add_argument("--discovery", type=int, default=150,
                   help="only affects which point each policy lands on, not the axes")
    p.add_argument("--trace-discovery", default="0,150,1000,5000,20000,100000",
                   help="prices at which to place rent-optimal, tracing the frontier")
    p.set_defaults(func=cmd_pareto)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
