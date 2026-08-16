"""Core data model: tool catalog, traces, and the cost model.

Everything here is deliberately dumb. The simulator never asks what a tool
*does* - only how big its schema is and when it is needed. That is the whole
point: it isolates residency from every other variable (retrieval quality,
model ability, prompt wording) so the residency cost can be attributed to the
residency policy and nothing else.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Tool:
    """One entry in the tool catalog.

    `schema_tokens` is the cost of having this tool's full definition present
    in a request - name, description, JSON schema, argument docs.

    `reactivation_tokens` is a per-tool surcharge on top of the shared search
    round trip, for tools that are expensive to bring back specifically: a
    remote MCP server round trip, an embedding+rerank lookup, a capability
    renegotiation. Zero means "no surcharge, the shared search covers it",
    which is what the v0.1 catalog uses throughout. It exists because the
    break-even idle gap is `D_i / S_i`, and pretending every tool shares one
    global `D` is a modelling choice, not a fact.

    `failure_rate` is this tool's own probability that a reactivation fails.
    `None` means "use the cost model's global rate". Per-tool rather than
    global because retrieval failure is not a coin flip that the universe
    re-tosses each time: a tool with a vague name and a thin description fails
    to be re-found *every* time, and a well-named one essentially never does.
    Modelling it as an i.i.d. global rate spreads that failure evenly over all
    tools and hides the effect it actually has, which is to make a small
    minority of tools individually too dangerous to evict at all.
    """

    id: str
    schema_tokens: int
    server: str = ""
    reactivation_tokens: int = 0
    failure_rate: float | None = None


@dataclass(frozen=True)
class Step:
    """One turn of the trace.

    `tools` is what the agent needs at this turn. `phase` is recorded but no
    baseline policy in this repo reads it - it is there for phase-aware
    policies, which are explicitly out of scope for v1 (see README).
    """

    tools: tuple[str, ...]
    phase: str = ""


@dataclass
class Workload:
    name: str
    description: str
    catalog: dict[str, Tool]
    steps: list[Step]

    def __len__(self) -> int:
        return len(self.steps)

    @property
    def catalog_tokens(self) -> int:
        return sum(t.schema_tokens for t in self.catalog.values())

    def used_tools(self) -> set[str]:
        return {t for step in self.steps for t in step.tools}

    def tokens(self, tool_ids) -> int:
        return sum(self.catalog[t].schema_tokens for t in tool_ids)


@dataclass(frozen=True)
class CostModel:
    """How tokens are charged.

    Three separate costs, kept separate on purpose (see docs/problem.md):

    - residency: every resident schema is re-sent on every request. This is
      the rent, and it is what `Resident Token-Turns` measures.
    - discovery: one search call + its result, charged once per turn that has
      at least one miss. Batched, because a real agent searches once for
      everything it is missing, not once per tool.
    - reactivation turn: a search costs a whole extra request, and that
      request carries the schemas already resident. Without this term,
      "evict everything immediately" looks free, which it is not.

    `discovery_tokens = 0` and `search_turn = False` reduce this to a pure
    residency model. Both are sweepable from the CLI, and the crossover point
    they produce is more interesting than any single number.

    Reactivation can also **fail** - the search comes back empty, or with the
    wrong tool. That is priced two different ways on purpose, because the two
    do not behave alike:

    - `failure_rate` x `failure_penalty` is the **expected token cost**, folded
      into `D_i` so the closed form keeps working. Being linear, it collapses
      into the reactivation price: a phase diagram over these two axes is
      really one-dimensional in `D_eff`.
    - `Result.session_success_prob` is the **session-level reliability**,
      `(1 - failure_rate) ** reloads`. This one does *not* collapse. It decays
      geometrically in the number of reactivations, so a policy that reloads
      690 times at a 1% failure rate is near-certain to hit a failure even
      though its expected token cost looks excellent. Token accounting cannot
      see this, which is exactly why it needs its own number.
    """

    discovery_tokens: int = 150
    search_turn: bool = True
    premature_window: int = 5
    failure_rate: float = 0.0
    failure_penalty: int = 0

    # Opt-in: actually draw failures instead of charging their expectation,
    # so that retries have a control flow rather than a price. Off by default
    # so every result up to v0.2.1 stays reproducible and deterministic.
    simulate_failures: bool = False
    # Retries default to 0 so that the expectation `p_i * L_fail` is exact and
    # every result up to v0.2.1 is unchanged. Set it and both the priced and
    # the simulated path account for retries consistently - which they must,
    # or a policy parameterised from one is being scored against the other.
    retries: int = 0
    seed: int = 0

    def failure_rate_for(self, tool: Tool) -> float:
        """`p_i` - this tool's own failure rate, or the global one."""
        return self.failure_rate if tool.failure_rate is None else tool.failure_rate

    def expected_failure_cost(self, tool: Tool) -> int:
        """Expected extra cost of one reactivation, retries included.

        With `n = retries` further attempts allowed after the first, a tool
        that fails with probability `p` costs

            sum_{k=1..n} p^k * (retry search)   expected retries
          + p^(n+1) * failure_penalty           expected unrecovered failure

        The second term is the one that is easy to get wrong. A retry budget
        does not reduce the failure *rate*, it reduces the rate at which a
        failure becomes **unrecoverable** - and it does so exponentially. At
        `p = 0.5` with two retries, the chance of actually losing the tool is
        0.125, not 0.5. Charging `p * L_fail` there overstates the risk
        four-fold and makes a policy hold dangerous tools far longer than the
        world it is being scored in would justify.
        """
        p = self.failure_rate_for(tool)
        if p <= 0.0:
            return 0
        retry_cost = self.discovery_tokens + tool.reactivation_tokens
        expected_retries = sum(p ** k for k in range(1, self.retries + 1))
        return int(expected_retries * retry_cost
                   + (p ** (self.retries + 1)) * self.failure_penalty)

    def reactivation(self, tool: Tool) -> int:
        """`D_i^eff` - the expected cost of bringing this tool back.

        Per-tool failure rates enter here, which is what lets a policy treat
        an unreliable tool differently from a reliable one of the same size:
        a high `p_i` inflates `D_i`, which raises `g*_i = D_i / S_i`, which
        makes the tool worth holding for longer. At a high enough `p_i` the
        break-even gap exceeds any realistic trace length and the tool becomes
        *effectively unevictable* - which is the correct answer, and one a
        global failure rate cannot express.
        """
        return (
            self.discovery_tokens
            + tool.reactivation_tokens
            + self.expected_failure_cost(tool)
        )

    def draw_failure(self, tool: Tool, attempt: int) -> bool:
        """Does this specific reactivation attempt fail?

        Keyed on `(seed, tool id, attempt)` rather than drawn from a running
        stream, so that two policies see the *same* outcome for the same tool
        on the same attempt number. Without that, a policy could look better
        purely because its reloads landed on luckier draws - the classic
        common-random-numbers correction, and it matters a lot here because
        the quantity under study is precisely which tools get reloaded.

        BLAKE2b rather than `hash()`, which is salted per interpreter run for
        strings and would make results irreproducible across processes - and
        rather than CRC32, which was the first attempt here and was wrong.
        CRC32 is a linear checksum, not a pseudo-random function: keys
        differing only in a trailing attempt index produce *correlated*
        outputs, and consecutive attempts within one retry sequence are
        exactly such keys. The observable symptom was unrecovered-failure
        rates of 0.21 and 0.042 where independence demands 0.16 and 0.064.
        Caught by `test_priced_and_simulated_failure_agree_in_expectation`.
        """
        p = self.failure_rate_for(tool)
        if p <= 0.0:
            return False
        key = f"{self.seed}|{tool.id}|{attempt}".encode()
        digest = hashlib.blake2b(key, digest_size=8).digest()
        return (int.from_bytes(digest, "big") / 2**64) < p

    def label(self) -> str:
        base = f"discovery={self.discovery_tokens}, search_turn={self.search_turn}"
        if self.failure_rate or self.simulate_failures:
            base += (f", p_fail={self.failure_rate:g}, "
                     f"L_fail={self.failure_penalty:,}")
        if self.simulate_failures:
            base += f", simulated retries={self.retries}, seed={self.seed}"
        return base


def load_catalog(path: str | Path) -> dict[str, Tool]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        t["id"]: Tool(
            t["id"],
            int(t["schema_tokens"]),
            t.get("server", ""),
            int(t.get("reactivation_tokens", 0)),
            t["failure_rate"] if "failure_rate" in t else None,
        )
        for t in raw["tools"]
    }


def load_workload(path: str | Path, catalog: dict[str, Tool]) -> Workload:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    steps = []
    for s in raw["steps"]:
        tools = tuple(s["tools"]) if "tools" in s else (s["tool"],)
        for t in tools:
            if t not in catalog:
                raise KeyError(f"{raw['name']}: step needs '{t}', not in catalog")
        steps.append(Step(tools, s.get("phase", "")))
    return Workload(raw["name"], raw.get("description", ""), catalog, steps)


def load_all(workload_dir: str | Path) -> list[Workload]:
    d = Path(workload_dir)
    catalog = load_catalog(d / "catalog.json")
    paths = sorted(p for p in d.glob("*.json") if p.name != "catalog.json")
    return [load_workload(p, catalog) for p in paths]
