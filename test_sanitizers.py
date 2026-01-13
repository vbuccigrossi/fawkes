#!/usr/bin/env python3
"""
Test script for sanitizer integration

Tests parsing and detection of:
- AddressSanitizer (ASAN)
- UndefinedBehaviorSanitizer (UBSAN)
- MemorySanitizer (MSAN)
- ThreadSanitizer (TSAN)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from sanitizers import SanitizerParser, SanitizerDetector, SanitizerType


def test_asan_parser():
    """Test ASAN output parsing"""
    print("=" * 60)
    print("TEST 1: AddressSanitizer (ASAN) Parsing")
    print("=" * 60)

    asan_output = """
=================================================================
==25123==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x60200000001c at pc 0x0000004008f3 bp 0x7ffe6d1e0a10 sp 0x7ffe6d1e0a08
READ of size 4 at 0x60200000001c thread T0
    #0 0x4008f2 in vulnerable_func /home/user/test.c:42:10
    #1 0x4008c3 in main /home/user/test.c:50:5
    #2 0x7f8e5c5a082f in __libc_start_main /build/glibc-S9d2JN/glibc-2.27/csu/../csu/libc-start.c:310

0x60200000001c is located 0 bytes to the right of 12-byte region [0x602000000010,0x60200000001c)
"""

    parser = SanitizerParser()
    report = parser.parse(asan_output)

    print(f"\nSanitizer Type: {report.sanitizer_type.value}")
    print(f"Error Type: {report.error_type}")
    print(f"Crash Address: {report.crash_address}")
    print(f"Access: {report.access_type} of size {report.access_size}")
    print(f"Backtrace frames: {len(report.backtrace)}")

    for frame in report.backtrace:
        print(f"  #{frame['frame']}: {frame['function']} at {frame.get('file', '??')}:{frame.get('line', '??')}")

    assert report.sanitizer_type == SanitizerType.ASAN
    assert report.error_type == "heap-buffer-overflow"
    assert report.crash_address == "0x60200000001c"
    assert report.access_type == "read"
    assert report.access_size == 4
    assert len(report.backtrace) >= 2

    print("\n✓ ASAN parsing test PASSED\n")
    return report


def test_ubsan_parser():
    """Test UBSAN output parsing"""
    print("=" * 60)
    print("TEST 2: UndefinedBehaviorSanitizer (UBSAN) Parsing")
    print("=" * 60)

    ubsan_output = """
/home/user/test.c:15:10: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'
"""

    parser = SanitizerParser()
    report = parser.parse(ubsan_output)

    print(f"\nSanitizer Type: {report.sanitizer_type.value}")
    print(f"Error Type: {report.error_type}")
    print(f"Error Message: {report.error_message}")
    print(f"Location: {report.backtrace[0]['file']}:{report.backtrace[0]['line']}")

    assert report.sanitizer_type == SanitizerType.UBSAN
    assert report.error_type == "integer_overflow"
    assert "overflow" in report.error_message
    assert len(report.backtrace) >= 1

    print("\n✓ UBSAN parsing test PASSED\n")
    return report


def test_msan_parser():
    """Test MSAN output parsing"""
    print("=" * 60)
    print("TEST 3: MemorySanitizer (MSAN) Parsing")
    print("=" * 60)

    msan_output = """
==12345==WARNING: MemorySanitizer: use-of-uninitialized-value
    #0 0x4008f2 in check_value /home/user/test.c:20:7
    #1 0x400910 in main /home/user/test.c:30:10
"""

    parser = SanitizerParser()
    report = parser.parse(msan_output)

    print(f"\nSanitizer Type: {report.sanitizer_type.value}")
    print(f"Error Type: {report.error_type}")
    print(f"Backtrace frames: {len(report.backtrace)}")

    assert report.sanitizer_type == SanitizerType.MSAN
    assert "uninitialized" in report.error_type
    assert len(report.backtrace) >= 2

    print("\n✓ MSAN parsing test PASSED\n")
    return report


def test_tsan_parser():
    """Test TSAN output parsing"""
    print("=" * 60)
    print("TEST 4: ThreadSanitizer (TSAN) Parsing")
    print("=" * 60)

    tsan_output = """
==================
WARNING: ThreadSanitizer: data race (pid=12345)
  Write of size 4 at 0x7b0400000000 by thread T1:
    #0 thread_worker /home/user/test.c:15:5
    #1 start_thread /build/glibc/nptl/pthread_create.c:463

  Previous write of size 4 at 0x7b0400000000 by main thread:
    #0 main /home/user/test.c:30:3
"""

    parser = SanitizerParser()
    report = parser.parse(tsan_output)

    print(f"\nSanitizer Type: {report.sanitizer_type.value}")
    print(f"Error Type: {report.error_type}")
    print(f"Crash Address: {report.crash_address}")
    print(f"Access: {report.access_type} of size {report.access_size}")
    print(f"Thread Info: {report.thread_info}")
    print(f"Backtrace frames: {len(report.backtrace)}")

    assert report.sanitizer_type == SanitizerType.TSAN
    assert report.error_type == "data_race"
    assert report.access_type == "write"
    assert report.access_size == 4
    assert len(report.backtrace) >= 1

    print("\n✓ TSAN parsing test PASSED\n")
    return report


def test_detector():
    """Test sanitizer detector"""
    print("=" * 60)
    print("TEST 5: Sanitizer Detection and Classification")
    print("=" * 60)

    detector = SanitizerDetector()

    # Test ASAN detection
    asan_output = """
Some program output...
==12345==ERROR: AddressSanitizer: use-after-free on address 0x614000000040 at pc 0x000000400a3e
READ of size 4 at 0x614000000040 thread T0
    #0 0x400a3d in use_ptr /home/user/test.c:25:10
"""

    report = detector.detect_in_output(asan_output)
    assert report is not None
    assert report.sanitizer_type == SanitizerType.ASAN

    severity = detector.classify_severity(report)
    exploitability = detector.get_exploitability(report)

    print(f"\nASAN Detection:")
    print(f"  Detected: {report.sanitizer_type.value}")
    print(f"  Error: {report.error_type}")
    print(f"  Severity: {severity}")
    print(f"  Exploitability: {exploitability}")

    assert severity == "critical"
    assert exploitability == "HIGH"

    # Test non-sanitizer output
    normal_output = "Just some normal program output\nNo crashes here\n"
    report = detector.detect_in_output(normal_output)
    assert report is None
    print(f"\nNormal Output: No sanitizer detected ✓")

    print("\n✓ Detector test PASSED\n")


def test_integration():
    """Test full integration with database"""
    print("=" * 60)
    print("TEST 6: Database Integration")
    print("=" * 60)

    from db.db import FawkesDB

    # Create test database
    db_path = "/tmp/test_fawkes_sanitizers.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    db = FawkesDB(db_path)

    # Create test job
    job_id = db.add_job("test_sanitizers", "/tmp/test_input", "radamsa")
    print(f"\nCreated test job: {job_id}")

    # Simulate ASAN crash
    parser = SanitizerParser()
    detector = SanitizerDetector()

    asan_output = """
==12345==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x60200000001c
READ of size 4 at 0x60200000001c thread T0
    #0 0x400a3d in vulnerable_func /home/user/test.c:42:10
"""

    report = parser.parse(asan_output)
    severity = detector.classify_severity(report)

    # Add crash with sanitizer info
    crash_id = db.add_crash(
        job_id=job_id,
        testcase_path="/tmp/test_asan.bin",
        crash_type=report.error_type,
        details=report.error_message,
        stack_hash=None,  # Could compute from backtrace
        backtrace=report.backtrace,
        crash_address=report.crash_address,
        sanitizer_type=report.sanitizer_type.value,
        sanitizer_report=report.to_dict(),
        severity=severity
    )

    print(f"Added ASAN crash: crash_id={crash_id}")
    print(f"  Type: {report.error_type}")
    print(f"  Severity: {severity}")
    print(f"  Address: {report.crash_address}")

    # Verify storage
    crashes = db.get_crashes(job_id)
    assert len(crashes) == 1

    crash = crashes[0]
    print(f"\nStored crash:")
    print(f"  crash_id: {crash[0]}")
    print(f"  crash_type: {crash[3]}")
    # Note: Need to check actual column indices

    # Cleanup
    db.close()
    os.remove(db_path)

    print("\n✓ Database integration test PASSED\n")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("SANITIZER INTEGRATION - COMPREHENSIVE TEST")
    print("=" * 60 + "\n")

    try:
        # Test parsers
        test_asan_parser()
        test_ubsan_parser()
        test_msan_parser()
        test_tsan_parser()

        # Test detector
        test_detector()

        # Test database integration
        test_integration()

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
