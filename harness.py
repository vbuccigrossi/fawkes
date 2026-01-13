import os
import logging
import shutil
from pathlib import Path
import time
import json
import zipfile
from datetime import datetime
from nbd import NbdManager
from qemu import QemuManager
from config import FawkesConfig, VMRegistry
from db.db import FawkesDB
from fuzzers import load_fuzzer
from analysis import load_analyzer
from fawkes.performance import perf_tracker
from sanitizers import SanitizerDetector

class FileFuzzHarness:
    def __init__(self, qemu_mgr: QemuManager, gdb_mgr, db, input_dir: str, disk_path: str,
                 snapshot_name: str = "clean", cfg=None):
        self.logger = logging.getLogger("fawkes.FileFuzzHarness")
        self.qemu_mgr = qemu_mgr
        self.gdb_mgr = gdb_mgr
        self.db = db
        self.input_dir = os.path.expanduser(input_dir)
        self.disk_path = os.path.expanduser(disk_path)
        self.snapshot_name = snapshot_name
        self.cfg = cfg

        self.logger.debug(f"calling load_fuzzer with options: cfg.fuzzer: {cfg.fuzzer} \n\t\tinput_dir: {input_dir} \n\t\tcfg.fuzzer_config: {cfg.fuzzer_config} \n\t\tself.cfg: {self.cfg}")
        self.fuzzer = load_fuzzer(cfg.fuzzer, input_dir, self.cfg)
        self.analyzer = load_analyzer(cfg.arch, cfg.crash_dir)  # Load arch-specific analyzer
        self.sanitizer_detector = SanitizerDetector()
        self.vm_id = None
        self.share_dir = None
        self.logger.info(f"Called load_fuzzers with options: cfg_fuzzer: {cfg.fuzzer} \n\tinput_dir: {input_dir} \n\tcgf.fuzzer_config: {cfg.fuzzer_config}")


    def setup_vm(self):
        """Set up a single VM without script injection."""
        temp_dir = os.path.join("/tmp", f"fawkes_vm_{os.urandom(4).hex()}")
        os.makedirs(temp_dir, exist_ok=True)
        temp_disk = os.path.join(temp_dir, f"disk_{os.urandom(4).hex()}.qcow2")
        self.logger.debug(f"Copying {self.disk_path} to {temp_disk}")
        shutil.copy2(self.disk_path, temp_disk)

        # Start VM with the disk
        self.vm_id = self.qemu_mgr.start_vm(
            disk=temp_disk,
            memory=None,
            debug=True,
            pause_on_start=False,
            extra_opts=None
        )

        self.logger.debug(f"got vm id: {self.vm_id}")
        if not self.vm_id:
            self.logger.error("Failed to initialize VM")
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise RuntimeError("VM setup failed")

        # Get share_dir from vm_info
        with self.qemu_mgr.registry._lock:
            vm_info = self.qemu_mgr.registry.get_vm(self.vm_id)
            self.share_dir = vm_info["share_dir"]
            os.makedirs(self.share_dir, exist_ok=True)

        self.temp_dir = temp_dir


    def run_single_testcase(self, job_id: int):
        self.logger.debug("Starting testcase execution")
        if not self.vm_id:
            with perf_tracker.measure("vm_setup"):
                self.setup_vm()
        try:
            # Revert to snapshot with performance tracking
            with perf_tracker.measure("snapshot_revert"):
                self.qemu_mgr.revert_to_snapshot(self.vm_id, self.snapshot_name)

            # Generate testcase
            with perf_tracker.measure("testcase_generation"):
                testcase_path = self.fuzzer.generate_testcase()

            # Measure execution time
            start_time = time.time()
            with perf_tracker.measure("testcase_injection"):
                self.inject_testcase(testcase_path, self.vm_id, job_id)

            with perf_tracker.measure("testcase_execution"):
                self.gdb_mgr.start_fuzz_worker(self.vm_id, fuzz_loop=False)
                worker_thread = self.gdb_mgr.workers.get(self.vm_id)
                if worker_thread:
                    worker_thread.join()
                    gdb_worker = self.gdb_mgr.get_worker(self.vm_id)
                    if gdb_worker and gdb_worker.crash_detected:
                        perf_tracker.increment("crash_detected")
                        with perf_tracker.measure("crash_handling"):
                            self._handle_crash(gdb_worker.crash_info, testcase_path, job_id)

                            # Feed crash back to intelligent fuzzer for learning
                            if hasattr(self.fuzzer, 'record_crash'):
                                self.fuzzer.record_crash(gdb_worker.crash_info, testcase_path)

            exec_time = (time.time() - start_time) * 1000  # ms
            perf_tracker.increment("testcase_execution_count")

            # Log testcase with execution time
            self.db.add_testcase(job_id, self.vm_id, testcase_path, exec_time)

            # Update fuzzer stats (total_testcases set in fuzzer init, update generated here)
            gen_tests = self.db._conn.execute(
                "SELECT COUNT(*) FROM testcases WHERE job_id = ?", (job_id,)
            ).fetchone()[0]
            self.db.update_fuzzer_stats(job_id, generated_testcases=gen_tests)

            if not self.fuzzer.next():
                self.logger.info("Fuzzer exhausted testcases")
                return False
            return True
        except Exception as e:
            self.logger.error(f"Error in testcase execution: {e}", exc_info=True)
            return True
         
    def _handle_crash(self, crash_info: dict, testcase_path: str, job_id: int):
        crash_type = crash_info.get("type")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_id = f"crash_{job_id}_{timestamp}"
        crash_dir = os.path.expanduser(self.cfg.crash_dir)
        os.makedirs(crash_dir, exist_ok=True)
        crash_zip = os.path.join(crash_dir, f"{crash_id}.zip")

        # Extract enhanced crash information
        stack_hash = crash_info.get("stack_hash")
        backtrace = crash_info.get("backtrace")
        crash_address = crash_info.get("crash_address")
        signal = crash_info.get("signal")

        # Detect sanitizer output
        sanitizer_report = None
        sanitizer_type = None
        severity = None
        gdb_output = crash_info.get("gdb_output", "")

        if gdb_output:
            sanitizer_report_obj = self.sanitizer_detector.detect_in_output(gdb_output)
            if sanitizer_report_obj:
                sanitizer_type = sanitizer_report_obj.sanitizer_type.value
                severity = self.sanitizer_detector.classify_severity(sanitizer_report_obj)
                sanitizer_report = sanitizer_report_obj.to_dict()

                self.logger.info(f"Sanitizer detected: {sanitizer_type}, severity: {severity}")

                # Override crash type with sanitizer error type
                if not crash_type or crash_type == "kernel":
                    crash_type = sanitizer_report_obj.error_type

                # Use sanitizer backtrace if we don't have one
                if not backtrace and sanitizer_report_obj.backtrace:
                    backtrace = sanitizer_report_obj.backtrace

                # Use sanitizer crash address if we don't have one
                if not crash_address and sanitizer_report_obj.crash_address:
                    crash_address = sanitizer_report_obj.crash_address

        with zipfile.ZipFile(crash_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            if crash_type == "kernel":
                gdb_output = crash_info["gdb_output"]
                details = signal or gdb_output

                # Log crash with stack hash info
                if stack_hash:
                    self.logger.info(f"Kernel crash detected - stack_hash={stack_hash[:16]}..., "
                                   f"signal={signal}, crash_addr={crash_address}")
                else:
                    self.logger.info(f"Kernel crash detected: {gdb_output}")

                # Add crash to database with enhanced deduplication and sanitizer info
                self.db.add_crash(
                    job_id=job_id,
                    testcase_path=testcase_path,
                    crash_type=crash_type,
                    details=details,
                    crash_file=crash_zip,
                    stack_hash=stack_hash,
                    backtrace=backtrace,
                    crash_address=crash_address,
                    sanitizer_type=sanitizer_type,
                    sanitizer_report=sanitizer_report,
                    severity=severity
                )

                zf.writestr("gdb_output.txt", gdb_output)

                # Store backtrace if available
                if backtrace:
                    backtrace_text = "\n".join([
                        f"#{frame['frame']}: {frame['function']} at {frame.get('file', '??')}:{frame.get('line', '??')}"
                        for frame in backtrace
                    ])
                    zf.writestr("backtrace.txt", backtrace_text)

                # Store sanitizer report if available
                if sanitizer_report:
                    sanitizer_text = f"Sanitizer: {sanitizer_type}\n"
                    sanitizer_text += f"Severity: {severity}\n"
                    sanitizer_text += f"Error Type: {sanitizer_report.get('error_type', 'unknown')}\n"
                    sanitizer_text += f"Error Message: {sanitizer_report.get('error_message', '')}\n"
                    if sanitizer_report.get('crash_address'):
                        sanitizer_text += f"Crash Address: {sanitizer_report['crash_address']}\n"
                    if sanitizer_report.get('access_type'):
                        sanitizer_text += f"Access: {sanitizer_report['access_type']} of size {sanitizer_report.get('access_size', '?')}\n"

                    zf.writestr("sanitizer_report.txt", sanitizer_text)
                    zf.writestr("sanitizer_report.json", json.dumps(sanitizer_report, indent=2))

            elif crash_type == "user":
                crash_details = f"PID={crash_info['pid']}, EXE={crash_info['exe']}, Exception={crash_info['exception']}"
                self.logger.info(f"User-space crash detected: {crash_details}")

                # Add user-space crash (no stack hash for now, could be enhanced later)
                self.db.add_crash(
                    job_id=job_id,
                    testcase_path=testcase_path,
                    crash_type="user",
                    details=crash_details,
                    crash_file=crash_info.get("file")
                )

                zf.writestr("crash_info.json", json.dumps(crash_info, indent=2))

            testcase_name = os.path.basename(testcase_path)
            zf.write(testcase_path, f"testcase/{testcase_name}")
            for root, _, files in os.walk(self.share_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, self.share_dir)
                    zf.write(file_path, f"shared/{arcname}")

        self.logger.info(f"Crash package saved to {crash_zip}")
        self.analyzer.analyze_crash(crash_zip)  # Analyze post-zip

    def cleanup(self):
        if self.vm_id:
            self.qemu_mgr.stop_vm(self.vm_id)
            if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.vm_id = None

    def inject_testcase(self, testcase_path: str, vm_id: int, job_id: int):
        dest_path = os.path.join(self.share_dir, "fuzz_input.bin")
        with open(testcase_path, "rb") as src, open(dest_path, "wb") as dst:
            dst.write(src.read())
        self.logger.info(f"Injected {testcase_path} to {dest_path}")
        with self.qemu_mgr.registry._lock:
            vm_info = self.qemu_mgr.registry.get_vm(vm_id)
            vm_info["job_id"] = job_id
            vm_info["current_test"] = testcase_path
            self.qemu_mgr.registry.save()  # Fixed: Use qemu_mgr.registry, not self.registry
