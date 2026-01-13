#!/usr/bin/env python3
"""
Test script for crash deduplication by stack hash

This tests the integration of:
- StackHasher
- GDBBacktraceExtractor
- Database crash deduplication
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from crash_analysis import StackHasher
from crash_analysis.gdb_backtrace import GDBBacktraceExtractor
from db.db import FawkesDB


def test_gdb_backtrace_parsing():
    """Test GDB backtrace extraction"""
    print("=" * 60)
    print("TEST 1: GDB Backtrace Parsing")
    print("=" * 60)

    # Simulated GDB output
    gdb_output = """
Program received signal SIGSEGV, Segmentation fault.
0x0000555555555189 in vulnerable_func () at test.c:42
42      *ptr = 0x41414141;
#0  0x0000555555555189 in vulnerable_func () at test.c:42
#1  0x00005555555551c5 in process_input (data=0x7fffffffd810) at test.c:156
#2  0x00005555555551f0 in main (argc=2, argv=0x7fffffffd958) at test.c:200
"""

    extractor = GDBBacktraceExtractor(arch="x86_64")

    # Parse backtrace
    backtrace = extractor._parse_gdb_backtrace(gdb_output)
    print(f"\nExtracted {len(backtrace)} stack frames:")
    for frame in backtrace:
        print(f"  #{frame['frame']}: {frame['function']} at {frame.get('file', '??')}:{frame.get('line', '??')}")

    # Extract crash address
    crash_address = extractor.extract_crash_address(gdb_output)
    print(f"\nCrash address: {crash_address}")

    # Extract signal
    signal = extractor.extract_signal(gdb_output)
    print(f"Signal: {signal}")

    assert len(backtrace) == 3, f"Expected 3 frames, got {len(backtrace)}"
    assert crash_address == "0000555555555189", f"Wrong crash address: {crash_address}"
    assert signal == "SIGSEGV", f"Wrong signal: {signal}"

    print("\n✓ GDB backtrace parsing test PASSED\n")
    return backtrace, crash_address, signal


def test_stack_hashing(backtrace):
    """Test stack hash generation"""
    print("=" * 60)
    print("TEST 2: Stack Hashing")
    print("=" * 60)

    hasher = StackHasher(depth=10, ignore_system_libs=True)

    # Generate hash
    stack_hash = hasher.hash_backtrace(backtrace)
    print(f"\nStack hash: {stack_hash[:32]}...")

    # Test with same backtrace but different line numbers (simulating recompilation)
    backtrace_recompiled = [
        {'frame': 0, 'function': 'vulnerable_func', 'file': 'test.c', 'line': 45},
        {'frame': 1, 'function': 'process_input', 'file': 'test.c', 'line': 160},
        {'frame': 2, 'function': 'main', 'file': 'test.c', 'line': 205},
    ]

    hash_recompiled = hasher.hash_backtrace(backtrace_recompiled)
    print(f"Hash after recompilation: {hash_recompiled[:32]}...")

    # Hashes should match (line numbers ignored)
    assert stack_hash == hash_recompiled, "Hashes should match after recompilation!"
    print("\n✓ Stack hashes match (line numbers correctly ignored)")

    # Test with different backtrace
    backtrace_different = [
        {'frame': 0, 'function': 'different_func', 'file': 'other.c', 'line': 10},
        {'frame': 1, 'function': 'main', 'file': 'test.c', 'line': 200},
    ]

    hash_different = hasher.hash_backtrace(backtrace_different)
    print(f"Hash for different crash: {hash_different[:32]}...")

    assert stack_hash != hash_different, "Different crashes should have different hashes!"
    print("✓ Different crashes have different hashes")

    print("\n✓ Stack hashing test PASSED\n")
    return stack_hash


def test_database_deduplication(backtrace, stack_hash, crash_address, signal):
    """Test database crash deduplication"""
    print("=" * 60)
    print("TEST 3: Database Deduplication")
    print("=" * 60)

    # Create test database
    db_path = "/tmp/test_fawkes_dedup.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    db = FawkesDB(db_path)

    # Create test job
    job_id = db.add_job("test_dedup", "/tmp/test_input", "radamsa")
    print(f"\nCreated test job: {job_id}")

    # Add first crash
    crash_id_1 = db.add_crash(
        job_id=job_id,
        testcase_path="/tmp/test1.bin",
        crash_type="SIGSEGV",
        details=signal,
        stack_hash=stack_hash,
        backtrace=backtrace,
        crash_address=crash_address
    )
    print(f"Added crash 1: crash_id={crash_id_1}")

    # Add duplicate crash (same stack hash)
    crash_id_2 = db.add_crash(
        job_id=job_id,
        testcase_path="/tmp/test2.bin",
        crash_type="SIGSEGV",
        details=signal,
        stack_hash=stack_hash,
        backtrace=backtrace,
        crash_address=crash_address
    )
    print(f"Added crash 2 (duplicate): crash_id={crash_id_2}")

    # Should return same crash_id for duplicate
    assert crash_id_1 == crash_id_2, f"Duplicate should return same ID! {crash_id_1} != {crash_id_2}"
    print("✓ Duplicate crash correctly identified")

    # Add different crash
    backtrace_different = [
        {'frame': 0, 'function': 'different_func', 'file': 'other.c', 'line': 10},
        {'frame': 1, 'function': 'main', 'file': 'test.c', 'line': 200},
    ]
    hasher = StackHasher()
    stack_hash_different = hasher.get_crash_signature(backtrace_different, "SIGABRT")

    crash_id_3 = db.add_crash(
        job_id=job_id,
        testcase_path="/tmp/test3.bin",
        crash_type="SIGABRT",
        details="SIGABRT",
        stack_hash=stack_hash_different,
        backtrace=backtrace_different,
        crash_address="0x400000"
    )
    print(f"Added crash 3 (unique): crash_id={crash_id_3}")

    # Should be different crash_id
    assert crash_id_3 != crash_id_1, "Different crash should have different ID!"
    print("✓ Unique crash correctly identified")

    # Check statistics
    stats = db.get_crash_statistics(job_id)
    print(f"\nCrash statistics:")
    print(f"  Total crashes: {stats['total_crashes']}")
    print(f"  Unique crashes: {stats['unique_crashes']}")
    print(f"  Duplicate crashes: {stats['duplicate_crashes']}")
    print(f"  Deduplication ratio: {stats['dedup_ratio']:.1f}%")

    # We added 3 crashes total, but one was a duplicate, so:
    # - Total unique crashes in DB: 2 (the first SIGSEGV and the SIGABRT)
    # - Duplicate count: 1 (the second SIGSEGV matched the first)
    # But the get_crash_statistics returns count based on database rows, not crash attempts
    # The duplicate doesn't create a new row, it just increments duplicate_count
    assert stats['total_crashes'] == 2, f"Expected 2 crash records, got {stats['total_crashes']}"
    assert stats['unique_crashes'] == 2, f"Expected 2 unique crashes, got {stats['unique_crashes']}"
    assert stats['duplicate_crashes'] == 0, f"Expected 0 duplicate records, got {stats['duplicate_crashes']}"

    # Get unique crashes
    unique_crashes = db.get_unique_crashes(job_id)
    print(f"\nUnique crashes: {len(unique_crashes)}")
    for crash in unique_crashes:
        crash_id, job_id, testcase, crash_type, details, sig, expl, crash_file, ts, dup_count, sh, ca, iu = crash
        print(f"  - crash_id={crash_id}, type={crash_type}, stack_hash={sh[:16] if sh else 'N/A'}..., duplicates={dup_count}")

    assert len(unique_crashes) == 2, f"Expected 2 unique crashes, got {len(unique_crashes)}"

    # Cleanup
    db.close()
    os.remove(db_path)

    print("\n✓ Database deduplication test PASSED\n")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("CRASH DEDUPLICATION BY STACK HASH - INTEGRATION TEST")
    print("=" * 60 + "\n")

    try:
        # Test 1: GDB backtrace parsing
        backtrace, crash_address, signal = test_gdb_backtrace_parsing()

        # Test 2: Stack hashing
        stack_hash = test_stack_hashing(backtrace)

        # Test 3: Database deduplication
        test_database_deduplication(backtrace, stack_hash, crash_address, signal)

        print("=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
