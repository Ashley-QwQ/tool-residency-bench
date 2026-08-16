# When reactivation can fail

v0.1 priced residency and reactivation and found that aggressive eviction wins
on tokens almost everywhere. It also said, repeatedly, that this was an
artefact of the largest thing the model did not charge for: **retrieval never
failed**. This document adds that term and reports what changes.

The short version, in three steps, because the second one is a trap the first
version of this document fell into:

1. Priced as an i.i.d. global rate, failure **inverts the entire ranking** —
   the cheapest policy on tokens becomes the worst possible choice.
2. But that inversion is an **artefact of the i.i.d. assumption**. Real
   retrieval failure is per-tool and persistent, and modelling it that way
   substantially un-inverts the result: risk localises to specific tools, and
   so does residency.
3. Either way, the value of semantic knowledge lands somewhere different from
   where the v0.1 framing expected to find it.

```bash
python -m trb reliability -w long_mixed
python -m trb reliability -w long_mixed --failure-profile persistent
```

## Failure has two effects, and they do not behave alike

**As expected token cost, failure is linear and therefore boring.**
`D_i^eff = D_i^search + p_fail · L_fail` folds straight into the reactivation
price, so the closed form keeps working untouched and a two-axis sweep over
`(p_fail, L_fail)` collapses into the one-dimensional `D_eff` sweep that
already existed. That is worth stating rather than dressing up: on this axis,
failure is the reactivation-cost knob wearing a hat.

**As session reliability, failure is geometric and therefore decisive.**
Surviving `R` reactivations at failure rate `p` has probability `(1−p)^R`.
Nothing in a token budget can see this. Cost grows linearly in `R` while the
probability of getting through the session at all decays exponentially in it.

Same parameter. Two completely different shapes.

## The inversion

`long_mixed`, 938 turns, at `p_fail = 0.01` — a one-in-a-hundred failure rate,
which is optimistic for a real retriever:

| policy | reactivations | P(session completes) |
|---|---|---|
| search-only | 0 | **100.0%** |
| min-loads | 0 | **100.0%** |
| lru-8 | 145 | 23.3% |
| ttl-20 | 149 | 22.4% |
| ttl-5 | 245 | 8.5% |
| no-cache | 690 | 0.1% |
| ski-rental | 912 | **0.0%** |

`ski-rental` is the best policy in the entire repo on expected tokens — 1.04x
the offline optimum on this trace — and it is the *worst possible choice* here.
Not marginally: it will essentially never complete a session intact.

Cheapest policy, as a function of the two failure parameters:

```text
ignoring reliability                 requiring P(complete) >= 95%

p_fail | any L_fail                  p_fail | any L_fail
-------+---------------              -------+---------------
0      | ski-rental                  0      | ski-rental
0.001  | ski-rental                  0.001  | min-loads
0.01   | ski-rental                  0.01   | min-loads
0.05   | ski-rental                  0.05   | min-loads
0.1    | ski-rental                  0.1    | min-loads
```

The moment reactivation can fail *at all*, a reliability floor forces the
choice to a **zero-reload** policy, and among zero-reload policies the cheapest
is `min-loads`. The maximally aggressive policy and the maximally conservative
one swap places at `p_fail > 0`.

This is the sentence from v0.1 —

> retrieval reliability sets the ceiling on eviction aggressiveness

— turned into a boundary that can be pointed at rather than a slogan.

## Except that conclusion is an artefact of assuming failure is uniform

The table above gives every tool the same `p_fail`, which is the assumption
that seemed harmless enough to start with. It is not, and correcting it
changes the answer.

Retrieval failure is not a coin the universe re-tosses per attempt. A tool
with a vague name and a thin description is not *unlucky* — it is unfindable,
and it is unfindable every single time. A well-named one is findable every
time. The realistic distribution is not "every tool fails 1% of the time" but
"90% of tools never fail and 10% fail half the time." Both have a mean near
1%; they describe completely different worlds.

`Tool.failure_rate` sets `p_i` per tool, and `--failure-profile` spreads a mean
across the catalog in three shapes: `uniform` (the i.i.d. null hypothesis),
`mixed` (80% at a quarter the rate, 20% at four times), and `persistent` (90%
never, 10% at `p = 0.5`). Session survival becomes a **product over the tools
actually reactivated**, not `(1−p)^R` — because which tools a policy chooses to
reload is exactly what a residency policy controls.

With `persistent` on `long_mixed`, sweeping how expensive a failure is:

| L_fail | policy | reactivations | riskiest tool reloaded | P(completes) | rent |
|---|---|---|---|---|---|
| 0 | rent-optimal | 690 | p=0.5 | 0.0% | 805,290 |
| 10,000 | rent-optimal | 617 | p=0.5 | 0.0% | 940,380 |
| 100,000 | rent-optimal | 600 | p=0.5 | 0.0% | 1,371,530 |
| **1,000,000** | **rent-optimal** | **575** | **p=0.0001** | **94.4%** | 3,013,040 |
| 1,000,000 | ski-rental | 752 | p=0.0001 | 92.8% | 3,099,040 |

Read the fourth column. As failure gets expensive, the policy does not
gradually reload less — it **stops reloading the dangerous tools specifically**
while continuing to reload the safe ones 575 times. Session completion goes
from 0% to 94% while the reload count barely moves.

The mechanism needs no new machinery: a high `p_i` inflates `D_i^eff`, which
inflates `g*_i = D_i / S_i`, until the break-even gap exceeds any realistic
trace and the tool is simply never evicted. **Risk localises, and so does
residency.** A dangerous tool becomes effectively unevictable; everything else
stays as disposable as before.

So the corrected conclusion, and it is a materially different one:

```text
under uniform p_fail    reliability is bought by reloading LESS
                        -> a global aggressive/conservative trade-off
                        -> the only safe policies are zero-reload ones

under per-tool p_fail   reliability is bought by reloading DIFFERENT THINGS
                        -> a per-tool decision, not a global posture
                        -> 575 reactivations at 94% completion is available,
                           which the uniform model said was impossible
```

The v0.1 slogan survives but needs restating. It is not that retrieval
reliability caps how aggressive a policy may be. It is that **reliability caps
aggression per tool**, and a policy that cannot tell its tools apart is forced
to apply the worst tool's ceiling to all of them.

That is a second kind of per-tool knowledge the cost model cannot derive from
access history — alongside "which tools are dead", which is the semantic one.
Both are the same shape of answer: **the interesting information about a tool
is not in when it was last used.**

## What this does to the case for semantic eviction

The v0.1 story was: cheap deterministic rules capture most of the win, and
semantics is left fighting for the last few percent. `ski-rental`'s median
1.13x across 300 random workloads made that look close to a dead end.

The reliability grid says the v0.1 story was asking the wrong question — and
the per-tool correction above sharpens rather than removes that, because
`p_i` tells a policy which tools are *dangerous to lose* but says nothing at
all about which are *already finished*. Consider what separates the two
zero-reload policies:

- `search-only` reloads nothing because it **never evicts**. It pays full
  monotonic rent — 17.7M token-turns on `long_mixed`.
- `min-loads` reloads nothing because it **only evicts what is never needed
  again**. It pays 15.6M, and would pay far less on a trace with more dead
  tools.

Both are perfectly reliable. One of them is doing real work. The difference
between them is not aggressiveness — it is **knowing which tools are dead**.

And that is exactly what a phase boundary, a completed plan item, or a
materialised artifact tells you. `min-loads` is, functionally, a *perfect
semantic policy*: it evicts precisely what will never be used again, and
therefore evicts at **zero reactivation exposure**.

So the role of semantics is not what v0.1 implicitly assumed:

```text
v0.1 framing   semantics helps you evict SOONER
               -> competes with ski-rental on token cost
               -> ~1.13x of optimum already taken, little left to win

v0.2 framing   semantics helps you evict WITHOUT EXPOSURE
               -> competes with min-loads on reload count
               -> the entire gap between 15.6M and 0.9M is contestable,
                  and no cost-model-only policy can touch it
```

A tool whose owning phase has completed can be dropped with a reload
probability of zero, because it is genuinely finished — not because a
`D/S` threshold expired and we are gambling that it will not come back. The
ski-rental barrier of 2x applies to policies reasoning about *cost*. A policy
reasoning about *task structure* is not playing that game at all: it is trying
to reduce `R`, not to spend it well.

This also retroactively explains the original motivating example. Grayscale
called 26 times and then finished is not interesting because it is expensive
to hold — it is interesting because the phase boundary makes it evictable at
**no risk**, which no recency, frequency, or `D/S` rule can ever establish.

## What v0.3 has to beat

Two baselines, not one, and they bracket the problem from opposite sides:

| baseline | knows | strength | weakness |
|---|---|---|---|
| `ski-rental` | costs, including `p_i` | 1.13x median on tokens | reloads whatever is cheap to reload, safe or not, unless `p_i` is supplied |
| `min-loads` | the future | zero reloads, perfectly reliable | not implementable; leaves rent on the table |

Note that `ski-rental` already handles per-tool risk *correctly* once `p_i` is
supplied — that is the 94% row above. So the open problem is not "make the
policy risk-aware"; the cost model does that on its own. It is **where `p_i`
and 'this tool is dead' come from**, and neither is in the access history.

A semantic policy is interesting exactly to the degree that it is **near
ski-rental on rent while near min-loads on reload count**. That is a
two-dimensional target on the Pareto plot, and it is currently empty.

## Limitations of this model, in turn

- `p_i` is per tool but still independent across attempts *for that tool*. The
  fully faithful version is closer to deterministic: a tool is findable or it
  is not, and `p_i` near 0 or near 1 with little in between. The `persistent`
  profile approximates this; a genuinely bimodal model would go further.
- Nothing measures `p_i`. It is an input here. A real system would have to
  estimate it — from description quality, catalog ambiguity, or simply from
  observed re-search outcomes, which is the cheapest option and requires only
  that the harness records whether a re-search found what it went looking for.
- `L_fail` is a single number. A failure that costs a retry and a failure that
  ends the task are not the same event, and collapsing them is a
  simplification, though the reliability grid partly sidesteps this by asking
  about completion probability rather than cost.
- First loads are assumed to succeed. Only reloads carry exposure here, on the
  grounds that every on-demand policy pays the same first loads, so it is the
  differential that distinguishes policies. Absolute completion probabilities
  are therefore optimistic for all of them equally.
- No recovery model: a failed reactivation is not retried, re-planned around,
  or escalated. A real agent would do all three.
