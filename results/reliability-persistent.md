
### long_mixed - failure profile: persistent

**Cheapest by expected tokens** (reliability ignored)

| p_fail \ L_fail | 0 | 1,000 | 10,000 | 100,000 |
|---|---|---|---|---|
| 0 | ski-rental | ski-rental | ski-rental | ski-rental |
| 0.001 | ski-rental | ski-rental | ski-rental | ski-rental |
| 0.01 | ski-rental | ski-rental | ski-rental | ski-rental |
| 0.05 | ski-rental | ski-rental | ski-rental | ski-rental |
| 0.1 | ski-rental | ski-rental | ski-rental | ski-rental |

**Cheapest with P(session completes) >= 95%**

| p_fail \ L_fail | 0 | 1,000 | 10,000 | 100,000 |
|---|---|---|---|---|
| 0 | min-loads | min-loads | min-loads | min-loads |
| 0.001 | min-loads | min-loads | min-loads | min-loads |
| 0.01 | min-loads | min-loads | min-loads | min-loads |
| 0.05 | min-loads | min-loads | min-loads | min-loads |
| 0.1 | min-loads | min-loads | min-loads | min-loads |

Reactivation exposure at mean p_fail=0.01, L_fail=10,000 (why the two grids differ):

| policy | reactivations | riskiest tool reloaded | P(session completes) | rent |
|---|---|---|---|---|
| search-only | 0 | p=0 | 100.0% | 17,432,290 |
| ttl-20 | 149 | p=0.5 | 0.0% | 5,465,720 |
| ttl-5 | 245 | p=0.5 | 0.0% | 3,096,400 |
| lru-8 | 145 | p=0.5 | 0.0% | 6,455,970 |
| ski-rental | 807 | p=0.5 | 0.0% | 1,102,430 |
| no-cache | 690 | p=0.5 | 0.0% | 1,426,360 |
| min-loads | 0 | p=0 | 100.0% | 15,339,210 |
