"""
Fawkes Persistent Mode / Snapshot Fuzzing Optimization

Provides ultra-fast fuzzing by keeping VMs running and using in-memory
snapshot restoration instead of full VM restarts.

Performance improvements:
- 10-100x speedup compared to full VM restarts
- Snapshot revert: ~10-50ms (vs 2-5 seconds for VM restart)
- In-process fuzzing: ~1-5ms per iteration (with custom harness)
"""

from .persistent_harness import PersistentFuzzHarness
from .snapshot_optimizer import SnapshotOptimizer

__all__ = ['PersistentFuzzHarness', 'SnapshotOptimizer']
