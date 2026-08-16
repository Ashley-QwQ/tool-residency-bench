"""Randomly sampled workloads, for checking that conclusions are not artefacts.

The seven committed traces are hand-shaped to be pathological in named ways.
That is what makes them explanatory, and also exactly what makes them suspect:
a conclusion that only holds on traces built to produce it is not a
conclusion. This module samples workloads from distributions instead - random
catalog sizes up to a thousand tools, random schema sizes, random phase
structure, random reuse gaps - so the same claims can be re-checked on
workloads nobody designed.

Everything is seeded and reproducible. Nothing here is used by `trb run`.
"""

from __future__ import annotations

import random

from .model import Step, Tool, Workload


FAILURE_PROFILES = ("uniform", "mixed", "persistent")


def apply_failure_profile(
    workload: Workload, profile: str, base_rate: float
) -> Workload:
    """Spread a mean failure rate across tools in different shapes.

    The shapes matter more than the mean. All three below have roughly the
    same expected failure rate; they describe completely different worlds.

    - `uniform`: every tool fails at `base_rate`. The i.i.d. assumption, kept
      as the null hypothesis.
    - `mixed`: 80% of tools at a quarter the rate, 20% at four times it. Some
      tools are simply harder to find than others.
    - `persistent`: 90% of tools essentially never fail, 10% fail *half* the
      time. This is the realistic one - a tool with a vague name and a thin
      description is not unlucky, it is unfindable, and it is unfindable every
      single time you look.

    Assignment is deterministic in the tool id, so a given catalog always gets
    the same profile and results stay reproducible.
    """
    if profile not in FAILURE_PROFILES:
        raise ValueError(f"unknown failure profile '{profile}'")

    catalog = {}
    for i, (tid, tool) in enumerate(sorted(workload.catalog.items())):
        if profile == "uniform":
            rate = base_rate
        elif profile == "mixed":
            rate = base_rate * (4.0 if i % 5 == 0 else 0.25)
        else:  # persistent
            rate = 0.5 if i % 10 == 0 else base_rate * 0.01
        catalog[tid] = Tool(
            tool.id, tool.schema_tokens, tool.server,
            tool.reactivation_tokens, min(rate, 0.99),
        )
    return Workload(workload.name, workload.description, catalog, workload.steps)


def sample_catalog(rng: random.Random, size: int) -> dict[str, Tool]:
    """Schema sizes log-uniform over roughly the range real MCP tools occupy.

    Log-uniform rather than uniform because tool schemas are not symmetrically
    distributed: most are small, a few are enormous, and the ratio between
    them is what `g* = D/S` is sensitive to.
    """
    catalog = {}
    for i in range(size):
        lo, hi = 100, 2500
        tokens = int(lo * (hi / lo) ** rng.random())
        catalog[f"t{i:04d}"] = Tool(f"t{i:04d}", tokens)
    return catalog


def sample_workload(
    seed: int,
    catalog_size: int | None = None,
    turns: int | None = None,
) -> Workload:
    """One random workload: phases, bursts, recurrence and a long tail.

    The generative structure is deliberately *not* one of the seven committed
    traces - it mixes all of their features at random strengths, so a policy
    tuned to any single pathology has nowhere to hide.
    """
    rng = random.Random(seed)
    catalog_size = catalog_size or rng.choice([42, 100, 250, 500, 1000])
    turns = turns or rng.randint(60, 1500)
    catalog = sample_catalog(rng, catalog_size)
    ids = list(catalog)

    # A working set far smaller than the catalog, which is the realistic case:
    # a big catalog exists, a task touches a slice of it.
    active = rng.sample(ids, min(len(ids), rng.randint(4, 40)))
    n_phases = rng.randint(1, 8)
    phases = [
        rng.sample(active, min(len(active), rng.randint(2, 6)))
        for _ in range(n_phases)
    ]
    # How often a never-seen-again specialist interrupts the work.
    tail_rate = rng.choice([0.0, 0.01, 0.03, 0.08])
    # How bursty each phase is: high -> long runs of one tool.
    burst = rng.choice([1, 3, 10, 25])
    # Whether phases recur (cyclic work) or run once (a pipeline).
    cyclic = rng.random() < 0.5

    steps: list[Step] = []
    phase_idx = 0
    while len(steps) < turns:
        tools = phases[phase_idx % n_phases]
        length = rng.randint(max(1, turns // (n_phases * 4)), max(2, turns // n_phases))
        tool = rng.choice(tools)
        for _ in range(length):
            if len(steps) >= turns:
                break
            if rng.random() < tail_rate:
                steps.append(Step((rng.choice(ids),), f"phase{phase_idx}"))
                continue
            if rng.random() < 1.0 / burst:
                tool = rng.choice(tools)
            steps.append(Step((tool,), f"phase{phase_idx}"))
        phase_idx += 1
        if not cyclic and phase_idx >= n_phases:
            phase_idx = 0 if rng.random() < 0.3 else phase_idx
            if phase_idx >= n_phases:
                break

    if not steps:  # degenerate draw; keep the sampler total
        steps = [Step((ids[0],), "phase0")]
    return Workload(f"seed{seed}", "", catalog, steps)
