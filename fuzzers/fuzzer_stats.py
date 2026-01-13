"""
Fawkes Fuzzer Statistics Tracker

Tracks detailed fuzzing statistics for progress monitoring and optimization.
"""

import json
import time
import logging
from pathlib import Path
from typing import Dict, List
from datetime import datetime, timedelta
from collections import defaultdict


logger = logging.getLogger("fawkes.fuzzer_stats")


class FuzzerStats:
    """
    Tracks comprehensive fuzzing statistics.

    Metrics tracked:
    - Executions per second (current and average)
    - Total testcases executed
    - Crashes found (by type)
    - Strategy effectiveness
    - Corpus coverage
    - Time elapsed
    """

    def __init__(self, stats_file: str = None):
        self.stats_file = stats_file
        self.start_time = time.time()
        self.last_update = self.start_time

        # Execution stats
        self.total_execs = 0
        self.last_execs = 0
        self.execs_per_sec_current = 0.0
        self.execs_per_sec_avg = 0.0

        # Crash stats
        self.crashes_total = 0
        self.crashes_by_type = defaultdict(int)
        self.unique_crashes = set()

        # Strategy stats
        self.strategy_stats = defaultdict(lambda: {"attempts": 0, "crashes": 0})

        # Corpus stats
        self.corpus_size = 0
        self.corpus_processed = 0

        # Timing
        self.elapsed_time = 0

    def record_execution(self):
        """Record a single testcase execution"""
        self.total_execs += 1

    def record_crash(self, crash_type: str, crash_sig: str, strategy: str = None):
        """
        Record a crash discovery.

        Args:
            crash_type: Type of crash (buffer_overflow, null_pointer, etc.)
            crash_sig: Unique crash signature (e.g., hash of backtrace)
            strategy: Mutation strategy that found the crash
        """
        self.crashes_total += 1
        self.crashes_by_type[crash_type] += 1

        if crash_sig not in self.unique_crashes:
            self.unique_crashes.add(crash_sig)
            logger.info(f"New unique crash found: {crash_type} (total unique: {len(self.unique_crashes)})")

        if strategy:
            self.strategy_stats[strategy]["crashes"] += 1

    def record_strategy_use(self, strategy: str):
        """Record usage of a mutation strategy"""
        self.strategy_stats[strategy]["attempts"] += 1

    def update(self):
        """Update calculated statistics (call periodically)"""
        now = time.time()
        self.elapsed_time = now - self.start_time

        # Calculate exec/sec
        time_delta = now - self.last_update
        if time_delta > 0:
            execs_delta = self.total_execs - self.last_execs
            self.execs_per_sec_current = execs_delta / time_delta
            self.last_execs = self.total_execs
            self.last_update = now

        if self.elapsed_time > 0:
            self.execs_per_sec_avg = self.total_execs / self.elapsed_time

    def get_stats(self) -> Dict:
        """Get all statistics as a dictionary"""
        self.update()

        return {
            "elapsed_time": self.elapsed_time,
            "total_execs": self.total_execs,
            "execs_per_sec_current": self.execs_per_sec_current,
            "execs_per_sec_avg": self.execs_per_sec_avg,
            "crashes_total": self.crashes_total,
            "crashes_unique": len(self.unique_crashes),
            "crashes_by_type": dict(self.crashes_by_type),
            "corpus_size": self.corpus_size,
            "corpus_processed": self.corpus_processed,
            "corpus_progress": (self.corpus_processed / max(1, self.corpus_size)) * 100,
            "strategy_stats": dict(self.strategy_stats),
        }

    def get_strategy_rankings(self) -> List[tuple]:
        """
        Get mutation strategies ranked by effectiveness.

        Returns:
            List of (strategy, crash_rate, attempts, crashes)
        """
        rankings = []

        for strategy, stats in self.strategy_stats.items():
            attempts = stats["attempts"]
            crashes = stats["crashes"]
            crash_rate = (crashes / max(1, attempts)) * 100

            rankings.append((strategy, crash_rate, attempts, crashes))

        # Sort by crash rate descending
        rankings.sort(key=lambda x: x[1], reverse=True)

        return rankings

    def print_summary(self):
        """Print a human-readable statistics summary"""
        stats = self.get_stats()

        elapsed = timedelta(seconds=int(stats["elapsed_time"]))

        print("\n" + "="*60)
        print("FUZZER STATISTICS")
        print("="*60)
        print(f"Elapsed time:         {elapsed}")
        print(f"Total executions:     {stats['total_execs']:,}")
        print(f"Exec/sec (current):   {stats['execs_per_sec_current']:.2f}")
        print(f"Exec/sec (average):   {stats['execs_per_sec_avg']:.2f}")
        print()
        print(f"Crashes found:        {stats['crashes_total']}")
        print(f"Unique crashes:       {stats['crashes_unique']}")
        print()
        print("Crashes by type:")
        for crash_type, count in sorted(stats['crashes_by_type'].items(), key=lambda x: -x[1]):
            print(f"  {crash_type:20s}  {count:5d}")
        print()
        print(f"Corpus progress:      {stats['corpus_progress']:.1f}% "
              f"({stats['corpus_processed']}/{stats['corpus_size']})")
        print("="*60)

        if stats['strategy_stats']:
            print("\nTOP MUTATION STRATEGIES (by crash rate):")
            print("-" * 60)
            rankings = self.get_strategy_rankings()
            for i, (strategy, crash_rate, attempts, crashes) in enumerate(rankings[:10], 1):
                print(f"{i:2d}. {strategy:20s}  "
                      f"Rate: {crash_rate:6.2f}%  "
                      f"Crashes: {crashes:4d}  "
                      f"Attempts: {attempts:6d}")
            print("="*60)

    def save_to_file(self, filepath: str = None):
        """Save statistics to JSON file"""
        if filepath is None:
            filepath = self.stats_file

        if filepath is None:
            logger.warning("No stats file specified, skipping save")
            return

        stats = self.get_stats()
        stats["timestamp"] = datetime.now().isoformat()

        try:
            with open(filepath, "w") as f:
                json.dump(stats, f, indent=2)
            logger.debug(f"Saved stats to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save stats: {e}")

    def load_from_file(self, filepath: str = None):
        """Load statistics from JSON file"""
        if filepath is None:
            filepath = self.stats_file

        if filepath is None or not Path(filepath).exists():
            logger.debug("No stats file to load")
            return

        try:
            with open(filepath, "r") as f:
                stats = json.load(f)

            self.total_execs = stats.get("total_execs", 0)
            self.crashes_total = stats.get("crashes_total", 0)
            self.unique_crashes = set(stats.get("unique_crashes_list", []))
            self.crashes_by_type = defaultdict(int, stats.get("crashes_by_type", {}))
            self.corpus_size = stats.get("corpus_size", 0)
            self.corpus_processed = stats.get("corpus_processed", 0)

            # Restore strategy stats
            for strategy, s_stats in stats.get("strategy_stats", {}).items():
                self.strategy_stats[strategy] = s_stats

            logger.info(f"Loaded stats from {filepath}")
        except Exception as e:
            logger.error(f"Failed to load stats: {e}")


class EnergyScheduler:
    """
    Assigns 'energy' (number of mutations) to each corpus seed.
    Seeds that found crashes get more energy (more mutations).

    Inspired by AFL's power schedules.
    """

    def __init__(self, default_energy: int = 100):
        self.default_energy = default_energy
        self.seed_energy = {}  # seed_hash -> energy
        self.seed_crashes = defaultdict(int)  # seed_hash -> crash count

    def get_energy(self, seed_hash: str) -> int:
        """
        Get the number of mutations to perform for this seed.

        Seeds that found crashes get boosted energy.
        """
        base_energy = self.seed_energy.get(seed_hash, self.default_energy)

        # Boost energy for seeds that found crashes
        crashes = self.seed_crashes.get(seed_hash, 0)
        if crashes > 0:
            # Exponential boost: 2x per crash found (capped at 10x)
            boost = min(2 ** crashes, 10)
            return int(base_energy * boost)

        return base_energy

    def record_crash(self, seed_hash: str):
        """Record that this seed found a crash"""
        self.seed_crashes[seed_hash] += 1
        logger.info(f"Seed {seed_hash[:8]} found crash #{self.seed_crashes[seed_hash]}, "
                   f"energy boosted to {self.get_energy(seed_hash)}")

    def set_energy(self, seed_hash: str, energy: int):
        """Manually set energy for a seed"""
        self.seed_energy[seed_hash] = energy
