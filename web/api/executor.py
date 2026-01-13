"""
Job Executor Service for Fawkes Web UI

Manages the actual execution of fuzzing jobs by spawning and controlling
Fawkes fuzzing processes. This bridges the web UI with the actual fuzzing engine.
"""

import asyncio
import logging
import os
import sys
import signal
import threading
import multiprocessing
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

# Add parent directory to import Fawkes modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import FawkesConfig, VMRegistry
from db.db import FawkesDB
from modes.local import run_local_mode
from modes.controller import run_controller_mode
from modes.worker import run_worker_mode
from globals import shutdown_event

logger = logging.getLogger("fawkes.web.executor")


class JobProcess:
    """Represents a running job process."""

    def __init__(self, job_id: int, process: multiprocessing.Process, config: Dict[str, Any]):
        self.job_id = job_id
        self.process = process
        self.config = config
        self.started_at = datetime.now()
        self.status = "running"

    def is_alive(self) -> bool:
        return self.process.is_alive()

    def terminate(self):
        """Terminate the job process."""
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=5)
            if self.process.is_alive():
                self.process.kill()
        self.status = "stopped"


def _run_local_job(job_config: Dict[str, Any], stop_event: multiprocessing.Event):
    """
    Worker function that runs in a separate process to execute a local fuzzing job.
    """
    try:
        # Set up logging for this process
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        proc_logger = logging.getLogger(f"fawkes.job.{job_config.get('job_id', 0)}")
        proc_logger.info(f"Starting job: {job_config.get('name', 'Unnamed')}")

        # Create config from job settings
        cfg = FawkesConfig()

        # Apply job configuration
        cfg.disk_image = os.path.expanduser(job_config.get('disk', job_config.get('disk_image', '')))
        cfg.snapshot_name = job_config.get('snapshot', job_config.get('snapshot_name', 'clean'))
        cfg.input_dir = os.path.expanduser(job_config.get('input_dir', '~/fuzz_inputs'))
        cfg.share_dir = os.path.expanduser(job_config.get('share_dir', '~/fawkes_shared'))
        cfg.crash_dir = job_config.get('crash_dir', './fawkes/crashes')
        cfg.arch = job_config.get('arch', 'x86_64')
        cfg.timeout = job_config.get('timeout', 60)
        cfg.loop = job_config.get('loop', True)
        cfg.no_headless = job_config.get('no_headless', False)
        cfg.vfs = job_config.get('vfs', False)
        cfg.smb = job_config.get('smb', True)
        cfg.fuzzer = job_config.get('fuzzer_type', 'file')
        cfg.job_id = job_config.get('job_id')
        cfg.job_name = job_config.get('name', 'WebUI Job')

        # Get fuzzer config if provided (ensure it's always a dict)
        fuzzer_config = job_config.get('fuzzer_config') or {}
        if fuzzer_config:
            cfg.fuzzer_config = fuzzer_config
            # Apply nested fuzzer config options
            if fuzzer_config.get('input_dir'):
                cfg.input_dir = os.path.expanduser(fuzzer_config['input_dir'])
            if fuzzer_config.get('share_dir'):
                cfg.share_dir = os.path.expanduser(fuzzer_config['share_dir'])
            if fuzzer_config.get('crash_dir'):
                cfg.crash_dir = fuzzer_config['crash_dir']
            if fuzzer_config.get('timeout'):
                cfg.timeout = fuzzer_config['timeout']
            if fuzzer_config.get('arch'):
                cfg.arch = fuzzer_config['arch']

        # VM parameters
        cfg.vm_params = job_config.get('vm_params') or fuzzer_config.get('vm_params')

        # Parallel VMs
        parallel = job_config.get('vm_count', 1) or fuzzer_config.get('max_parallel_vms', 1)
        if parallel == 0:
            parallel = 1

        # Initialize VM registry
        registry = VMRegistry(cfg.get("registry_file"))

        # Connect to database
        db_path = os.path.expanduser(cfg.get("db_path", "~/.fawkes/fawkes.db"))
        cfg.db = FawkesDB(db_path)

        proc_logger.info(f"Job config: disk={cfg.disk_image}, snapshot={cfg.snapshot_name}, "
                        f"input={cfg.input_dir}, parallel={parallel}")

        # Override the global shutdown event with our stop event
        # This allows the web UI to stop the job
        def check_stop():
            return stop_event.is_set()

        # Patch the shutdown check - run_local_mode checks shutdown_event
        import globals
        original_shutdown = globals.shutdown_event

        # Create a wrapper that checks both
        class CombinedEvent:
            def is_set(self):
                return stop_event.is_set() or original_shutdown.is_set()
            def set(self):
                stop_event.set()
                original_shutdown.set()
            def clear(self):
                stop_event.clear()

        globals.shutdown_event = CombinedEvent()

        try:
            # Run the actual fuzzing
            run_local_mode(
                cfg,
                registry,
                parallel=parallel,
                loop=cfg.loop,
                seed_dir=cfg.input_dir
            )
        finally:
            globals.shutdown_event = original_shutdown
            if cfg.db:
                cfg.db.close()

        proc_logger.info(f"Job {job_config.get('job_id')} completed")

    except Exception as e:
        logging.error(f"Job execution error: {e}", exc_info=True)
        raise


def _run_controller_service(config: Dict[str, Any], stop_event: multiprocessing.Event):
    """
    Worker function that runs the controller service in a separate process.
    """
    try:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        proc_logger = logging.getLogger("fawkes.controller")
        proc_logger.info("Starting controller service...")

        # Create config
        cfg = FawkesConfig()
        cfg.controller_host = config.get('controller_host', '0.0.0.0')
        cfg.controller_port = config.get('controller_port', 5000)
        cfg.poll_interval = config.get('poll_interval', 60)
        cfg.job_dir = os.path.expanduser(config.get('job_dir', '~/.fawkes/jobs/'))

        # Ensure job directory exists
        os.makedirs(cfg.job_dir, exist_ok=True)

        proc_logger.info(f"Controller listening on {cfg.controller_host}:{cfg.controller_port}")

        # Override shutdown event
        import globals
        original_shutdown = globals.shutdown_event

        class CombinedEvent:
            def is_set(self):
                return stop_event.is_set() or original_shutdown.is_set()
            def set(self):
                stop_event.set()
                original_shutdown.set()
            def clear(self):
                stop_event.clear()

        globals.shutdown_event = CombinedEvent()

        try:
            run_controller_mode(cfg)
        finally:
            globals.shutdown_event = original_shutdown

        proc_logger.info("Controller service stopped")

    except Exception as e:
        logging.error(f"Controller service error: {e}", exc_info=True)
        raise


class JobExecutor:
    """
    Manages execution of fuzzing jobs.

    This class handles:
    - Starting jobs as separate processes
    - Stopping/pausing running jobs
    - Tracking job status
    - Managing the controller service
    """

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.running_jobs: Dict[int, JobProcess] = {}
        self.stop_events: Dict[int, multiprocessing.Event] = {}
        self.controller_process: Optional[multiprocessing.Process] = None
        self.controller_stop_event: Optional[multiprocessing.Event] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False

        # Start the monitoring thread
        self.start_monitor()

    def start_monitor(self):
        """Start the background thread that monitors job processes."""
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._running = True
            self._monitor_thread = threading.Thread(target=self._monitor_jobs, daemon=True)
            self._monitor_thread.start()
            logger.info("Job monitor thread started")

    def _monitor_jobs(self):
        """Background thread that monitors running job processes."""
        while self._running:
            try:
                # Check each running job
                completed_jobs = []
                for job_id, job_proc in list(self.running_jobs.items()):
                    if not job_proc.is_alive():
                        completed_jobs.append(job_id)
                        logger.info(f"Job {job_id} process ended")

                # Update status for completed jobs
                for job_id in completed_jobs:
                    try:
                        self.db_manager.update_job_status(job_id, "completed")
                        del self.running_jobs[job_id]
                        if job_id in self.stop_events:
                            del self.stop_events[job_id]
                    except Exception as e:
                        logger.error(f"Error updating completed job {job_id}: {e}")

                # Check controller process
                if self.controller_process and not self.controller_process.is_alive():
                    logger.warning("Controller process ended unexpectedly")
                    self.controller_process = None

            except Exception as e:
                logger.error(f"Error in job monitor: {e}")

            # Check every 2 seconds
            threading.Event().wait(2)

    def start_job(self, job_id: int) -> Dict[str, Any]:
        """
        Start a fuzzing job.

        Args:
            job_id: ID of the job to start

        Returns:
            Status dict with success/error info
        """
        # Check if job is already running
        if job_id in self.running_jobs:
            if self.running_jobs[job_id].is_alive():
                return {"success": False, "error": f"Job {job_id} is already running"}

        # Get job from database
        job = self.db_manager.get_job(job_id)
        if not job:
            return {"success": False, "error": f"Job {job_id} not found"}

        try:
            # Create stop event for this job
            stop_event = multiprocessing.Event()
            self.stop_events[job_id] = stop_event

            # Create and start the process
            process = multiprocessing.Process(
                target=_run_local_job,
                args=(job, stop_event),
                name=f"FawkesJob-{job_id}"
            )
            process.start()

            # Track the process
            job_proc = JobProcess(job_id, process, job)
            self.running_jobs[job_id] = job_proc

            # Update database status
            self.db_manager.update_job_status(job_id, "running")

            logger.info(f"Started job {job_id} (PID: {process.pid})")

            return {
                "success": True,
                "message": f"Job {job_id} started",
                "pid": process.pid
            }

        except Exception as e:
            logger.error(f"Failed to start job {job_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def stop_job(self, job_id: int) -> Dict[str, Any]:
        """
        Stop a running job.

        Args:
            job_id: ID of the job to stop

        Returns:
            Status dict with success/error info
        """
        if job_id not in self.running_jobs:
            # Update status anyway
            self.db_manager.update_job_status(job_id, "stopped")
            return {"success": True, "message": f"Job {job_id} was not running"}

        try:
            job_proc = self.running_jobs[job_id]

            # Signal the job to stop gracefully
            if job_id in self.stop_events:
                self.stop_events[job_id].set()

            # Wait a bit for graceful shutdown
            if job_proc.process.is_alive():
                job_proc.process.join(timeout=10)

            # Force kill if still running
            if job_proc.process.is_alive():
                logger.warning(f"Force killing job {job_id}")
                job_proc.terminate()

            # Clean up
            del self.running_jobs[job_id]
            if job_id in self.stop_events:
                del self.stop_events[job_id]

            # Update database
            self.db_manager.update_job_status(job_id, "stopped")

            logger.info(f"Stopped job {job_id}")

            return {"success": True, "message": f"Job {job_id} stopped"}

        except Exception as e:
            logger.error(f"Failed to stop job {job_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def pause_job(self, job_id: int) -> Dict[str, Any]:
        """
        Pause a running job.

        Note: True pause/resume requires more complex state management.
        For now, pause is equivalent to stop.

        Args:
            job_id: ID of the job to pause

        Returns:
            Status dict with success/error info
        """
        # For now, pause is the same as stop
        # TODO: Implement proper pause/resume with VM snapshot
        result = self.stop_job(job_id)
        if result["success"]:
            self.db_manager.update_job_status(job_id, "paused")
            result["message"] = f"Job {job_id} paused"
        return result

    def get_job_status(self, job_id: int) -> Dict[str, Any]:
        """Get the current status of a job."""
        if job_id in self.running_jobs:
            job_proc = self.running_jobs[job_id]
            return {
                "job_id": job_id,
                "status": "running" if job_proc.is_alive() else "completed",
                "pid": job_proc.process.pid if job_proc.process else None,
                "started_at": job_proc.started_at.isoformat()
            }

        # Get from database
        job = self.db_manager.get_job(job_id)
        if job:
            return {
                "job_id": job_id,
                "status": job.get("status", "unknown"),
                "pid": None,
                "started_at": None
            }

        return {"job_id": job_id, "status": "not_found"}

    def get_running_jobs(self) -> Dict[int, Dict[str, Any]]:
        """Get all currently running jobs."""
        return {
            job_id: {
                "job_id": job_id,
                "status": "running" if jp.is_alive() else "completed",
                "pid": jp.process.pid if jp.process else None,
                "started_at": jp.started_at.isoformat(),
                "name": jp.config.get("name", "Unknown")
            }
            for job_id, jp in self.running_jobs.items()
        }

    # Controller service management

    def start_controller(self, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Start the controller service for distributed fuzzing.

        Args:
            config: Controller configuration (host, port, etc.)

        Returns:
            Status dict
        """
        if self.controller_process and self.controller_process.is_alive():
            return {"success": False, "error": "Controller is already running"}

        try:
            config = config or self.db_manager.config

            self.controller_stop_event = multiprocessing.Event()

            self.controller_process = multiprocessing.Process(
                target=_run_controller_service,
                args=(config, self.controller_stop_event),
                name="FawkesController"
            )
            self.controller_process.start()

            logger.info(f"Started controller service (PID: {self.controller_process.pid})")

            return {
                "success": True,
                "message": "Controller service started",
                "pid": self.controller_process.pid
            }

        except Exception as e:
            logger.error(f"Failed to start controller: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def stop_controller(self) -> Dict[str, Any]:
        """Stop the controller service."""
        if not self.controller_process:
            return {"success": True, "message": "Controller was not running"}

        try:
            # Signal stop
            if self.controller_stop_event:
                self.controller_stop_event.set()

            # Wait for graceful shutdown
            self.controller_process.join(timeout=10)

            # Force kill if needed
            if self.controller_process.is_alive():
                self.controller_process.terminate()
                self.controller_process.join(timeout=5)

            self.controller_process = None
            self.controller_stop_event = None

            logger.info("Controller service stopped")

            return {"success": True, "message": "Controller service stopped"}

        except Exception as e:
            logger.error(f"Failed to stop controller: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def is_controller_running(self) -> bool:
        """Check if the controller service is running."""
        return self.controller_process is not None and self.controller_process.is_alive()

    def shutdown(self):
        """Shutdown the executor and all running jobs."""
        logger.info("Shutting down job executor...")
        self._running = False

        # Stop all running jobs
        for job_id in list(self.running_jobs.keys()):
            self.stop_job(job_id)

        # Stop controller
        self.stop_controller()

        logger.info("Job executor shutdown complete")


# Global executor instance (initialized in main.py lifespan)
job_executor: Optional[JobExecutor] = None


def get_executor() -> JobExecutor:
    """Get the global job executor instance."""
    global job_executor
    if job_executor is None:
        raise RuntimeError("Job executor not initialized")
    return job_executor


def initialize_executor(db_manager) -> JobExecutor:
    """Initialize the global job executor."""
    global job_executor
    job_executor = JobExecutor(db_manager)
    return job_executor
