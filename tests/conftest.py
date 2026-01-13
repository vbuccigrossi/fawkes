"""
Pytest configuration and fixtures for Fawkes core tests.
"""

import os
import sys
import pytest
import tempfile
import shutil
import json
from pathlib import Path

# Add project root to path for all imports
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.fixture(scope="session")
def temp_dir():
    """Create a temporary directory for test files."""
    temp = tempfile.mkdtemp(prefix="fawkes_test_")
    yield temp
    shutil.rmtree(temp, ignore_errors=True)


@pytest.fixture
def temp_fawkes_dir(tmp_path):
    """Create a temporary .fawkes directory structure."""
    fawkes_dir = tmp_path / ".fawkes"
    fawkes_dir.mkdir(parents=True)

    # Create subdirectories
    (fawkes_dir / "jobs").mkdir()
    (fawkes_dir / "crashes").mkdir()
    (fawkes_dir / "corpus").mkdir()
    (fawkes_dir / "shared").mkdir()
    (fawkes_dir / "screenshots").mkdir()
    (fawkes_dir / "images").mkdir()

    return fawkes_dir


@pytest.fixture
def sample_config_data():
    """Sample configuration data for testing."""
    return {
        "max_parallel_vms": 2,
        "controller_host": "127.0.0.1",
        "controller_port": 5000,
        "disk_image": "/tmp/test-disk.qcow2",
        "input_dir": "/tmp/corpus",
        "share_dir": "/tmp/shared",
        "poll_interval": 30,
        "max_retries": 3,
        "snapshot_name": "clean",
        "arch": "x86_64",
        "timeout": 60,
        "fuzzer": "file",
    }


@pytest.fixture
def sample_vm_data():
    """Sample VM data for registry testing."""
    return {
        "pid": 12345,
        "disk_path": "/tmp/test-vm.qcow2",
        "original_disk": "/home/user/base-disk.qcow2",
        "memory": "2G",
        "debug": True,
        "debug_port": 1234,
        "monitor_port": 5555,
        "vnc_port": 5900,
        "agent_port": 9999,
        "extra_opts": "",
        "status": "Running",
        "share_dir": "/tmp/share",
        "arch": "x86_64",
        "temp_dir": "/tmp/vm_temp",
        "snapshot_name": "clean",
        "screenshots_enabled": False
    }


@pytest.fixture
def sample_format_spec():
    """Sample format specification for fuzzer testing."""
    return {
        "name": "test_format",
        "fields": [
            {"name": "magic", "type": "fixed", "length": 4, "value": b"TEST"},
            {"name": "version", "type": "uint16", "length": 2},
            {"name": "data_length", "type": "uint32", "length": 4, "controls": "data"},
            {"name": "data", "type": "bytes", "length_field": "data_length"},
            {"name": "checksum", "type": "crc32", "length": 4, "covers": ["magic", "version", "data"]}
        ]
    }


@pytest.fixture
def sample_seed_file(tmp_path):
    """Create a sample seed file for fuzzer testing."""
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    seed_file = seed_dir / "test_seed.bin"
    seed_file.write_bytes(b"TEST\x00\x01\x00\x00\x00\x04DATA" + b"\x00" * 4)
    return str(seed_dir)


@pytest.fixture
def sample_crash_data():
    """Sample crash data for database testing."""
    return {
        "testcase_path": "/tmp/crash_input.bin",
        "crash_type": "SIGSEGV",
        "details": "Segmentation fault at 0x41414141",
        "stack_hash": "abc123def456",
        "backtrace": [
            {"func": "vulnerable_func", "addr": "0x41414141"},
            {"func": "main", "addr": "0x80001234"}
        ],
        "crash_address": "0x41414141",
        "sanitizer_type": "ASAN",
        "sanitizer_report": {"type": "heap-buffer-overflow", "size": 8},
        "severity": "high"
    }


@pytest.fixture
def sample_job_data():
    """Sample job data for database testing."""
    return {
        "name": "test_job",
        "input_dir": "/tmp/corpus",
        "fuzzer_type": "file",
        "fuzzer_config": {"mutations_per_seed": 100}
    }
