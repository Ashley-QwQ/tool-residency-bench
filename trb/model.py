"""Core data model: tool catalog, traces, and the cost model.

Everything here is deliberately dumb. The simulator never asks what a tool
*does* - only how big its schema is and when it is needed. That is the whole
point: it isolates residency from every other variable (retrieval quality,
model ability, prompt wording) so the residency cost can be attributed to the
residency policy and nothing else.
"""

from __future__ import annotations

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
    """

    id: str
    schema_tokens: int
    server: str = ""
    reactivation_tokens: int = 0


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
    """

    discovery_tokens: int = 150
    search_turn: bool = True
    premature_window: int = 5

    def reactivation(self, tool: Tool) -> int:
        """`D_i` - what it costs to bring this specific tool back."""
        return self.discovery_tokens + tool.reactivation_tokens

    def label(self) -> str:
        return f"discovery={self.discovery_tokens}, search_turn={self.search_turn}"


def load_catalog(path: str | Path) -> dict[str, Tool]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        t["id"]: Tool(
            t["id"],
            int(t["schema_tokens"]),
            t.get("server", ""),
            int(t.get("reactivation_tokens", 0)),
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
