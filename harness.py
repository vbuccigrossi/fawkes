import os
import logging
import shutil
from pathlib import Path
import time
from fawkes.nbd import NbdManager
from fawkes.qemu import QemuManager
from fawkes.config import FawkesConfig, VMRegistry
from fawkes.db.db import FawkesDB
from fawkes.fuzzers import load_fuzzer
from fawkes.analysis import load_analyzer

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
            self.setup_vm()
        try:
            self.qemu_mgr.revert_to_snapshot(self.vm_id, self.snapshot_name)
            testcase_path = self.fuzzer.generate_testcase()
            
            # Measure execution time
            start_time = time.time()
            self.inject_testcase(testcase_path, self.vm_id, job_id)
            self.gdb_mgr.start_fuzz_worker(self.vm_id, fuzz_loop=False)
            worker_thread = self.gdb_mgr.workers.get(self.vm_id)
            if worker_thread:
                worker_thread.join()
                gdb_worker = self.gdb_mgr.get_worker(self.vm_id)
                if gdb_worker and gdb_worker.crash_detected:
                    self._handle_crash(gdb_worker.crash_info, testcase_path, job_id)
            exec_time = (time.time() - start_time) * 1000  # ms
            
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

        with zipfile.ZipFile(crash_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            if crash_type == "kernel":
                gdb_output = crash_info["gdb_output"]
                self.logger.info(f"Kernel crash detected: {gdb_output}")
                self.db.add_crash(job_id, testcase_path, "kernel", gdb_output)
                zf.writestr("gdb_output.txt", gdb_output)
            elif crash_type == "user":
                crash_details = f"PID={crash_info['pid']}, EXE={crash_info['exe']}, Exception={crash_info['exception']}"
                self.logger.info(f"User-space crash detected: {crash_details}")
                self.db.add_crash(job_id, testcase_path, "user", crash_details, crash_info["file"])
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
