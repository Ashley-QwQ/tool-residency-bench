
### long_mixed - failure profile: uniform

**Cheapest by expected tokens** (reliability ignored)

| p_fail \ L_fail | 0 | 1,000 | 10,000 | 100,000 |
|---|---|---|---|---|
| 0 | ski-rental | ski-rental | ski-rental | ski-rental |
| 0.001 | ski-rental | ski-rental | ski-rental | ski-rental |
| 0.01 | ski-rental | ski-rental | ski-rental | ski-rental |
| 0.05 | ski-rental | ski-rental | ski-rental | ski-rental |
| 0.1 | ski-rental | ski-rental | ski-rental | ttl-5 |

**Cheapest with P(session completes) >= 95%**

| p_fail \ L_fail | 0 | 1,000 | 10,000 | 100,000 |
|---|---|---|---|---|
| 0 | ski-rental | ski-rental | ski-rental | ski-rental |
| 0.001 | min-loads | min-loads | min-loads | min-loads |
| 0.01 | min-loads | min-loads | min-loads | min-loads |
| 0.05 | min-loads | min-loads | min-loads | min-loads |
| 0.1 | min-loads | min-loads | min-loads | min-loads |

Reactivation exposure at mean p_fail=0.01, L_fail=10,000 (why the two grids differ):

| policy | reactivations | riskiest tool reloaded | P(session completes) | rent |
|---|---|---|---|---|
| search-only | 0 | p=0 | 100.0% | 17,432,290 |
| ttl-20 | 149 | p=0.01 | 22.4% | 5,465,720 |
| ttl-5 | 245 | p=0.01 | 8.5% | 3,096,400 |
| lru-8 | 145 | p=0.01 | 23.3% | 6,455,970 |
| ski-rental | 892 | p=0.01 | 0.0% | 814,550 |
| no-cache | 690 | p=0.01 | 0.1% | 1,426,360 |
| min-loads | 0 | p=0 | 100.0% | 15,339,210 |

### long_tail - failure profile: uniform

**Cheapest by expected tokens** (reliability ignored)

| p_fail \ L_fail | 0 | 1,000 | 10,000 | 100,000 |
|---|---|---|---|---|
| 0 | ski-rental | ski-rental | ski-rental | ski-rental |
| 0.001 | ski-rental | ski-rental | ski-rental | ski-rental |
| 0.01 | ski-rental | ski-rental | ski-rental | ski-rental |
| 0.05 | ski-rental | ski-rental | ski-rental | min-loads |
| 0.1 | ski-rental | ski-rental | ski-rental | min-loads |

**Cheapest with P(session completes) >= 95%**

| p_fail \ L_fail | 0 | 1,000 | 10,000 | 100,000 |
|---|---|---|---|---|
| 0 | ski-rental | ski-rental | ski-rental | ski-rental |
| 0.001 | min-loads | min-loads | min-loads | min-loads |
| 0.01 | min-loads | min-loads | min-loads | min-loads |
| 0.05 | min-loads | min-loads | min-loads | min-loads |
| 0.1 | min-loads | min-loads | min-loads | min-loads |

Reactivation exposure at mean p_fail=0.01, L_fail=10,000 (why the two grids differ):

| policy | reactivations | riskiest tool reloaded | P(session completes) | rent |
|---|---|---|---|---|
| search-only | 0 | p=0 | 100.0% | 1,091,910 |
| ttl-20 | 0 | p=0 | 100.0% | 336,730 |
| ttl-5 | 14 | p=0.01 | 86.9% | 197,530 |
| lru-8 | 0 | p=0 | 100.0% | 969,320 |
| ski-rental | 93 | p=0.01 | 39.3% | 77,800 |
| no-cache | 87 | p=0.01 | 41.7% | 104,500 |
| min-loads | 0 | p=0 | 100.0% | 162,250 |
