"""Command line entry point.

    python -m trb run                      # everything, writes results/summary.md
    python -m trb run -w burst -p ttl-5
    python -m trb sweep -w late_reuse      # where does eviction stop paying?
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import policies as pol
from . import synthetic
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
        "`RTR` (Resident Token Rent) is the sum, over every turn, of the "
        "schema tokens resident on that turn. `total tokens` adds the one-off "
        "discovery, re-search and expected-failure costs on top. `opt gap` is "
        "the ratio to `rent-optimal`, the offline optimum for this objective.",
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
        "ski-rental", "min-loads", "rent-optimal",
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


def cmd_robustness(args) -> None:
    """Re-check every headline claim on workloads nobody designed.

    Each claim is stated as a proposition that can fail, evaluated
    independently on every sampled workload, and reported as the fraction of
    samples where it held plus the distribution of the underlying quantity. A
    claim that only survives on the committed traces should show up here as a
    number well below 100%.
    """
    cost = CostModel(discovery_tokens=args.discovery,
                     search_turn=not args.no_search_turn)
    ttl_grid = [pol.TTL(n) for n in (5, 10, 20, 50)]
    lru_grid = [pol.LRU(n) for n in (4, 8, 16, 32)]

    claims = {
        "search-only costs >2x the optimum (accumulation is real)": [],
        "min-loads costs >2x the optimum (wrong objective)": [],
        "best TTL beats best count cap (rent != capacity)": [],
        "ski-rental within 2x of the optimum (D/S is the right horizon)": [],
        "every *heuristic* is Pareto-dominated": [],
        "ski-rental reaches the Pareto frontier": [],
    }
    ratios = {"search-only": [], "min-loads": [], "ski-rental": [], "best-ttl": []}

    for seed in range(args.seeds):
        wl = synthetic.sample_workload(seed, args.catalog_size, args.turns)
        opt = run(wl, pol.RentOptimal(), cost)
        base = opt.total_tokens or 1

        search = run(wl, pol.SearchOnly(), cost)
        loads = run(wl, pol.MinLoads(), cost)
        ski = run(wl, pol.SkiRental(), cost)
        best_ttl = min((run(wl, p, cost) for p in ttl_grid), key=lambda r: r.total_tokens)
        best_lru = min((run(wl, p, cost) for p in lru_grid), key=lambda r: r.total_tokens)

        ratios["search-only"].append(search.total_tokens / base)
        ratios["min-loads"].append(loads.total_tokens / base)
        ratios["ski-rental"].append(ski.total_tokens / base)
        ratios["best-ttl"].append(best_ttl.total_tokens / base)

        claims["search-only costs >2x the optimum (accumulation is real)"].append(
            search.total_tokens > 2 * base)
        claims["min-loads costs >2x the optimum (wrong objective)"].append(
            loads.total_tokens > 2 * base)
        claims["best TTL beats best count cap (rent != capacity)"].append(
            best_ttl.total_tokens < best_lru.total_tokens)
        claims["ski-rental within 2x of the optimum (D/S is the right horizon)"].append(
            ski.total_tokens <= 2 * base)

        pts = [(r.policy, r.reloads, r.resident_token_rent) for r in
               (search, loads, ski, best_ttl, best_lru,
                run(wl, pol.Static(), cost), run(wl, pol.NoCache(), cost))]
        # The frontier is traced by the optimum at a range of prices, exactly
        # as `trb pareto` does. Comparing against a single optimum point would
        # understate it and make the heuristics look better than they are.
        for d in (0, 150, 1000, 5000, 20000, 100000):
            r = run(wl, pol.RentOptimal(),
                    CostModel(discovery_tokens=d, search_turn=cost.search_turn))
            pts.append((f"opt@{d}", r.reloads, r.resident_token_rent))
        front = pareto_front(pts)
        heuristics = {"search-only", "no-cache", "static",
                      best_ttl.policy, best_lru.policy}
        claims["every *heuristic* is Pareto-dominated"].append(
            not (front & heuristics))
        claims["ski-rental reaches the Pareto frontier"].append(
            "ski-rental" in front)

    def pct(v):
        return 100.0 * sum(v) / len(v) if v else 0.0

    def quart(v):
        s = sorted(v)
        return s[len(s) // 4], s[len(s) // 2], s[3 * len(s) // 4]

    print(f"\n## Robustness over {args.seeds} randomly sampled workloads\n")
    print(f"Cost model: {cost.label()}. Catalogs up to 1,000 tools, traces up "
          "to 1,500 turns, random phase structure, burstiness, recurrence and "
          "long-tail rate. Seeds 0..N, fully reproducible.\n")
    print("| claim | holds on |")
    print("|---|---|")
    for name, vals in claims.items():
        print(f"| {name} | **{pct(vals):.1f}%** of samples |")

    print("\n| cost relative to rent-optimal | p25 | median | p75 |")
    print("|---|---|---|---|")
    for name, vals in ratios.items():
        a, b, c = quart(vals)
        print(f"| {name} | {a:.2f}x | **{b:.2f}x** | {c:.2f}x |")


def cmd_reliability(args) -> None:
    """v0.2: what happens once reactivation is allowed to fail.

    Two grids, because failure has two effects that behave nothing alike.

    As an **expected token cost** it is linear, so it folds into `D_eff` and
    changes nothing structural - the first grid is really the reactivation
    sweep wearing a different hat, and saying so is more useful than dressing
    it up as a new phenomenon.

    As **session reliability** it is geometric: surviving `R` reactivations at
    failure rate `p` has probability `(1-p)^R`. Token accounting cannot see
    this at all. A policy reloading 912 times at p=0.01 has a 0.01% chance of
    getting through the session untouched, while its expected token cost still
    looks like the best number in the table.

    The second grid therefore asks a different question: cheapest policy that
    still completes the session with probability >= the floor. That is where
    "retrieval reliability sets the ceiling on eviction aggressiveness" stops
    being a slogan and becomes a boundary you can point at.
    """
    workloads = _load(args.workload)
    ps = [float(x) for x in args.failure_rates.split(",")]
    ls = [int(x) for x in args.failure_penalties.split(",")]
    specs = args.policy or [
        "search-only", "ttl-20", "ttl-5", "lru-8", "ski-rental",
        "no-cache", "min-loads",
    ]
    for wl in workloads:
        print(f"\n### {wl.name} - failure profile: {args.failure_profile}\n")
        for floor in (None, args.reliability_floor):
            if floor is None:
                print("**Cheapest by expected tokens** (reliability ignored)\n")
            else:
                print(f"\n**Cheapest with P(session completes) >= {floor:.0%}**\n")
            print("| p_fail \\ L_fail | " + " | ".join(f"{x:,}" for x in ls) + " |")
            print("|" + "|".join("---" for _ in range(len(ls) + 1)) + "|")
            for p in ps:
                cells = []
                for L in ls:
                    cost = CostModel(discovery_tokens=args.discovery,
                                     search_turn=not args.no_search_turn,
                                     failure_rate=p, failure_penalty=L)
                    shaped = (wl if args.failure_profile == "uniform"
                              else synthetic.apply_failure_profile(
                                  wl, args.failure_profile, p))
                    rs = [run(shaped, pol.build(s), cost) for s in specs]
                    if floor is not None:
                        ok = [r for r in rs if r.session_success_prob >= floor]
                        if not ok:
                            cells.append("_none_")
                            continue
                        rs = ok
                    best = min(rs, key=lambda r: r.total_tokens)
                    cells.append(best.policy)
                print(f"| {p:g} | " + " | ".join(cells) + " |")
        print()
        cost = CostModel(discovery_tokens=args.discovery, failure_rate=0.01,
                         failure_penalty=args.exposure_penalty)
        shaped = (wl if args.failure_profile == "uniform"
                  else synthetic.apply_failure_profile(wl, args.failure_profile, 0.01))
        print(f"Reactivation exposure at mean p_fail=0.01, "
              f"L_fail={args.exposure_penalty:,} (why the two grids differ):\n")
        print("| policy | reactivations | riskiest tool reloaded | "
              "P(session completes) | rent |")
        print("|---|---|---|---|---|")
        for s in specs:
            r = run(shaped, pol.build(s), cost)
            print(f"| {s} | {r.reloads:,} | p={r.riskiest_reload:.3g} | "
                  f"{r.session_success_prob:.1%} | {r.resident_token_rent:,} |")


def cmd_failures(args) -> None:
    """Draw failures instead of pricing them, and try to *learn* p_i.

    v0.2 charged the expectation of a failure. This enacts it: each attempt
    is drawn, a failed one is retried up to `--retries` times, and only an
    exhausted retry budget counts as an unrecovered failure. Draws are keyed
    on `(seed, tool, attempt)` so every policy meets the same outcome for the
    same tool - common random numbers, which matters because the quantity
    under study is exactly *which* tools a policy chooses to reload.

    `adaptive-ski` is the same rule with `p_i` estimated from what it has
    actually observed rather than handed to it, which is the question v0.2
    left open: is `p_i` learnable in-session?
    """
    workloads = _load(args.workload)
    specs = args.policy or [
        "search-only", "ttl-20", "ski-rental", "adaptive-ski", "min-loads",
    ]
    for wl in workloads:
        shaped = (wl if args.failure_profile == "uniform"
                  else synthetic.apply_failure_profile(
                      wl, args.failure_profile, args.failure_rate))
        print(f"\n### {wl.name} - simulated failures, profile "
              f"{args.failure_profile}, {args.seeds} seeds, "
              f"retries={args.retries}, L_fail={args.failure_penalty:,}\n")
        print("| policy | mean total tokens | mean unrecovered failures | "
              "mean reloads | clean sessions |")
        print("|---|---|---|---|---|")
        for s in specs:
            totals, unrec, reloads, clean = [], [], [], 0
            for seed in range(args.seeds):
                cost = CostModel(
                    discovery_tokens=args.discovery,
                    search_turn=not args.no_search_turn,
                    failure_rate=args.failure_rate,
                    failure_penalty=args.failure_penalty,
                    simulate_failures=True, retries=args.retries, seed=seed)
                r = run(shaped, pol.build(s), cost)
                totals.append(r.total_tokens)
                unrec.append(r.unrecovered_failures)
                reloads.append(r.reloads)
                clean += r.completed
            n = len(totals)
            print(f"| {s} | {sum(totals)/n:,.0f} | {sum(unrec)/n:.2f} | "
                  f"{sum(reloads)/n:.0f} | {clean}/{n} |")
        print("\nTokens and unrecovered failures are two axes, not one. A "
              "policy that is cheaper *and* fails more has moved along the "
              "trade-off, not beaten it.")


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

    rb = sub.add_parser("robustness", parents=[common],
                        help="re-check the claims on randomly sampled workloads")
    rb.add_argument("--seeds", type=int, default=200)
    rb.add_argument("--discovery", type=int, default=150)
    rb.add_argument("--catalog-size", type=int, default=None,
                    help="fix the catalog size instead of sampling it")
    rb.add_argument("--turns", type=int, default=None,
                    help="fix the trace length instead of sampling it")
    rb.set_defaults(func=cmd_robustness)

    rel = sub.add_parser("reliability", parents=[common],
                         help="v0.2: policy choice once reactivation can fail")
    rel.add_argument("--discovery", type=int, default=150)
    rel.add_argument("--failure-rates", default="0,0.001,0.01,0.05,0.1")
    rel.add_argument("--failure-penalties", default="0,1000,10000,100000")
    rel.add_argument("--reliability-floor", type=float, default=0.95)
    rel.add_argument("--exposure-penalty", type=int, default=10000,
                     help="L_fail used for the exposure table at the bottom")
    rel.add_argument("--failure-profile", default="uniform",
                     choices=list(synthetic.FAILURE_PROFILES),
                     help="how the mean failure rate is spread across tools")
    rel.set_defaults(func=cmd_reliability)

    fl = sub.add_parser("failures", parents=[common],
                        help="simulate failures and retries; try to learn p_i")
    fl.add_argument("--discovery", type=int, default=150)
    fl.add_argument("--failure-rate", type=float, default=0.01)
    fl.add_argument("--failure-penalty", type=int, default=100000)
    fl.add_argument("--retries", type=int, default=2)
    fl.add_argument("--seeds", type=int, default=40)
    fl.add_argument("--failure-profile", default="persistent",
                    choices=list(synthetic.FAILURE_PROFILES))
    fl.set_defaults(func=cmd_failures)

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
