# qemu.py
import signal
import socket
import logging
import os
import shutil
import subprocess
import tempfile
import time
import io
from pathlib import Path
from typing import Optional, Dict, Any
from config import FawkesConfig, VMRegistry
from arch.architectures import SupportedArchitectures
from fawkes.performance import perf_tracker

# Screenshot format conversion (optional - PIL provides better compression)
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

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
    
        # Display configuration
        vnc_port = None
        if self.config.get("enable_vm_screenshots", False):
            # Use VNC display for screenshots (headless VNC - no window needed on host)
            vnc_port = pick_free_port()
            vnc_display = vnc_port - 5900  # VNC display number (port 5900 + display)
            if vnc_display < 0:
                vnc_display = 0
                vnc_port = 5900
            cmd += ["-vnc", f"127.0.0.1:{vnc_display}"]
            self.logger.debug(f"VNC display enabled for screenshots on port {vnc_port}")
        elif not self.config.get("no_headless", False):
            cmd += ["-nographic"]

        debug_port = None
        monitor_port = None

        # Enable monitor port for debug mode OR screenshot mode
        needs_monitor = debug or self.config.get("enable_vm_screenshots", False)
        if needs_monitor:
            monitor_port = pick_free_port()
            cmd += ["-monitor", f"tcp:127.0.0.1:{monitor_port},server,nowait"]
            self.logger.debug(f"QEMU monitor enabled on port {monitor_port}")

        if debug:
            debug_port = pick_free_port()
            cmd += ["-gdb", f"tcp::{debug_port}"]
            if pause_on_start:
                cmd.append("-S")

        vm_params = self.config.get("vm_params", False)
        if vm_params:
            cmd.extend(vm_params.split())

        # Time compression via QEMU icount mode
        if self.config.get("enable_time_compression", False):
            shift = self.config.get("time_compression_shift", "auto")
            skip_idle = self.config.get("skip_idle_loops", True)

            # Build icount options
            icount_opts = f"shift={shift}"
            if skip_idle:
                icount_opts += ",align=off,sleep=off"

            cmd.extend(["-icount", icount_opts])
            cmd.extend(["-rtc", "clock=vm"])

            self.logger.info(f"Time compression enabled: icount={icount_opts}, rtc=vm (expected 3-10x speedup)")

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
                "vnc_port": vnc_port,
                "agent_port": agent_port,
                "extra_opts": extra_opts or "",
                "status": "Running",
                "share_dir": share_dir,
                "arch": arch,
                "temp_dir": str(temp_dir),
                "snapshot_name": snapshot_name,
                "screenshots_enabled": self.config.get("enable_vm_screenshots", False)
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

    def revert_to_snapshot(self, vm_id: int, snapshot_name: str, fast: bool = True):
        """
        Revert a VM to a snapshot.

        Args:
            vm_id: VM identifier
            snapshot_name: Name of snapshot to revert to
            fast: If True, use QEMU monitor loadvm (fast). If False, restart VM (slow).

        Performance:
            - Fast mode (monitor loadvm): ~100-200ms
            - Slow mode (VM restart): ~2-5 seconds
        """
        with self.registry._lock:
            vm_info = self.registry.get_vm(vm_id)
            if not vm_info:
                self.logger.error(f"VM {vm_id} not found")
                return

            monitor_port = vm_info.get("monitor_port")

        # Fast path: Use QEMU monitor to revert snapshot without restarting VM
        if fast and monitor_port:
            with perf_tracker.measure("snapshot_revert_fast"):
                if self._monitor_loadvm(vm_id, monitor_port, snapshot_name):
                    self.logger.debug(f"Fast snapshot revert successful for VM {vm_id}")
                    perf_tracker.increment("snapshot_revert_fast_success")
                    return
                else:
                    self.logger.warning(f"Fast snapshot revert failed for VM {vm_id}, falling back to slow path")
                    perf_tracker.increment("snapshot_revert_fast_failure")

        # Slow path: Stop and restart VM with snapshot (fallback or explicit)
        with perf_tracker.measure("snapshot_revert_slow"):
            self._slow_revert_to_snapshot(vm_id, snapshot_name)
            perf_tracker.increment("snapshot_revert_slow_count")

    def _monitor_loadvm(self, vm_id: int, monitor_port: int, snapshot_name: str) -> bool:
        """
        Use QEMU monitor to load a snapshot without restarting the VM.
        This is much faster than stopping and restarting.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Connect to QEMU monitor
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(('127.0.0.1', monitor_port))

            # Read QEMU monitor banner
            banner = sock.recv(4096).decode('utf-8', errors='ignore')
            self.logger.debug(f"QEMU monitor banner: {banner[:100]}")

            # Send stop command to pause VM
            sock.sendall(b"stop\n")
            time.sleep(0.1)
            response = sock.recv(4096).decode('utf-8', errors='ignore')
            self.logger.debug(f"Stop response: {response}")

            # Send loadvm command to revert snapshot
            loadvm_cmd = f"loadvm {snapshot_name}\n"
            sock.sendall(loadvm_cmd.encode())
            time.sleep(0.2)  # Give time for snapshot load
            response = sock.recv(4096).decode('utf-8', errors='ignore')
            self.logger.debug(f"Loadvm response: {response}")

            # Check for errors
            if "error" in response.lower() or "unknown" in response.lower():
                self.logger.error(f"Loadvm failed: {response}")
                sock.close()
                return False

            # Send cont command to resume VM
            sock.sendall(b"cont\n")
            time.sleep(0.1)
            response = sock.recv(4096).decode('utf-8', errors='ignore')
            self.logger.debug(f"Cont response: {response}")

            sock.close()
            return True

        except socket.timeout:
            self.logger.error(f"Timeout connecting to QEMU monitor on port {monitor_port}")
            return False
        except socket.error as e:
            self.logger.error(f"Socket error communicating with QEMU monitor: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during monitor loadvm: {e}", exc_info=True)
            return False

    def _slow_revert_to_snapshot(self, vm_id: int, snapshot_name: str):
        """Slow path: Revert VM to snapshot by stopping and restarting (legacy behavior)."""
        with self.registry._lock:
            vm_info = self.registry.get_vm(vm_id)
            if not vm_info:
                self.logger.error(f"VM {vm_id} not found")
                return

            if vm_info["status"] != "Running":
                self.logger.error(f"VM {vm_id} is not running")

            pid = vm_info["pid"]
            disk_path = vm_info["disk_path"]
            debug_port = vm_info["debug_port"]
            monitor_port = vm_info.get("monitor_port")
            agent_port = vm_info["agent_port"]
            share_dir = vm_info["share_dir"]
            arch = vm_info["arch"]

        # Stop the VM if running
        if vm_info["status"] == "Running":
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

        if self.config.get("use_smb", False):
            cmd += ["-net", f"user,smb={share_dir},hostfwd=tcp::{agent_port}-:9999", "-net", "nic"]
        elif self.config.get("use_vfs", False):
            cmd += ["-virtfs", f"local,path={share_dir},mount_tag=hostshare,security_model=none"]
        else:
            cmd += ["-net", f"user,smb={share_dir},hostfwd=tcp::{agent_port}-:9999", "-net", "nic"]

        if not self.config.get("no_headless", False):
            cmd += ["-nographic"]

        if not monitor_port:
            monitor_port = pick_free_port()

        cmd += ["-gdb", f"tcp::{debug_port}"]
        cmd += ["-monitor", f"tcp:127.0.0.1:{monitor_port},server,nowait"]
        cmd += ["-S"]

        vm_params = self.config.get("vm_params", False)
        if vm_params:
            cmd.extend(vm_params.split())

        self.logger.debug(f"Restarting VM {vm_id} with snapshot {snapshot_name}")
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
                vm_info["monitor_port"] = monitor_port
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

    # Screenshot functionality for web UI
    def capture_screenshot(self, vm_id: int, output_path: str = None) -> Optional[bytes]:
        """
        Capture a screenshot from a running VM using QEMU monitor's screendump command.

        Args:
            vm_id: VM identifier
            output_path: Optional path to save the screenshot (if None, returns bytes)

        Returns:
            Screenshot as PNG bytes if output_path is None, else None (saves to file)
        """
        vm_info = self.registry.get_vm(vm_id)
        if not vm_info:
            self.logger.error(f"VM {vm_id} not found")
            return None

        if vm_info.get("status") != "Running":
            self.logger.debug(f"VM {vm_id} is not running, cannot capture screenshot")
            return None

        monitor_port = vm_info.get("monitor_port")
        if not monitor_port:
            self.logger.debug(f"VM {vm_id} has no monitor port, screenshots not available")
            return None

        # Create temp file for screendump
        screenshot_dir = os.path.expanduser(self.config.get("screenshot_dir", "~/.fawkes/screenshots"))
        os.makedirs(screenshot_dir, exist_ok=True)
        temp_ppm = os.path.join(screenshot_dir, f"vm_{vm_id}_temp.ppm")

        try:
            # Connect to QEMU monitor
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(('127.0.0.1', monitor_port))

            # Read QEMU monitor banner
            banner = sock.recv(4096).decode('utf-8', errors='ignore')
            self.logger.debug(f"Monitor connected for screenshot (VM {vm_id})")

            # Send screendump command
            screendump_cmd = f"screendump {temp_ppm}\n"
            sock.sendall(screendump_cmd.encode())
            time.sleep(0.3)  # Give time for screenshot to be written

            # Read response
            response = sock.recv(4096).decode('utf-8', errors='ignore')
            sock.close()

            # Check if file was created
            if not os.path.exists(temp_ppm):
                self.logger.error(f"Screendump failed for VM {vm_id}: file not created")
                return None

            # Convert PPM to PNG
            png_bytes = self._convert_ppm_to_png(temp_ppm)

            # Clean up temp file
            try:
                os.remove(temp_ppm)
            except OSError:
                pass

            if output_path:
                with open(output_path, 'wb') as f:
                    f.write(png_bytes)
                self.logger.debug(f"Screenshot saved to {output_path}")
                return None
            else:
                return png_bytes

        except socket.timeout:
            self.logger.error(f"Timeout connecting to QEMU monitor for VM {vm_id}")
            return None
        except socket.error as e:
            self.logger.error(f"Socket error capturing screenshot for VM {vm_id}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error capturing screenshot for VM {vm_id}: {e}", exc_info=True)
            return None

    def _convert_ppm_to_png(self, ppm_path: str) -> bytes:
        """
        Convert PPM file to PNG bytes.

        Uses PIL if available for better compression, otherwise uses basic conversion.
        """
        if HAS_PIL:
            # Use PIL for conversion (better quality and compression)
            with Image.open(ppm_path) as img:
                buffer = io.BytesIO()
                img.save(buffer, format='PNG', optimize=True)
                return buffer.getvalue()
        else:
            # Fallback: Read PPM and return raw (or use subprocess convert if available)
            try:
                # Try using ImageMagick's convert if available
                result = subprocess.run(
                    ['convert', ppm_path, 'png:-'],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return result.stdout
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

            # Last resort: return raw PPM data (browser won't display it)
            self.logger.warning("Neither PIL nor ImageMagick available for PNG conversion")
            with open(ppm_path, 'rb') as f:
                return f.read()

    def get_all_vm_screenshots(self) -> Dict[int, bytes]:
        """
        Capture screenshots from all running VMs.

        Returns:
            Dict mapping vm_id to PNG bytes
        """
        screenshots = {}
        for vm_id, vm_info in self.registry.vms.items():
            if not isinstance(vm_info, dict):
                continue
            if vm_info.get("status") == "Running" and vm_info.get("screenshots_enabled"):
                screenshot = self.capture_screenshot(vm_id)
                if screenshot:
                    screenshots[vm_id] = screenshot
        return screenshots

