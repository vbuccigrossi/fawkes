"""
Fawkes Performance Monitoring and Metrics

Tracks performance metrics for fuzzing operations including:
- Executions per second (exec/sec)
- VM lifecycle times (start, stop, snapshot revert)
- Testcase generation and execution times
- Crash processing times
- Overall throughput

Usage:
    from fawkes.performance import PerformanceMonitor

    perf = PerformanceMonitor()

    with perf.measure("testcase_execution"):
        run_testcase()

    stats = perf.get_stats()
    print(f"Exec/sec: {stats['exec_per_sec']}")
"""

import time
import logging
from collections import defaultdict, deque
from typing import Dict, List, Optional, Any
from contextlib import contextmanager
from datetime import datetime, timedelta


class PerformanceMonitor:
    """Monitor and track fuzzing performance metrics."""

    def __init__(self, window_size: int = 100):
        """
        Initialize performance monitor.

        Args:
            window_size: Number of recent measurements to keep for rolling averages
        """
        self.logger = logging.getLogger("fawkes.performance")
        self.window_size = window_size

        # Timing measurements (rolling window)
        self.timings = defaultdict(lambda: deque(maxlen=window_size))

        # Counters
        self.counters = defaultdict(int)

        # Start time for overall metrics
        self.start_time = time.time()

        # Last exec/sec calculation
        self.last_exec_calc = time.time()
        self.last_exec_count = 0

    @contextmanager
    def measure(self, operation: str):
        """
        Context manager for measuring operation duration.

        Usage:
            with perf.measure("vm_start"):
                qemu_mgr.start_vm(...)
        """
        start = time.time()
        try:
            yield
        finally:
            duration = (time.time() - start) * 1000  # Convert to milliseconds
            self.record_timing(operation, duration)

    def record_timing(self, operation: str, duration_ms: float):
        """
        Record a timing measurement.

        Args:
            operation: Name of the operation
            duration_ms: Duration in milliseconds
        """
        self.timings[operation].append(duration_ms)
        self.counters[f"{operation}_count"] += 1

    def increment(self, counter: str, value: int = 1):
        """
        Increment a counter.

        Args:
            counter: Counter name
            value: Amount to increment (default: 1)
        """
        self.counters[counter] += value

    def get_average(self, operation: str) -> Optional[float]:
        """
        Get average time for an operation.

        Args:
            operation: Operation name

        Returns:
            Average duration in milliseconds, or None if no data
        """
        if operation not in self.timings or not self.timings[operation]:
            return None
        return sum(self.timings[operation]) / len(self.timings[operation])

    def get_percentile(self, operation: str, percentile: float) -> Optional[float]:
        """
        Get percentile time for an operation.

        Args:
            operation: Operation name
            percentile: Percentile (0-100)

        Returns:
            Duration at percentile in milliseconds, or None if no data
        """
        if operation not in self.timings or not self.timings[operation]:
            return None

        sorted_timings = sorted(self.timings[operation])
        index = int(len(sorted_timings) * (percentile / 100.0))
        return sorted_timings[min(index, len(sorted_timings) - 1)]

    def get_exec_per_sec(self) -> float:
        """
        Calculate current executions per second.

        Returns:
            Exec/sec rate
        """
        total_execs = self.counters.get("testcase_execution_count", 0)
        elapsed = time.time() - self.start_time

        if elapsed == 0:
            return 0.0

        return total_execs / elapsed

    def get_instantaneous_exec_per_sec(self) -> float:
        """
        Calculate instantaneous exec/sec based on recent activity.

        Returns:
            Recent exec/sec rate
        """
        now = time.time()
        total_execs = self.counters.get("testcase_execution_count", 0)

        elapsed = now - self.last_exec_calc
        if elapsed < 1.0:  # Don't calculate too frequently
            return self.get_exec_per_sec()

        execs_since_last = total_execs - self.last_exec_count
        rate = execs_since_last / elapsed if elapsed > 0 else 0.0

        self.last_exec_calc = now
        self.last_exec_count = total_execs

        return rate

    def get_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive performance statistics.

        Returns:
            Dictionary of performance metrics
        """
        stats = {
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "elapsed_seconds": time.time() - self.start_time,
            "exec_per_sec": self.get_exec_per_sec(),
            "exec_per_sec_recent": self.get_instantaneous_exec_per_sec(),
            "total_testcases": self.counters.get("testcase_execution_count", 0),
            "total_crashes": self.counters.get("crash_detected", 0),
            "timings": {},
            "counters": dict(self.counters)
        }

        # Add timing statistics for all measured operations
        for operation in self.timings.keys():
            if self.timings[operation]:
                stats["timings"][operation] = {
                    "avg_ms": self.get_average(operation),
                    "p50_ms": self.get_percentile(operation, 50),
                    "p95_ms": self.get_percentile(operation, 95),
                    "p99_ms": self.get_percentile(operation, 99),
                    "min_ms": min(self.timings[operation]),
                    "max_ms": max(self.timings[operation]),
                    "count": len(self.timings[operation])
                }

        return stats

    def print_stats(self):
        """Print formatted performance statistics."""
        stats = self.get_stats()

        print("\n" + "=" * 80)
        print("FAWKES PERFORMANCE STATISTICS")
        print("=" * 80)

        # Overall metrics
        print(f"\nOverall Metrics:")
        print(f"  Start Time:           {stats['start_time']}")
        print(f"  Elapsed:              {stats['elapsed_seconds']:.2f}s")
        print(f"  Total Testcases:      {stats['total_testcases']}")
        print(f"  Total Crashes:        {stats['total_crashes']}")
        print(f"  Exec/sec (average):   {stats['exec_per_sec']:.2f}")
        print(f"  Exec/sec (recent):    {stats['exec_per_sec_recent']:.2f}")

        # Timing breakdowns
        if stats["timings"]:
            print(f"\nTiming Breakdown:")
            print(f"  {'Operation':<30} {'Avg (ms)':<10} {'P50 (ms)':<10} {'P95 (ms)':<10} {'P99 (ms)':<10} {'Count':<10}")
            print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")

            for operation, timing in sorted(stats["timings"].items()):
                avg = timing["avg_ms"]
                p50 = timing["p50_ms"]
                p95 = timing["p95_ms"]
                p99 = timing["p99_ms"]
                count = timing["count"]

                print(f"  {operation:<30} {avg:<10.2f} {p50:<10.2f} {p95:<10.2f} {p99:<10.2f} {count:<10}")

        # Efficiency metrics
        if "snapshot_revert_fast" in stats["timings"] and "snapshot_revert_slow" in stats["timings"]:
            fast_avg = stats["timings"]["snapshot_revert_fast"]["avg_ms"]
            slow_avg = stats["timings"]["snapshot_revert_slow"]["avg_ms"]
            speedup = slow_avg / fast_avg if fast_avg > 0 else 0

            print(f"\nSnapshot Revert Optimization:")
            print(f"  Fast mode avg:        {fast_avg:.2f}ms")
            print(f"  Slow mode avg:        {slow_avg:.2f}ms")
            print(f"  Speedup:              {speedup:.2f}x")

        print("=" * 80 + "\n")

    def reset(self):
        """Reset all performance metrics."""
        self.timings.clear()
        self.counters.clear()
        self.start_time = time.time()
        self.last_exec_calc = time.time()
        self.last_exec_count = 0

    def get_summary(self) -> str:
        """
        Get a one-line performance summary.

        Returns:
            Summary string
        """
        stats = self.get_stats()
        return (f"Exec/sec: {stats['exec_per_sec']:.2f} | "
                f"Testcases: {stats['total_testcases']} | "
                f"Crashes: {stats['total_crashes']} | "
                f"Elapsed: {stats['elapsed_seconds']:.1f}s")


class PerformanceTracker:
    """
    Singleton performance tracker for global access.

    Usage:
        from fawkes.performance import perf_tracker

        with perf_tracker.measure("operation"):
            do_operation()

        perf_tracker.print_stats()
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = PerformanceMonitor()
        return cls._instance


# Global performance tracker instance
perf_tracker = PerformanceTracker()


def format_duration(ms: float) -> str:
    """
    Format duration in human-readable form.

    Args:
        ms: Duration in milliseconds

    Returns:
        Formatted string (e.g., "1.23s", "456ms", "12.3us")
    """
    if ms >= 1000:
        return f"{ms/1000:.2f}s"
    elif ms >= 1:
        return f"{ms:.0f}ms"
    elif ms >= 0.001:
        return f"{ms*1000:.1f}us"
    else:
        return f"{ms*1000000:.1f}ns"


def format_rate(rate: float) -> str:
    """
    Format rate in human-readable form.

    Args:
        rate: Rate value

    Returns:
        Formatted string (e.g., "1.2k/s", "456/s")
    """
    if rate >= 1000:
        return f"{rate/1000:.1f}k/s"
    else:
        return f"{rate:.1f}/s"
