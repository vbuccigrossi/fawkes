"""
Fawkes Differential Fuzzing

Compare behavior across different versions/implementations to find
semantic bugs and behavioral divergences.
"""

from .engine import (
    DifferentialEngine,
    ExecutionResult,
    Divergence,
    DivergenceType,
    DivergenceSeverity
)

from .harness import (
    DifferentialHarness,
    DifferentialTarget
)

from .db import DifferentialDB

__all__ = [
    "DifferentialEngine",
    "ExecutionResult",
    "Divergence",
    "DivergenceType",
    "DivergenceSeverity",
    "DifferentialHarness",
    "DifferentialTarget",
    "DifferentialDB"
]
