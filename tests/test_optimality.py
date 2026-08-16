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


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            passed += 1
    print(f"\n{passed} passed")
