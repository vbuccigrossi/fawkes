#!/usr/bin/env python3
"""
Test Kernel Fuzzing Support
"""

import sys
sys.path.insert(0, '/home/ebrown/Desktop/projects/fawkes')

from kernel import SyscallFuzzer, SyscallGenerator, ArgType
from kernel import KASANParser, KASANErrorType, KASANReport
from kernel import KCOVManager, KCOVCoverageTracker


def test_syscall_generator():
    """Test syscall argument generation."""
    print("\n=== Test 1: Syscall Generator ===")

    generator = SyscallGenerator(use_interesting=True)

    # Test different argument types
    fd = generator.generate_arg(ArgType.FD)
    assert isinstance(fd, int), "FD should be int"
    print(f"✓ FD generated: {fd}")

    ptr = generator.generate_arg(ArgType.PTR)
    assert isinstance(ptr, int), "PTR should be int"
    print(f"✓ PTR generated: {hex(ptr)}")

    size = generator.generate_arg(ArgType.SIZE)
    assert isinstance(size, int) and size >= 0, "SIZE should be non-negative int"
    print(f"✓ SIZE generated: {size}")

    flags = generator.generate_arg(ArgType.FLAGS)
    assert isinstance(flags, int), "FLAGS should be int"
    print(f"✓ FLAGS generated: {hex(flags)}")

    # Test buffer generation
    buffer = generator.generate_arg(ArgType.BUFFER, context={'size': 1024})
    assert isinstance(buffer, int), "BUFFER should be int (address)"
    print(f"✓ BUFFER generated: {hex(buffer)}")

    print("✓ All argument types generated successfully!\n")


def test_syscall_fuzzer():
    """Test syscall fuzzer."""
    print("=== Test 2: Syscall Fuzzer ===")

    fuzzer = SyscallFuzzer()

    # Test syscall count
    count = fuzzer.get_syscall_count()
    assert count > 0, "Should have syscalls"
    print(f"✓ Available syscalls: {count}")

    # List syscalls
    syscalls = fuzzer.list_syscalls()
    assert 'open' in syscalls, "Should have open syscall"
    assert 'read' in syscalls, "Should have read syscall"
    assert 'write' in syscalls, "Should have write syscall"
    assert 'mmap' in syscalls, "Should have mmap syscall"
    print(f"✓ Common syscalls present: open, read, write, mmap")

    # Generate random syscall
    syscall = fuzzer.generate_syscall()
    assert 'name' in syscall, "Syscall should have name"
    assert 'args' in syscall, "Syscall should have args"
    print(f"✓ Random syscall: {syscall['name']}({', '.join(map(str, syscall['args']))})")

    # Generate specific syscall
    open_syscall = fuzzer.generate_syscall("open")
    assert open_syscall['name'] == 'open', "Name should be 'open'"
    assert len(open_syscall['args']) == 3, "open() has 3 arguments"
    print(f"✓ open() syscall: {fuzzer.format_syscall_c(open_syscall)}")

    # Test mmap syscall
    mmap_syscall = fuzzer.generate_syscall("mmap")
    assert mmap_syscall['name'] == 'mmap', "Name should be 'mmap'"
    assert len(mmap_syscall['args']) == 6, "mmap() has 6 arguments"
    print(f"✓ mmap() syscall: {fuzzer.format_syscall_c(mmap_syscall)}")

    # Test batch generation
    batch = fuzzer.generate_batch(count=10)
    assert len(batch) == 10, "Should generate 10 syscalls"
    print(f"✓ Batch generation: {len(batch)} syscalls")

    # Test specific syscall batch
    read_batch = fuzzer.generate_batch(count=5, syscall_name="read")
    assert all(s['name'] == 'read' for s in read_batch), "All should be read()"
    print(f"✓ Specific batch: 5x read()")

    print("✓ All syscall fuzzer tests passed!\n")


def test_syscall_formatting():
    """Test syscall formatting."""
    print("=== Test 3: Syscall Formatting ===")

    fuzzer = SyscallFuzzer()

    syscall = {
        'name': 'open',
        'args': [0x20000000, 0, 0o644]
    }

    # Test C formatting
    c_code = fuzzer.format_syscall_c(syscall)
    assert 'open' in c_code, "Should contain 'open'"
    assert '0x20000000' in c_code, "Should contain address"
    print(f"✓ C format: {c_code}")

    # Test Python formatting
    py_code = fuzzer.format_syscall_python(syscall)
    assert 'libc.open' in py_code, "Should contain 'libc.open'"
    print(f"✓ Python format: {py_code}")

    print("✓ All formatting tests passed!\n")


def test_custom_syscalls():
    """Test custom syscall definitions."""
    print("=== Test 4: Custom Syscalls ===")

    fuzzer = SyscallFuzzer()  # Start with defaults

    # Add custom syscall
    fuzzer.add_custom_syscall("my_ioctl", [ArgType.FD, ArgType.UINT, ArgType.PTR])

    # Verify added
    assert "my_ioctl" in fuzzer.list_syscalls(), "Should have my_ioctl"
    print(f"✓ Custom syscall added")

    # Generate custom syscall
    syscall = fuzzer.generate_syscall("my_ioctl")
    assert syscall['name'] == 'my_ioctl', "Name should be my_ioctl"
    assert len(syscall['args']) == 3, "Should have 3 arguments"
    print(f"✓ Custom syscall generated: {fuzzer.format_syscall_c(syscall)}")

    # Get signature
    sig = fuzzer.get_syscall_signature("my_ioctl")
    assert sig == [ArgType.FD, ArgType.UINT, ArgType.PTR], "Signature should match"
    print(f"✓ Signature: {[t.value for t in sig]}")

    print("✓ All custom syscall tests passed!\n")


def test_kasan_parser():
    """Test KASAN report parsing."""
    print("=== Test 5: KASAN Parser ===")

    sample_report = """
==================================================================
BUG: KASAN: use-after-free in kfree+0x2b/0x80
Write of size 8 at addr ffff8881f2345678 by task fuzzer/1234

CPU: 0 PID: 1234 Comm: fuzzer Not tainted 5.10.0 #1
Call Trace:
 dump_stack+0x64/0x8c
 kasan_report+0x37/0x7f
 kfree+0x2b/0x80
 test_func+0x123/0x456

Allocated by task 1234:
 kasan_save_stack+0x19/0x40
 __kasan_kmalloc+0xc6/0xd0
 kmalloc+0x151/0x2c0

Freed by task 1234:
 kasan_save_stack+0x19/0x40
 __kasan_slab_free+0x111/0x160
 kfree+0x2b/0x80
==================================================================
"""

    parser = KASANParser()

    # Test detection
    assert parser.detect_in_output(sample_report), "Should detect KASAN report"
    print("✓ KASAN report detected")

    # Test parsing
    report = parser.parse(sample_report)
    assert report is not None, "Should parse report"
    print(f"✓ Report parsed: {report}")

    # Verify fields
    assert report.error_type == KASANErrorType.USE_AFTER_FREE, f"Error type should be USE_AFTER_FREE, got {report.error_type}"
    assert report.access_type == "WRITE", f"Access should be WRITE, got {report.access_type}"
    assert report.size == 8, f"Size should be 8, got {report.size}"
    assert report.address == 0xffff8881f2345678, f"Address should match"
    assert report.function == "kfree", f"Function should be kfree, got {report.function}"
    print("✓ All fields correct")

    # Test backtraces
    assert len(report.backtrace) > 0, "Should have call trace"
    assert len(report.allocation_backtrace) > 0, "Should have allocation trace"
    assert len(report.free_backtrace) > 0, "Should have free trace"
    print(f"✓ Backtraces: {len(report.backtrace)} call, {len(report.allocation_backtrace)} alloc, {len(report.free_backtrace)} free")

    # Test severity
    severity = parser.classify_severity(report)
    assert severity == "HIGH", "UAF should be HIGH severity"
    print(f"✓ Severity: {severity}")

    # Test exploitability
    exploitability = parser.get_exploitability(report)
    assert exploitability == "HIGH", "UAF write should be highly exploitable"
    print(f"✓ Exploitability: {exploitability}")

    # Test to_dict
    report_dict = report.to_dict()
    assert 'error_type' in report_dict, "Dict should have error_type"
    assert report_dict['error_type'] == 'use-after-free', "Error type should match"
    print("✓ Dict conversion successful")

    print("✓ All KASAN parser tests passed!\n")


def test_kasan_error_types():
    """Test different KASAN error types."""
    print("=== Test 6: KASAN Error Types ===")

    parser = KASANParser()

    # Test out-of-bounds
    oob_report = """
BUG: KASAN: slab-out-of-bounds in test_func+0x123/0x456
Read of size 4 at addr ffff8881abcdef00 by task test/5678
"""
    report = parser.parse(oob_report)
    assert report.error_type == KASANErrorType.SLAB_OUT_OF_BOUNDS, "Should be slab-out-of-bounds"
    assert report.access_type == "READ", "Should be READ"
    print("✓ Slab out-of-bounds parsed")

    severity = parser.classify_severity(report)
    assert severity == "MEDIUM", "OOB should be MEDIUM severity"
    print(f"✓ Severity: {severity}")

    # Test double-free
    df_report = """
BUG: KASAN: double-free in kfree+0x2b/0x80
Invalid access of size 8 at addr ffff8881abcd0000 by task test/1111
"""
    report = parser.parse(df_report)
    assert report.error_type == KASANErrorType.DOUBLE_FREE, "Should be double-free"
    print("✓ Double-free parsed")

    severity = parser.classify_severity(report)
    assert severity == "HIGH", "Double-free should be HIGH severity"
    exploitability = parser.get_exploitability(report)
    assert exploitability == "HIGH", "Double-free should be highly exploitable"
    print(f"✓ Severity: {severity}, Exploitability: {exploitability}")

    print("✓ All error type tests passed!\n")


def test_kcov_coverage_tracker():
    """Test KCOV coverage tracker."""
    print("=== Test 7: KCOV Coverage Tracker ===")

    tracker = KCOVCoverageTracker()

    # Simulate coverage from executions
    exec1 = [0x1000, 0x2000, 0x3000]
    exec2 = [0x2000, 0x3000, 0x4000]
    exec3 = [0x1000, 0x2000, 0x5000]

    # Update with first execution
    new1 = tracker.update(exec1)
    assert new1 == 3, f"First execution should add 3 new PCs, got {new1}"
    assert tracker.get_total_coverage() == 3, "Total should be 3"
    print(f"✓ Execution 1: {new1} new PCs (total: {tracker.get_total_coverage()})")

    # Update with second execution
    new2 = tracker.update(exec2)
    assert new2 == 1, f"Second execution should add 1 new PC (0x4000), got {new2}"
    assert tracker.get_total_coverage() == 4, "Total should be 4"
    print(f"✓ Execution 2: {new2} new PCs (total: {tracker.get_total_coverage()})")

    # Update with third execution
    new3 = tracker.update(exec3)
    assert new3 == 1, f"Third execution should add 1 new PC (0x5000), got {new3}"
    assert tracker.get_total_coverage() == 5, "Total should be 5"
    print(f"✓ Execution 3: {new3} new PCs (total: {tracker.get_total_coverage()})")

    # Test is_interesting
    assert tracker.is_interesting([0x6000]) == True, "New PC should be interesting"
    assert tracker.is_interesting([0x1000, 0x2000]) == False, "Old PCs should not be interesting"
    print("✓ Interesting testcase detection works")

    # Test get_coverage_pcs
    all_pcs = tracker.get_coverage_pcs()
    assert len(all_pcs) == 5, "Should have 5 unique PCs"
    assert 0x1000 in all_pcs, "Should contain 0x1000"
    assert 0x5000 in all_pcs, "Should contain 0x5000"
    print(f"✓ Coverage PCs: {', '.join(hex(pc) for pc in sorted(all_pcs))}")

    # Test reset
    tracker.reset()
    assert tracker.get_total_coverage() == 0, "Should be reset to 0"
    assert tracker.executions == 0, "Executions should be reset"
    print("✓ Reset works")

    print("✓ All coverage tracker tests passed!\n")


def test_integration():
    """Test integration between components."""
    print("=== Test 8: Integration ===")

    # Syscall fuzzing -> KASAN parsing workflow
    fuzzer = SyscallFuzzer(syscalls=['open', 'read', 'write'])
    kasan_parser = KASANParser()

    # Generate syscalls
    syscalls = fuzzer.generate_batch(count=10)
    assert len(syscalls) == 10, "Should generate 10 syscalls"
    print(f"✓ Generated {len(syscalls)} syscalls")

    # Simulate fuzzing loop
    crashes_found = 0
    for i, syscall in enumerate(syscalls):
        # Simulate execution (would be real execution in practice)
        c_code = fuzzer.format_syscall_c(syscall)

        # Simulate random KASAN report
        if i == 5:  # Pretend 6th execution crashes
            fake_output = """
BUG: KASAN: use-after-free in kfree+0x2b/0x80
Write of size 8 at addr ffff8881f2345678 by task fuzzer/1234
"""
            if kasan_parser.detect_in_output(fake_output):
                report = kasan_parser.parse(fake_output)
                crashes_found += 1
                print(f"  Crash #{crashes_found}: {syscall['name']}() -> {report.error_type.value}")

    assert crashes_found == 1, "Should find 1 simulated crash"
    print(f"✓ Found {crashes_found} crash(es)")

    # Coverage tracking workflow
    tracker = KCOVCoverageTracker()

    # Simulate coverage-guided fuzzing
    interesting_count = 0
    for i in range(20):
        # Simulate coverage
        import random
        coverage = [random.randint(0x1000, 0x10000) for _ in range(random.randint(5, 15))]

        if tracker.is_interesting(coverage):
            interesting_count += 1
            tracker.update(coverage)

    print(f"✓ Interesting testcases: {interesting_count}/20")
    print(f"✓ Total coverage: {tracker.get_total_coverage()} PCs")

    print("✓ All integration tests passed!\n")


def main():
    """Run all tests."""
    print("=" * 70)
    print("KERNEL FUZZING TEST SUITE")
    print("=" * 70)

    try:
        test_syscall_generator()
        test_syscall_fuzzer()
        test_syscall_formatting()
        test_custom_syscalls()
        test_kasan_parser()
        test_kasan_error_types()
        test_kcov_coverage_tracker()
        test_integration()

        print("=" * 70)
        print("✅ ALL TESTS PASSED!")
        print("=" * 70)

        # Print summary
        print("\nKernel Fuzzing Implementation Summary:")
        print("  ✓ Syscall Fuzzer - Type-aware argument generation")
        print("    • 30+ syscall definitions (file, process, memory, network)")
        print("    • 12 argument types (int, ptr, fd, size, flags, etc.)")
        print("    • Intelligent value selection (valid, boundary, invalid)")
        print("    • Custom syscall support")
        print("  ✓ KASAN Parser - Kernel Address Sanitizer integration")
        print("    • 9 error types (UAF, OOB, double-free, etc.)")
        print("    • Backtrace extraction (call, allocation, free)")
        print("    • Severity classification (HIGH/MEDIUM/LOW)")
        print("    • Exploitability estimation")
        print("  ✓ KCOV Manager - Kernel code coverage")
        print("    • Coverage collection via /dev/kcov")
        print("    • PC deduplication and tracking")
        print("    • Interesting testcase detection")
        print("    • Coverage-guided fuzzing support")

        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
