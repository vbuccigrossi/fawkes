"""
Differential Fuzzing Harness

Executes testcases across multiple targets (versions/implementations)
and compares their behavior.
"""

import os
import logging
import shutil
import time
import hashlib
from typing import Dict, List, Optional
from pathlib import Path

from fawkes.qemu import QemuManager
from fawkes.gdb import GdbFuzzManager
from fawkes.config import VMRegistry
from .engine import (
    DifferentialEngine,
    ExecutionResult,
    Divergence
)


class DifferentialTarget:
    """Represents one target (version/implementation) for differential fuzzing"""

    def __init__(self, target_id: str, version: str, disk_image: str,
                 snapshot_name: str, arch: str = "x86_64"):
        self.target_id = target_id
        self.version = version
        self.disk_image = os.path.expanduser(disk_image)
        self.snapshot_name = snapshot_name
        self.arch = arch

        if not os.path.exists(self.disk_image):
            raise FileNotFoundError(f"Disk image not found: {self.disk_image}")

    def __repr__(self):
        return f"DifferentialTarget({self.target_id}, {self.version})"


class DifferentialHarness:
    """
    Harness for differential fuzzing across multiple targets

    Executes the same testcase on multiple targets and compares results.
    """

    def __init__(self, targets: List[DifferentialTarget], timeout: int = 60,
                 output_dir: str = "~/.fawkes/differential"):
        """
        Args:
            targets: List of targets to compare
            timeout: Execution timeout per target (seconds)
            output_dir: Directory for storing results
        """
        self.logger = logging.getLogger("fawkes.differential.harness")
        self.targets = targets
        self.timeout = timeout
        self.output_dir = os.path.expanduser(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        # Initialize differential engine
        self.engine = DifferentialEngine()

        # Initialize QEMU and GDB managers for each target
        self.qemu_managers: Dict[str, QemuManager] = {}
        self.gdb_managers: Dict[str, GdbFuzzManager] = {}
        self.vm_ids: Dict[str, int] = {}

        self.logger.info(f"Initialized differential harness with {len(targets)} targets")
        for target in targets:
            self.logger.info(f"  - {target.target_id}: {target.version} ({target.arch})")

    def setup_target(self, target: DifferentialTarget) -> bool:
        """
        Setup VM for a specific target

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create registry for this target
            registry_path = os.path.join(self.output_dir, f"registry_{target.target_id}.json")
            registry = VMRegistry(registry_path)

            # Create QEMU manager
            from fawkes.config import FawkesConfig
            config = FawkesConfig()
            config.arch = target.arch
            config.snapshot_name = target.snapshot_name
            config.max_parallel_vms = 1

            qemu_mgr = QemuManager(config, registry)
            self.qemu_managers[target.target_id] = qemu_mgr

            # Start VM
            vm_id = qemu_mgr.start_vm(
                disk=target.disk_image,
                memory="2G",
                debug=True,
                pause_on_start=False
            )

            if not vm_id:
                self.logger.error(f"Failed to start VM for target {target.target_id}")
                return False

            self.vm_ids[target.target_id] = vm_id

            # Create GDB manager
            gdb_mgr = GdbFuzzManager(qemu_mgr, self.timeout)
            self.gdb_managers[target.target_id] = gdb_mgr

            self.logger.info(f"Target {target.target_id} setup complete (VM ID: {vm_id})")
            return True

        except Exception as e:
            self.logger.error(f"Error setting up target {target.target_id}: {e}", exc_info=True)
            return False

    def execute_on_target(self, target: DifferentialTarget,
                         testcase_path: str) -> Optional[ExecutionResult]:
        """
        Execute testcase on a specific target

        Args:
            target: Target to execute on
            testcase_path: Path to testcase file

        Returns:
            ExecutionResult or None if execution failed
        """
        target_id = target.target_id
        vm_id = self.vm_ids.get(target_id)

        if not vm_id:
            self.logger.error(f"No VM for target {target_id}")
            return None

        try:
            qemu_mgr = self.qemu_managers[target_id]
            gdb_mgr = self.gdb_managers[target_id]

            # Revert to clean snapshot
            qemu_mgr.revert_to_snapshot(vm_id, target.snapshot_name)
            time.sleep(0.5)  # Let VM stabilize

            # Get share directory
            with qemu_mgr.registry._lock:
                vm_info = qemu_mgr.registry.get_vm(vm_id)
                share_dir = vm_info["share_dir"]

            # Copy testcase to share directory
            testcase_name = os.path.basename(testcase_path)
            share_testcase = os.path.join(share_dir, testcase_name)
            shutil.copy2(testcase_path, share_testcase)

            # Execute with GDB monitoring
            start_time = time.time()

            gdb_mgr.start_fuzz_worker(vm_id, fuzz_loop=False)
            worker_thread = gdb_mgr.workers.get(vm_id)

            # Wait for execution to complete or timeout
            if worker_thread:
                worker_thread.join(timeout=self.timeout + 5)

            execution_time = (time.time() - start_time) * 1000  # milliseconds

            # Get results from GDB worker
            gdb_worker = gdb_mgr.get_worker(vm_id)

            # Collect execution results
            crashed = False
            signal = None
            registers = None
            timeout_occurred = execution_time > (self.timeout * 1000)

            if gdb_worker and gdb_worker.crash_detected:
                crashed = True
                crash_info = gdb_worker.crash_info
                signal = crash_info.get("signal")
                registers = self._parse_registers(crash_info.get("reg_bt", ""))

            # Capture output (if available)
            stdout = None
            stderr = None
            output_hash = None

            # Try to read output file if exists
            output_file = os.path.join(share_dir, "output.txt")
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    stdout = f.read()
                    output_hash = hashlib.sha256(stdout.encode()).hexdigest()

            result = ExecutionResult(
                target_id=target_id,
                target_version=target.version,
                testcase_path=testcase_path,
                crashed=crashed,
                exit_code=0 if not crashed else -1,
                timeout=timeout_occurred,
                execution_time=execution_time,
                stdout=stdout,
                stderr=stderr,
                output_hash=output_hash,
                registers=registers,
                signal=signal,
                memory_usage=None,  # TODO: Implement memory tracking
                error_message=None
            )

            self.logger.debug(f"Executed {testcase_name} on {target_id}: "
                            f"crashed={crashed}, timeout={timeout_occurred}, "
                            f"time={execution_time:.1f}ms")

            return result

        except Exception as e:
            self.logger.error(f"Error executing on target {target_id}: {e}", exc_info=True)
            return ExecutionResult(
                target_id=target_id,
                target_version=target.version,
                testcase_path=testcase_path,
                crashed=False,
                exit_code=-1,
                timeout=False,
                execution_time=0,
                stdout=None,
                stderr=None,
                output_hash=None,
                registers=None,
                signal=None,
                memory_usage=None,
                error_message=str(e)
            )

    def run_differential_testcase(self, testcase_path: str) -> List[Divergence]:
        """
        Run testcase across all targets and detect divergences

        Args:
            testcase_path: Path to testcase

        Returns:
            List of detected divergences
        """
        self.logger.info(f"Running differential testcase: {testcase_path}")

        # Execute on all targets
        results = []
        for target in self.targets:
            result = self.execute_on_target(target, testcase_path)
            if result:
                results.append(result)
            else:
                self.logger.warning(f"Execution failed for target {target.target_id}")

        if len(results) < 2:
            self.logger.error("Need at least 2 successful executions for comparison")
            return []

        # Compare all pairs of results
        divergences = []
        for i in range(len(results)):
            for j in range(i + 1, len(results)):
                divs = self.engine.compare_executions(results[i], results[j])
                divergences.extend(divs)

        # Update stats
        self.engine.stats["testcases_executed"] += 1
        if any(r.crashed for r in results):
            self.engine.stats["crashes_found"] += 1
        if any(r.timeout for r in results):
            self.engine.stats["timeouts"] += 1

        return divergences

    def run_campaign(self, testcase_dir: str, max_testcases: Optional[int] = None) -> Dict:
        """
        Run differential fuzzing campaign across all testcases

        Args:
            testcase_dir: Directory containing testcases
            max_testcases: Maximum number of testcases to run (None = all)

        Returns:
            Campaign statistics
        """
        testcase_dir = os.path.expanduser(testcase_dir)
        if not os.path.isdir(testcase_dir):
            raise ValueError(f"Testcase directory not found: {testcase_dir}")

        # Setup all targets
        self.logger.info("Setting up targets...")
        for target in self.targets:
            if not self.setup_target(target):
                raise RuntimeError(f"Failed to setup target {target.target_id}")

        # Get all testcases
        testcases = []
        for root, dirs, files in os.walk(testcase_dir):
            for file in files:
                testcases.append(os.path.join(root, file))

        if max_testcases:
            testcases = testcases[:max_testcases]

        self.logger.info(f"Running campaign with {len(testcases)} testcases...")

        # Run testcases
        for i, testcase_path in enumerate(testcases, 1):
            self.logger.info(f"[{i}/{len(testcases)}] Processing {os.path.basename(testcase_path)}")

            divergences = self.run_differential_testcase(testcase_path)

            if divergences:
                self.logger.warning(f"Found {len(divergences)} divergences!")
                for div in divergences:
                    self.logger.warning(f"  {div.divergence_type.value}: {div.description}")

        # Cleanup
        self.cleanup()

        return self.engine.get_stats()

    def cleanup(self):
        """Cleanup all VMs and resources"""
        self.logger.info("Cleaning up targets...")
        for target_id, qemu_mgr in self.qemu_managers.items():
            vm_id = self.vm_ids.get(target_id)
            if vm_id:
                qemu_mgr.stop_vm(vm_id, force=True)

    def _parse_registers(self, reg_bt: str) -> Dict[str, str]:
        """Parse register values from GDB output"""
        registers = {}
        for line in reg_bt.split('\n'):
            line = line.strip()
            if not line or '=' not in line:
                continue

            parts = line.split('=', 1)
            if len(parts) == 2:
                reg_name = parts[0].strip()
                reg_value = parts[1].strip().split()[0]  # Take first token
                registers[reg_name] = reg_value

        return registers

    def get_divergences(self) -> List[Divergence]:
        """Get all detected divergences"""
        return self.engine.divergences

    def get_critical_divergences(self) -> List[Divergence]:
        """Get critical divergences"""
        return self.engine.get_critical_divergences()

    def generate_report(self) -> str:
        """Generate summary report"""
        return self.engine.generate_summary_report()
