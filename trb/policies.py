"""Residency policies.

A policy answers exactly one question: *given that the right tool has already
been found and loaded, when should it stop being resident?*

It never answers "which tool do I need" - the simulator hands that over for
free (perfect oracle discovery). That separation is the experiment.
"""

from __future__ import annotations

from typing import Iterable

from .model import CostModel, Workload


def next_use_table(workload: Workload) -> list[dict[str, int]]:
    """`table[t][tool]` = the first turn >= t at which `tool` is needed.

    Only the offline policies use this. They are bounds, not proposals.
    """
    nxt: dict[str, int] = {}
    table: list[dict[str, int]] = [{}] * len(workload.steps)
    for t in range(len(workload.steps) - 1, -1, -1):
        for tool in workload.steps[t].tools:
            nxt[tool] = t
        table[t] = dict(nxt)
    return table


class Policy:
    """Base class. Default behaviour is search-only: admit, never evict."""

    name = "policy"

    def start(self, workload: Workload, cost: CostModel) -> set[str]:
        """Tools resident before turn 0. Free of charge (preconfigured)."""
        return set()

    def evict(self, t: int, resident: set[str], workload: Workload) -> set[str]:
        """Called after turn `t` has been served. Return tools to drop.

        `resident` includes whatever was just used at turn `t`.
        """
        return set()

    # Bookkeeping the simulator feeds in; most policies only need last_use.
    def observe(self, t: int, used: Iterable[str]) -> None:
        for tool in used:
            self._last_use[tool] = t

    def __init__(self) -> None:
        self._last_use: dict[str, int] = {}


class Static(Policy):
    """The default of most harnesses today: the whole catalog, always.

    No search, no misses, no eviction. Its cost is a flat line at
    `catalog_tokens` for the entire session, which is exactly what makes it a
    useful ceiling.
    """

    name = "static"

    def start(self, workload: Workload, cost: CostModel) -> set[str]:
        return set(workload.catalog)


class SearchOnly(Policy):
    """Load on demand, never unload. Monotonic lazy loading.

    This is the shape of every shipped tool-search implementation the README
    surveys. It is the central baseline of this repo: it has *perfect*
    discovery here, and still accumulates.
    """

    name = "search-only"


class NoCache(Policy):
    """Evict everything not needed at this exact turn.

    The naive opposite of search-only, included to show that aggressive
    eviction is not free - on an alternating trace it thrashes.
    """

    name = "no-cache"

    def evict(self, t: int, resident: set[str], workload: Workload) -> set[str]:
        return {x for x in resident if self._last_use.get(x) != t}


class TTL(Policy):
    """Denning's working set: keep whatever was used in the last tau turns."""

    def __init__(self, tau: int = 10) -> None:
        super().__init__()
        self.tau = tau
        self.name = f"ttl-{tau}"

    def evict(self, t: int, resident: set[str], workload: Workload) -> set[str]:
        return {x for x in resident if t - self._last_use.get(x, -(10**9)) > self.tau}


class LRU(Policy):
    """Capacity-bounded LRU: at most `capacity` tools resident.

    Bounds tool *count* rather than tokens, because the count is what the
    30-50 tool selection-accuracy ceiling is expressed in.
    """

    def __init__(self, capacity: int = 8) -> None:
        super().__init__()
        self.capacity = capacity
        self.name = f"lru-{capacity}"

    def evict(self, t: int, resident: set[str], workload: Workload) -> set[str]:
        if len(resident) <= self.capacity:
            return set()
        ranked = sorted(resident, key=lambda x: self._last_use.get(x, -(10**9)))
        return set(ranked[: len(resident) - self.capacity])


# ---------------------------------------------------------------------------
# Offline bounds. All three read the future of the trace, so none of them is
# implementable in a real agent, and none is a proposal. They exist to answer
# "how much is there to win, and under which objective", which has to be
# settled before anyone builds a real policy. Keeping three of them apart
# matters: they optimise *different things*, and conflating them is exactly
# the mistake this repo is about.
# ---------------------------------------------------------------------------


class Oracle(Policy):
    """Fixed-horizon lookahead: evict what is not needed within H turns.

    A heuristic that happens to be given the future - not an optimum. H is an
    arbitrary constant, and `rent-optimal` below beats it.
    """

    def __init__(self, horizon: int = 16) -> None:
        super().__init__()
        self.horizon = horizon
        self.name = f"oracle-{horizon}"
        self._next: list[dict[str, int]] = []

    def start(self, workload: Workload, cost: CostModel) -> set[str]:
        self._next = next_use_table(workload)
        return set()

    def evict(self, t: int, resident: set[str], workload: Workload) -> set[str]:
        if t + 1 >= len(self._next):
            return set()  # session is over; evicting now saves nothing
        upcoming = self._next[t + 1]
        return {
            x
            for x in resident
            if x not in upcoming or upcoming[x] - t > self.horizon
        }


class MinLoads(Policy):
    """Belady's MIN: never evict anything that is ever needed again.

    Unbounded capacity, so it evicts eagerly the moment a tool has no future
    use at all. That makes it **load-optimal**: every tool is loaded exactly
    once, which is the minimum any policy can achieve. It is the best possible
    policy under the classical objective.

    It is *not* the best policy under this benchmark's objective, and it is
    not close. That is the finding, not a defect: MIN minimises misses, and
    misses are not what a context window charges for. Named `min-loads` rather
    than `belady-min` so nobody reads it as "the omniscient optimum" - the
    omniscient optimum for *this* objective is `rent-optimal`.
    """

    name = "min-loads"

    def __init__(self) -> None:
        super().__init__()
        self._next: list[dict[str, int]] = []

    def start(self, workload: Workload, cost: CostModel) -> set[str]:
        self._next = next_use_table(workload)
        return set()

    def evict(self, t: int, resident: set[str], workload: Workload) -> set[str]:
        if t + 1 >= len(self._next):
            return set()
        upcoming = self._next[t + 1]
        return {x for x in resident if x not in upcoming}


class RentOptimal(Policy):
    """Offline optimum for the rental objective: rent + reactivation.

    Unlike capacity-constrained caching, there is no capacity here - tools do
    not compete for slots - so the decision decomposes per tool, per idle gap,
    and the optimum is a closed form rather than a search:

        after a use at turn t with the next use at turn n,
        holding costs   S * (n - t - 1)   (rent for every idle turn)
        dropping costs  D                 (one re-search)
        so hold iff     S * (n - t - 1) <= D

    Note what this says: the break-even idle gap is `D / S` turns, which for a
    700-token schema and a 150-token search is *under one turn*. The rental
    arithmetic really is that lopsided, and any reason to hold longer has to
    come from somewhere the token model cannot see - latency, or the risk that
    re-search fails.

    Exactness: this is provably optimal when discovery is charged per tool
    load and there is no search-turn rent. Under the defaults both of those
    couple tools together - a turn that reloads two tools pays one search, and
    a search turn pays rent on everything already resident - so with those on
    it is a very tight bound rather than a proven optimum. Both couplings make
    eviction *cheaper* than this rule assumes, so it errs toward holding.
    """

    name = "rent-optimal"

    def __init__(self) -> None:
        super().__init__()
        self._next: list[dict[str, int]] = []
        self._discovery = 0

    def start(self, workload: Workload, cost: CostModel) -> set[str]:
        self._next = next_use_table(workload)
        self._discovery = cost.discovery_tokens
        return set()

    def evict(self, t: int, resident: set[str], workload: Workload) -> set[str]:
        if t + 1 >= len(self._next):
            return set()
        upcoming = self._next[t + 1]
        drop = set()
        for x in resident:
            if x not in upcoming:
                drop.add(x)
                continue
            idle = upcoming[x] - t - 1
            if workload.catalog[x].schema_tokens * idle > self._discovery:
                drop.add(x)
        return drop


def default_policies() -> list[Policy]:
    """The v1 baseline set: implementable policies first, then the bounds."""
    return [
        Static(),
        SearchOnly(),
        TTL(20),
        TTL(5),
        LRU(8),
        NoCache(),
        Oracle(16),
        MinLoads(),
        RentOptimal(),
    ]


ALIASES = {
    "search-only": "search",
    "no-cache": "nocache",
    "min-loads": "minloads",
    "belady-min": "minloads",
    "belady": "minloads",
    "rent-optimal": "rentoptimal",
    "optimal": "rentoptimal",
}


def build(spec: str) -> Policy:
    """Parse a policy spec like `ttl-5`, `lru-8`, `oracle-16`, `static`."""
    spec = ALIASES.get(spec.strip().lower(), spec.strip().lower())
    name, _, arg = spec.partition("-")
    table = {
        "static": lambda: Static(),
        "search": lambda: SearchOnly(),
        "nocache": lambda: NoCache(),
        "minloads": lambda: MinLoads(),
        "rentoptimal": lambda: RentOptimal(),
        "ttl": lambda: TTL(int(arg or 10)),
        "lru": lambda: LRU(int(arg or 8)),
        "oracle": lambda: Oracle(int(arg or 16)),
    }
    if name not in table:
        raise ValueError(f"unknown policy '{spec}'; known: {sorted(table)}")
    return table[name]()
