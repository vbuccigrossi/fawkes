"""
Fawkes Crash Deduplicator

Identifies unique crashes and groups duplicates using stack hashing.
"""

import logging
from typing import Dict, List, Set, Tuple
from collections import defaultdict
from datetime import datetime

from .stack_hasher import StackHasher


logger = logging.getLogger("fawkes.deduplicator")


class CrashDeduplicator:
    """
    Deduplicates crashes using stack hashing.

    Features:
    - Track unique crashes by stack hash
    - Group duplicate crashes
    - Maintain crash statistics
    - Identify crash "buckets" (groups of similar crashes)
    """

    def __init__(self, stack_depth: int = 10, ignore_system_libs: bool = True):
        """
        Initialize crash deduplicator.

        Args:
            stack_depth: Number of stack frames to consider
            ignore_system_libs: Skip system library frames in hash
        """
        self.hasher = StackHasher(depth=stack_depth, ignore_system_libs=ignore_system_libs)

        # Track unique crashes: stack_hash -> crash_info
        self.unique_crashes: Dict[str, Dict] = {}

        # Track all crashes: crash_id -> crash_info
        self.all_crashes: Dict[str, Dict] = {}

        # Crash buckets: stack_hash -> list of crash_ids
        self.crash_buckets: Dict[str, List[str]] = defaultdict(list)

        # Statistics
        self.total_crashes = 0
        self.unique_count = 0
        self.duplicate_count = 0

    def add_crash(self,
                  crash_id: str,
                  backtrace: List[Dict],
                  crash_type: str = None,
                  crash_address: str = None,
                  testcase_path: str = None,
                  metadata: Dict = None) -> Tuple[bool, str]:
        """
        Add a crash and determine if it's unique.

        Args:
            crash_id: Unique identifier for this crash
            backtrace: Stack backtrace
            crash_type: Type of crash (e.g., "SIGSEGV")
            crash_address: Memory address where crash occurred
            testcase_path: Path to crashing testcase
            metadata: Additional metadata

        Returns:
            Tuple of (is_unique, stack_hash)
        """
        # Generate stack hash
        stack_hash = self.hasher.get_crash_signature(backtrace, crash_type)

        # Create crash info
        crash_info = {
            'crash_id': crash_id,
            'stack_hash': stack_hash,
            'crash_type': crash_type,
            'crash_address': crash_address,
            'backtrace': backtrace,
            'testcase_path': testcase_path,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }

        # Store in all crashes
        self.all_crashes[crash_id] = crash_info

        # Add to bucket
        self.crash_buckets[stack_hash].append(crash_id)

        # Update statistics
        self.total_crashes += 1

        # Check if unique
        is_unique = stack_hash not in self.unique_crashes

        if is_unique:
            # First time seeing this crash
            self.unique_crashes[stack_hash] = crash_info
            self.unique_count += 1
            logger.info(f"New unique crash: {crash_id} (stack_hash: {stack_hash[:16]}...)")
        else:
            # Duplicate crash
            self.duplicate_count += 1
            logger.debug(f"Duplicate crash: {crash_id} matches {stack_hash[:16]}...")

        return is_unique, stack_hash

    def is_unique(self, backtrace: List[Dict], crash_type: str = None) -> bool:
        """
        Check if crash is unique without adding it.

        Args:
            backtrace: Stack backtrace
            crash_type: Crash type

        Returns:
            True if crash is unique
        """
        stack_hash = self.hasher.get_crash_signature(backtrace, crash_type)
        return stack_hash not in self.unique_crashes

    def get_bucket(self, stack_hash: str) -> List[str]:
        """
        Get all crash IDs in a bucket.

        Args:
            stack_hash: Stack hash identifying the bucket

        Returns:
            List of crash IDs in this bucket
        """
        return self.crash_buckets.get(stack_hash, [])

    def get_unique_crashes(self) -> List[Dict]:
        """
        Get list of all unique crashes.

        Returns:
            List of crash info dicts
        """
        return list(self.unique_crashes.values())

    def get_crash_info(self, crash_id: str) -> Dict:
        """
        Get crash info by ID.

        Args:
            crash_id: Crash identifier

        Returns:
            Crash info dict or None
        """
        return self.all_crashes.get(crash_id)

    def get_statistics(self) -> Dict:
        """
        Get deduplication statistics.

        Returns:
            Dict with statistics
        """
        bucket_sizes = [len(bucket) for bucket in self.crash_buckets.values()]

        stats = {
            'total_crashes': self.total_crashes,
            'unique_crashes': self.unique_count,
            'duplicate_crashes': self.duplicate_count,
            'dedup_ratio': (self.duplicate_count / max(1, self.total_crashes)) * 100,
            'total_buckets': len(self.crash_buckets),
            'avg_bucket_size': sum(bucket_sizes) / max(1, len(bucket_sizes)),
            'max_bucket_size': max(bucket_sizes) if bucket_sizes else 0,
        }

        return stats

    def get_top_crashes(self, n: int = 10) -> List[Tuple[str, int, Dict]]:
        """
        Get top N most frequently occurring crashes.

        Args:
            n: Number of top crashes to return

        Returns:
            List of (stack_hash, count, crash_info) tuples
        """
        # Count crashes per bucket
        crash_counts = [
            (stack_hash, len(crashes), self.unique_crashes[stack_hash])
            for stack_hash, crashes in self.crash_buckets.items()
        ]

        # Sort by count descending
        crash_counts.sort(key=lambda x: x[1], reverse=True)

        return crash_counts[:n]

    def print_summary(self):
        """Print human-readable summary of crashes."""
        stats = self.get_statistics()

        print("\n" + "=" * 60)
        print("CRASH DEDUPLICATION SUMMARY")
        print("=" * 60)
        print(f"Total crashes:        {stats['total_crashes']}")
        print(f"Unique crashes:       {stats['unique_crashes']}")
        print(f"Duplicate crashes:    {stats['duplicate_crashes']}")
        print(f"Deduplication ratio:  {stats['dedup_ratio']:.1f}%")
        print()
        print(f"Total buckets:        {stats['total_buckets']}")
        print(f"Avg bucket size:      {stats['avg_bucket_size']:.1f}")
        print(f"Max bucket size:      {stats['max_bucket_size']}")
        print("=" * 60)

        if self.unique_count > 0:
            print("\nTOP CRASHES (by occurrence):")
            print("-" * 60)
            top_crashes = self.get_top_crashes(10)

            for i, (stack_hash, count, crash_info) in enumerate(top_crashes, 1):
                crash_type = crash_info.get('crash_type', 'unknown')
                crash_id = crash_info.get('crash_id', 'unknown')

                print(f"{i:2d}. {crash_type:20s}  "
                      f"Count: {count:4d}  "
                      f"Hash: {stack_hash[:12]}...  "
                      f"First: {crash_id}")

            print("=" * 60)

    def export_buckets(self, output_file: str):
        """
        Export crash buckets to JSON file.

        Args:
            output_file: Path to output JSON file
        """
        import json

        export_data = {
            'statistics': self.get_statistics(),
            'unique_crashes': [
                {
                    'stack_hash': stack_hash,
                    'crash_type': info.get('crash_type'),
                    'crash_address': info.get('crash_address'),
                    'count': len(self.crash_buckets[stack_hash]),
                    'first_seen': info.get('timestamp'),
                    'testcase': info.get('testcase_path'),
                }
                for stack_hash, info in self.unique_crashes.items()
            ],
            'buckets': {
                stack_hash: [
                    self.all_crashes[crash_id].get('crash_id')
                    for crash_id in crashes
                ]
                for stack_hash, crashes in self.crash_buckets.items()
            }
        }

        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Exported crash buckets to {output_file}")


# Example usage
if __name__ == "__main__":
    # Create deduplicator
    dedup = CrashDeduplicator()

    # Simulate finding crashes
    print("Simulating crash discovery...\n")

    # Crash 1: Buffer overflow
    backtrace1 = [
        {'function': 'memcpy', 'file': 'string.c', 'line': 42},
        {'function': 'copy_data', 'file': 'app.c', 'line': 156},
        {'function': 'main', 'file': 'app.c', 'line': 200},
    ]
    is_unique, hash1 = dedup.add_crash(
        crash_id="crash_001",
        backtrace=backtrace1,
        crash_type="buffer_overflow",
        testcase_path="/crashes/crash_001.bin"
    )
    print(f"Crash 001: unique={is_unique}, hash={hash1[:16]}...")

    # Crash 2: Same as crash 1 (different testcase)
    backtrace2 = [
        {'function': 'memcpy', 'file': 'string.c', 'line': 42},
        {'function': 'copy_data', 'file': 'app.c', 'line': 156},
        {'function': 'main', 'file': 'app.c', 'line': 200},
    ]
    is_unique, hash2 = dedup.add_crash(
        crash_id="crash_002",
        backtrace=backtrace2,
        crash_type="buffer_overflow",
        testcase_path="/crashes/crash_002.bin"
    )
    print(f"Crash 002: unique={is_unique}, hash={hash2[:16]}...")

    # Crash 3: Different crash (null pointer)
    backtrace3 = [
        {'function': 'process_request', 'file': 'net.c', 'line': 89},
        {'function': 'handle_connection', 'file': 'net.c', 'line': 234},
        {'function': 'main', 'file': 'app.c', 'line': 200},
    ]
    is_unique, hash3 = dedup.add_crash(
        crash_id="crash_003",
        backtrace=backtrace3,
        crash_type="null_pointer",
        testcase_path="/crashes/crash_003.bin"
    )
    print(f"Crash 003: unique={is_unique}, hash={hash3[:16]}...")

    # Crash 4: Another duplicate of crash 1
    is_unique, hash4 = dedup.add_crash(
        crash_id="crash_004",
        backtrace=backtrace1,
        crash_type="buffer_overflow",
        testcase_path="/crashes/crash_004.bin"
    )
    print(f"Crash 004: unique={is_unique}, hash={hash4[:16]}...")

    # Print summary
    dedup.print_summary()
