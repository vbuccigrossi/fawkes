# fawkes/qemu.py
import signal
import socket
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict, Any
from fawkes.config import FawkesConfig, VMRegistry
from fawkes.arch.architectures import SupportedArchitectures

def pick_free_port():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

class QemuManager:
    def __init__(self, config: FawkesConfig, registry: VMRegistry):
        self.config = config
        self.registry = registry
        self.logger = logging.getLogger("fawkes.QemuManager")

        # Use comprehensive architecture support
        self.supported_archs = SupportedArchitectures

        # Fix race condition: acquire lock before checking statuses
        if self.registry:
            self.refresh_statuses()  # Check VM statuses on init

    def refresh_statuses(self):
        """Update the status of all VMs based on PID aliveness."""
        if not self.registry:
            return
        with self.registry._lock:
            # Iterate over VM data (values), not VM IDs (keys)
            for vm in self.registry.vms.values():
                if not isinstance(vm, dict):  # Skip metadata like "last_vm_id"
                    continue
                if vm["status"] == "Running" and not is_pid_alive(vm["pid"]):
                    vm["status"] = "Stopped"
                    self.logger.debug(f"Updated VM {vm['id']} status to Stopped (PID {vm['pid']} not alive)")
            self.registry.save()

    def start_vm(self, disk: str, memory: str = None, debug: bool = False,
                 pause_on_start: bool = True, extra_opts: Optional[str] = None) -> Optional[int]:
        with self.registry._lock:
            running_count = sum(1 for v in self.registry.vms.values() if isinstance(v, dict) and v["status"] == "Running")

            max_vms = self.config.get("max_parallel_vms")
            if max_vms != 0 and running_count >= max_vms:
                self.logger.error("Maximum parallel VMs reached (%d). Cannot start new VM.", self.config.get("max_parallel_vms"))
                return None

        if not os.path.exists(disk):
            self.logger.error(f"Original disk '{disk}' does not exist.")
            return None

        # this is a temp fix so obviously it's now permenent so live with that knowledge...
        temp_disk = Path(disk)
        temp_dir = temp_disk.parent
        sub_dir = temp_dir / "fawkes_shared"
        sub_dir.mkdir(parents=True, exist_ok=True)
        self.logger.debug(f"Created share directory for at {sub_dir}")

        arch = self.config.get("arch", "x86_64")
        qemu_binary = self.supported_archs.get_qemu_binary(arch)
        if not qemu_binary:
            self.logger.error(f"Unsupported architecture: {arch}")
            self.logger.error(f"Supported architectures: {', '.join(self.supported_archs.list_architectures())}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        cmd = [qemu_binary, "-drive", f"file={temp_disk},format=qcow2"]

        snapshot_name = self.config.get("snapshot_name")
        if snapshot_name:
            cmd += ["-loadvm", snapshot_name]
            self.logger.debug(f"Loading snapshot '{snapshot_name}' for VM")

        share_dir = os.path.expanduser(sub_dir)
        os.makedirs(share_dir, exist_ok=True)
        agent_port = pick_free_port()

        if self.config.get("use_smb", False):  # SMB for Windows
            cmd += ["-net", f"user,smb={share_dir},hostfwd=tcp::{agent_port}-:9999", "-net", "nic"]
            self.logger.debug(f"Using SMB share at {share_dir} with agent port {agent_port}")
        elif self.config.get("use_vfs", False):  # VirtFS for Linux/Unix
            cmd += ["-virtfs", f"local,path={share_dir},mount_tag=hostshare,security_model=none"]
            self.logger.debug(f"Using VirtFS share at {share_dir}")
        else:  # Default to SMB
            cmd += ["-net", f"user,smb={share_dir},hostfwd=tcp::{agent_port}-:9999", "-net", "nic"]
            self.logger.debug(f"No share method specified, defaulting to SMB at {share_dir} with agent port {agent_port}")
    
        if not self.config.get("no_headless", False):
            cmd += ["-nographic"]

        debug_port = None
        monitor_port = None
        if debug:
            debug_port = pick_free_port()
            monitor_port = pick_free_port()  # Add monitor port for VM control
            cmd += ["-gdb", f"tcp::{debug_port}"]
            # Add QEMU monitor on TCP for programmatic control
            cmd += ["-monitor", f"tcp:127.0.0.1:{monitor_port},server,nowait"]
            if pause_on_start:
                cmd.append("-S")

        vm_params = self.config.get("vm_params", False)
        if vm_params:
            cmd.extend(vm_params.split())

        self.logger.debug(f"Starting QEMU with command: {' '.join(cmd)}")
        try:
            # Capture stderr to check for errors properly
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL, stderr=subprocess.PIPE)
            time.sleep(1)
            if proc.poll() is not None:
                stderr_output = ""
                if proc.stderr:
                    stderr_output = proc.stderr.read().decode()
                self.logger.debug(f"QEMU stderr output: {stderr_output}")
                if "disk-only snapshot" in stderr_output:
                    error_msg = (
                        f"Snapshot '{snapshot_name}' is disk-only and cannot be loaded with -loadvm. "
                        f"To fix: Boot VM with '{qemu_binary} -drive file={disk},format=qcow2 -m 256M', "
                        f"then in QEMU monitor (Ctrl+Alt+2): savevm {snapshot_name}, shut down, and retry."
                    )
                    self.logger.error(error_msg)
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    raise RuntimeError(error_msg)
                self.logger.error(f"QEMU failed to start: {stderr_output}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

            vm_data = {
                "pid": proc.pid,
                "disk_path": str(temp_disk),
                "original_disk": disk,
                "memory": memory,
                "debug": debug,
                "debug_port": debug_port,
                "monitor_port": monitor_port,
                "agent_port": agent_port,
                "extra_opts": extra_opts or "",
                "status": "Running",
                "share_dir": share_dir,
                "arch": arch,
                "temp_dir": str(temp_dir),
                "snapshot_name": snapshot_name
            }
            try:
                vm_id = self.registry.add_vm(vm_data)
            except Exception as e:
                self.logger.error("Failed to register VM with error: {e}")
            self.logger.debug(f"Add VM to registry with vm_id: {vm_id}")
            self.logger.info(f"Started VM {vm_id} (PID={proc.pid}, debug_port={debug_port}, arch={arch})")
            return vm_id
        except Exception as e:
            self.logger.error(f"Failed to start QEMU: {e}", exc_info=True)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

    def stop_vm(self, vm_id: int, force: bool = False):
        """Stop a VM, optionally forcing cleanup."""
        with self.registry._lock:
            vm_info = self.registry.get_vm(vm_id)
            if not vm_info or vm_info["status"] != "Running":
                self.logger.debug(f"VM {vm_id} not running or not found")
                return
            pid = vm_info["pid"]
            self.logger.info(f"Stopping VM {vm_id} (PID={pid})")
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                if is_pid_alive(pid):
                    self.logger.warning(f"Force-killing VM {vm_id}")
                    os.kill(pid, signal.SIGKILL)
                vm_info["status"] = "Stopped"
                if force:
                    temp_dir = vm_info.get("temp_dir")
                    if temp_dir and os.path.exists(temp_dir):
                        self.logger.debug(f"Cleaning up temp dir {temp_dir} for VM {vm_id}")
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    self.registry.remove_vm(vm_id)
                self.registry.save()
            except Exception as e:
                self.logger.error(f"Failed to stop VM {vm_id}: {e}", exc_info=True)
   
    def stop_all(self) -> None:
        """Stop all running VMs and clean up."""
        if not self.registry:
            return
        with self.registry._lock:
            for vm_id, vm in list(self.registry.vms.items()):
                if not isinstance(vm, dict):  # Skip "last_vm_id"
                    continue
                if vm["status"] == "Running":
                    self.stop_vm(vm_id)
            self.registry.save()
    
   # Snapshot management
    def create_snapshot(self, disk_path: str, snap_name: str) -> bool:
        """
        Create a new snapshot in disk_path. Return True if success, False if error.
        """
        if not os.path.exists(disk_path):
            self.logger.error(f"[FAWKES] Disk path '{disk_path}' does not exist.")
            return False

        cmd = ["qemu-img", "snapshot", "-c", snap_name, disk_path]
        ret = subprocess.run(cmd, capture_output=True, text=True)
        if ret.returncode == 0:
            self.logger.info(f"[FAWKES] Snapshot '{snap_name}' created on '{disk_path}'.")
            return True
        else:
            self.logger.error(f"[FAWKES] Failed to create snapshot '{snap_name}': {ret.stderr}")
            return False

    def revert_to_snapshot(self, vm_id: int, snapshot_name: str):
        """Revert a VM to a snapshot by restarting it cleanly."""
        with self.registry._lock:
            vm_info = self.registry.get_vm(vm_id)
            if not vm_info:
                self.logger.error(f"VM: {vm_id} could not be found so it will not be started/restarted")
                return

            if vm_info["status"] != "Running":
                self.logger.error(f"VM {vm_id} is not running starting it now")
           
            pid = vm_info["pid"]
            disk_path = vm_info["disk_path"]
            debug_port = vm_info["debug_port"]
            monitor_port = vm_info.get("monitor_port")  # Get existing monitor port
            agent_port = vm_info["agent_port"]
            share_dir = vm_info["share_dir"]
            arch = vm_info["arch"]
   
        # Stop the VM if we see it is still running
        if  vm_info["status"] == "Running":
            self.stop_vm(vm_id, force=False)

        # Restart with snapshot
        qemu_binary = self.supported_archs.get_qemu_binary(arch)
        if not qemu_binary:
            self.logger.error(f"Unsupported architecture for restart: {arch}")
            return

        cmd = [
            qemu_binary, "-drive", f"file={disk_path},format=qcow2",
            "-loadvm", snapshot_name,
        ]

        if self.config.get("use_smb", False):  # SMB for Windows
            cmd += ["-net", f"user,smb={share_dir},hostfwd=tcp::{agent_port}-:9999", "-net", "nic"]
            self.logger.debug(f"Using SMB share at {share_dir} with agent port {agent_port}")
        elif self.config.get("use_vfs", False):  # VirtFS for Linux/Unix
            cmd += ["-virtfs", f"local,path={share_dir},mount_tag=hostshare,security_model=none"]
            self.logger.debug(f"Using VirtFS share at {share_dir}")
        else:  # Default to SMB
            cmd += ["-net", f"user,smb={share_dir},hostfwd=tcp::{agent_port}-:9999", "-net", "nic"]
            self.logger.debug(f"No share method specified, defaulting to SMB at {share_dir} with agent port {agent_port}")
        
        if not self.config.get("no_headless", False):
            cmd += ["-nographic"]

        # Allocate new monitor port if not exists, or reuse existing
        if not monitor_port:
            monitor_port = pick_free_port()

        cmd += ["-gdb", f"tcp::{debug_port}"]
        cmd += ["-monitor", f"tcp:127.0.0.1:{monitor_port},server,nowait"]
        cmd += ["-S"]

        vm_params = self.config.get("vm_params", False)
        if vm_params:
            cmd.extend(vm_params.split())

        self.logger.debug(f"Restarting VM {vm_id} with snapshot {snapshot_name}: {' '.join(cmd)}")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL, stderr=subprocess.PIPE)
            time.sleep(1)
            if proc.poll() is not None:
                stderr_output = ""
                if proc.stderr:
                    stderr_output = proc.stderr.read().decode()
                self.logger.error(f"QEMU restart failed: {stderr_output}")
                return
            with self.registry._lock:
                vm_info["pid"] = proc.pid
                vm_info["status"] = "Running"
                vm_info["monitor_port"] = monitor_port  # Update monitor port
                self.registry.save()
        except Exception as e:
            self.logger.error(f"Failed to restart VM {vm_id}: {e}", exc_info=True)
    
    def list_snapshots(self, disk_path: str) -> None:
        """
        Print the list of snapshots on a given disk.
        """
        cmd = ["qemu-img", "snapshot", "-l", disk_path]
        ret = subprocess.run(cmd, capture_output=True, text=True)
        if ret.returncode == 0:
            logger.info(f"[FAWKES] Found snapshots on image: {ret.stdout}")
        else:
            self.logger.error(f"[FAWKES] Error listing snapshots: {ret.stderr}")

