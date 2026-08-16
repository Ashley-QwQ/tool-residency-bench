"""Invariants the simulator must satisfy.

These are properties, not golden numbers: a benchmark whose tests only pin
its own output cannot tell you it is wrong.

    python -m pytest tests/          (or: python tests/test_simulator.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trb import CostModel, load_all, load_catalog, load_workload, run  # noqa: E402
from trb import policies as pol  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORKLOADS = ROOT / "workloads"

ALL = load_all(WORKLOADS)
FREE = CostModel(discovery_tokens=0, search_turn=False)


def test_static_never_searches():
    for wl in ALL:
        r = run(wl, pol.Static(), FREE)
        assert r.searches == 0 and r.loads == 0 and r.misses == 0
        # A flat line at the full catalog for the whole session.
        assert set(r.series) == {wl.catalog_tokens}


def test_search_only_is_monotonic():
    """The central claim of the repo, asserted as code."""
    for wl in ALL:
        r = run(wl, pol.SearchOnly(), FREE)
        assert r.evictions == 0
        assert r.reloads == 0, "never evicts, so can never reload"
        assert all(b >= a for a, b in zip(r.count_series, r.count_series[1:])), (
            f"{wl.name}: resident set decreased under a never-evict policy"
        )
        # Each distinct tool is loaded exactly once.
        assert r.loads == len(wl.used_tools())


def test_search_only_never_exceeds_static():
    """Lazy loading is always at least as good as eager loading on rent."""
    for wl in ALL:
        lazy = run(wl, pol.SearchOnly(), FREE)
        eager = run(wl, pol.Static(), FREE)
        assert lazy.resident_token_turns <= eager.resident_token_turns


def test_evicting_policies_are_subsets_of_search_only():
    """Any policy that only ever removes tools must hold less rent.

    This is what makes the comparison fair: TTL/LRU/oracle see exactly the
    same admissions as search-only and differ *only* in what they drop.
    """
    for wl in ALL:
        base = run(wl, pol.SearchOnly(), FREE)
        for p in (pol.TTL(5), pol.TTL(20), pol.LRU(8), pol.Oracle(16),
                  pol.NoCache(), pol.RentOptimal()):
            r = run(wl, p, FREE)
            assert r.resident_token_turns <= base.resident_token_turns, (
                f"{wl.name}/{p.name} held more rent than never evicting"
            )


def test_min_loads_is_load_optimal():
    """MIN drops only what is never needed again, so it is provably

    load-optimal: every tool is fetched exactly once, which no policy can
    beat. It is the best possible policy under the classical miss-count
    objective - which is the whole point of it losing on tokens.
    """
    for wl in ALL:
        r = run(wl, pol.MinLoads(), FREE)
        assert r.reloads == 0, f"{wl.name}: MIN evicted something still needed"
        assert r.loads == len(wl.used_tools())
        for p in pol.default_policies():
            if isinstance(p, pol.Static):
                continue  # loads nothing because it pre-pays for everything
            assert run(wl, p, FREE).loads >= r.loads, "nothing can load less than MIN"


def test_rent_optimal_dominates_every_other_policy():
    """The offline optimum for *this* objective must not lose to anything.

    This is the assertion that keeps the two optima honest. `min-loads` is
    optimal for miss count; `rent-optimal` is optimal for rent + reactivation.
    If a heuristic ever beat rent-optimal on total tokens, the closed form in
    RentOptimal would be wrong.
    """
    for cost in (CostModel(), CostModel(discovery_tokens=1000), FREE):
        for wl in ALL:
            best = run(wl, pol.RentOptimal(), cost)
            for p in pol.default_policies():
                r = run(wl, p, cost)
                assert r.total_tokens >= best.total_tokens, (
                    f"{wl.name}: {p.name} beat rent-optimal "
                    f"({r.total_tokens:,} < {best.total_tokens:,}) at {cost.label()}"
                )


def test_the_two_optima_optimise_different_things():
    """The headline finding, asserted rather than asserted-in-prose.

    Load-optimal is not rent-optimal, and on a long trace the gap is an order
    of magnitude. If these two ever converged, the repo's central claim -
    that residency is a rental problem and not a capacity problem - would be
    empty.
    """
    wl = next(w for w in ALL if w.name == "long_mixed")
    loads = run(wl, pol.MinLoads(), CostModel())
    rent = run(wl, pol.RentOptimal(), CostModel())
    assert loads.loads < rent.loads, "MIN should fetch less"
    assert loads.total_tokens > 10 * rent.total_tokens, "and pay far more for it"


def test_no_cache_thrashes_on_alternating():
    wl = next(w for w in ALL if w.name == "alternating")
    r = run(wl, pol.NoCache(), FREE)
    assert r.hit_rate == 0.0, "evicting on last use should miss every turn"
    assert r.thrash_rate > 0.9


def test_working_set_policies_are_free_on_a_short_trace():
    """A plain working set must not charge anything on a task that ends first.

    ttl-5 and lru-8 never reach their thresholds inside three turns, so they
    have to be byte-for-byte identical to never evicting. If they are not,
    the policy is doing work it was not asked to do.
    """
    wl = next(w for w in ALL if w.name == "short")
    base = run(wl, pol.SearchOnly(), CostModel())
    for p in (pol.TTL(5), pol.LRU(8)):
        assert run(wl, p, CostModel()).total_tokens == base.total_tokens


def test_headroom_is_what_scales_with_task_length_not_policy_cleverness():
    """The gating question is how much there is to win, not who wins.

    On the 3-turn trace even a clairvoyant policy saves less than one search
    round trip - which is why running lifecycle machinery there is a loss no
    matter how good the machinery is. On the long trace the same policy saves
    two orders of magnitude more. Same policies, same code; only the headroom
    moved.
    """
    def headroom(name: str) -> int:
        wl = next(w for w in ALL if w.name == name)
        base = run(wl, pol.SearchOnly(), CostModel())
        best = run(wl, pol.RentOptimal(), CostModel())
        return base.total_tokens - best.total_tokens

    short, long = headroom("short"), headroom("long_mixed")
    assert short < 3_000, f"expected negligible headroom on a 3-turn task, got {short:,}"
    assert long > 1_000_000, f"expected large headroom on a long task, got {long:,}"
    assert long > 1_000 * short


def test_every_required_tool_is_resident_when_used():
    """Correctness floor: a policy may not make a needed tool unavailable."""
    for wl in ALL:
        for p in pol.default_policies():
            r = run(wl, p, FREE)
            assert r.hits + r.misses == sum(len(s.tools) for s in wl.steps)


def test_cost_model_knobs_move_the_answer():
    """A free re-search favours eviction; an expensive one favours holding."""
    wl = next(w for w in ALL if w.name == "late_reuse")
    cheap = run(wl, pol.TTL(5), CostModel(discovery_tokens=0, search_turn=False))
    dear = run(wl, pol.TTL(5), CostModel(discovery_tokens=5000, search_turn=True))
    assert dear.total_tokens > cheap.total_tokens


def test_catalog_matches_workload_references():
    catalog = load_catalog(WORKLOADS / "catalog.json")
    for path in sorted(WORKLOADS.glob("*.json")):
        if path.name == "catalog.json":
            continue
        load_workload(path, catalog)  # raises KeyError on an unknown tool


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            passed += 1
    print(f"\n{passed} passed")
