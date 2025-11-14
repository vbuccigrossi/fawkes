import logging
import socket
import threading
import tempfile
import shutil
import os
import json
import time
import tarfile
import ssl
from fawkes.globals import shutdown_event, SystemResources
from fawkes.qemu import QemuManager
from fawkes.gdb import GdbFuzzManager
from fawkes.db.db import FawkesDB
from fawkes.db.auth_db import AuthDB
from fawkes.harness import FileFuzzHarness
from fawkes.auth.middleware import authenticate_request, AuthenticationError, create_auth_response
from fawkes.auth.tls import create_ssl_context, ensure_certificates

def run_worker_mode(cfg):
    """Run Fawkes in worker mode, handling distributed fuzzing tasks from the controller."""
    system_resources = SystemResources()
    logger = logging.getLogger("fawkes")
    logger.info("Entering worker mode")

    # Register this worker process as an instance
    system_resources.register_instance()

    # Network setup from config
    host = cfg.get("controller_host", "0.0.0.0")
    port = cfg.get("controller_port", 9999)

    auth_enabled = cfg.get("auth_enabled", False)
    tls_enabled = cfg.get("tls_enabled", False)

    # Initialize authentication database if enabled
    auth_db = None
    if auth_enabled:
        auth_db_path = os.path.expanduser(cfg.get("auth_db_path", "~/.fawkes/auth.db"))
        auth_db = AuthDB(auth_db_path)
        logger.info("Authentication: ENABLED")

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
                is_server=True
            )
            logger.info("TLS encryption: ENABLED")
        except Exception as e:
            logger.error(f"Failed to initialize TLS: {e}")
            return

    # Start TCP server
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    logger.info(f"Worker listening on {host}:{port}")

    # Shared state for active jobs: {job_id: {"thread": thread, "status": dict, "lock": lock}}
    active_jobs = {}
    job_lock = threading.Lock()

    def handle_connection(conn, addr):
        """Handle incoming connections from the controller."""
        try:
            # Wrap with TLS if enabled
            if tls_enabled and ssl_context:
                conn = ssl_context.wrap_socket(conn, server_side=True)
                logger.debug(f"Established TLS connection from {addr}")

            # Receive message length
            msg_len = int.from_bytes(conn.recv(4), byteorder="big")

            # Receive JSON message
            msg_data = b""
            while len(msg_data) < msg_len:
                chunk = conn.recv(1024)
                if not chunk:
                    raise ConnectionError("Connection closed prematurely")
                msg_data += chunk
            msg = json.loads(msg_data.decode())
            logger.debug(f"Received message from {addr}: {msg.get('type')}")

            # Authenticate request if enabled
            if auth_enabled and auth_db:
                try:
                    principal = authenticate_request(auth_db, msg)
                    logger.debug(f"Authenticated: {principal.get('key_name') or principal.get('username')}")
                except AuthenticationError as e:
                    logger.warning(f"Authentication failed from {addr}: {e}")
                    error_response = create_auth_response(False, str(e))
                    error_data = json.dumps(error_response).encode()
                    conn.send(len(error_data).to_bytes(4, byteorder="big"))
                    conn.send(error_data)
                    return

            if msg["type"] == "PUSH_JOB":
                job_id = msg["job_id"]
                job_config = msg["config"]
                package_size = msg["package_size"]
                logger.info(f"Received PUSH_JOB for job_id={job_id}")

                # Prepare job directory
                job_dir = os.path.expanduser(f"~/.fawkes/jobs/{job_id}")
                os.makedirs(job_dir, exist_ok=True)
                
                # Receive tarball
                tar_path = os.path.join(job_dir, "job_package.tar.gz")
                bytes_received = 0
                with open(tar_path, "wb") as f:
                    while bytes_received < package_size:
                        chunk = conn.recv(4096)
                        if not chunk:
                            raise ConnectionError("Connection closed during file transfer")
                        f.write(chunk)
                        bytes_received += len(chunk)
                logger.debug(f"Received job package for {job_id}: {bytes_received} bytes")

                # Unpack tarball with path validation to prevent directory traversal
                with tarfile.open(tar_path, "r:gz") as tar:
                    for member in tar.getmembers():
                        # Validate path to prevent directory traversal attacks
                        member_path = os.path.normpath(member.name)
                        if member_path.startswith("..") or member_path.startswith("/") or member_path.startswith("\\"):
                            logger.warning(f"Skipping potentially malicious path in tarball: {member.name}")
                            continue
                        tar.extract(member, job_dir)
                os.unlink(tar_path)
                
                # Update job_config with local paths
                job_config["disk_image"] = os.path.join(job_dir, os.path.basename(job_config["disk_image"]))
                job_config["input_dir"] = os.path.join(job_dir, "testcases")
                job_config["db_path"] = os.path.join(job_dir, f"job_{job_id}.db")
                logger.info(f"Unpacked job {job_id} to {job_dir}")

                # Start job in a new thread
                job_thread = threading.Thread(
                    target=run_job,
                    args=(job_id, job_config, active_jobs, job_lock),
                    name=f"Job-{job_id}"
                )
                job_thread.start()

                # Register job in active_jobs
                with job_lock:
                    active_jobs[job_id] = {
                        "thread": job_thread,
                        "status": {"db_path": job_config["db_path"]},
                        "lock": threading.Lock()
                    }
                logger.info(f"Started job {job_id}")

                # Send acknowledgment
                conn.send("ACK".encode())
                logger.debug(f"Sent ACK for job {job_id}")

            elif msg["type"] == "STATUS_REQUEST":
                with job_lock:
                    status = {jid: job["status"] for jid, job in active_jobs.items()}
                response = {"type": "STATUS_RESPONSE", "status": status}
                response_data = json.dumps(response).encode()
                conn.send(len(response_data).to_bytes(4, byteorder="big"))
                conn.send(response_data)
                logger.debug(f"Sent status response: {status}")

            elif msg["type"] == "CRASH_REQUEST":
                job_id = msg.get("job_id")
                with job_lock:
                    if job_id in active_jobs and "db_path" in active_jobs[job_id]["status"]:
                        db_path = active_jobs[job_id]["status"]["db_path"]
                        db = FawkesDB(db_path)
                        # Fetch full crash records
                        cursor = db._conn.execute("""
                            SELECT crash_id, job_id, testcase_path, crash_type, details,
                                   signature, exploitability, crash_file, timestamp, duplicate_count
                            FROM crashes WHERE job_id = ?
                        """, (job_id,))
                        crashes = [
                            {
                                "crash_id": row[0],
                                "job_id": row[1],
                                "testcase_path": row[2],
                                "crash_type": row[3],
                                "details": row[4],
                                "signature": row[5],
                                "exploitability": row[6],
                                "crash_file": row[7],
                                "timestamp": row[8],
                                "duplicate_count": row[9]
                            }
                            for row in cursor.fetchall()
                        ]
                        response = {"type": "CRASH_RESPONSE", "job_id": job_id, "crashes": crashes}
                        db.close()
                    else:
                        response = {"type": "CRASH_RESPONSE", "job_id": job_id, "error": "Job not found or DB not ready"}
                response_data = json.dumps(response).encode()
                conn.send(len(response_data).to_bytes(4, byteorder="big"))
                conn.send(response_data)
                logger.debug(f"Sent crash data for job {job_id}: {len(crashes)} crashes")

        except Exception as e:
            logger.error(f"Error handling connection from {addr}: {e}", exc_info=True)
        finally:
            conn.close()

    def run_job(job_id, job_cfg, active_jobs, job_lock):
        """Run a single fuzzing job in a separate thread."""
        logger = logging.getLogger(f"fawkes.job.{job_id}")
        db = FawkesDB(job_cfg["db_path"])
        job_cfg.db = db
        job_cfg.job_id = job_id
        # Create a VM registry for this worker job
        from fawkes.config import VMRegistry
        registry_path = os.path.join(os.path.dirname(job_cfg["db_path"]), f"registry_{job_id}.json")
        registry = VMRegistry(registry_path)
        qemu_mgr = QemuManager(job_cfg, registry)
        gdb_mgr = GdbFuzzManager(qemu_mgr, job_cfg.get("timeout", 60))

        harnesses = []
        running = True

        db.add_job(f"worker_job_{job_id}", job_cfg["input_dir"], job_cfg.get("snapshot_name", "clean"))

        while running and not shutdown_event.is_set():
            with job_lock:
                job_count = len(active_jobs)
            worker_fair_share = system_resources.get_fair_share()
            fair_share_per_job = worker_fair_share // job_count if job_count > 0 else 0

            if len(harnesses) > fair_share_per_job:
                excess = len(harnesses) - fair_share_per_job
                for _ in range(excess):
                    harness = harnesses.pop()
                    harness.cleanup()
                    system_resources.unregister_vms(1)
                db.update_job_vms(job_id, len(harnesses))
                logger.info(f"Reduced VMs to {len(harnesses)} for job {job_id}")
            elif len(harnesses) < fair_share_per_job:
                additional = fair_share_per_job - len(harnesses)
                for _ in range(additional):
                    if system_resources.register_vms(1):
                        harnesses.append(
                            FileFuzzHarness(
                                qemu_mgr, gdb_mgr, db, job_cfg["input_dir"],
                                job_cfg["disk_image"], job_cfg.get("snapshot_name", "clean"), job_cfg
                            )
                        )
                    else:
                        break
                db.update_job_vms(job_id, len(harnesses))
                logger.info(f"Increased VMs to {len(harnesses)} for job {job_id}")

            if len(harnesses) == 0:
                logger.warning(f"No VMs allocated for job {job_id}, waiting...")
                time.sleep(5)
                continue

            for harness in harnesses:
                if not harness.run_single_testcase(job_id):
                    running = job_cfg.get("loop", True)

            with active_jobs[job_id]["lock"]:
                active_jobs[job_id]["status"] = {
                    "running": running,
                    "vm_count": len(harnesses),
                    "crashes": len(db.get_crashes(job_id)),
                    "db_path": job_cfg["db_path"]
                }

        for harness in harnesses:
            harness.cleanup()
        system_resources.unregister_vms(len(harnesses))
        try:
            if job_id:  # Assuming job_id is available
                db._conn.execute(
                    "UPDATE jobs SET status = ? WHERE job_id = ?",
                    ("stopped", job_id)
                )
                db._conn.commit()
                logger.debug(f"Marked job {job_id} as stopped in database")
        except Exception as e:
            logger.error(f"Failed to update job status: {e}")

        db.close()
        logger.info(f"Job {job_id} completed")

        with job_lock:
            if job_id in active_jobs:
                del active_jobs[job_id]

    try:
        server.settimeout(1.0)
        while not shutdown_event.is_set():
            try:
                conn, addr = server.accept()
                logger.debug(f"Accepted connection from {addr}")
                threading.Thread(target=handle_connection, args=(conn, addr)).start()
            except socket.timeout:
                continue
    except Exception as e:
        logger.error(f"Worker server error: {e}", exc_info=True)
    finally:
        server.close()
        system_resources.unregister_instance()
        logger.info("Worker shutting down")

if __name__ == "__main__":
    import sys
    from fawkes.config import FawkesConfig
    logging.basicConfig(level=logging.INFO)
    cfg = FawkesConfig.load(sys.argv[1] if len(sys.argv) > 1 else "~/.fawkes/config.json")
    run_worker_mode(cfg)
