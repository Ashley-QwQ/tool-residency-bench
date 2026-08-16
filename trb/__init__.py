"""tool-residency-bench: measuring how long a loaded tool should stay loaded.

Tool discovery answers *what* to load. It does not answer *when to unload it*.
This package simulates the second question in isolation, with discovery held
at a perfect oracle so nothing else can explain the results.
"""

from .model import CostModel, Step, Tool, Workload, load_all, load_catalog, load_workload
from .policies import Policy, build, default_policies
from .simulator import Result, run, run_matrix

__version__ = "0.1.0"

__all__ = [
    "CostModel", "Step", "Tool", "Workload",
    "load_all", "load_catalog", "load_workload",
    "Policy", "build", "default_policies",
    "Result", "run", "run_matrix",
]
