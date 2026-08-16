# tool-residency-bench

**Tool discovery answers what to load. It does not answer when to unload it.**

Every shipped system for scaling agents past a handful of tools solves
*admission*: given a task, find the right tool and load its schema. None of
them systematically solve *residency*: once that schema is in the context, how
long should it stay there?

This repository does one narrow thing — it shows that residency is a separate
problem from discovery, and that its cost can be measured on its own.

It does **not** propose a residency policy. That is deliberate; see
[Status](#status).

---

## The claim, in one picture

240 turns. Two tools do essentially all the work. Ten one-off specialists show
up once each and are never needed again. Discovery is a **perfect oracle** —
the system is never wrong about which tool it needs.

```text
  9,710 |                                                                ####
  8,827 |                                                                    
  7,944 |                                                          ######    
  7,061 |                                                   #######          
  6,179 |                                            #######                 
  5,296 |                                                                    
  4,413 |                              ##############                        
  3,530 |                                                                    
  2,648 |                        ######                                      
  1,765 |          ##############      *******       *******             ****
    882 |   #######********************o      *******+      *************+   
      0 |###o++oooo+++oooo++ooooo++oooo ++oooo+++oooo ++oooo +ooooo++oooo ++o
        +--------------------------------------------------------------------
         0                            turn                            240
         # search-only  * ttl-20  o ttl-5  + rent-optimal

         resident tool-schema tokens per turn
```

The staircase is `search-only`: load on demand, never unload. It has flawless
retrieval and still finishes the session re-sending 9,710 tokens of schema on
every request — to do work whose two workhorse tools total 640.

**Perfect tool discovery does not imply bounded tool residency.**

---

## This is caching — but not the caching objective you think

The obvious reaction is "textbook cache replacement, use LRU, move on." The
right answer is: yes, it is caching, and that is why the benchmark ships
Belady's MIN as a baseline. What it is not is the *classical* caching
objective.

Classical replacement minimises **misses** under a **capacity** constraint.
Occupying a slot is free once you are in it; you only decide who to throw out
when you need room. A context window inverts that: there is no hard slot
limit, and occupancy is exactly what costs, **every turn, forever, in
proportion to schema size**.

That variant has a name in the literature. Khare & Young's *Caching with
rental cost and zapping* ([arXiv:1208.2724](https://arxiv.org/abs/1208.2724),
2012) defines caching where each cached file incurs a rental cost per time
unit and the objective is retrieval cost **plus** rental cost. Tool residency
sits squarely in that family, with three LLM-specific additions the 2012 model
has no reason to contain: rent is proportional to **schema size** rather than
uniform, reactivation can **fail**, and resident count independently degrades
**tool-selection accuracy**.

So the claim is not "caching does not apply." It is:

> **Tool residency is rental caching, not capacity-constrained caching, and
> the two have different optima.**

The benchmark demonstrates that rather than asserting it, by shipping both
optima side by side:

| bound | optimises | on `long_mixed` |
|---|---|---|
| `min-loads` (Belady's MIN) | miss count — provably load-optimal, 26 loads | 15,592,740 tokens |
| `rent-optimal` | rent + reactivation, closed form | **912,690 tokens** |

**17x apart, both omniscient.** `min-loads` is not handicapped: it has the
whole future, unbounded capacity, and achieves the theoretical minimum number
of fetches any policy can. It loses because it is optimising the wrong thing.

And the two are not rivals — they are the same policy at different rents.
Sweep the cost of one re-search upward and `rent-optimal` walks continuously
into `min-loads`, landing on it exactly (`long_tail`, 409,080 tokens for both
at a re-search cost of 20,000). Classical MIN is the limiting case of the
rental optimum as reactivation becomes infinitely expensive. Real agents do
not live at that limit; they live at the end of the curve where holding is
expensive and re-searching is cheap, which is the end nobody schedules for.

---

## Three costs, kept apart

Most designs collapse these into one. They behave completely differently.

| | question | when paid |
|---|---|---|
| **Discovery** | which tool do I need? | once, per search |
| **Residency** | how long does its schema stay loaded? | **every turn, for every resident tool** |
| **Reactivation** | what does it cost to bring it back? | once, per reload |

Residency is the only one that compounds. A 1,000-token schema left resident
for 100 idle turns costs 100,000 tokens; re-finding it costs a few hundred.
That asymmetry is the whole subject of this repo, and it is why the headline
metric is not "final context size" but:

> **Resident Token-Turns (RTT)** — the sum, over every turn, of the schema
> tokens resident on that turn. The area under the curve above.

Two sessions can end with identical context sizes while one of them paid rent
on a dead tool for four hundred turns. Only RTT can tell them apart.

---

## Quickstart

No dependencies. Python 3.9+.

```bash
python -m trb run
```

Writes [`results/summary.md`](results/summary.md) — every policy against every
workload, with tables and curves.

```bash
python -m trb run -w burst -p search-only -p ttl-5 -p min-loads -p rent-optimal
python -m trb sweep -w long_tail
python tests/test_simulator.py
```

`sweep` varies the cost of one re-search, because whether eviction pays is not
a property of the policy — it is a property of the ratio between schema size
and re-search cost. Any benchmark that reports a single number for that ratio
is hiding the interesting part.

---

## What is simulated

One turn:

1. the trace declares which tools this turn needs — **perfect oracle
   discovery**, so retrieval quality can never explain a result;
2. anything missing is loaded, charging one search round trip;
3. every resident schema is charged, because every resident schema is re-sent;
4. the policy may evict.

No LLM is involved anywhere, on purpose. A result that moves when a model
changes its mind is not a measurement of a cache policy. Everything is
deterministic and reproducible from a clean checkout.

### Baselines

| policy | rule | stands for |
|---|---|---|
| `static` | whole catalog resident from turn 0 | `tools=[...]`, the pre-tool-search default |
| `search-only` | load on demand, never unload | **every shipped tool-search implementation** |
| `ttl-N` | drop anything unused for N turns | Denning's working set (1968) |
| `lru-N` | keep at most N tools | the reflex answer |
| `no-cache` | drop everything not used this turn | maximally aggressive; the thrash control |
| `oracle-N` | drop what is not needed within N turns | *offline heuristic* — arbitrary horizon, not an optimum |
| `min-loads` | never drop anything ever needed again | Belady's MIN: **optimal for miss count** |
| `rent-optimal` | drop iff `schema × idle turns > search cost` | **optimal for rent + reactivation** |

The last three read the future of the trace, so none is implementable and none
is a proposal. They exist to answer the question that has to come first: **is
there enough headroom here to be worth anyone's effort, and under which
objective?**

`rent-optimal` is a closed form rather than a search, because without a
capacity constraint the tools do not compete and the decision decomposes per
tool, per idle gap. It is exactly optimal when discovery is charged per tool
load with no search-turn rent; under the defaults, batched searches and
search-turn rent couple tools together, so it is a very tight bound rather
than a proven optimum — and both couplings make eviction cheaper than the rule
assumes, so it errs toward holding. A test asserts no other policy ever beats
it.

### Workloads

Seven traces over one 42-tool catalog (32,830 tokens if all resident — the
same order of magnitude Anthropic cites as typical for five MCP servers).

| trace | turns | what it is for |
|---|---|---|
| `short` | 3 | the disqualifier: nothing to manage, so nothing may be spent |
| `burst` | 29 | one tool used 26x, then dead — recency and frequency both mislead |
| `phase_shift` | 48 | download → process → upload → report |
| `late_reuse` | 104 | idle 100 turns, then needed once more |
| `alternating` | 80 | A B A B — the thrashing trap |
| `long_tail` | 240 | two workhorses plus a stream of one-off specialists |
| `long_mixed` | 938 | recurring phases, occasional detours; the realistic one |

---

## Findings

Cost model: 150 tokens per search round trip, and a re-search costs one extra
request. Full tables in [`results/summary.md`](results/summary.md).

**1. Miss-optimal caching does not optimise residency rent.** `min-loads` is
Belady's MIN with unbounded capacity and full knowledge of the future. It
achieves the provably minimum number of fetches — 26 loads on `long_mixed`,
which nothing can beat — and costs **17x** what the rent-optimal offline
policy costs on the same trace (15,592,740 vs 912,690 tokens). Both are
omniscient. The gap is entirely the objective function. This is the finding
that forces a reader to re-examine what is being optimised, rather than
nodding along at "lazy loading accumulates."

**2. Perfect discovery does not bound residency growth.** On `long_tail`,
`search-only` has 100% retrieval precision by construction and still grows
monotonically to 9,710 resident tokens per turn — 1.13M token-turns against
83K for the rent-optimal bound. **−93%** left on the table by a system doing
discovery flawlessly.

**3. A resident-count cap is not, by itself, a residency-cost policy.**
`lru-8`: −11% on `long_tail`, 0% on `phase_shift`. `ttl-20` on the same
traces: −70% and −19%. A count cap only acts when the count is the thing that
is high; a phase needing 4–6 tools never trips `max_resident=8`, so dead tools
lie around comfortably until the task ends. This does not mean count is
irrelevant — it means **there are two budgets, and one policy cannot serve
both**:

```text
Residency budget   resident schema token-rent      <- what this repo measures
Selection budget   resident count / ambiguity      <- the 30-50 tool accuracy ceiling
```

They are not even in the same units. 8 tools is a very coarse instrument for
a catalog whose schemas run from 150 to 1,810 tokens.

**4. Recency and frequency point the wrong way at phase boundaries.** In
`burst`, the grayscale tool is the most recently *and* most frequently used
tool in the trace at the exact moment it becomes dead weight. `ttl-5`,
`ttl-20` and `lru-8` all save literally nothing there (`+0%`). The phase
boundary is a semantic event; no access-history statistic can see it.

**5. Without pricing reactivation, aggressive eviction looks artificially
optimal.** In this model eviction is free, re-search is cheap and flat, and
retrieval never fails — so of course the model endorses "use it and throw it
away." `no-cache` is the cheapest implementable policy on `long_mixed` at a
discovery cost of 150 tokens and the second most expensive at 20,000, while
reloading on 62–74% of its loads. Read the right way round, this is
informative rather than embarrassing: **residency management is not valuable
because eviction is virtuous, it is valuable because reactivation is costly
and unreliable.** The crossover is real and sits around 1,000–5,000 tokens per
re-search on these traces:

```text
long_tail, total tool tokens        python -m trb sweep -w long_tail

| re-search cost | search-only |    ttl-20 |  no-cache | min-loads | rent-optimal |
|            0   |   1,133,310 |   343,560 |   141,070 |   169,080 |       67,930 |
|          150   |   1,135,110 |   345,360 |   155,920 |   170,880 |       82,780 |
|        1,000   |   1,145,310 |   355,560 |   240,070 |   181,080 |      134,790 |
|        5,000   |   1,193,310 |   403,560 |   636,070 |   229,080 |      223,640 |
|       20,000   |   1,373,310 |   583,560 | 2,121,070 |   409,080 |      409,080 |  <- converged
|      100,000   |   2,333,310 | 1,543,560 |10,041,070 | 1,369,080 |    1,369,080 |
```

`no-cache` goes from best to 5x worse than the bound across that range without
its code changing at all. Whether eviction pays is a property of the cost
ratio, not of the policy — which is why a benchmark that reports a single
number for that ratio is hiding the interesting part.

**6. The value of lifecycle management varies by orders of magnitude across
workloads.** On `short`, `rent-optimal` saves 1,360 tokens against never
evicting — less than the single `cloud_deploy` schema (1,810). On `long_mixed`
the same policy saves 16.8M. Four orders of magnitude, same policy, same code.

This motivates **pressure-based gating**: the benefit of managing residency is
directly observable from accumulated residency cost, whereas remaining task
length has to be predicted. It does not by itself prove observed pressure is a
*better* gate than predicted length — that needs a gating benchmark that holds
prediction accuracy fixed and compares the two triggers, which this repo does
not contain.

---

## Limitations

Read these before quoting any number above.

- **Discovery is a perfect oracle, and reactivation never fails.** Real
  re-search can return nothing, or the wrong thing. That risk is priced
  nowhere in this model, and it is the single biggest reason `no-cache`'s
  token win must **not** be read as a recommendation. See finding 5: the
  model endorses aggressive eviction because the model does not charge for
  the thing that makes aggressive eviction dangerous. The full objective a
  real policy should be minimising is

  ```text
  residency rent          schema_tokens x resident_turns     (modelled here)
  + reactivation cost     search tokens + latency            (partly modelled)
  + failure cost          P(retrieval fails) x penalty       (not modelled)
  ```
- **Tokens only.** No wall-clock latency, no user-visible stalls, and no model
  behaviour. In particular, the documented degradation of tool-selection
  accuracy past 30–50 visible tools is *not* modelled — including it would
  penalise `static` and `search-only` considerably more than these numbers do.
- **Prompt caching is not modelled.** In a real deployment an unchanged tool
  prefix can be cached, which lowers the effective cost of holding tools; the
  same mechanism means eviction has to be done carefully to avoid invalidating
  the cache. Anthropic's `tool_addition` / `tool_removal` blocks exist
  precisely to change the resident set without breaking the cached prefix.
- **The traces are synthetic and the schema sizes are hand-estimated.** They
  are shaped from real agent workloads, not sampled from them. They are meant
  to be pathological in specific, named ways, which is a different goal from
  being representative.
- **Management overhead is not charged.** A real policy costs something to
  run. Finding 6 says short tasks have almost no headroom to pay for it; this
  simulator does not model the bill itself.

---

## Where this sits in the prior art

Discovery is crowded. Residency is not.

| work | discovery | residency |
|---|---|---|
| [Caching with rental cost and zapping (1208.2724)](https://arxiv.org/abs/1208.2724) | — | **the theoretical home.** Caching where each cached file pays rent per time unit; objective is retrieval + rental cost. Predates LLM agents by a decade and describes their tool context better than classical replacement does |
| [Anthropic tool search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool) | BM25 / regex over the catalog, `defer_loading` | none — the docs state discovered tools are re-expanded throughout history so Claude can reuse them "without re-searching" |
| [Anthropic mid-conversation tool changes](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching) | — | `tool_addition` / `tool_removal` blocks: the eviction **primitive** exists and is cache-safe. No policy ships with it |
| [MCP-Zero (2506.01056)](https://arxiv.org/abs/2506.01056) | active tool request + hierarchical semantic routing | not addressed |
| [MemTool (2507.21428)](https://arxiv.org/abs/2507.21428) | search tool | **the closest prior work.** Gives the agent an explicit `RemoveTool`. Reports 90–94% removal efficiency for large reasoning models but **0–60% for mid-sized ones**, and measures a *removal ratio* rather than a residency cost |
| [Tool Attention (2604.21816)](https://arxiv.org/abs/2604.21816) | intent–schema overlap, lazy two-phase schema loading | per-turn gating; end-to-end figures are the authors' projections, not live measurements |
| [Beyond Compaction / CWL (2606.11213)](https://arxiv.org/abs/2606.11213) | — | deterministic LLM-free eviction — of trajectory episodes, not tool schemas |
| [Demand paging for context windows (2603.09023)](https://arxiv.org/abs/2603.09023) | — | real paging over context generally; names semantic units as future work |
| [Looking Is Not Picking (2606.16364)](https://arxiv.org/pdf/2606.16364) | — | why a bloated tool set degrades selection even when it fits |

Two things follow. First, MemTool already established that tools should be
removed — this repo is not claiming the idea is new. What it adds is that the
cost of *not* removing them is measurable without an LLM in the loop, which
matters exactly because MemTool's own result is that smaller models are bad at
doing the removing themselves. Second, the systems above that do evict, evict
*something else* (conversation episodes, context pages). Tool schemas are an
unusually good target — they are large, self-contained, and losslessly
restorable — and nobody appears to be scheduling them specifically.

---

## Status

v0.1. The simulator, seven traces, seven baselines, and the metric.

Explicitly **not** in this repo, and not by accident:

- a proposed residency policy
- any semantic, phase-aware, or plan-aware eviction
- an embedding or BM25 retriever (discovery is an oracle here on purpose)
- an LLM anywhere in the loop
- an MCP client or agent framework

Each of those is a variable that would make it impossible to attribute a
result to the residency policy alone, which is the only thing v0.1 is trying
to establish.

The three things v0.2 should do, in order of how much they would sharpen the
argument:

1. **Price reactivation failure and draw the phase diagram.** Degrade oracle
   discovery from 100% to 99 / 95 / 90%, give a miss a controllable penalty,
   and plot re-search cost against failure rate. `no-cache`'s advantage should
   collapse somewhere on that surface, and the optimal policy should migrate
   `no-cache → ttl → conservative residency` as you move across it. That turns
   "retrieval reliability sets the ceiling on eviction aggressiveness" from a
   sentence into a figure.
2. **Measure the selection budget.** Find where tool-call error rate actually
   starts climbing for an 8B–30B local model as resident tool count grows.
   Anthropic's 30–50 figure is for a frontier model; a smaller one is almost
   certainly lower, and it is directly measurable rather than assumable by
   analogy. That number turns finding 3's second budget into a real axis.
3. **A phase-aware policy**, measured against `rent-optimal` on these traces.
   `Step.phase` is already in every trace and read by nothing.

Issues and traces that break the baselines are very welcome. A trace where
`search-only` is genuinely the right answer would be the most useful
contribution of all.

## License

MIT.
