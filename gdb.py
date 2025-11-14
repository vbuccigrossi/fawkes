# fawkes/gdb.py
import errno
import hashlib
import threading
import time
import logging
import subprocess
import tempfile
import os
import socket
import json
from typing import Dict, Any, Optional

from fawkes.config import FawkesConfig, VMRegistry
from fawkes.qemu import QemuManager
from fawkes.db.db import FawkesDB

class GdbFuzzWorker:
    # GDB architecture mapping for different QEMU architectures
    GDB_ARCH_MAP = {
        "i386": "i386",
        "x86_64": "i386:x86-64",
        "aarch64": "aarch64",
        "arm": "arm",
        "mips": "mips",
        "mipsel": "mips",
        "sparc": "sparc",
        "sparc64": "sparc:v9",
        "ppc": "powerpc:common",
        "ppc64": "powerpc:common64",
    }

    def __init__(self, vm_id: int, qemu_mgr, timeout: int, fuzz_loop: bool = True):
        self.vm_id = vm_id
        self.qemu_mgr = qemu_mgr
        self.timeout = timeout
        self.fuzz_loop = fuzz_loop
        self.logger = logging.getLogger(f"fawkes.GdbFuzzWorker-{vm_id}")
        self.crash_detected = False
        self.crash_info = {}
        self.logger.debug(f"Initialized with timeout={self.timeout}")


    def wait_gdb_stub(self, host: str, port: int, timeout=5.0):
        deadline = time.time() + timeout
        while True:
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return          # success
            except OSError as e:
                if e.errno not in (errno.ECONNREFUSED, errno.ECONNRESET):
                    raise           # other network error
            if time.time() > deadline:
                raise TimeoutError(f"GDB stub on {host}:{port} not ready")
            time.sleep(0.1)


    def _send_monitor_command(self, host: str, port: int, command: str, timeout: float = 2.0) -> bool:
        """Send a command to QEMU monitor and return success status."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((host, port))
                time.sleep(0.1)  # Wait for monitor prompt
                s.recv(1024)  # Read initial prompt
                s.sendall(f"{command}\n".encode('utf-8'))
                time.sleep(0.1)
                response = s.recv(1024).decode('utf-8', errors='ignore')
                self.logger.debug(f"Monitor command '{command}' response: {response}")
                return True
        except Exception as e:
            self.logger.error(f"Failed to send monitor command '{command}': {e}")
            return False

    def start(self):
        """Start the GDB fuzz worker, checking both kernel and user-space crashes."""
        self.logger.info(f"Starting fuzz worker for VM {self.vm_id}, fuzz_loop={self.fuzz_loop}")
        with self.qemu_mgr.registry._lock:
            vm_info = self.qemu_mgr.registry.get_vm(self.vm_id)
            debug_port = vm_info["debug_port"]
            monitor_port = vm_info.get("monitor_port")  # Get monitor port for fallback
            agent_port = vm_info["agent_port"]  # Get per-VM agent port
            arch = vm_info.get("arch", "x86_64")  # Get architecture, default to x86_64
            if not debug_port or not agent_port:
                self.logger.error(f"Missing debug_port ({debug_port}) or agent_port ({agent_port}) for VM {self.vm_id}")
                return

        # Map QEMU architecture to GDB architecture
        gdb_arch = self.GDB_ARCH_MAP.get(arch, "auto")
        self.logger.debug(f"Using GDB architecture '{gdb_arch}' for QEMU arch '{arch}'")

        # Prepare enhanced GDB script with better state synchronization
        # This helps with modern Windows (10+) HAL initialization
        gdb_script = (
            f"target remote 127.0.0.1:{debug_port}\n"
            "set confirm off\n"
            f"set architecture {gdb_arch}\n"
            "set pagination off\n"
            "info registers\n"      # Force GDB to sync with target state
            "continue\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".gdb", delete=False) as f:
            f.write(gdb_script)
            gdb_script_path = f.name

        self.wait_gdb_stub("127.0.0.1", debug_port)
        # Spawn GDB
        try:
            self.logger.debug(f"Spawning GDB with command: gdb -q -x {gdb_script_path}")
            gdb_process = subprocess.Popen(
                ["gdb", "-q", "-x", f"{gdb_script_path}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            first_line = gdb_process.stdout.readline().rstrip()
            self.logger.debug(f"GDB first line: {first_line!r}")
        except Exception as e:
            self.logger.error(f"Failed to start GDB (is it installed?) error: {e}")

        # Wait a moment for GDB to execute its script
        time.sleep(0.5)

        # Use QEMU monitor as fallback to ensure VM continues
        # This is especially important for modern Windows (10+) which may not
        # respond properly to GDB continue commands alone
        if monitor_port:
            self.logger.debug(f"Sending 'cont' command via QEMU monitor on port {monitor_port}")
            if self._send_monitor_command("127.0.0.1", monitor_port, "cont"):
                self.logger.info(f"Successfully sent continue command via QEMU monitor for VM {self.vm_id}")
            else:
                self.logger.warning(f"Failed to send continue via monitor, relying on GDB only")
        else:
            self.logger.warning(f"No monitor port available for VM {self.vm_id}, relying on GDB only")

        # Monitor GDB and agent
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if gdb_process.poll() is not None:  # GDB exited (likely a crash)
                stdout, stderr = gdb_process.communicate()
                self.logger.debug(f"GDB exited: stdout={stdout}, stderr={stderr}")
                if "Program received signal" in stderr or "Segmentation fault" in stderr:
                    self.crash_detected = True
                    self.crash_info = {
                        "type": "kernel",
                        "gdb_output": stderr
                    }
                    self.logger.info(f"Kernel crash detected for VM {self.vm_id}")
                    break

            # Check user-space agent
            agent_crash = self._check_agent_crash(agent_port)
            if agent_crash.get("crash", False):
                self.crash_detected = True
                self.crash_info = {
                    "type": "user",
                    "pid": agent_crash.get("pid"),
                    "exe": agent_crash.get("exe"),
                    "exception": agent_crash.get("exception"),
                    "file": agent_crash.get("file")
                }
                self.logger.info(f"User-space crash detected for VM {self.vm_id}: {self.crash_info}")
                break

            time.sleep(0.5)  # Poll interval

        # Cleanup
        if gdb_process.poll() is None:
            gdb_process.terminate()
            try:
                gdb_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                gdb_process.kill()
        subprocess.run(["rm", "-f", gdb_script_path], check=False)

        if not self.crash_detected and not self.fuzz_loop:
            self.logger.debug(f"No crash detected for VM {self.vm_id} within timeout")

    def _check_agent_crash(self, agent_port: int) -> dict:
        """Query the user-space crash agent via TCP on the VM-specific port."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(("127.0.0.1", agent_port))  # Use VM-specific port
                s.sendall(b"GET_CRASH\n")  # Adjust if your agent expects different
                response = s.recv(1024).decode("utf-8")
                return json.loads(response)
        except (socket.error, json.JSONDecodeError) as e:
            self.logger.debug(f"Failed to query crash agent on port {agent_port}: {e}")
            return {"crash": False}


class GdbFuzzManager:
    def __init__(self, qemu_mgr, timeout: int):
        self.qemu_mgr = qemu_mgr
        self.timeout = timeout
        self.workers = {}  # {vm_id: Thread}
        self.worker_instances = {}  # {vm_id: GdbFuzzWorker}
        self.logger = logging.getLogger("fawkes.GdbFuzzManager")

    def start_fuzz_worker(self, vm_id: int, fuzz_loop: bool = True):
        """Start a GDB fuzz worker for a VM and store the instance."""
        worker = GdbFuzzWorker(vm_id, self.qemu_mgr, self.timeout, fuzz_loop)
        from threading import Thread
        thread = Thread(target=worker.start, name=f"GdbFuzzWorker-{vm_id}")
        thread.start()
        self.workers[vm_id] = thread
        self.worker_instances[vm_id] = worker  # Store the worker instance
        self.logger.info(f"Started fuzz worker for VM {vm_id}")

    def stop_all_workers(self):
        """Stop all running GDB workers."""
        for vm_id, thread in self.workers.items():
            if thread.is_alive():
                thread.join(timeout=2)
        self.workers.clear()
        self.worker_instances.clear()
        self.logger.info("Stopped all fuzz workers.")

    def get_worker(self, vm_id: int) -> Optional['GdbFuzzWorker']:
        """Get the GdbFuzzWorker instance for a VM."""
        return self.worker_instances.get(vm_id)


