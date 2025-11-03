import logging
import time
import socket
import json
import os
import glob
import tarfile
import tempfile
from pathlib import Path
from fawkes.db.controller_db import ControllerDB
from fawkes.globals import shutdown_event

logger = logging.getLogger("fawkes")
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
        if os.path.exists(tar_path):
            os.unlink(tar_path)

def check_for_new_jobs(db, cfg):
    """Check job directory for new job configurations."""
    job_dir = cfg.get("job_dir", "~/.fawkes/jobs/")
    job_dir = os.path.expanduser(job_dir)
    os.makedirs(job_dir, exist_ok=True)
    for job_file in glob.glob(os.path.join(job_dir, "*.json")):
        with open(job_file, "r") as f:
            job_config = json.load(f)
        job_config["job_id"] = db.add_job(job_config)
        available_workers = db.get_available_workers()
        if available_workers:
            worker = available_workers[0]
            db.assign_job_to_worker(job_config["job_id"], worker["worker_id"])
            push_job_to_worker(worker["ip_address"], job_config)
            logger.info(f"Assigned job {job_config['job_id']} to worker {worker['ip_address']}")
        os.remove(job_file)

def run_controller_mode(cfg):
    """Main controller logic."""
    db_path = os.path.expanduser(cfg.get("controller_db_path", "~/.fawkes/controller.db"))
    db = ControllerDB(db_path)

    workers = cfg.get("workers", [])
    for worker_ip in workers:
        db.add_worker(worker_ip)

    logger.info("Controller started")

    while not shutdown_event.is_set():
        for worker in db.get_workers():
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((worker["ip_address"], CONTROLLER_PORT))

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
                db.update_worker_status(worker["worker_id"], "online")
                logger.debug(f"Received status from {worker['ip_address']}: {status}")

                # Request crashes for each running job
                for job_id in status.get("status", {}):
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
                        for crash in crash_data.get("crashes", []):
                            db.add_crash(crash["job_id"], worker["worker_id"], crash)
                        logger.debug(f"Stored {len(crash_data.get('crashes', []))} crashes for job {job_id} from {worker['ip_address']}")

            except Exception as e:
                db.update_worker_status(worker["worker_id"], "offline")
                logger.warning(f"Worker {worker['ip_address']} offline: {e}")
            finally:
                if sock:
                    sock.close()

        check_for_new_jobs(db, cfg)
        time.sleep(cfg.get("poll_interval", 60))

    logger.info("Controller shutting down")
