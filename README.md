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
    882 |   #######********************o      *******       *************    
      0 |###o++oooo ++oooo +ooooo +oooo ++oooo ++oooo ++oooo +ooooo +oooo ++o
        +--------------------------------------------------------------------
         0                            turn                            240
         # search-only  * ttl-20  o ttl-5  + oracle-16

         resident tool-schema tokens per turn
```

The staircase is `search-only`: load on demand, never unload. It has flawless
retrieval and still finishes the session re-sending 9,710 tokens of schema on
every request — to do work whose two workhorse tools total 640.

**Perfect tool discovery does not imply bounded tool residency.**

---

## Why this is not just "add a cache"

The obvious reaction is that this is textbook cache replacement, so use LRU and
move on. Two of the results below say otherwise:

- **Belady's MIN — the provably optimal cache policy — is not optimal here.**
  On the long trace it costs **6x more** than a mediocre lookahead heuristic
  (15.6M vs 2.6M token-turns). MIN never evicts anything that will be needed
  again, which is correct when holding an entry is free and *capacity* is the
  constraint. In a context window, holding is not free: every resident schema
  is re-sent on every request. The binding constraint is **rent**, not
  capacity, and that changes what optimal means.
- **Bounding the number of resident tools barely helps.** `lru-8` saves 11% on
  `long_tail` and exactly 0% on `phase_shift`, where a plain 20-turn working
  set saves 70% and 19%. Capping the count does nothing when the count was
  never the thing running up the bill.

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
python -m trb run -w burst -p search-only -p ttl-5 -p oracle-16
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
| `oracle-N` | drop what is not needed within N turns | cheats; an upper bound on what any policy could win |
| `belady-min` | never drop anything ever needed again | classical cache optimum — see above |

`oracle-N` and `belady-min` read the future of the trace. They are not
proposals. They exist to answer the question that has to come first: **is
there enough headroom here to be worth anyone's effort?**

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

**1. Discovery precision does not bound residency growth.** On `long_tail`,
`search-only` has 100% retrieval precision by construction and still grows
monotonically to 9,710 resident tokens per turn — 1.13M token-turns against
162K for a lookahead policy on the same trace. **-86%** was left on the table
by a system doing discovery perfectly.

**2. Recency and frequency point the wrong way at phase boundaries.** In
`burst`, the grayscale tool is the most recently *and* most frequently used
tool in the trace at the exact moment it becomes dead weight. `ttl-5`,
`ttl-20` and `lru-8` all save literally nothing there (`+0%`); the phase
boundary is a semantic event, and no access-history statistic can see it.

**3. The classical cache optimum is the wrong optimum.** `belady-min` costs
15.6M tokens on `long_mixed` where `oracle-16` costs 2.6M. Optimality under
"capacity is scarce" is not optimality under "everything resident is re-sent
every turn."

**4. Capping tool count is the wrong knob for tokens.** `lru-8`: −11% on
`long_tail`, 0% on `phase_shift`. `ttl-20` on the same traces: −70% and −19%.
(Tool *count* still matters for a different reason — selection accuracy
degrades past 30–50 visible tools — but that is not what RTT measures, and the
two should not be conflated.)

**5. Aggressive eviction is only free while re-search is free.** `no-cache` is
the cheapest policy on `long_mixed` at a discovery cost of 150 tokens, and the
second most expensive at 20,000. It reloads on 62–74% of its loads. The
crossover is real and sits at a discovery cost of roughly 1,000–5,000 tokens
on these traces:

```text
long_tail, total tool tokens

| re-search cost |  search-only |    ttl-20 |  no-cache | oracle-16 | best       |
|            0   |    1,133,310 |   343,560 |   141,070 |   160,690 | no-cache   |
|          150   |    1,135,110 |   345,360 |   155,920 |   162,640 | no-cache   |
|        1,000   |    1,145,310 |   355,560 |   240,070 |   173,690 | oracle-16  |
|        5,000   |    1,193,310 |   403,560 |   636,070 |   225,690 | oracle-16  |
|      100,000   |    2,333,310 | 1,543,560 | 10,041,070| 1,460,690 | oracle-16  |
```

**6. Short tasks have no headroom, and that is measurable rather than
predictable.** On `short`, a clairvoyant policy saves 1,360 tokens against
never evicting — less than one tool schema. On `long_mixed` the same policy
saves 15.1M, four orders of magnitude more. So the question "should lifecycle
management run at all?" should be gated on **observed headroom**, not on a
prediction of how long the task will be. (Predicting task length is
unreliable in the direction that matters: "fix a typo" routinely becomes
forty turns.)

---

## Limitations

Read these before quoting any number above.

- **Discovery is a perfect oracle.** Real re-search can return nothing, or the
  wrong thing. That risk is not priced anywhere in this model, and it is the
  single biggest reason `no-cache`'s token win must **not** be read as a
  recommendation. Retrieval reliability is what actually bounds how
  aggressively a real system can evict.
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
to establish. The natural v0.2 is a phase-aware policy measured against
`oracle-16` on these same traces, and a measurement of where tool-call error
rate actually starts climbing for a small local model — the number that would
turn finding 4's parenthetical into a second axis.

Issues and traces that break the baselines are very welcome. A trace where
`search-only` is genuinely the right answer would be the most useful
contribution of all.

## License

MIT.
