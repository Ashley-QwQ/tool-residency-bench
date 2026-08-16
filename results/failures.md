
### long_mixed - simulated failures, profile persistent, 40 seeds, retries=2, L_fail=100,000

| policy | mean total tokens | mean unrecovered failures | mean reloads | clean sessions |
|---|---|---|---|---|
| search-only | 17,692,490 | 0.00 | 0 | 40/40 |
| ttl-20 | 6,647,948 | 2.98 | 149 | 1/40 |
| ski-rental | 2,248,162 | 3.08 | 796 | 1/40 |
| adaptive-ski | 2,250,630 | 5.05 | 796 | 0/40 |
| min-loads | 15,592,740 | 0.00 | 0 | 40/40 |

Tokens and unrecovered failures are two axes, not one. A policy that is cheaper *and* fails more has moved along the trade-off, not beaten it.

### long_tail - simulated failures, profile persistent, 40 seeds, retries=2, L_fail=100,000

| policy | mean total tokens | mean unrecovered failures | mean reloads | clean sessions |
|---|---|---|---|---|
| search-only | 1,135,110 | 0.00 | 0 | 40/40 |
| ttl-20 | 345,360 | 0.00 | 0 | 40/40 |
| ski-rental | 152,850 | 0.00 | 228 | 40/40 |
| adaptive-ski | 108,230 | 0.00 | 47 | 40/40 |
| min-loads | 170,880 | 0.00 | 0 | 40/40 |

Tokens and unrecovered failures are two axes, not one. A policy that is cheaper *and* fails more has moved along the trade-off, not beaten it.
