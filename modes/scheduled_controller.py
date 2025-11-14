"""
Enhanced Scheduler-Based Controller Mode

Uses the advanced scheduler for distributed job management with:
- Priority-based job scheduling
- Load-aware worker allocation
- Heartbeat-based health monitoring
- Automatic failure recovery
- Deadline enforcement
"""

import logging
import time
import socket
import json
import os
import tarfile
import tempfile
from pathlib import Path

from fawkes.db.scheduler_db import SchedulerDB
from fawkes.scheduler.scheduler import SchedulerOrchestrator
from fawkes.globals import shutdown_event

logger = logging.getLogger("fawkes.controller")
CONTROLLER_PORT = 9999


def push_job_to_worker(worker_ip: str, job_config: dict):
    """Send job configuration, VM image, and test cases to a worker."""
    sock = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as temp_tar:
            tar_path = temp_tar.name
            with tarfile.open(tar_path, "w:gz") as tar:
                disk_image = os.path.expanduser(job_config.get("disk_image"))
                if not os.path.isfile(disk_image):
                    logger.error(f"VM image not found: {disk_image}")
                    return False
                tar.add(disk_image, arcname=os.path.basename(disk_image))
                logger.debug(f"Added VM image to tar: {disk_image}")

                input_dir = os.path.expanduser(job_config.get("input_dir"))
                if not os.path.isdir(input_dir):
                    logger.error(f"Input directory not found: {input_dir}")
                    return False
                for root, _, files in os.walk(input_dir):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        arcname = os.path.join("testcases", os.path.relpath(fpath, input_dir))
                        tar.add(fpath, arcname=arcname)
                        logger.debug(f"Added testcase to tar: {fpath}")

        tar_size = os.path.getsize(tar_path)
        logger.info(f"Prepared job package for {job_config['job_id']}: {tar_size} bytes")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((worker_ip, CONTROLLER_PORT))

        msg = {
            "type": "PUSH_JOB",
            "job_id": job_config["job_id"],
            "config": job_config,
            "package_size": tar_size
        }
        msg_data = json.dumps(msg).encode()
        sock.send(len(msg_data).to_bytes(4, byteorder="big"))
        sock.send(msg_data)
        logger.debug(f"Sent job config to {worker_ip}: {job_config['job_id']}")

        with open(tar_path, "rb") as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                sock.send(chunk)
        logger.info(f"Sent job package to {worker_ip} for job {job_config['job_id']}")

        ack = sock.recv(1024).decode()
        if ack != "ACK":
            logger.error(f"Worker {worker_ip} failed to acknowledge job {job_config['job_id']}: {ack}")
            return False
        logger.debug(f"Worker {worker_ip} acknowledged job {job_config['job_id']}")

        return True

    except socket.timeout:
        logger.error(f"Connection to worker {worker_ip} timed out")
        return False
    except socket.error as e:
        logger.error(f"Network error with worker {worker_ip}: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to push job {job_config['job_id']} to {worker_ip}: {e}", exc_info=True)
        return False
    finally:
        if sock:
            sock.close()
        if 'tar_path' in locals() and os.path.exists(tar_path):
            os.unlink(tar_path)


def collect_worker_status(worker_ip: str) -> dict:
    """Request status from a worker"""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((worker_ip, CONTROLLER_PORT))

        # Request status
        status_msg = {"type": "STATUS_REQUEST"}
        status_data = json.dumps(status_msg).encode()
        sock.send(len(status_data).to_bytes(4, byteorder="big"))
        sock.send(status_data)

        status_len = int.from_bytes(sock.recv(4), byteorder="big")
        status_response = b""
        while len(status_response) < status_len:
            chunk = sock.recv(1024)
            if not chunk:
                raise ConnectionError("Connection closed during status response")
            status_response += chunk

        status = json.loads(status_response.decode())
        logger.debug(f"Received status from {worker_ip}: {status}")
        return status

    except Exception as e:
        logger.warning(f"Failed to get status from {worker_ip}: {e}")
        return {}
    finally:
        if sock:
            sock.close()


def collect_worker_crashes(worker_ip: str, job_id: int) -> list:
    """Request crashes from a worker for a specific job"""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((worker_ip, CONTROLLER_PORT))

        crash_msg = {"type": "CRASH_REQUEST", "job_id": job_id}
        crash_data = json.dumps(crash_msg).encode()
        sock.send(len(crash_data).to_bytes(4, byteorder="big"))
        sock.send(crash_data)

        crash_len = int.from_bytes(sock.recv(4), byteorder="big")
        crash_response = b""
        while len(crash_response) < crash_len:
            chunk = sock.recv(1024)
            if not chunk:
                raise ConnectionError("Connection closed during crash response")
            crash_response += chunk

        crash_data = json.loads(crash_response.decode())
        if "crashes" in crash_data:
            logger.debug(f"Received {len(crash_data['crashes'])} crashes for job {job_id} from {worker_ip}")
            return crash_data.get("crashes", [])
        return []

    except Exception as e:
        logger.warning(f"Failed to get crashes from {worker_ip}: {e}")
        return []
    finally:
        if sock:
            sock.close()


def run_scheduled_controller(cfg):
    """
    Main controller logic using the advanced scheduler

    This replaces the basic controller with priority scheduling,
    load-aware allocation, and failure recovery.
    """
    db_path = os.path.expanduser(cfg.get("controller_db_path", "~/.fawkes/scheduler.db"))
    db = SchedulerDB(db_path)

    # Initialize scheduler
    allocation_strategy = cfg.get("allocation_strategy", "load_aware")
    heartbeat_timeout = cfg.get("heartbeat_timeout", 90)
    scheduler = SchedulerOrchestrator(db, allocation_strategy, heartbeat_timeout)

    # Register configured workers
    workers = cfg.get("workers", [])
    for worker_config in workers:
        if isinstance(worker_config, str):
            # Simple IP address
            db.register_worker(worker_config)
        elif isinstance(worker_config, dict):
            # Detailed worker config
            db.register_worker(
                worker_config.get("ip"),
                hostname=worker_config.get("hostname"),
                capabilities=worker_config.get("capabilities"),
                tags=worker_config.get("tags")
            )

    logger.info(f"Scheduler-based controller started (strategy={allocation_strategy})")

    # Track assigned jobs that need to be pushed to workers
    pending_pushes = {}

    poll_interval = cfg.get("poll_interval", 30)

    while not shutdown_event.is_set():
        try:
            # Run scheduler cycle
            cycle_stats = scheduler.run_cycle()
            logger.debug(f"Scheduler cycle: {cycle_stats}")

            # Get all workers
            all_workers = db.get_available_workers()

            # Update worker status and collect crashes
            for worker_data in all_workers:
                worker_id = worker_data["worker_id"]
                worker_ip = worker_data["ip_address"]

                # Collect status
                status = collect_worker_status(worker_ip)
                if status:
                    # Update heartbeat
                    current_load = {
                        "active_jobs": len(status.get("status", {})),
                        "used_vms": sum(job.get("vm_count", 0) for job in status.get("status", {}).values()),
                        "cpu_usage": 0,  # TODO: Get actual CPU usage
                        "ram_usage": 0   # TODO: Get actual RAM usage
                    }
                    db.update_worker_heartbeat(worker_id, current_load)

                    # Collect crashes for all running jobs
                    for job_id in status.get("status", {}):
                        crashes = collect_worker_crashes(worker_ip, job_id)
                        for crash in crashes:
                            db.add_crash(job_id, worker_id, crash)
                else:
                    # Worker didn't respond - heartbeat will mark it offline
                    pass

            # Check for newly assigned jobs that need to be pushed
            cursor = db.conn.cursor()
            cursor.execute('''SELECT j.job_id, j.config, j.assigned_worker_id, w.ip_address
                             FROM jobs j
                             JOIN workers w ON j.assigned_worker_id = w.worker_id
                             WHERE j.status = 'assigned' ''')

            for job_id, config_json, worker_id, worker_ip in cursor.fetchall():
                if job_id not in pending_pushes:
                    job_config = json.loads(config_json)
                    job_config["job_id"] = job_id

                    logger.info(f"Pushing job {job_id} to worker {worker_id} ({worker_ip})")
                    if push_job_to_worker(worker_ip, job_config):
                        db.update_job_status(job_id, "running")
                        logger.info(f"Job {job_id} successfully pushed to worker {worker_id}")
                    else:
                        logger.error(f"Failed to push job {job_id} to worker {worker_id}")
                        # Increment retry and re-queue
                        db.increment_job_retry(job_id)

                    pending_pushes[job_id] = True

            # Check for completed jobs
            cursor.execute('''SELECT j.job_id FROM jobs j
                             WHERE j.status = 'running' ''')
            running_jobs = [row[0] for row in cursor.fetchall()]

            for job_id in list(pending_pushes.keys()):
                if job_id not in running_jobs:
                    # Job is no longer running, remove from pending pushes
                    del pending_pushes[job_id]

            # Print status summary
            status = scheduler.get_status()
            logger.info(f"Status: {status['queue_length']} queued, "
                       f"{status['jobs'].get('running', 0)} running, "
                       f"{status['workers'].get('online', 0)} workers online")

            time.sleep(poll_interval)

        except KeyboardInterrupt:
            logger.info("Controller shutting down...")
            break
        except Exception as e:
            logger.error(f"Error in controller loop: {e}", exc_info=True)
            time.sleep(poll_interval)

    db.close()
    logger.info("Scheduler-based controller shut down")
