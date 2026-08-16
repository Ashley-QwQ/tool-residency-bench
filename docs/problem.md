# Tool residency: the problem statement

This document states the problem the benchmark is built around, and argues
that it is not already solved by (a) tool search, (b) context compaction, or
(c) classical cache replacement. If you only want the numbers, read the
[README](../README.md) instead.

## The pipeline everyone actually has

```
                   tool registry / catalog
                             |
                    discovery policy          "which tool do I need?"
                             v
                        admission
                             |
                             v
                 +-----------------------+
                 |  resident working set |   re-sent on every request
                 +-----------------------+
                             |
                    residency policy          "how long does it stay?"
                             v
                         eviction
                             |
                             v
                       non-resident
                             |
                  reactivation policy         "what does it cost to return?"
                             +--------------> back to admission
```

Real systems have built the top box and the arrow out of it. The middle box
is where the tokens are actually spent, and it is mostly empty.

## Why the middle box is the expensive one

Discovery and reactivation are **one-off** costs: a search, a result, an
expansion. Residency is a **recurring** cost, because a resident tool schema
is part of every subsequent request.

For a tool with schema size `S` idle for `k` turns:

```
cost of holding it   =  S * k     (paid every turn it sits idle)
cost of dropping it  =  D         (paid once, on the way back)
```

where `D` is the cost of one re-search. The schema tokens on the turn the tool
is actually used are paid either way and cancel. Holding is cheaper only while
`k < D / S` — with a 700-token schema and a 150-token search, **less than one
idle turn**.

Taken literally that says "evict on last use, always," and the `alternating`
trace in the README shows why that is still wrong: `no-cache` thrashes on 98%
of its loads there. But the reason it is wrong is *not* the token arithmetic,
which really is that lopsided. It is latency, extra round trips, and the risk
that re-search fails — none of which appear in the inequality above. That
mismatch is the point: the token model alone will always push toward
aggressive eviction, so anything holding a policy back has to be justified on
some other axis, explicitly.

The same lopsidedness is why the sweep struggles to find a re-search price at
which never evicting wins. Even at an absurd 100,000 tokens per re-search, a
16-turn lookahead still edges out `search-only` on the 938-turn trace
(20.1M vs 20.3M) — though at that price the margin is under 1%, and simple
TTL policies have long since lost.

This is a much more one-sided inequality than intuition suggests, and it is
worth being precise about why the intuition fails. The instinctive question is
*"might I need this tool again?"* — to which the answer is almost always
"maybe, eventually." That question is not decision-relevant. The
decision-relevant question is *"is re-finding it reliable enough to bet on?"*,
which is a question about the retrieval system, not about the tool.

Which yields the one genuinely load-bearing coupling between the two halves:
**retrieval reliability sets the ceiling on eviction aggressiveness.**
Improving discovery is not only a discovery improvement — it buys permission
to evict harder.

## Why this is not classical cache replacement

The simulator includes `belady-min`, the classical optimum: never evict
anything that will be referenced again. It loses badly — 15.6M tokens against
2.6M for a crude 16-turn lookahead on `long_mixed`.

That is not a bug in the implementation. MIN is optimal for the problem it was
designed for, where:

- capacity is fixed and scarce,
- occupying a slot is free once you are in it,
- and the only cost is a miss.

A context window inverts the second assumption. Occupancy is precisely what
costs, and it costs *per turn*. So the objective is not "minimise misses
subject to capacity" but "minimise `Σ_t Σ_{i ∈ resident(t)} schema_tokens_i`
plus reload costs" — a rent-minimisation problem, not a hit-rate problem. The
right analogy from systems is not the CPU cache. It is a garbage collector, or
paging under memory *pressure* rather than a hard memory *limit*.

Two consequences that a hit-rate framing would miss:

- A tool that will definitely be used again in 200 turns should still be
  evicted now. MIN cannot express this. Reuse *distance* matters, not reuse.
- A large schema used occasionally can be worth evicting while a tiny schema
  used at the same rate is not. Size belongs in the policy; hit rate alone
  hides it.

## Why frequency and recency are not enough

`burst` is the counterexample, and it is deliberately unfair to the statistics
rather than to the policies: a tool called 26 times in a row, whose 26th call
is its last. At that instant it is simultaneously the most recently used and
the most frequently used tool in the session. Every access-history statistic
ranks it as the hottest thing in the cache, one turn before it becomes dead
weight.

What actually changed at that boundary was not observable in the access
history at all: a *phase completed*. That signal exists in the agent — it is
in the plan, the todo list, the sub-goal that just got marked done — but only
if the harness is built to record it. This is the strongest argument that a
good residency policy is not a pure cache policy: the information that would
make it accurate is semantic, cheap, and thrown away by most harnesses.

A related and even cheaper signal: when a tool's output has been **materialised
into a durable artifact** — a file on disk, a row in a table — downstream steps
depend on the artifact, not on the producing tool. The producer can be evicted
the moment the artifact exists, with no prediction involved at all.

Neither signal is implemented here. `Step.phase` is recorded in every trace and
read by no policy in v0.1, because the point of v0.1 is to establish the
headroom before anyone spends effort filling it.

## Why not just wait for compaction

Context compaction is the standard answer to "the context is filling up", and
it is a poor substitute for residency management on three counts:

1. **It fires too late.** Compaction is triggered by pressure, near the limit.
   Everything spent up to that point was already spent — RTT is an integral,
   and you cannot reclaim area under a curve retroactively.
2. **It targets the wrong thing.** Compaction drops tool *results* and
   summarises history. Tool *definitions* are typically structural and survive
   it. The staircase in the README is made of definitions.
3. **It is lossy in a way eviction is not.** A summarised conversation cannot
   be restored. An evicted tool schema can be restored exactly, from the
   registry, byte for byte. Tool schemas are an unusually forgiving eviction
   target — large, self-contained, and losslessly restorable — which is what
   makes it strange that they are not the *first* thing scheduled.

## What would count as evidence against all this

Stated up front, so the repo can be wrong in a checkable way:

- A trace, plausibly shaped like real agent work, where `search-only` beats
  every evicting policy on total tokens at a realistic re-search cost. The
  sweep is the place to demonstrate it.
- A demonstration that resident tool count has no measurable effect on tool
  call quality for small models, which would remove the second motivation for
  bounding the working set and leave only the token argument.
- Evidence that prompt caching makes the residency term cheap enough in
  practice to stop mattering. This is the most plausible of the three, and it
  is the reason caching is called out as an unmodelled limitation rather than
  buried.

## Open questions

- **What is the right pressure signal?** Level, or trend? "35% utilisation,
  flat for 20 turns" and "35% and climbing 4 → 7 → 11 → 14 → 18 resident tools"
  read identically to a threshold and mean very different things.
- **Does the weak generational hypothesis hold for tools?** Generational GC
  works because most objects die young and survivors keep surviving. Whether
  tool usage has that shape is an assumption, not a measurement, and it is
  checkable against real traces.
- **Where does tool-call error rate actually start climbing** for an 8B–30B
  local model as resident tool count grows? The 30–50 figure in Anthropic's
  documentation is for a frontier model. A smaller model's ceiling is almost
  certainly lower, and it is directly measurable rather than something to
  assume by analogy.
- **What is the cheapest useful WARM tier?** Keeping a few tens of bytes per
  evicted tool — an id and a capability tag — may make reactivation a lookup
  instead of a search, which would lower `D` and, by the inequality above,
  license more aggressive eviction.
