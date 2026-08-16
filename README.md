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

> **Resident Token Rent (RTR)** — the sum, over every turn, of the schema
> tokens resident on that turn, measured in token-turns. The area under the
> curve above.
>
> (Abbreviated RTR, not RTT. In a systems context RTT is round-trip time, and
> "RTT fell 83%" would read as a latency claim.)

Two sessions can end with identical context sizes while one of them paid rent
on a dead tool for four hundred turns. Only RTR can tell them apart.

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
python -m trb sweep       -w long_tail  # optimality gap vs. reactivation price
python -m trb pareto      -w long_tail  # the trade-off with no price assumed
python -m trb reliability -w long_mixed --failure-profile persistent
python -m trb robustness --seeds 300    # the claims on random workloads
python tests/test_simulator.py        # invariants
python tests/test_optimality.py       # brute-force validation of the optimum
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

Exactly *when* each of those happens is load-bearing, not bookkeeping: whether
eviction takes effect this turn or the next is the entire difference between
`no-cache` and the aggressive end of the optimum, and it is worth 2x on
`long_tail`. The convention is written down in
[`docs/timing-model.md`](docs/timing-model.md) rather than left to be inferred
from the code.

### Baselines

| policy | rule | stands for |
|---|---|---|
| `static` | whole catalog resident from turn 0 | `tools=[...]`, the pre-tool-search default |
| `search-only` | load on demand, never unload | **every shipped tool-search implementation** |
| `ttl-N` | drop anything unused for N turns | Denning's working set (1968) |
| `lru-N` | keep at most N tools | the reflex answer |
| `no-cache` | drop everything not used this turn | maximally aggressive; the thrash control |
| `ski-rental` | hold `ceil(D/S)-1` idle turns, then drop | **the strong online baseline**: 2-competitive, and provably the best any cost-only policy can be |
| `oracle-N` | drop what is not needed within N turns | *offline heuristic* — arbitrary horizon, not an optimum |
| `min-loads` | never drop anything ever needed again | Belady's MIN: **optimal for miss count** |
| `rent-optimal` | drop iff `schema × idle turns > D_i` | **optimal for rent + reactivation** |

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

`python -m trb sweep -w long_tail`, reported as **optimality gap** — each
policy's total cost divided by the rent-optimal cost at that same reactivation
price:

```text
| D       | rent-optimal | search-only | ttl-20 | lru-8  | no-cache | min-loads |
| 0       |       67,930 |      16.68x |  5.06x | 14.82x |    2.08x |     2.49x |
| 150     |       82,780 |      13.71x |  4.17x | 12.19x |    1.88x |     2.06x |
| 1,000   |      134,790 |       8.50x |  2.64x |  7.56x |    1.78x |     1.34x |
| 5,000   |      223,640 |       5.34x |  1.80x |  4.77x |    2.84x |     1.02x |
| 20,000  |      409,080 |       3.36x |  1.43x |  3.05x |    5.18x |   * 1.00x |
| 100,000 |    1,369,080 |       1.70x |  1.13x |  1.61x |    7.33x |   * 1.00x |
```

`no-cache` goes from second-best to 7x worse than the bound without its code
changing at all, while `min-loads` walks the other way and lands exactly on
the optimum. Normalising against the optimum is what makes that structure
visible: these are not rival policies scattered across a table, they are
points on one continuum with two limits.

```text
D -> 0      optimum is evict-on-last-use     any idle turn costs more than
                                             fetching the tool back
D -> inf    optimum is min-loads             never pay to fetch twice
```

Classical miss minimisation is not a competing theory of this problem. It is
the `D -> inf` regime of it. Real agents live in the middle, and closer to the
left end than anyone schedules for.

(One detail worth not glossing: `no-cache` does not reach 1.00x at `D = 0`,
because it evicts a turn late — it keeps whatever was used most recently, so a
dead tool rides along for one more request. That single turn of lag costs 2x
on this trace. The `D -> 0` limit is "evict immediately on last use", which is
what `rent-optimal` does there.)

**6. No implementable baseline is on the Pareto frontier — on any workload.**
Everything above prices a reactivation at some number of tokens, and a reader
is entitled to disagree with that price. `python -m trb pareto` declines to
choose one, plotting residency rent against reactivations directly:

```text
long_tail

| policy        | reactivations | rent      | on frontier |
| static        |             0 | 7,879,200 | dominated   |
| search-only   |             0 | 1,091,910 | dominated   |
| ttl-20        |             0 |   336,730 | dominated   |
| ttl-5         |            14 |   197,530 | dominated   |
| lru-8         |             0 |   969,320 | dominated   |
| no-cache      |            87 |   104,500 | dominated   |
| min-loads     |             0 |   162,250 | frontier    |
| opt @ D=5,000 |             3 |   142,900 | frontier    |
| opt @ D=1,000 |            25 |    90,010 | frontier    |
| opt @ D=150   |            87 |    67,930 | frontier    |
```

A dominated policy is beaten on **both** axes at once, so no exchange rate
between them can rescue it — this conclusion holds whatever anyone thinks `D`
should be. Every heuristic in the suite is dominated, on all seven workloads
and on 95.7% of 300 randomly sampled ones. `D` turns out not to decide who is
good, only **where on the frontier** a deployment wants to sit.

That reframes what a residency policy is for. It is not "beat LRU" — LRU is
not even on the map. It is **get an online policy onto a frontier otherwise
occupied only by policies that can see the future.**

**7. The value of lifecycle management varies by orders of magnitude across
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

**8. The online problem is ski rental — which caps how much cleverness can
help.** Strip one idle gap to its decision and it is exact: pay `S` per turn to
keep renting, or `D` once to settle it. So the classic rule applies (hold
`⌈D/S⌉ − 1` idle turns, then evict), it is **2-competitive**, and the
Proposition's independence makes the per-gap guarantee a whole-session one.
That ships as `ski-rental`.

The barrier matters more than the algorithm. Ski rental's deterministic lower
bound is also 2, and this problem contains ski rental as a special case, so no
deterministic online policy can beat 2x — `e/(e−1) ≈ 1.58` randomised — using
cost reasoning alone. Getting below that requires information about `g` itself,
which is exactly what a phase boundary is.

And the measured news is bad for the semantic thesis, stated plainly:
`ski-rental` knows *nothing* about the task and lands at a **median 1.13x** of
the offline optimum across 300 random workloads (**1.04x** on `long_mixed`).
On token cost, semantics has almost nothing left to win.

**9. Which is the wrong place to have been looking. Once reactivation can
fail, the whole ranking inverts.** At `p_fail = 0.01` on `long_mixed`:

| policy | reactivations | P(session completes) |
|---|---|---|
| search-only | 0 | 100.0% |
| min-loads | 0 | 100.0% |
| ttl-20 | 149 | 22.4% |
| no-cache | 690 | 0.1% |
| ski-rental | 912 | **0.0%** |

Expected token cost grows linearly in reactivations; the probability of
completing the session decays geometrically in them. `ski-rental` is the best
policy in the repo on tokens and unusable here. Impose a 95% completion floor
and the cheapest policy at **any** non-zero failure rate becomes `min-loads` —
the most conservative one.

**10. But that inversion is largely an artefact of assuming failure is
uniform.** Retrieval failure is not a coin re-tossed per attempt: a tool with
a vague name and thin description is unfindable *every* time, and a well-named
one essentially never is. `Tool.failure_rate` sets `p_i` per tool, and session
survival becomes a product over the tools actually reactivated rather than
`(1−p)^R`. With 90% of tools safe and 10% failing half the time
(`--failure-profile persistent`), as failure gets expensive:

| L_fail | reactivations | riskiest tool reloaded | P(completes) |
|---|---|---|---|
| 0 | 690 | p=0.5 | 0.0% |
| 100,000 | 600 | p=0.5 | 0.0% |
| **1,000,000** | **575** | **p=0.0001** | **94.4%** |

The policy does not gradually reload less — it stops reloading the *dangerous*
tools specifically while still reloading the safe ones 575 times. No new
machinery is needed: a high `p_i` inflates `D_i`, which inflates `g*_i`, until
the tool is effectively unevictable. **Risk localises, and so does residency.**

So the v0.1 slogan needs restating. Reliability does not cap how aggressive a
policy may be; it caps **aggression per tool**, and a policy that cannot tell
its tools apart is stuck applying the worst tool's ceiling to all of them.
Which is a second kind of per-tool knowledge that is not in the access
history — alongside "which tools are dead". Same shape of answer: **what is
worth knowing about a tool is not when it was last used.**

So the value of semantic knowledge is not that it evicts *sooner*. It is that
it evicts **without exposure**: a tool whose phase has completed can be dropped
at a reload probability of zero, rather than on a `D/S` bet that it will not
come back. `min-loads` is functionally a perfect semantic policy — it evicts
exactly what is dead — and the gap between it and the rent optimum is the part
no cost-only policy can reach. Details in
[`docs/reliability.md`](docs/reliability.md).

---

## Do the conclusions survive workloads nobody designed?

The seven traces are hand-shaped to be pathological in named ways, which is
what makes them explanatory and also what makes them suspect.
`python -m trb robustness` re-checks every claim on randomly sampled
workloads — catalogs up to 1,000 tools, traces up to 1,500 turns, random phase
structure, burstiness, recurrence and long-tail rate:

```text
300 sampled workloads

| claim                                                     | holds on |
| search-only costs >2x the optimum                         |    98.7% |
| min-loads costs >2x the optimum (wrong objective)         |    92.3% |
| best TTL beats best count cap (rent != capacity)          |    98.0% |
| ski-rental within 2x of the optimum (D/S is the horizon)  |   100.0% |
| every heuristic is Pareto-dominated                       |    95.7% |

| cost relative to rent-optimal | p25   | median | p75   |
| search-only                   | 7.51x | 12.22x | 21.60x|
| min-loads                     | 3.26x |  4.97x |  7.48x|
| best TTL                      | 1.61x |  2.21x |  3.10x|
| ski-rental                    | 1.08x |  1.13x |  1.17x|
```

Nothing here rests on the seven traces.

---

## Limitations

Read these before quoting any number above.

- **Discovery is a perfect oracle.** The agent always knows *which* tool it
  needs; only reactivation can fail. Findings 1-8 are all computed with
  failure switched off, so read them as the token-only regime rather than as
  recommendations — finding 5 in particular endorses aggressive eviction
  precisely because that regime does not charge for what makes it dangerous.

  ```text
  residency rent          schema_tokens x resident_turns   modelled
  + reactivation cost     search tokens, per tool          modelled
  + failure cost          p_i x penalty, per tool          modelled (v0.2)
  + failure recovery      retry, re-plan, escalate         NOT modelled
  ```

- **A failed reactivation is priced, not simulated.** There is no retry, no
  re-planning around the missing capability, and no fallback to a different
  tool. A real agent would do all three, and `p_i` is an input here rather
  than something measured.
- **RTR is logical context occupancy, not compute.** This is the caveat most
  likely to be mistaken for a claim it is not making. **15M token-turns does
  not mean 15M extra tokens were processed.** With prompt caching, KV reuse,
  and cached-input pricing, a schema that is logically resident on every turn
  is emphatically not re-prefilled on every turn. Three different axes get
  conflated here routinely:

  ```text
  RTR                     logical residency pressure   <- the only one measured
  compute rent            FLOPs, latency, API dollars  <- implementation-dependent
  selection interference  wrong tool, bad arguments    <- model-dependent
  ```

  RTR bounds context headroom and is a necessary input to the other two, but
  it is not a substitute for either. Anyone wanting latency or dollar figures
  needs an execution model this repo does not have.

- **No model behaviour at all.** The documented degradation of tool-selection
  accuracy past 30–50 visible tools is not modelled; including it would
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

**v0.1 — problem characterisation.** Tagged `v0.1` / `v0.1.1`. A cost model and
a benchmark, not a framework, and complete as that:

```text
+ perfect oracle discovery, no LLM anywhere
+ 42-tool heterogeneous catalog (150-1,810 tokens per schema)
+ 7 hand-shaped workloads, 9 policies
+ Resident Token Rent as the metric
+ min-loads oracle    (miss-optimal)
+ rent-optimal oracle (rent-optimal, closed form + proof)
+ reactivation-cost sweep, reported as optimality gap
+ Pareto frontier, so nothing depends on one choice of price
+ the closed form validated against exhaustive enumeration of every
  eviction schedule on small traces, plus metamorphic invariants
+ event semantics pinned down in docs/timing-model.md
+ ski-rental online baseline: 2-competitive, matching lower bound
+ robustness sweep over randomly sampled workloads
+ stated falsification criteria
```

**v0.2 — pricing failure.** Landed: `trb reliability`, and
[`docs/reliability.md`](docs/reliability.md). This is where the v0.1 framing
turned out to be looking in the wrong place — see findings 8 and 9. Still open
for v0.2:

- **Measuring `p_i` rather than assuming it.** Per-tool failure rates are
  modelled and they change the conclusion (finding 10), but nothing here
  estimates them. The cheapest source is the harness itself: record whether a
  re-search found what it went looking for, and `p_i` falls out of the logs.
- **Failure recovery.** A failed reactivation currently just costs tokens.
  Retry, re-plan, and fallback-to-another-tool are all missing, and they are
  what determines whether a failure is an annoyance or the end of the task.
- **The selection budget.** Where tool-call error rate actually starts
  climbing for an 8B–30B local model as resident tool count grows. Anthropic's
  30–50 figure is for a frontier model; a smaller one is almost certainly
  lower and it is directly measurable rather than assumable by analogy. This
  belongs in its own benchmark, with count, total schema tokens, and inter-tool
  similarity varied separately — they are three different hypotheses and are
  routinely conflated into one.
- **Real traces.** Not thousands of sessions: twenty would do, reduced to
  `turn, tool_id, schema_size, phase` and nothing else. The single question
  worth asking of them is the shape of `P(next_use_gap = g)`, because that
  distribution is what every result here is ultimately a function of. If it
  looks like the committed traces, they are justified; if it does not, the
  generator is wrong and that is worth knowing early.

**v0.3 — the first semantic policy.** Deliberately last. The target is now
precise, which it was not before v0.2: get near `ski-rental` on rent while
near `min-loads` on reload count. That region of the Pareto plot is currently
empty, and no cost-only policy can enter it — the ski-rental lower bound says
so. `Step.phase` is already recorded in every trace and read by nothing.

Explicitly **not** in this repo, and not by accident:

- a proposed *semantic* residency policy (`ski-rental` is a baseline derived
  from the cost model, not a proposal — it exists so that v0.3 has something
  real to beat)
- an embedding or BM25 retriever (discovery is an oracle here on purpose)
- an LLM anywhere in the loop
- an MCP client or agent framework

Each is a variable that would make it impossible to attribute a result to the
residency policy alone.

Issues and traces that break the baselines are very welcome. A trace where
`search-only` is genuinely the right answer would be the most useful
contribution of all.

## License

MIT.
