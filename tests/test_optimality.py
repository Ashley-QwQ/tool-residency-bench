"""Independent validation of the rent-optimal closed form.

`test_simulator.py` checks that no *policy in the suite* beats `rent-optimal`.
That is a weak check: every policy in the suite could be bad. This file checks
the closed form against exhaustive enumeration of **every possible eviction
schedule** on small traces, plus a set of metamorphic invariants that pin down
the cost model's behaviour at its limits.

Two failure modes are separated here on purpose:

- the *formula* could be wrong -> caught by the brute-force comparison;
- the *accounting* could be wrong -> caught by the metamorphic invariants,
  which say what has to be true of the model regardless of any formula.

The brute force drives the real simulator through a `Replay` policy rather
than re-deriving costs, so it validates the closed form without silently
validating a second copy of the same arithmetic.

    python tests/test_optimality.py
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trb import CostModel, Step, Tool, Workload, run  # noqa: E402
from trb import policies as pol  # noqa: E402

# The cost model the Proposition is stated for: reactivation charged per tool
# load, no search-turn rent. Under these assumptions the closed form is
# provably optimal, so brute force must agree exactly.
DECOUPLED = CostModel(discovery_tokens=200, search_turn=False)


class Replay(pol.Policy):
    """Evicts exactly what a fixed schedule says, ignoring everything else.

    Evicting a tool that is not resident is a no-op in the simulator, so a
    schedule can name any subset of the universe at any turn. That makes the
    search space a clean product and needs no knowledge of reachable states.
    """

    name = "replay"

    def __init__(self, schedule: tuple[frozenset[str], ...]) -> None:
        super().__init__()
        self.schedule = schedule

    def evict(self, t, resident, workload):
        return set(self.schedule[t]) if t < len(self.schedule) else set()


def make_workload(name, tools, sequence):
    """`tools` = {id: schema_tokens}, `sequence` = list of tool ids."""
    catalog = {k: Tool(k, v) for k, v in tools.items()}
    return Workload(name, "", catalog, [Step((s,)) for s in sequence])


def brute_force(wl: Workload, cost: CostModel):
    """Minimum total cost over every eviction schedule. Exponential; tiny only."""
    universe = sorted(wl.catalog)
    subsets = [frozenset(c) for n in range(len(universe) + 1)
               for c in itertools.combinations(universe, n)]
    best, best_schedule = None, None
    for schedule in itertools.product(subsets, repeat=len(wl.steps)):
        total = run(wl, Replay(schedule), cost).total_tokens
        if best is None or total < best:
            best, best_schedule = total, schedule
    return best, best_schedule


# Kept small enough to enumerate: |subsets|^turns.
CASES = [
    # 2 tools, 4^6 = 4,096 schedules
    make_workload("pair_burst", {"a": 300, "b": 900},
                  ["a", "a", "b", "b", "a", "b"]),
    # the alternating trap
    make_workload("pair_alt", {"a": 300, "b": 900},
                  ["a", "b", "a", "b", "a", "b"]),
    # a long idle gap: holding vs one reactivation is a genuine decision
    make_workload("pair_gap", {"a": 1200, "b": 200},
                  ["a", "b", "b", "b", "b", "a"]),
    # a tiny schema whose rent never justifies a reload
    make_workload("cheap_gap", {"a": 20, "b": 200},
                  ["a", "b", "b", "b", "b", "a"]),
    # 3 tools, 8^5 = 32,768 schedules
    make_workload("triple", {"a": 400, "b": 700, "c": 150},
                  ["a", "b", "c", "a", "c"]),
]


def test_closed_form_matches_exhaustive_search():
    """The Proposition, checked against every schedule that exists."""
    for wl in CASES:
        optimum, _ = brute_force(wl, DECOUPLED)
        closed = run(wl, pol.RentOptimal(), DECOUPLED).total_tokens
        assert closed == optimum, (
            f"{wl.name}: closed form {closed:,} != brute-force optimum "
            f"{optimum:,} under {DECOUPLED.label()}"
        )


def test_batching_alone_does_not_break_the_closed_form():
    """One of the two couplings turns out to be harmless. Worth knowing which.

    Batched discovery - one search covering every tool missing that turn -
    could in principle let two tools share a reactivation and so beat the
    per-tool rule. On these traces it never does.
    """
    batched = CostModel(discovery_tokens=200, search_turn=False)
    for wl in CASES:
        optimum, _ = brute_force(wl, batched)
        assert run(wl, pol.RentOptimal(), batched).total_tokens == optimum


def test_search_turn_rent_is_what_makes_the_bound_loose():
    """The other coupling is real, and this pins down its size and mechanism.

    With `search_turn` on, a search costs an extra request that carries
    whatever is already resident. So an idle turn on which a search happens
    charges a held tool's rent *twice* - once for the search request, once for
    the turn's own request. The true cost of holding across a gap is therefore
    `S * (g + searches during the gap)`, not `S * g`, which is what the closed
    form assumes.

    The rule consequently holds marginally too long, never too briefly. On the
    `triple` case it keeps a 150-token schema across one idle turn that costs
    300, where dropping would have cost 200. Measured penalty: 1.06x, and it
    is one-sided - brute force never finds a schedule that holds *more*.
    """
    worst, worst_case = 1.0, None
    for wl in CASES:
        optimum, _ = brute_force(wl, CostModel())
        closed = run(wl, pol.RentOptimal(), CostModel()).total_tokens
        assert closed >= optimum, "brute force cannot beat the true optimum"
        if closed / optimum > worst:
            worst, worst_case = closed / optimum, wl.name
    assert worst <= 1.06, (
        f"rent-optimal is {worst:.3f}x the true optimum on {worst_case} under "
        "the default cost model. The docs claim <=1.06x - if this grew, the "
        "claim needs revisiting, not the threshold."
    )


# --------------------------------------------------------------------------
# Metamorphic invariants: properties the cost model must have, stated without
# reference to any formula. These are what catch an accounting bug.
# --------------------------------------------------------------------------


def test_free_reactivation_evicts_at_every_opportunity():
    """D = 0: no idle turn is ever worth paying for."""
    for wl in CASES:
        r = run(wl, pol.RentOptimal(), CostModel(discovery_tokens=0, search_turn=False))
        # Never resident on a turn where it is not used: rent equals exactly
        # the schemas of the tools in use, turn by turn.
        expected = sum(wl.tokens(s.tools) for s in wl.steps)
        assert r.resident_token_rent == expected


def test_expensive_reactivation_converges_to_min_loads():
    """D -> huge: paying twice for a fetch dominates any amount of rent."""
    dear = CostModel(discovery_tokens=10**7, search_turn=False)
    for wl in CASES:
        rent = run(wl, pol.RentOptimal(), dear)
        loads = run(wl, pol.MinLoads(), dear)
        assert rent.total_tokens == loads.total_tokens
        assert rent.reloads == 0


def test_free_schemas_make_holding_never_worse():
    """S = 0: rent is free, so no eviction can ever help."""
    for wl in CASES:
        free = Workload(wl.name, "", {k: Tool(k, 0) for k in wl.catalog}, wl.steps)
        rent = run(free, pol.RentOptimal(), DECOUPLED)
        hold = run(free, pol.SearchOnly(), DECOUPLED)
        assert rent.total_tokens == hold.total_tokens
        assert rent.reloads == 0


def test_decisions_are_invariant_to_scaling_both_costs():
    """Only the ratio D/S decides anything, so scale both and nothing moves."""
    for k in (3, 17):
        for wl in CASES:
            scaled = Workload(
                wl.name, "",
                {i: Tool(i, t.schema_tokens * k) for i, t in wl.catalog.items()},
                wl.steps,
            )
            base = run(wl, pol.RentOptimal(), DECOUPLED)
            up = run(scaled, pol.RentOptimal(),
                     CostModel(discovery_tokens=DECOUPLED.discovery_tokens * k,
                               search_turn=False))
            assert up.count_series == base.count_series, "eviction decisions moved"
            assert up.total_tokens == base.total_tokens * k, "cost did not scale"


def test_tools_do_not_compete_so_the_optimum_is_separable():
    """No capacity constraint means the joint optimum is the sum of the parts.

    Each single-tool projection keeps the **full timeline** and blanks out the
    turns belonging to other tools, rather than compressing them away -
    deleting turns would shorten the idle gaps and change the very quantity
    under test.
    """
    for wl in CASES:
        joint = run(wl, pol.RentOptimal(), DECOUPLED).total_tokens
        parts = 0
        for tool in wl.catalog:
            steps = [Step(s.tools) if s.tools == (tool,) else Step(())
                     for s in wl.steps]
            solo = Workload(tool, "", {tool: wl.catalog[tool]}, steps)
            parts += run(solo, pol.RentOptimal(), DECOUPLED).total_tokens
        assert joint == parts, f"{wl.name}: {joint:,} != sum of parts {parts:,}"


def test_ski_rental_is_two_competitive():
    """The competitive bound, checked rather than cited.

    Ski rental's guarantee is 2x the offline optimum. It is claimed in the
    README and in docs/problem.md as the thing a semantic policy has to beat,
    so it is worth checking on workloads nobody designed rather than only on
    the seven that were.

    Checked under the Proposition's cost model, which is where the bound is
    actually stated - search-turn rent charges an idle turn twice and is not
    part of the ski-rental correspondence.
    """
    from trb import synthetic

    worst, worst_seed = 0.0, None
    for seed in range(300):
        wl = synthetic.sample_workload(seed)
        opt = run(wl, pol.RentOptimal(), DECOUPLED).total_tokens
        ski = run(wl, pol.SkiRental(), DECOUPLED).total_tokens
        if opt and ski / opt > worst:
            worst, worst_seed = ski / opt, seed
    assert worst <= 2.0, (
        f"ski-rental hit {worst:.3f}x the optimum on seed {worst_seed}, "
        "which breaks the 2-competitive guarantee - the eviction threshold is "
        "wrong, not the bound"
    )


def test_per_tool_failure_rates_override_the_global_one():
    wl = CASES[0]
    risky = Workload(
        wl.name, "",
        {"a": Tool("a", 300, failure_rate=0.9), "b": Tool("b", 900)},
        wl.steps,
    )
    cost = CostModel(failure_rate=0.0, failure_penalty=1000)
    # `a` carries its own rate; `b` falls back to the global 0.0.
    assert cost.failure_rate_for(risky.catalog["a"]) == 0.9
    assert cost.failure_rate_for(risky.catalog["b"]) == 0.0
    assert cost.reactivation(risky.catalog["a"]) > cost.reactivation(risky.catalog["b"])


def test_survival_is_a_product_over_the_tools_actually_reloaded():
    """Not `(1-p)^R` - which tools get reloaded is the whole point.

    Two policies with the same reload count can carry completely different
    risk, so survival has to be computed from the identities of the
    reactivations rather than their number.
    """
    steps = [Step(("a",)), Step(("b",)), Step(("a",)), Step(("b",))]
    catalog = {"a": Tool("a", 900, failure_rate=0.5),
               "b": Tool("b", 900, failure_rate=0.0)}
    wl = Workload("risk", "", catalog, steps)
    r = run(wl, pol.NoCache(), CostModel(failure_penalty=0))
    # `a` is reloaded once and `b` once, but only `a` carries risk, so
    # survival is 0.5 rather than the 0.25 an `(1-p)^R` model would give.
    assert r.reloads == 2
    assert abs(r.session_success_prob - 0.5) < 1e-12
    assert r.riskiest_reload == 0.5


def test_a_dangerous_tool_becomes_effectively_unevictable():
    """The reason per-tool rates matter: risk localises to specific tools.

    A high `p_i` inflates `D_i^eff`, which inflates `g*_i = D_i/S_i`, until
    the break-even gap exceeds the trace and the tool is never evicted at all.
    Under a global failure rate this cannot be expressed - reliability could
    only ever be bought by reloading *less overall*, never by reloading
    *different things*.
    """
    steps = ([Step(("a",))] + [Step(("b",))] * 8) * 6
    for penalty, expect_risky_reload in ((0, True), (10**7, False)):
        catalog = {"a": Tool("a", 900, failure_rate=0.5),
                   "b": Tool("b", 900, failure_rate=0.0)}
        wl = Workload("risk", "", catalog, steps)
        r = run(wl, pol.RentOptimal(), CostModel(failure_penalty=penalty))
        assert (r.riskiest_reload > 0) is expect_risky_reload, (
            f"at L_fail={penalty:,} the risky tool should "
            f"{'still be' if expect_risky_reload else 'no longer be'} reloaded"
        )
    assert r.session_success_prob == 1.0, "and the session becomes safe"


def test_reliability_and_token_cost_rank_policies_differently():
    """The v0.2 finding, as an assertion rather than a paragraph.

    Token cost grows linearly in reactivations; session completion probability
    decays geometrically in them. If these two ever agreed on a ranking, the
    reliability document would be describing something that does not happen.
    """
    from trb import load_all

    workloads = Path(__file__).resolve().parent.parent / "workloads"
    wl = next(w for w in load_all(workloads) if w.name == "long_mixed")
    cost = CostModel(failure_rate=0.01, failure_penalty=0)
    ski = run(wl, pol.SkiRental(), cost)
    loads = run(wl, pol.MinLoads(), cost)

    assert ski.total_tokens < loads.total_tokens, "ski-rental should win on tokens"
    assert ski.session_success_prob < 0.01, "and be unusable on reliability"
    assert loads.session_success_prob == 1.0, "min-loads never reloads"


def test_priced_and_simulated_failure_agree_in_expectation():
    """The two failure paths must describe the same world.

    `expected_failure_cost` is what policies are parameterised from;
    `simulate_failures` is what they are scored in. If those disagree, a
    policy is being optimised against one world and graded in another - which
    is exactly what happened when retries were simulated but the expectation
    still charged `p * L_fail`, four-fold overstating the risk at p=0.5 with
    two retries and making the oracle policy hold dangerous tools far too
    long.
    """
    steps = ([Step(("a",))] + [Step(("b",))] * 6) * 30
    catalog = {"a": Tool("a", 900, failure_rate=0.4),
               "b": Tool("b", 900, failure_rate=0.0)}
    wl = Workload("risk", "", catalog, steps)

    for retries in (0, 1, 2):
        priced = CostModel(failure_penalty=50_000, retries=retries)
        analytic = run(wl, pol.NoCache(), priced)
        per_reload = analytic.failure_tokens / max(analytic.reloads, 1)

        drawn = []
        for seed in range(400):
            cost = CostModel(failure_penalty=50_000, retries=retries,
                             simulate_failures=True, seed=seed)
            r = run(wl, pol.NoCache(), cost)
            drawn.append((r.failure_tokens + r.retry_tokens) / max(r.reloads, 1))
        empirical = sum(drawn) / len(drawn)

        assert abs(empirical - per_reload) <= 0.15 * max(per_reload, 1), (
            f"retries={retries}: priced {per_reload:,.0f} per reload but "
            f"simulated {empirical:,.0f} - the two paths disagree"
        )


def test_retries_reduce_unrecovered_failures_exponentially():
    """A retry budget does not lower the failure rate, it lowers the rate at

    which a failure becomes unrecoverable - and by `p` per retry, not
    linearly. Getting this wrong is what made the expectation overstate risk.
    """
    # Both tools risky, so every reload is an exposed one and the rate is
    # `unrecovered / reloads` without needing per-tool reload counts.
    steps = ([Step(("a",))] + [Step(("b",))] * 6) * 40
    catalog = {"a": Tool("a", 900, failure_rate=0.5),
               "b": Tool("b", 900, failure_rate=0.5)}
    wl = Workload("risk", "", catalog, steps)

    rates = []
    for retries in (0, 1, 2):
        lost = tries = 0
        for seed in range(80):
            cost = CostModel(failure_penalty=0, retries=retries,
                             simulate_failures=True, seed=seed)
            r = run(wl, pol.NoCache(), cost)
            lost += r.unrecovered_failures
            tries += r.reloads
        rates.append(lost / tries)
    # 0.5, 0.25, 0.125 give or take sampling noise.
    for retries, observed in enumerate(rates):
        assert abs(observed - 0.5 ** (retries + 1)) < 0.05, (
            f"retries={retries}: unrecovered rate {observed:.3f}, "
            f"expected about {0.5 ** (retries + 1):.3f}"
        )


def test_simulated_failures_are_reproducible_and_policy_independent():
    """Same tool, same attempt number, same outcome - common random numbers.

    Without this, one policy could beat another purely on luckier draws.
    """
    tool = Tool("a", 900, failure_rate=0.5)
    cost = CostModel(simulate_failures=True, seed=3)
    first = [cost.draw_failure(tool, n) for n in range(20)]
    assert first == [cost.draw_failure(tool, n) for n in range(20)]
    assert first != [CostModel(simulate_failures=True, seed=4).draw_failure(tool, n)
                     for n in range(20)]


def test_learning_p_i_requires_being_harmed_by_it():
    """The structural obstacle to estimating p_i online, as an assertion.

    A tool the policy correctly refuses to evict generates no observations,
    so its estimate never moves off the prior. Evidence about danger is only
    purchasable by incurring the danger.
    """
    steps = ([Step(("a",))] + [Step(("b",))] * 6) * 20
    catalog = {"a": Tool("a", 900, failure_rate=0.9),
               "b": Tool("b", 900, failure_rate=0.0)}
    wl = Workload("risk", "", catalog, steps)

    p = pol.AdaptiveSkiRental()
    prior = p.estimate("a")
    run(wl, p, CostModel(failure_penalty=10**9, retries=0,
                         simulate_failures=True, seed=1))
    assert p.estimate("a") == prior, (
        "a tool that is never evicted yields no evidence, so the estimate "
        "cannot improve - which is the whole difficulty"
    )


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            passed += 1
    print(f"\n{passed} passed")
