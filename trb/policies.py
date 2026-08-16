"""Residency policies.

A policy answers exactly one question: *given that the right tool has already
been found and loaded, when should it stop being resident?*

It never answers "which tool do I need" - the simulator hands that over for
free (perfect oracle discovery). That separation is the experiment.
"""

from __future__ import annotations

from typing import Iterable

from .model import Workload


class Policy:
    """Base class. Default behaviour is search-only: admit, never evict."""

    name = "policy"

    def start(self, workload: Workload) -> set[str]:
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

    def start(self, workload: Workload) -> set[str]:
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


class Oracle(Policy):
    """Belady-style upper bound: evict what is not needed within H turns.

    Cheats by reading the future of the trace. Not implementable in a real
    agent - that is the point. It answers "how much room is there for a
    smarter policy at all", which has to be checked before anyone spends
    effort building one.
    """

    def __init__(self, horizon: int = 16) -> None:
        super().__init__()
        self.horizon = horizon
        self.name = f"oracle-{horizon}"
        self._next: list[dict[str, int]] = []

    def start(self, workload: Workload) -> set[str]:
        # next_use[t][tool] = first turn >= t at which tool is needed.
        nxt: dict[str, int] = {}
        table: list[dict[str, int]] = [dict()] * len(workload.steps)
        for t in range(len(workload.steps) - 1, -1, -1):
            for tool in workload.steps[t].tools:
                nxt[tool] = t
            table[t] = dict(nxt)
        self._next = table
        return set()

    def evict(self, t: int, resident: set[str], workload: Workload) -> set[str]:
        if t + 1 >= len(self._next):
            return set()  # session is over; evicting now would cost nothing and save nothing
        upcoming = self._next[t + 1]
        return {
            x
            for x in resident
            if x not in upcoming or upcoming[x] - t > self.horizon
        }


class BeladyMin(Policy):
    """True MIN: never evict anything that is ever needed again.

    The theoretical floor for a policy that pays zero reload cost. Together
    with oracle-H it brackets the achievable range.
    """

    name = "belady-min"

    def __init__(self) -> None:
        super().__init__()
        self._next: list[dict[str, int]] = []

    def start(self, workload: Workload) -> set[str]:
        nxt: dict[str, int] = {}
        table: list[dict[str, int]] = [dict()] * len(workload.steps)
        for t in range(len(workload.steps) - 1, -1, -1):
            for tool in workload.steps[t].tools:
                nxt[tool] = t
            table[t] = dict(nxt)
        self._next = table
        return set()

    def evict(self, t: int, resident: set[str], workload: Workload) -> set[str]:
        if t + 1 >= len(self._next):
            return set()
        upcoming = self._next[t + 1]
        return {x for x in resident if x not in upcoming}


def default_policies() -> list[Policy]:
    """The v1 baseline set, ordered from most to least conservative."""
    return [
        Static(),
        SearchOnly(),
        TTL(20),
        TTL(5),
        LRU(8),
        NoCache(),
        Oracle(16),
        BeladyMin(),
    ]


ALIASES = {
    "search-only": "search",
    "no-cache": "nocache",
    "belady-min": "belady",
    "min": "belady",
}


def build(spec: str) -> Policy:
    """Parse a policy spec like `ttl-5`, `lru-8`, `oracle-16`, `static`."""
    spec = ALIASES.get(spec.strip().lower(), spec.strip().lower())
    name, _, arg = spec.partition("-")
    table = {
        "static": lambda: Static(),
        "search": lambda: SearchOnly(),
        "nocache": lambda: NoCache(),
        "belady": lambda: BeladyMin(),
        "ttl": lambda: TTL(int(arg or 10)),
        "lru": lambda: LRU(int(arg or 8)),
        "oracle": lambda: Oracle(int(arg or 16)),
    }
    if name not in table:
        raise ValueError(f"unknown policy '{spec}'; known: {sorted(table)}")
    return table[name]()
