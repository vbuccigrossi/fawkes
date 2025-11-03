import psutil
import time
import logging
from typing import Dict
from fawkes.config import FawkesConfig, VMRegistry

logger = logging.getLogger("fawkes.monitor")

class ResourceMonitor:
    def __init__(self, cfg: FawkesConfig, registry: VMRegistry):
        self.cfg = cfg
        self.registry = registry
        self.logger = logger
        self.stats = {"cpu_percent": 0.0, "memory_percent": 0.0, "running_vms": 0}

    def update(self) -> Dict[str, float]:
        self.stats["cpu_percent"] = psutil.cpu_percent(interval=1)
        self.stats["memory_percent"] = psutil.virtual_memory().percent
        with self.registry._lock:
            running = 0
            for vm_id in self.registry.vms:
                vm_info = self.registry.get_vm(vm_id)
                # Debug to see what we're getting
                self.logger.debug(f"VM {vm_id} info: {vm_info}")
                if isinstance(vm_info, dict) and vm_info.get("status") == "Running":
                    running += 1
                elif vm_info == vm_id:  # Fallback if get_vm returns the ID
                    self.logger.warning(f"get_vm({vm_id}) returned ID instead of dict, assuming not running")
            self.stats["running_vms"] = running
        self.logger.debug(f"Resource stats: {self.stats}")
        return self.stats

    def can_spawn_vm(self) -> bool:
        self.update()
        cpu_ok = self.stats["cpu_percent"] < 90.0
        mem_ok = self.stats["memory_percent"] < 90.0
        vms_ok = self.stats["running_vms"] < self.cfg.max_parallel_vms
        return cpu_ok and mem_ok and vms_ok

def get_monitor(cfg: FawkesConfig, registry: VMRegistry) -> ResourceMonitor:
    return ResourceMonitor(cfg, registry)
