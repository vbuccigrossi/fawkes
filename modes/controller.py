import logging
import time
import socket
import json
import os
import glob
import tarfile
import tempfile
import ssl
from pathlib import Path
from fawkes.db.controller_db import ControllerDB
from fawkes.db.auth_db import AuthDB
from fawkes.globals import shutdown_event
from fawkes.auth.middleware import add_authentication, AuthenticationError
from fawkes.auth.tls import create_ssl_context, ensure_certificates

logger = logging.getLogger("fawkes")
CONTROLLER_PORT = 9999

def push_job_to_worker(worker_ip: str, job_config: dict, cfg: dict = None):
    """Send job configuration, VM image, and test cases to a worker."""
    sock = None
    cfg = cfg or {}
    auth_enabled = cfg.get("auth_enabled", False)
    tls_enabled = cfg.get("tls_enabled", False)

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

        # Wrap with TLS if enabled
        if tls_enabled:
            try:
                cert_file, key_file = ensure_certificates(
                    cfg.get("tls_cert"),
                    cfg.get("tls_key")
                )
                ssl_context = create_ssl_context(
                    cert_file=cert_file,
                    key_file=key_file,
                    is_server=False
                )
                sock = ssl_context.wrap_socket(sock, server_hostname=worker_ip)
                logger.debug(f"Established TLS connection to {worker_ip}")
            except Exception as e:
                logger.error(f"TLS handshake failed with {worker_ip}: {e}")
                raise

        msg = {
            "type": "PUSH_JOB",
            "job_id": job_config["job_id"],
            "config": job_config,
            "package_size": tar_size
        }

        # Add authentication if enabled
        if auth_enabled:
            api_key = cfg.get("controller_api_key")
            if not api_key:
                logger.error("Authentication enabled but no controller_api_key configured")
                return False
            msg = add_authentication(msg, "api_key", api_key)

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
            push_job_to_worker(worker["ip_address"], job_config, cfg)
            logger.info(f"Assigned job {job_config['job_id']} to worker {worker['ip_address']}")
        os.remove(job_file)

def run_controller_mode(cfg):
    """Main controller logic."""
    db_path = os.path.expanduser(cfg.get("controller_db_path", "~/.fawkes/controller.db"))
    db = ControllerDB(db_path)

    auth_enabled = cfg.get("auth_enabled", False)
    tls_enabled = cfg.get("tls_enabled", False)

    # Initialize TLS if enabled
    ssl_context = None
    if tls_enabled:
        try:
            cert_file, key_file = ensure_certificates(
                cfg.get("tls_cert"),
                cfg.get("tls_key")
            )
            ssl_context = create_ssl_context(
                cert_file=cert_file,
                key_file=key_file,
                is_server=False
            )
            logger.info("TLS enabled for controller")
        except Exception as e:
            logger.error(f"Failed to initialize TLS: {e}")
            return

    workers = cfg.get("workers", [])
    for worker_ip in workers:
        db.add_worker(worker_ip)

    logger.info("Controller started")
    if auth_enabled:
        logger.info("Authentication: ENABLED")
    if tls_enabled:
        logger.info("TLS encryption: ENABLED")

    while not shutdown_event.is_set():
        for worker in db.get_workers():
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((worker["ip_address"], CONTROLLER_PORT))

                # Wrap with TLS if enabled
                if tls_enabled and ssl_context:
                    sock = ssl_context.wrap_socket(sock, server_hostname=worker["ip_address"])

                # Request status
                status_msg = {"type": "STATUS_REQUEST"}

                # Add authentication if enabled
                if auth_enabled:
                    api_key = cfg.get("controller_api_key")
                    if api_key:
                        status_msg = add_authentication(status_msg, "api_key", api_key)

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

                    # Add authentication if enabled
                    if auth_enabled:
                        api_key = cfg.get("controller_api_key")
                        if api_key:
                            crash_msg = add_authentication(crash_msg, "api_key", api_key)

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
