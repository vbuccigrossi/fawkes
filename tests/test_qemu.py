"""
Tests for qemu.py - QemuManager and utility functions.
"""

import os
import sys
import socket
import pytest
import threading
import tempfile
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Mock the fawkes.performance module before importing qemu
sys.modules['fawkes'] = Mock()
sys.modules['fawkes.performance'] = Mock()
sys.modules['fawkes.performance'].perf_tracker = Mock()
sys.modules['fawkes.performance'].perf_tracker.measure = MagicMock(return_value=MagicMock(__enter__=Mock(), __exit__=Mock()))
sys.modules['fawkes.performance'].perf_tracker.increment = Mock()

from qemu import QemuManager, pick_free_port, is_pid_alive
from config import FawkesConfig, VMRegistry


class TestUtilityFunctions:
    """Tests for QEMU utility functions."""

    def test_pick_free_port(self):
        """Test that pick_free_port returns a valid port."""
        port = pick_free_port()
        assert isinstance(port, int)
        assert 1024 <= port <= 65535

    def test_pick_free_port_unique(self):
        """Test that multiple calls return different ports."""
        ports = [pick_free_port() for _ in range(10)]
        # Most should be unique (slight chance of collision)
        assert len(set(ports)) >= 8

    def test_pick_free_port_is_usable(self):
        """Test that the picked port can actually be bound."""
        port = pick_free_port()

        # Should be able to bind to this port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("", port))
            sock.close()
        except OSError:
            pytest.fail(f"Could not bind to port {port}")

    def test_is_pid_alive_current_process(self):
        """Test is_pid_alive with current process."""
        assert is_pid_alive(os.getpid()) is True

    def test_is_pid_alive_nonexistent(self):
        """Test is_pid_alive with non-existent PID."""
        # Use a very high PID unlikely to exist
        assert is_pid_alive(99999999) is False

    def test_is_pid_alive_invalid_pid(self):
        """Test is_pid_alive with invalid PID (0 checks permission only)."""
        # Note: On Linux, os.kill(-1, 0) signals ALL processes the user can signal,
        # which returns True if any exist (permission granted).
        # Use PID 0 which refers to the process group - behavior varies by platform.
        # We simply test that it returns a boolean (doesn't crash).
        result = is_pid_alive(-1)
        assert isinstance(result, bool)


class TestQemuManagerInit:
    """Tests for QemuManager initialization."""

    def test_manager_init(self, tmp_path, sample_config_data, sample_vm_data):
        """Test basic QemuManager initialization."""
        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))

        manager = QemuManager(config, registry)

        assert manager.config is config
        assert manager.registry is registry

    def test_manager_init_with_existing_vms(self, tmp_path, sample_config_data, sample_vm_data):
        """Test manager init refreshes VM statuses."""
        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))

        # Add a VM with fake PID (should be marked stopped)
        vm_data = sample_vm_data.copy()
        vm_data["pid"] = 99999999  # Non-existent PID
        registry.add_vm(vm_data)

        manager = QemuManager(config, registry)

        # VM should be marked as stopped
        vm = registry.get_vm(1)
        assert vm["status"] == "Stopped"


class TestQemuManagerStartVM:
    """Tests for VM start operations (mocked to avoid real QEMU)."""

    @patch('qemu.subprocess.Popen')
    @patch('qemu.os.path.exists')
    def test_start_vm_disk_not_found(self, mock_exists, mock_popen, tmp_path, sample_config_data):
        """Test start_vm fails when disk doesn't exist."""
        mock_exists.return_value = False

        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))
        manager = QemuManager(config, registry)

        result = manager.start_vm("/nonexistent/disk.qcow2")
        assert result is None

    @patch('qemu.subprocess.Popen')
    def test_start_vm_max_vms_reached(self, mock_popen, tmp_path, sample_config_data, sample_vm_data):
        """Test start_vm fails when max VMs reached."""
        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(max_parallel_vms=1, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))

        # Add one running VM
        vm_data = sample_vm_data.copy()
        vm_data["pid"] = os.getpid()  # Use current PID so it appears "alive"
        registry.add_vm(vm_data)

        manager = QemuManager(config, registry)

        # Mock os.path.exists only during start_vm call
        with patch('qemu.os.path.exists', return_value=True):
            result = manager.start_vm("/some/disk.qcow2")

        assert result is None

    @patch('qemu.subprocess.Popen')
    @patch('qemu.shutil.rmtree')
    @patch('qemu.os.makedirs')
    @patch('qemu.Path.mkdir')
    def test_start_vm_qemu_fails(self, mock_path_mkdir, mock_makedirs, mock_rmtree, mock_popen, tmp_path, sample_config_data):
        """Test start_vm handles QEMU startup failure."""
        # Mock QEMU process that fails immediately
        mock_proc = Mock()
        mock_proc.poll.return_value = 1  # Non-zero = failed
        mock_proc.stderr = Mock()
        mock_proc.stderr.read.return_value = b"QEMU error"
        mock_popen.return_value = mock_proc

        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))
        manager = QemuManager(config, registry)

        # Mock os.path.exists and Path.mkdir only during start_vm call
        with patch('qemu.os.path.exists', return_value=True):
            result = manager.start_vm(str(tmp_path / "disk.qcow2"))
        assert result is None

    @patch('qemu.subprocess.Popen')
    @patch('qemu.shutil.rmtree')
    @patch('qemu.os.makedirs')
    @patch('qemu.Path.mkdir')
    def test_start_vm_snapshot_disk_only_error(self, mock_path_mkdir, mock_makedirs, mock_rmtree, mock_popen, tmp_path, sample_config_data, caplog):
        """Test start_vm logs disk-only snapshot error and returns None."""
        # Mock QEMU process that fails with disk-only snapshot error
        mock_proc = Mock()
        mock_proc.poll.return_value = 1
        mock_proc.stderr = Mock()
        mock_proc.stderr.read.return_value = b"disk-only snapshot"
        mock_popen.return_value = mock_proc

        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))
        manager = QemuManager(config, registry)

        # Mock os.path.exists and Path.mkdir only during start_vm call
        # The RuntimeError is caught internally and logged, returns None
        with patch('qemu.os.path.exists', return_value=True):
            result = manager.start_vm(str(tmp_path / "disk.qcow2"))

        assert result is None
        # Verify the disk-only error was logged
        assert any("disk-only" in record.message for record in caplog.records)


class TestQemuManagerStopVM:
    """Tests for VM stop operations."""

    def test_stop_nonexistent_vm(self, tmp_path, sample_config_data):
        """Test stopping a non-existent VM."""
        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))
        manager = QemuManager(config, registry)

        # Should not raise
        manager.stop_vm(999)

    def test_stop_already_stopped_vm(self, tmp_path, sample_config_data, sample_vm_data):
        """Test stopping an already stopped VM."""
        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))

        vm_data = sample_vm_data.copy()
        vm_data["status"] = "Stopped"
        vm_id = registry.add_vm(vm_data)

        manager = QemuManager(config, registry)
        manager.stop_vm(vm_id)  # Should not raise


class TestQemuManagerSnapshots:
    """Tests for snapshot management."""

    @patch('qemu.subprocess.run')
    def test_create_snapshot_success(self, mock_run, tmp_path, sample_config_data):
        """Test successful snapshot creation."""
        mock_run.return_value = Mock(returncode=0)

        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))
        manager = QemuManager(config, registry)

        # Create a temp file to act as disk
        disk_path = tmp_path / "test.qcow2"
        disk_path.touch()

        result = manager.create_snapshot(str(disk_path), "clean")
        assert result is True
        mock_run.assert_called_once()

    @patch('qemu.subprocess.run')
    def test_create_snapshot_failure(self, mock_run, tmp_path, sample_config_data):
        """Test snapshot creation failure."""
        mock_run.return_value = Mock(returncode=1, stderr="Error creating snapshot")

        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))
        manager = QemuManager(config, registry)

        disk_path = tmp_path / "test.qcow2"
        disk_path.touch()

        result = manager.create_snapshot(str(disk_path), "clean")
        assert result is False

    def test_create_snapshot_disk_not_found(self, tmp_path, sample_config_data):
        """Test snapshot creation with non-existent disk."""
        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))
        manager = QemuManager(config, registry)

        result = manager.create_snapshot("/nonexistent/disk.qcow2", "clean")
        assert result is False


class TestQemuManagerScreenshots:
    """Tests for screenshot functionality."""

    def test_capture_screenshot_vm_not_found(self, tmp_path, sample_config_data):
        """Test screenshot capture with non-existent VM."""
        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))
        manager = QemuManager(config, registry)

        result = manager.capture_screenshot(999)
        assert result is None

    def test_capture_screenshot_vm_not_running(self, tmp_path, sample_config_data, sample_vm_data):
        """Test screenshot capture with stopped VM."""
        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))

        vm_data = sample_vm_data.copy()
        vm_data["status"] = "Stopped"
        vm_id = registry.add_vm(vm_data)

        manager = QemuManager(config, registry)
        result = manager.capture_screenshot(vm_id)
        assert result is None

    def test_capture_screenshot_no_monitor_port(self, tmp_path, sample_config_data, sample_vm_data):
        """Test screenshot capture without monitor port."""
        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))

        vm_data = sample_vm_data.copy()
        vm_data["monitor_port"] = None
        vm_id = registry.add_vm(vm_data)

        manager = QemuManager(config, registry)
        result = manager.capture_screenshot(vm_id)
        assert result is None


class TestQemuManagerTimeCompression:
    """Tests for time compression settings."""

    def test_time_compression_config(self, tmp_path):
        """Test time compression configuration can be set dynamically."""
        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(registry_file=str(registry_path))

        # FawkesConfig supports dynamic attribute setting via __setattr__
        config.enable_time_compression = True
        config.time_compression_shift = "auto"
        config.skip_idle_loops = True

        registry = VMRegistry(str(registry_path))
        manager = QemuManager(config, registry)

        # Verify the attributes were set
        assert config.enable_time_compression is True
        assert config.time_compression_shift == "auto"
        assert config.skip_idle_loops is True


class TestQemuManagerRefreshStatuses:
    """Tests for VM status refresh functionality."""

    def test_refresh_marks_dead_vms_stopped(self, tmp_path, sample_config_data, sample_vm_data):
        """Test that refresh marks VMs with dead PIDs as stopped."""
        registry_path = tmp_path / "registry.json"
        registry = VMRegistry(str(registry_path))

        # Add VM with non-existent PID
        vm_data = sample_vm_data.copy()
        vm_data["pid"] = 99999999  # Very unlikely to exist
        vm_data["status"] = "Running"
        vm_id = registry.add_vm(vm_data)

        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        manager = QemuManager(config, registry)

        # After init, refresh should have run
        vm = registry.get_vm(vm_id)
        assert vm["status"] == "Stopped"

    def test_refresh_skips_metadata(self, tmp_path, sample_config_data, sample_vm_data):
        """Test that refresh skips non-VM entries like last_vm_id."""
        registry_path = tmp_path / "registry.json"
        registry = VMRegistry(str(registry_path))

        # Add a VM to create last_vm_id
        vm_data = sample_vm_data.copy()
        vm_data["pid"] = os.getpid()  # Current PID
        registry.add_vm(vm_data)

        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        manager = QemuManager(config, registry)

        # Should not raise when encountering last_vm_id
        manager.refresh_statuses()


class TestQemuManagerStopAll:
    """Tests for stop_all functionality."""

    def test_stop_all_no_vms(self, tmp_path, sample_config_data):
        """Test stop_all with no VMs."""
        registry_path = tmp_path / "registry.json"
        config = FawkesConfig(**sample_config_data, registry_file=str(registry_path))
        registry = VMRegistry(str(registry_path))
        manager = QemuManager(config, registry)

        # Should not raise
        manager.stop_all()

    def test_stop_all_no_registry(self, tmp_path, sample_config_data):
        """Test stop_all with no registry."""
        config = FawkesConfig(**sample_config_data)
        manager = QemuManager(config, None)

        # Should not raise
        manager.stop_all()
