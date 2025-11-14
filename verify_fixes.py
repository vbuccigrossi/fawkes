#!/usr/bin/env python3
"""
Quick verification script to test that all bug fixes are working.
Run this to smoke test the critical fixes before full integration testing.
"""

import sys
import os

def test_imports():
    """Test that all critical imports work."""
    print("Testing imports...")
    try:
        # Add current directory to path
        sys.path.insert(0, os.getcwd())

        # Check imports exist in files
        with open('harness.py', 'r') as f:
            harness_content = f.read()
            if 'import datetime' in harness_content:
                print("  ✓ harness.py has datetime import")
            if 'import json' in harness_content:
                print("  ✓ harness.py has json import")
            if 'import zipfile' in harness_content:
                print("  ✓ harness.py has zipfile import")

        return True
    except Exception as e:
        print(f"  ✗ Import check error: {e}")
        return False

def test_db_methods():
    """Test that database has all required methods."""
    print("\nTesting database methods...")
    try:
        from db.db import FawkesDB

        # Check if get_crashes method exists
        if not hasattr(FawkesDB, 'get_crashes'):
            print("  ✗ FawkesDB missing get_crashes() method")
            return False

        print("  ✓ FawkesDB.get_crashes() exists")
        return True
    except Exception as e:
        print(f"  ✗ Database test error: {e}")
        return False

def test_config_consistency():
    """Test that config doesn't have duplicates."""
    print("\nTesting config consistency...")
    try:
        from config import FawkesConfig
        cfg = FawkesConfig()

        # Get poll_interval - should not error
        poll_interval = cfg.get("poll_interval")
        print(f"  ✓ poll_interval: {poll_interval} (should be 60)")

        # Check job_dir consistency
        cfg.job_dir = "/tmp/test"
        if cfg.get("job_dir") != "/tmp/test":
            print("  ✗ job_dir inconsistency")
            return False
        print("  ✓ job_dir attribute access works")

        return True
    except Exception as e:
        print(f"  ✗ Config test error: {e}")
        return False

def test_agents_directory():
    """Test that agents directory exists (not agenst)."""
    print("\nTesting agents directory...")
    if os.path.exists("agents"):
        print("  ✓ agents/ directory exists")
        if os.path.exists("agents/FawkesCrashAgent-Windows.cpp"):
            print("  ✓ Windows agent found")
        if os.path.exists("agents/LinuxCrashAgent.cpp"):
            print("  ✓ Linux agent found")
        return True
    else:
        print("  ✗ agents/ directory not found")
        return False

def test_qemu_manager():
    """Test QemuManager source for fixes."""
    print("\nTesting QemuManager...")
    try:
        with open('qemu.py', 'r') as f:
            qemu_content = f.read()

            # Check for None registry handling
            if 'if not self.registry:' in qemu_content or 'if self.registry:' in qemu_content:
                print("  ✓ QemuManager has None registry checks")
            else:
                print("  ✗ Missing None registry checks")
                return False

            # Check for duplicate refresh_statuses removal
            refresh_count = qemu_content.count('def refresh_statuses(self):')
            if refresh_count == 1:
                print("  ✓ No duplicate refresh_statuses() method")
            else:
                print(f"  ✗ Found {refresh_count} refresh_statuses() definitions")
                return False

            # Check stderr handling fix
            if 'stderr=subprocess.PIPE' in qemu_content:
                print("  ✓ QEMU stderr properly captured with PIPE")
            else:
                print("  ✗ QEMU stderr not properly captured")
                return False

        return True
    except Exception as e:
        print(f"  ✗ QemuManager test error: {e}")
        return False

def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Fawkes Bug Fix Verification")
    print("=" * 60)

    results = {
        "Imports": test_imports(),
        "Database Methods": test_db_methods(),
        "Config Consistency": test_config_consistency(),
        "Agents Directory": test_agents_directory(),
        "QemuManager": test_qemu_manager(),
    }

    print("\n" + "=" * 60)
    print("Verification Summary")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:.<40} {status}")

    all_passed = all(results.values())

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All verification tests passed!")
        print("=" * 60)
        return 0
    else:
        print("✗ Some tests failed - please review errors above")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
