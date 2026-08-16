"""The simulator.

One turn is:

  1. the trace says which tools this turn needs (perfect oracle discovery -
     the agent is never wrong about *what* it needs, only about *how long to
     keep it*);
  2. anything missing is loaded. If it is a turn with at least one miss, one
     search round trip is charged: `discovery_tokens`, plus - if
     `search_turn` is on - one extra request carrying whatever was already
     resident;
  3. the request for this turn is charged: every resident schema, re-sent;
  4. the policy may evict.

No LLM is involved anywhere. That is deliberate: a result that depends on a
model's mood is not a measurement of a cache policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import CostModel, Workload
from .policies import Policy


@dataclass
class Result:
    workload: str
    policy: str
    turns: int

    # The headline metric: sum over turns of resident schema tokens.
    resident_token_turns: int = 0
    peak_resident_tokens: int = 0
    peak_resident_count: int = 0
    final_resident_count: int = 0

    searches: int = 0
    loads: int = 0
    reloads: int = 0
    evictions: int = 0
    hits: int = 0
    misses: int = 0

    premature_reloads: int = 0  # reloaded within CostModel.premature_window
    discovery_tokens: int = 0
    search_turn_tokens: int = 0

    series: list[int] = field(default_factory=list)  # resident tokens per turn
    count_series: list[int] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        """Everything the tool layer costs over the whole session."""
        return self.resident_token_turns + self.discovery_tokens + self.search_turn_tokens

    @property
    def mean_resident_tokens(self) -> float:
        return self.resident_token_turns / self.turns if self.turns else 0.0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 1.0

    @property
    def thrash_rate(self) -> float:
        """Share of loads that were re-loads of a recently evicted tool."""
        return self.premature_reloads / self.loads if self.loads else 0.0


def run(workload: Workload, policy: Policy, cost: CostModel | None = None) -> Result:
    cost = cost or CostModel()
    res = Result(workload.name, policy.name, len(workload.steps))

    resident: set[str] = set(policy.start(workload, cost))
    ever_loaded: set[str] = set()
    evicted_at: dict[str, int] = {}

    for t, step in enumerate(workload.steps):
        missing = [x for x in step.tools if x not in resident]
        res.hits += len(step.tools) - len(missing)
        res.misses += len(missing)

        if missing:
            # One search round trip covers everything missing this turn.
            res.searches += 1
            res.discovery_tokens += cost.discovery_tokens
            if cost.search_turn:
                res.search_turn_tokens += workload.tokens(resident)
            for tool in missing:
                res.loads += 1
                if tool in ever_loaded:
                    res.reloads += 1
                    if t - evicted_at.get(tool, -(10**9)) <= cost.premature_window:
                        res.premature_reloads += 1
                ever_loaded.add(tool)
                resident.add(tool)

        rent = workload.tokens(resident)
        res.resident_token_turns += rent
        res.series.append(rent)
        res.count_series.append(len(resident))
        res.peak_resident_tokens = max(res.peak_resident_tokens, rent)
        res.peak_resident_count = max(res.peak_resident_count, len(resident))

        policy.observe(t, step.tools)
        dropped = policy.evict(t, resident, workload) & resident
        for tool in dropped:
            evicted_at[tool] = t
        resident -= dropped
        res.evictions += len(dropped)

    res.final_resident_count = len(resident)
    return res


def run_matrix(
    workloads: list[Workload],
    policies_factory,
    cost: CostModel | None = None,
) -> list[Result]:
    """Run every policy against every workload.

    `policies_factory` must return *fresh* policy objects per workload -
    policies carry per-run state (last-use tables, oracle lookaheads) and
    reusing one across traces would silently leak information between runs.
    """
    out: list[Result] = []
    for wl in workloads:
        for pol in policies_factory():
            out.append(run(wl, pol, cost))
    return out
