# fawkes/config.py
import os
import json
import threading
from typing import Dict, Any, Optional

DEFAULT_MAX_PARALLEL_VMS = 0

class FawkesConfigError(Exception):
    """Custom exception for Fawkes configuration or registry errors."""
    pass

class FawkesConfig:
    def __init__(self, max_parallel_vms: int = DEFAULT_MAX_PARALLEL_VMS, registry_file: Optional[str] = None, **kwargs):
        self._data = {
            "max_parallel_vms": max_parallel_vms,
            "registry_file": registry_file or os.path.join(os.path.expanduser("~/.fawkes"), "registry.json") ,
            "controller_host": kwargs.get("controller_host", "0.0.0.0"),
            "controller_port": kwargs.get("controller_port", 5000),
            "disk_image": os.path.expanduser(kwargs.get("disk_image", "~/fawkes_test/target.qcow2")),
            "input_dir": os.path.expanduser(kwargs.get("input_dir", "~/fuzz_inputs")),
            "share_dir": os.path.expanduser(kwargs.get("share_dir", "~/fawkes_shared")),
            "poll_interval": kwargs.get("poll_interval", 1.0),
            "max_retries": kwargs.get("max_retries", 3),
            "db_path": os.path.expanduser(kwargs.get("db_path", "~/.fawkes/fawkes.db")),
            "controller_db_path": os.path.expanduser(kwargs.get("controller_db_path", "~/.fawkes/controller.db")),
            "snapshot_name": kwargs.get("snapshot_name", "clean"),
            "tui": kwargs.get("tui", False),
            "arch": kwargs.get("arch", "x86_64"),
            "cleanup_stopped_vms": kwargs.get("cleanup_stopped_vms", False),
            "timeout": kwargs.get("timeout", 60),
            "loop": True,
            "db": None,
            "no_headless": False,
            "vfs": False,
            "smb": True,
            "crash_dir": "./fawkes/crashes",
            "fuzzer": "file",
            "fuzzer_config": None,
            "workers": [],
            "poll_interval": 60,
            "job_dir": "~/.fawkes/jobs/",
            "job_name": "change_me",
            "vm_params": None,
            "job_id": None
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __getattr__(self, name: str) -> Any:
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"'FawkesConfig' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_data":
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    @classmethod
    def load(cls) -> "FawkesConfig":
        fawkes_dir = _ensure_fawkes_dir()
        config_path = os.path.join(fawkes_dir, "config.json")
        if not os.path.exists(config_path):
            default_cfg = {
                "max_parallel_vms": DEFAULT_MAX_PARALLEL_VMS,
                "registry_file": os.path.join(fawkes_dir, "registry.json"),
                "controller_host": "0.0.0.0",
                "controller_port": 5000,
                "db": None,
                "disk_image": "~/fawkes_test/target.qcow2",
                "input_dir": "~/fuzz_inputs",
                "share_dir": "~/fawkes_shared",
                "poll_interval": 1.0,
                "max_retries": 3,
                "db_path": "~/.fawkes/fawkes.db",
                "snapshot_name": "clean",
                "tui": False,
                "arch": "x86_64",
                "cleanup_stopped_vms": False,
                "timeout": 60,
                "loop": True,
                "no_headless": False,
                "vfs": False,
                "smb": True,
                "crash_dir": "./fawkes/crashes",
                "fuzzer": "file",
                "fuzzer_config": None,
                "workers": [], 
                "poll_interval": 60,
                "job_dir": "~/.fawkes/jobs/",
                "job_name": "change_me",
                "vm_params": None,
                "job_id": None
            }
            with open(config_path, "w") as f:
                json.dump(default_cfg, f, indent=2)
            return cls(**default_cfg)
        
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise FawkesConfigError(f"Failed to load config from {config_path}: {e}")
        return cls(**data)

    def save(self) -> None:
        fawkes_dir = _ensure_fawkes_dir()
        config_path = os.path.join(fawkes_dir, "config.json")
        try:
            with open(config_path, "w") as f:
                json.dump(self._data, f, indent=2)
        except OSError as e:
            raise FawkesConfigError(f"Failed to save Fawkes config: {e}")

def _ensure_fawkes_dir() -> str:
    """Ensure that ~/.fawkes/ directory exists. Return its path."""
    home = os.path.expanduser("~")
    fawkes_dir = os.path.join(home, ".fawkes")
    os.makedirs(fawkes_dir, exist_ok=True)
    return fawkes_dir

class VMRegistry:
    def __init__(self, registry_path: str):
        self._path = os.path.expanduser(registry_path)
        self._vms: Dict[Any, Dict[str, Any]] = {}  # Allow any key type for flexibility
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._path):
            self._vms = {}
            return
        try:
            with open(self._path, "r") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise FawkesConfigError(f"Failed to load VM registry from '{self._path}': {e}")
        # Handle both integer VM IDs and string metadata (e.g., "last_vm_id")
        self._vms = {}
        for k, v in raw.items():
            if k.isdigit():  # VM IDs are numeric
                self._vms[int(k)] = v
            else:  # Metadata like "last_vm_id" stays as string
                self._vms[k] = v

    def save(self) -> None:
        with self._lock:
            reg_dir = os.path.dirname(self._path)
            if reg_dir and not os.path.exists(reg_dir):
                os.makedirs(reg_dir, exist_ok=True)
            # Convert all keys to strings for JSON serialization
            serializable = {str(k): v for k, v in self._vms.items()}
            try:
                with open(self._path, "w") as f:
                    json.dump(serializable, f, indent=2)
            except OSError as e:
                raise FawkesConfigError(f"Failed to save VM registry to '{self._path}': {e}")

    @property
    def vms(self) -> Dict[Any, Dict[str, Any]]:
        return self._vms

    def add_vm(self, vm_data: Dict[str, Any]) -> int:
        with self._lock:
            last_id = self._vms.get("last_vm_id", 0)  # Get last used ID, default to 0
            vm_id = last_id + 1
            vm_data["id"] = vm_id
            self._vms[vm_id] = vm_data
            self._vms["last_vm_id"] = vm_id  # Update counter
            self.save()
            return vm_id

    def get_vm(self, vm_id: int) -> Dict[str, Any]:
        with self._lock:
            return self._vms.get(vm_id, {})  # Return empty dict if not found

    def remove_vm(self, vm_id: int) -> None:
        with self._lock:
            self._vms.pop(vm_id, None)  # Safe removal, no error if missing
            self.save()
