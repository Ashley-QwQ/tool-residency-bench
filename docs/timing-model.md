# Event semantics of a turn

This document exists because a one-turn difference in *when* eviction takes
effect was worth **2x** on `long_tail`. `no-cache` and the `D -> 0` limit of
`rent-optimal` make the same decision — drop the tool once it is done — and
differ only in that `no-cache` acts a turn later. That is not a detail.

Anyone comparing residency policies, here or elsewhere, is comparing timing
conventions as much as policies. So the convention is written down rather than
left to be inferred from the code.

## The order, exactly as implemented

`trb/simulator.py`, one iteration of the loop:

```
turn t begins
    |
    |  resident set carried in from turn t-1
    v
(1) the trace declares the tools this turn needs
    |     perfect oracle discovery: the agent is never wrong about *what*
    v
(2) misses computed against the carried-in resident set
    |
    |     if there is at least one miss:
    |       - one search event is charged: `discovery_tokens`
    |       - if `search_turn`: one extra request is charged, carrying the
    |         schemas resident *before* this turn's admissions
    |       - each missing tool is charged its `reactivation_tokens` surcharge
    v
(3) admission: every missing tool becomes resident
    |
    v
(4) RENT CHARGED for this turn: every resident schema, including the ones
    |  admitted a moment ago in step 3
    v
(5) the tool executes (not modelled - no outputs, no failures, no latency)
    |
    v
(6) the policy observes the post-use state: it sees which tools were used
    |  at turn t, with `last_use[tool] = t` already updated
    v
(7) eviction: whatever the policy returns is removed
    |
    v
turn t ends - the surviving set is what turn t+1 carries in
```

## The five questions this pins down

**Does eviction take effect this turn or the next?**
The next. Rent for turn `t` is charged at step 4, before the policy is
consulted at step 7. A tool evicted at the end of turn `t` has already been
paid for on turn `t` and first saves money on turn `t+1`.

*Consequence:* a policy cannot retroactively avoid the cost of a tool it
decides at the end of the turn it no longer wants. This is what makes
`no-cache` — which evicts everything except the most recently used tool —
carry each dead tool for exactly one extra request. Over 240 turns on
`long_tail` that lag alone is the difference between 104,500 and 67,930
token-turns.

**Does a newly loaded tool pay rent on the turn it is loaded?**
Yes, at step 4. It is genuinely in the request that uses it, so it is genuinely
being paid for. This cost is identical for every on-demand policy and cancels
out of any comparison between them, but it is included so that absolute
numbers mean something.

**When is reactivation charged?**
At step 2, on the turn the tool turns out to be needed — not when it was
evicted. Eviction itself is free. The bill arrives on return.

**What happens after a tool's last use?**
Nothing is charged after the final turn of the trace, so the offline policies
deliberately do *not* evict at the end: dropping everything on the last turn
would cost nothing and save nothing, and counting those as evictions would
inflate the eviction statistics without changing any cost. A tool dropped
mid-trace and never needed again simply stops paying rent from the next turn.

**How are multiple tools in one turn handled?**
`Step.tools` is a tuple, so a turn may need several. They are all admitted
before rent is charged, so they are all resident simultaneously. Discovery is
**batched**: one search event covers every tool missing that turn, on the
grounds that a real agent searching for three missing tools does not run three
separate searches. Per-tool `reactivation_tokens` surcharges are still charged
per tool.

The v0.1 traces all use exactly one tool per turn, so batching never actually
merges anything in the shipped results. This is checked, not assumed:
`test_batching_alone_does_not_break_the_closed_form` verifies by exhaustive
search that batching alone never lets two tools share a reactivation in a way
that beats the per-tool rule.

## Where this convention costs the closed form exactness

Under `search_turn = True` a search costs an extra request that carries the
currently resident schemas. So an idle turn on which a search happens charges
a held tool's rent **twice** — once for the search request, once for the turn's
own request. The true cost of holding a tool across a gap is therefore

```
S * (idle turns + searches occurring during those turns)
```

while the closed form in `RentOptimal` assumes `S * idle turns`. The rule
consequently holds on marginally too long, never too briefly.

This is measured rather than hoped: `tests/test_optimality.py` enumerates
every possible eviction schedule on small traces and compares.

| cost model | closed form vs. true optimum |
|---|---|
| reactivation per load, no search-turn rent | **exact** — the Proposition's assumptions |
| batching only | exact |
| default (batching + search-turn rent) | up to **1.06x**, one-sided |

If that 1.06x ever grows, the claim in the README needs revisiting — not the
threshold in the test.

## What is deliberately not modelled

Listed so nobody has to reverse-engineer the absence:

- tool execution time, output size, or failure;
- retrieval *discovery* is still a perfect oracle: the agent always knows
  which tool it needs. Reactivation **failure** is modelled as of v0.2, per
  tool, but a failed reactivation is priced rather than simulated - there is
  no retry, no re-plan, and no alternative-tool search (see docs/reliability.md);
- prompt caching and KV-cache reuse, so `rent` here is *logical* context
  occupancy rather than recomputation (see the README's three axes);
- any effect of resident tool count on the model's own behaviour;
- the cost of running the residency policy itself.
