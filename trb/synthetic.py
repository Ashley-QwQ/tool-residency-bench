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
