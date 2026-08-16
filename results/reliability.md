
### long_mixed

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

Reactivation exposure at p_fail=0.01 (why the two grids differ):

| policy | reactivations | P(session completes) |
|---|---|---|
| search-only | 0 | 100.0% |
| ttl-20 | 149 | 22.4% |
| ttl-5 | 245 | 8.5% |
| lru-8 | 145 | 23.3% |
| ski-rental | 912 | 0.0% |
| no-cache | 690 | 0.1% |
| min-loads | 0 | 100.0% |

### long_tail

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

Reactivation exposure at p_fail=0.01 (why the two grids differ):

| policy | reactivations | P(session completes) |
|---|---|---|
| search-only | 0 | 100.0% |
| ttl-20 | 0 | 100.0% |
| ttl-5 | 14 | 86.9% |
| lru-8 | 0 | 100.0% |
| ski-rental | 228 | 10.1% |
| no-cache | 87 | 41.7% |
| min-loads | 0 | 100.0% |
