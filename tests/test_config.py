"""
Tests for config.py - FawkesConfig and VMRegistry classes.
"""

import os
import json
import pytest
import threading
import tempfile
from pathlib import Path

from config import FawkesConfig, VMRegistry, FawkesConfigError, _ensure_fawkes_dir


class TestFawkesConfig:
    """Tests for the FawkesConfig class."""

    def test_config_init_defaults(self):
        """Test config initialization with default values."""
        config = FawkesConfig()
        assert config.max_parallel_vms == 0
        assert config.arch == "x86_64"
        assert config.timeout == 60
        assert config.fuzzer == "file"
        assert config.loop is True

    def test_config_init_custom_values(self):
        """Test config initialization with custom values."""
        config = FawkesConfig(
            max_parallel_vms=4,
            arch="arm",
            timeout=120,
            controller_port=6000
        )
        assert config.max_parallel_vms == 4
        assert config.arch == "arm"
        assert config.timeout == 120
        assert config.controller_port == 6000

    def test_config_get_method(self):
        """Test the get method with default fallback."""
        config = FawkesConfig(max_parallel_vms=2)
        assert config.get("max_parallel_vms") == 2
        assert config.get("nonexistent_key") is None
        assert config.get("nonexistent_key", "default") == "default"

    def test_config_attribute_access(self):
        """Test attribute-style access to config values."""
        config = FawkesConfig(arch="mips")
        assert config.arch == "mips"
        assert config.max_parallel_vms == 0

    def test_config_attribute_set(self):
        """Test setting config values via attributes."""
        config = FawkesConfig()
        config.arch = "riscv64"
        assert config.arch == "riscv64"

        config.custom_value = "test"
        assert config.custom_value == "test"

    def test_config_invalid_attribute(self):
        """Test accessing non-existent attribute raises error."""
        config = FawkesConfig()
        with pytest.raises(AttributeError):
            _ = config.nonexistent_attribute

    def test_config_save_and_load(self, tmp_path, monkeypatch):
        """Test saving and loading config from file."""
        # Monkey-patch the fawkes directory
        fawkes_dir = tmp_path / ".fawkes"
        fawkes_dir.mkdir()
        monkeypatch.setattr("config._ensure_fawkes_dir", lambda: str(fawkes_dir))

        config = FawkesConfig(max_parallel_vms=5, arch="arm")
        config.save()

        # Verify file was created
        config_path = fawkes_dir / "config.json"
        assert config_path.exists()

        # Load and verify
        with open(config_path) as f:
            data = json.load(f)
        assert data["max_parallel_vms"] == 5
        assert data["arch"] == "arm"

    def test_ensure_fawkes_dir(self, tmp_path, monkeypatch):
        """Test that fawkes directory is created if it doesn't exist."""
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        monkeypatch.setenv("HOME", str(home_dir))

        # The function should create ~/.fawkes
        result = _ensure_fawkes_dir()
        assert os.path.exists(result)
        assert result.endswith(".fawkes")

    def test_config_path_expansion(self):
        """Test that paths are properly expanded."""
        config = FawkesConfig(disk_image="~/test.qcow2")
        # Should expand ~ to home directory
        assert not config.disk_image.startswith("~")
        assert "/test.qcow2" in config.disk_image


class TestVMRegistry:
    """Tests for the VMRegistry class."""

    def test_registry_init_new_file(self, tmp_path):
        """Test registry initialization with non-existent file."""
        registry_path = tmp_path / "registry.json"
        registry = VMRegistry(str(registry_path))
        assert len(registry.vms) == 0

    def test_registry_add_vm(self, tmp_path, sample_vm_data):
        """Test adding a VM to the registry."""
        registry_path = tmp_path / "registry.json"
        registry = VMRegistry(str(registry_path))

        vm_id = registry.add_vm(sample_vm_data.copy())

        assert vm_id == 1
        assert vm_id in registry.vms
        assert registry.vms[vm_id]["pid"] == 12345
        assert registry.vms[vm_id]["status"] == "Running"

    def test_registry_add_multiple_vms(self, tmp_path, sample_vm_data):
        """Test adding multiple VMs with auto-increment IDs."""
        registry_path = tmp_path / "registry.json"
        registry = VMRegistry(str(registry_path))

        vm1_data = sample_vm_data.copy()
        vm1_data["pid"] = 1001
        vm2_data = sample_vm_data.copy()
        vm2_data["pid"] = 1002

        vm1_id = registry.add_vm(vm1_data)
        vm2_id = registry.add_vm(vm2_data)

        assert vm1_id == 1
        assert vm2_id == 2
        assert registry.vms["last_vm_id"] == 2

    def test_registry_get_vm(self, tmp_path, sample_vm_data):
        """Test getting a VM by ID."""
        registry_path = tmp_path / "registry.json"
        registry = VMRegistry(str(registry_path))

        vm_id = registry.add_vm(sample_vm_data.copy())
        vm_info = registry.get_vm(vm_id)

        assert vm_info["pid"] == 12345
        assert vm_info["status"] == "Running"

    def test_registry_get_nonexistent_vm(self, tmp_path):
        """Test getting a non-existent VM returns empty dict."""
        registry_path = tmp_path / "registry.json"
        registry = VMRegistry(str(registry_path))

        vm_info = registry.get_vm(999)
        assert vm_info == {}

    def test_registry_remove_vm(self, tmp_path, sample_vm_data):
        """Test removing a VM from the registry."""
        registry_path = tmp_path / "registry.json"
        registry = VMRegistry(str(registry_path))

        vm_id = registry.add_vm(sample_vm_data.copy())
        assert vm_id in registry.vms

        registry.remove_vm(vm_id)
        assert vm_id not in registry.vms

    def test_registry_remove_nonexistent_vm(self, tmp_path):
        """Test removing non-existent VM doesn't raise error."""
        registry_path = tmp_path / "registry.json"
        registry = VMRegistry(str(registry_path))

        # Should not raise
        registry.remove_vm(999)

    def test_registry_persistence(self, tmp_path, sample_vm_data):
        """Test that registry data persists across instances."""
        registry_path = tmp_path / "registry.json"

        # Create registry and add VM
        registry1 = VMRegistry(str(registry_path))
        vm_id = registry1.add_vm(sample_vm_data.copy())

        # Create new registry instance from same file
        registry2 = VMRegistry(str(registry_path))
        vm_info = registry2.get_vm(vm_id)

        assert vm_info["pid"] == 12345
        assert vm_info["status"] == "Running"

    def test_registry_thread_safety(self, tmp_path, sample_vm_data):
        """Test that registry operations are thread-safe."""
        registry_path = tmp_path / "registry.json"
        registry = VMRegistry(str(registry_path))
        results = []

        def add_vm_thread(i):
            vm_data = sample_vm_data.copy()
            vm_data["pid"] = 1000 + i
            vm_id = registry.add_vm(vm_data)
            results.append(vm_id)

        threads = [threading.Thread(target=add_vm_thread, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All IDs should be unique
        assert len(set(results)) == 10
        assert len(results) == 10

    def test_registry_invalid_file(self, tmp_path):
        """Test loading registry from invalid JSON raises error."""
        registry_path = tmp_path / "registry.json"
        registry_path.write_text("{ invalid json }")

        with pytest.raises(FawkesConfigError):
            VMRegistry(str(registry_path))

    def test_registry_mixed_keys(self, tmp_path, sample_vm_data):
        """Test registry handles both integer VM IDs and string metadata."""
        registry_path = tmp_path / "registry.json"
        registry = VMRegistry(str(registry_path))

        # Add VMs
        vm_id = registry.add_vm(sample_vm_data.copy())

        # last_vm_id should be stored as string key but handled correctly
        assert "last_vm_id" in registry.vms
        assert isinstance(registry.vms["last_vm_id"], int)
        assert isinstance(vm_id, int)

    def test_registry_save_creates_directory(self, tmp_path):
        """Test that save creates the directory if it doesn't exist."""
        registry_path = tmp_path / "subdir" / "registry.json"
        registry = VMRegistry(str(registry_path))

        # Should create directory on save
        registry.save()
        assert registry_path.parent.exists()


class TestConfigIntegration:
    """Integration tests for config and registry together."""

    def test_config_with_registry_path(self, tmp_path):
        """Test config specifying registry path."""
        registry_path = tmp_path / "custom_registry.json"
        config = FawkesConfig(registry_file=str(registry_path))

        assert config.registry_file == str(registry_path)

    def test_full_workflow(self, tmp_path, sample_vm_data):
        """Test full config and registry workflow."""
        registry_path = tmp_path / "registry.json"

        # Create config with custom registry
        config = FawkesConfig(
            max_parallel_vms=2,
            registry_file=str(registry_path),
            arch="x86_64"
        )

        # Create registry using config's registry_file
        registry = VMRegistry(config.registry_file)

        # Add VMs respecting max_parallel_vms
        vm1_id = registry.add_vm(sample_vm_data.copy())
        vm2_data = sample_vm_data.copy()
        vm2_data["pid"] = 54321
        vm2_id = registry.add_vm(vm2_data)

        # Verify
        assert vm1_id == 1
        assert vm2_id == 2
        assert registry.vms["last_vm_id"] == 2

        # Count running VMs
        running = sum(1 for v in registry.vms.values()
                      if isinstance(v, dict) and v.get("status") == "Running")
        assert running == 2
