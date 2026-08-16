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

import math
from dataclasses import dataclass, field

from .model import CostModel, Workload
from .policies import Policy


@dataclass
class Result:
    workload: str
    policy: str
    turns: int

    # The headline metric: Resident Token Rent, in token-turns. Sum over every
    # turn of the schema tokens resident on that turn. Abbreviated RTR, not
    # RTT - in a systems context RTT means round-trip time, and "RTT fell 83%"
    # would read as a latency claim.
    resident_token_rent: int = 0
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
    failure_tokens: int = 0
    # Accumulated log(1 - p_i) over every reactivation. Kept in log space
    # because per-tool rates mean the session survival probability is a
    # product of differing terms rather than a single power, and because a
    # few hundred reactivations underflow a naive product.
    log_survival: float = 0.0
    riskiest_reload: float = 0.0  # highest p_i actually reactivated

    series: list[int] = field(default_factory=list)  # resident tokens per turn
    count_series: list[int] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        """Everything the tool layer costs over the whole session."""
        return (self.resident_token_rent + self.discovery_tokens
                + self.search_turn_tokens + self.failure_tokens)

    @property
    def session_success_prob(self) -> float:
        """Probability that no reactivation in this session failed.

        With per-tool rates this is `prod over reactivations of (1 - p_i)`,
        not `(1 - p)^R` - which matters, because the reactivations a policy
        chooses are not a random sample of the catalog. A policy that happens
        to evict only the reliable tools can reload far more often at the same
        risk, and that is precisely the behaviour a residency policy should be
        rewarded for.

        Only reloads count. Every on-demand policy pays the same first loads,
        so those are common exposure; what differs between policies - and what
        eviction actually spends - is the number of *re*-activations.
        """
        return math.exp(self.log_survival)

    @property
    def mean_resident_tokens(self) -> float:
        return self.resident_token_rent / self.turns if self.turns else 0.0

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
    catalog = workload.catalog

    # Rent is tracked incrementally rather than re-summed each turn. At a
    # thousand-tool catalog the naive version dominates the runtime of the
    # robustness sweep, and the two agree exactly (integer arithmetic, no
    # accumulation error) - `test_static_never_searches` pins the flat line.
    rent = sum(catalog[x].schema_tokens for x in resident)

    for t, step in enumerate(workload.steps):
        missing = [x for x in step.tools if x not in resident]
        res.hits += len(step.tools) - len(missing)
        res.misses += len(missing)

        if missing:
            # One search round trip covers everything missing this turn.
            res.searches += 1
            res.discovery_tokens += cost.discovery_tokens
            if cost.search_turn:
                res.search_turn_tokens += rent
            for tool in missing:
                res.loads += 1
                # Per-tool surcharge on top of the shared round trip, for
                # tools that are expensive to rehydrate specifically, plus the
                # expected cost of a reactivation that fails.
                res.discovery_tokens += catalog[tool].reactivation_tokens
                if tool in ever_loaded:
                    res.reloads += 1
                    res.failure_tokens += cost.expected_failure_cost(catalog[tool])
                    p = cost.failure_rate_for(catalog[tool])
                    res.riskiest_reload = max(res.riskiest_reload, p)
                    res.log_survival += math.log1p(-p) if p < 1.0 else -math.inf
                    if t - evicted_at.get(tool, -(10**9)) <= cost.premature_window:
                        res.premature_reloads += 1
                ever_loaded.add(tool)
                resident.add(tool)
                rent += catalog[tool].schema_tokens

        res.resident_token_rent += rent
        res.series.append(rent)
        res.count_series.append(len(resident))
        res.peak_resident_tokens = max(res.peak_resident_tokens, rent)
        res.peak_resident_count = max(res.peak_resident_count, len(resident))

        policy.observe(t, step.tools)
        dropped = policy.evict(t, resident, workload) & resident
        for tool in dropped:
            evicted_at[tool] = t
            rent -= catalog[tool].schema_tokens
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
