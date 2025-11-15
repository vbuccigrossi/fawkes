import logging
import subprocess
import time
from globals import shutdown_event, SystemResources
from qemu import QemuManager
from gdb import GdbFuzzManager
from db.db import FawkesDB
from harness import FileFuzzHarness
from fawkes.performance import perf_tracker

def run_local_mode(cfg, registry, parallel: int = 1, loop: bool = False, seed_dir: str = None):
    system_resources = SystemResources()
    logger = logging.getLogger("fawkes")
    logger.info("Entering local fuzzing mode")
    db = FawkesDB(cfg.get("db_path", "~/.fawkes/fawkes.db"))
    cfg.db = db
    qemu_mgr = QemuManager(cfg, registry)
    gdb_mgr = GdbFuzzManager(qemu_mgr, cfg.timeout)

    system_resources.register_instance()
    try:
        max_vms = int(parallel) if int(parallel) > 0 else system_resources.get_max_vms()
        harnesses = []
        for _ in range(min(max_vms, cfg.max_parallel_vms or max_vms)):
            if system_resources.register_vms(1):
                harnesses.append(FileFuzzHarness(qemu_mgr, gdb_mgr, db, cfg.input_dir, cfg.disk_image, cfg.snapshot_name, cfg))
            else:
                break

        disk_path = cfg.get("disk_image")
        snapshot_name = cfg.get("snapshot_name", "clean")
        if snapshot_name:
            result = subprocess.run(["qemu-img", "snapshot", "-l", disk_path], capture_output=True, text=True)
            if snapshot_name not in result.stdout:
                logger.error(f"Snapshot '{snapshot_name}' not found in {disk_path}. Create it with QEMU monitor: savevm {snapshot_name}")
                return

        job_id = db.add_job(cfg.job_name, cfg.input_dir, snapshot_name)
        cfg.job_id = job_id
        logger.info(f"Job 'local_fuzz' added with job_id={job_id}")
        db.update_job_vms(job_id, len(harnesses))
        logger.debug(f"Updated global resource tracker with job: {job_id}")

        running = True
        while running and not shutdown_event.is_set():
            fair_share = system_resources.get_current_fair_share(max_vms)
            logger.debug(f"Fair share resources allocated: {fair_share}")
            if len(harnesses) > fair_share:
                excess = len(harnesses) - fair_share
                for _ in range(excess):
                    harness = harnesses.pop()
                    harness.cleanup()
                    system_resources.unregister_vms(1)
                db.update_job_vms(job_id, len(harnesses))
                logger.info(f"Reduced VMs to {len(harnesses)} due to instance balancing")
            elif len(harnesses) < fair_share:
                additional = fair_share - len(harnesses)
                for _ in range(additional):
                    if system_resources.register_vms(1):
                        harnesses.append(FileFuzzHarness(qemu_mgr, gdb_mgr, db, cfg.input_dir, cfg.disk_image, cfg.snapshot_name, cfg))
                    else:
                        break
                db.update_job_vms(job_id, len(harnesses))
                logger.info(f"Increased VMs to {len(harnesses)} due to instance balancing")

            if len(harnesses) == 0:
                logger.warning("No VMs allocated, waiting for resources")
                time.sleep(5)
                continue

            for harness in harnesses:
                if not harness.run_single_testcase(job_id):
                    running = loop
            if not loop:
                break
        logger.info("Local fuzzing complete")

        # Print performance statistics
        perf_tracker.print_stats()

    except Exception as e:
        logger.error(f"Error running local mode: {e}", exc_info=True)
    finally:
        for harness in harnesses:
            harness.cleanup()
        system_resources.unregister_vms(len(harnesses))
        system_resources.unregister_instance()
        gdb_mgr.stop_all_workers()

        try:
            if job_id:
                db._conn.execute(
                    "UPDATE jobs SET status = ? WHERE job_id = ?",
                    ("stopped", job_id)
                )
                db._conn.commit()
                logger.debug(f"Marked job {job_id} as stopped in database")
        except Exception as e:
            logger.error(f"Failed to update job status: {e}")

        db.close()
