# fawkes/globals.py
import threading
import psutil
import logging
import os
import json
import fcntl
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger("fawkes.globals")

shutdown_event = threading.Event()

@contextmanager
def file_lock(lock_file):
    """Context manager for file locking using fcntl.flock."""
    with open(lock_file, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

class SystemResources:
    def __init__(self):
        self._lock = threading.Lock()  # For in-process thread safety
        self._instance_file = os.path.expanduser("~/.fawkes/active_instances.json")
        self._lock_file = self._instance_file + ".lock"
        os.makedirs(os.path.dirname(self._instance_file), exist_ok=True)
        self.vm_cpu_usage = 25.0  # CPU usage per VM
        self.vm_memory_mb = 1024   # Memory per VM in MB
        self.min_cpu_free = 10.0  # Minimum free CPU percentage
        self.min_memory_mb = 1024 # Minimum free memory in MB

    def _is_pid_alive(self, pid: int) -> bool:
        """Check if a process ID is still running."""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _update_instance_count(self, delta: int, pid: int) -> int:
        """Update the instance count with file locking and PID tracking."""
        with file_lock(self._lock_file):
            data = {"instances": [], "current_vms": 0}
            if os.path.exists(self._instance_file):
                with open(self._instance_file, "r") as f:
                    data = json.load(f)
            instances = data["instances"]
            # Clean up dead PIDs
            alive_instances = [p for p in instances if self._is_pid_alive(p)]
            if delta > 0 and pid not in alive_instances:
                alive_instances.append(pid)
            elif delta < 0 and pid in alive_instances:
                alive_instances.remove(pid)
            data["instances"] = alive_instances
            with open(self._instance_file, "w") as f:
                json.dump(data, f)
                f.flush()
            logger.debug(f"Instance count updated to {len(alive_instances)}")
            return len(alive_instances)

    def register_instance(self):
        """Register a new instance with the current PID."""
        pid = os.getpid()
        instance_count = self._update_instance_count(1, pid)
        logger.debug(f"Registered new instance {pid}, total active: {instance_count}")

    def unregister_instance(self):
        """Unregister the current instance."""
        pid = os.getpid()
        instance_count = self._update_instance_count(-1, pid)
        logger.debug(f"Unregistered instance {pid}, total active: {instance_count}")

    def get_instance_count(self) -> int:
        """Get the current number of active instances, cleaning up dead PIDs."""
        with file_lock(self._lock_file):
            if os.path.exists(self._instance_file):
                with open(self._instance_file, "r") as f:
                    data = json.load(f)
                    instances = data["instances"]
                    alive_instances = [p for p in instances if self._is_pid_alive(p)]
                    if len(alive_instances) < len(instances):
                        data["instances"] = alive_instances
                        with open(self._instance_file, "w") as f:
                            json.dump(data, f)
                            f.flush()
                    return max(1, len(alive_instances))
            return 1

    def update_stats(self) -> dict:
        """Get current system resource stats."""
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_total_mb": psutil.virtual_memory().total / (1024 * 1024),
            "memory_used_mb": psutil.virtual_memory().used / (1024 * 1024),
        }

    def get_max_vms(self) -> int:
        """Calculate the maximum number of VMs this instance can run."""
        stats = self.update_stats()
        cpu_free = max(0, 100 - stats["cpu_percent"] - self.min_cpu_free)
        memory_free = max(0, stats["memory_total_mb"] - stats["memory_used_mb"] - self.min_memory_mb)
        cpu_max_vms = int(cpu_free / self.vm_cpu_usage)
        memory_max_vms = int(memory_free / self.vm_memory_mb)
        total_max_vms = min(cpu_max_vms, memory_max_vms)
        instance_count = self.get_instance_count()
        with file_lock(self._lock_file):
            data = {"instances": [], "current_vms": 0}
            if os.path.exists(self._instance_file):
                with open(self._instance_file, "r") as f:
                    data = json.load(f)
            current_vms = data["current_vms"]
            available_vms = max(0, total_max_vms - current_vms)
            per_instance_max = max(1, available_vms // instance_count if instance_count > 0 else available_vms)
            logger.debug(f"Total max VMs: {total_max_vms}, instances: {instance_count}, current_vms: {current_vms}, available: {available_vms}, per instance: {per_instance_max}")
            return per_instance_max

    def register_vms(self, count: int) -> bool:
        """Register a number of VMs if resources allow."""
        stats = self.update_stats()
        total_max_vms = min(
            int((100 - stats["cpu_percent"] - self.min_cpu_free) / self.vm_cpu_usage),
            int((stats["memory_total_mb"] - stats["memory_used_mb"] - self.min_memory_mb) / self.vm_memory_mb)
        )
        with file_lock(self._lock_file):
            data = {"instances": [], "current_vms": 0}
            if os.path.exists(self._instance_file):
                with open(self._instance_file, "r") as f:
                    data = json.load(f)
            current_vms = data["current_vms"]
            if current_vms + count <= total_max_vms:
                data["current_vms"] = current_vms + count
                with open(self._instance_file, "w") as f:
                    json.dump(data, f)
                    f.flush()
                logger.debug(f"Registered {count} VMs, total running: {data['current_vms']}")
                return True
            logger.warning(f"Cannot register {count} VMs, exceeds max {total_max_vms} (current: {current_vms})")
            return False

    def unregister_vms(self, count: int):
        """Unregister a number of VMs."""
        with file_lock(self._lock_file):
            data = {"instances": [], "current_vms": 0}
            if os.path.exists(self._instance_file):
                with open(self._instance_file, "r") as f:
                    data = json.load(f)
            new_vms = max(0, data["current_vms"] - count)
            data["current_vms"] = new_vms
            with open(self._instance_file, "w") as f:
                json.dump(data, f)
                f.flush()
            logger.debug(f"Unregistered {count} VMs, total running: {new_vms}")

    def get_total_max_vms(self):
        stats = self.update_stats()
        cpu_free = max(0, 100 - stats["cpu_percent"] - self.min_cpu_free)
        memory_free = max(0, stats["memory_total_mb"] - stats["memory_used_mb"] - self.min_memory_mb)
        cpu_max_vms = int(cpu_free / self.vm_cpu_usage)
        memory_max_vms = int(memory_free / self.vm_memory_mb)
        return min(cpu_max_vms, memory_max_vms)

    def get_fair_share(self, total_max_vms: int):
        #total_max_vms = self.get_total_max_vms()
        instance_count = self.get_instance_count()
        return total_max_vms // instance_count if instance_count > 0 else 0

    def get_current_fair_share(self, total_max_vms: int):
        instance_count = self.get_instance_count()
        return total_max_vms // instance_count if instance_count > 0 else 0
    

system_resources = SystemResources()

def get_max_vms() -> int:
    return system_resources.get_max_vms()
