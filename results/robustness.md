
## Robustness over 300 randomly sampled workloads

Cost model: discovery=150, search_turn=True. Catalogs up to 1,000 tools, traces up to 1,500 turns, random phase structure, burstiness, recurrence and long-tail rate. Seeds 0..N, fully reproducible.

| claim | holds on |
|---|---|
| search-only costs >2x the optimum (accumulation is real) | **98.7%** of samples |
| min-loads costs >2x the optimum (wrong objective) | **92.3%** of samples |
| best TTL beats best count cap (rent != capacity) | **98.0%** of samples |
| ski-rental within 2x of the optimum (D/S is the right horizon) | **100.0%** of samples |
| every *heuristic* is Pareto-dominated | **95.7%** of samples |
| ski-rental reaches the Pareto frontier | **0.0%** of samples |

| cost relative to rent-optimal | p25 | median | p75 |
|---|---|---|---|
| search-only | 7.51x | **12.22x** | 21.60x |
| min-loads | 3.26x | **4.97x** | 7.48x |
| ski-rental | 1.08x | **1.13x** | 1.17x |
| best-ttl | 1.61x | **2.21x** | 3.10x |
