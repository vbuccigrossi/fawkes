"""
Fawkes Job Scheduler

Core scheduling engine for distributed fuzzing jobs.
Implements priority-based scheduling, load-aware allocation, and failure recovery.
"""

import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger("fawkes.scheduler")


class JobScheduler:
    """
    Core job scheduler implementing priority-based scheduling and resource-aware allocation
    """

    def __init__(self, db):
        """
        Args:
            db: SchedulerDB instance
        """
        self.db = db
        logger.info("Job scheduler initialized")

    def schedule_next_job(self) -> Optional[Dict[str, Any]]:
        """
        Get the next job to schedule based on priority and resource requirements

        Returns:
            Job dict with job_id, priority, resource_requirements, or None if queue empty
        """
        job = self.db.get_next_job_from_queue()
        if not job:
            logger.debug("No jobs in queue")
            return None

        logger.info(f"Next job to schedule: {job['job_id']} (priority={job['priority']})")
        return job

    def allocate_job_to_worker(self, job: Dict[str, Any], allocation_strategy: str = "load_aware") -> Optional[int]:
        """
        Allocate a job to the best available worker

        Args:
            job: Job dict with job_id, priority, resource_requirements
            allocation_strategy: Strategy to use (load_aware, round_robin, first_fit)

        Returns:
            worker_id if allocated, None if no suitable worker found
        """
        job_id = job["job_id"]
        requirements = job.get("resource_requirements", {})

        # Get available workers
        workers = self.db.get_available_workers()
        if not workers:
            logger.debug(f"No available workers for job {job_id}")
            return None

        # Filter workers by resource requirements
        suitable_workers = self._filter_workers_by_requirements(workers, requirements)
        if not suitable_workers:
            logger.debug(f"No workers meet resource requirements for job {job_id}")
            return None

        # Select worker based on allocation strategy
        if allocation_strategy == "load_aware":
            worker = self._select_worker_load_aware(suitable_workers)
        elif allocation_strategy == "round_robin":
            worker = suitable_workers[0]  # Simple implementation
        elif allocation_strategy == "first_fit":
            worker = suitable_workers[0]
        else:
            logger.warning(f"Unknown allocation strategy '{allocation_strategy}', using first_fit")
            worker = suitable_workers[0]

        if worker:
            self.db.assign_job_to_worker(job_id, worker["worker_id"])
            logger.info(f"Allocated job {job_id} to worker {worker['worker_id']} ({worker['ip_address']})")
            return worker["worker_id"]

        return None

    def _filter_workers_by_requirements(self, workers: List[Dict[str, Any]],
                                       requirements: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Filter workers that can meet job resource requirements

        Args:
            workers: List of worker dicts
            requirements: Dict with cpu, ram, vms requirements

        Returns:
            List of suitable workers
        """
        if not requirements:
            return workers

        suitable = []
        for worker in workers:
            capabilities = worker.get("capabilities", {})
            current_load = worker.get("current_load", {})

            # Check CPU cores
            if "cpu" in requirements:
                max_cpu = capabilities.get("cpu_cores", 0)
                used_cpu = current_load.get("cpu_usage", 0)
                if (max_cpu - used_cpu) < requirements["cpu"]:
                    continue

            # Check RAM
            if "ram" in requirements:
                max_ram = capabilities.get("ram_gb", 0)
                used_ram = current_load.get("ram_usage", 0)
                if (max_ram - used_ram) < requirements["ram"]:
                    continue

            # Check VMs
            if "vms" in requirements:
                max_vms = capabilities.get("max_vms", 0)
                used_vms = current_load.get("used_vms", 0)
                if (max_vms - used_vms) < requirements["vms"]:
                    continue

            suitable.append(worker)

        return suitable

    def _select_worker_load_aware(self, workers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Select worker with lowest current load

        Scoring: Lower is better
        Score = (used_vms / max_vms) * 0.6 + (cpu_usage / cpu_cores) * 0.3 + (ram_usage / ram_gb) * 0.1

        Returns:
            Worker dict or None
        """
        if not workers:
            return None

        best_worker = None
        best_score = float('inf')

        for worker in workers:
            capabilities = worker.get("capabilities", {})
            current_load = worker.get("current_load", {})

            # Calculate normalized load metrics
            max_vms = capabilities.get("max_vms", 1)
            used_vms = current_load.get("used_vms", 0)
            vm_load = used_vms / max_vms if max_vms > 0 else 0

            max_cpu = capabilities.get("cpu_cores", 1)
            used_cpu = current_load.get("cpu_usage", 0)
            cpu_load = used_cpu / max_cpu if max_cpu > 0 else 0

            max_ram = capabilities.get("ram_gb", 1)
            used_ram = current_load.get("ram_usage", 0)
            ram_load = used_ram / max_ram if max_ram > 0 else 0

            # Weighted score (VM load is most important for fuzzing)
            score = vm_load * 0.6 + cpu_load * 0.3 + ram_load * 0.1

            if score < best_score:
                best_score = score
                best_worker = worker

        logger.debug(f"Selected worker {best_worker['worker_id']} with load score {best_score:.2f}")
        return best_worker

    def run_scheduling_cycle(self, max_jobs: int = 100):
        """
        Run one scheduling cycle - try to allocate pending jobs to workers

        Args:
            max_jobs: Maximum number of jobs to schedule in this cycle
        """
        scheduled_count = 0

        for _ in range(max_jobs):
            # Get next job from queue
            job = self.schedule_next_job()
            if not job:
                break

            # Try to allocate to a worker
            worker_id = self.allocate_job_to_worker(job)
            if worker_id:
                scheduled_count += 1
            else:
                # No suitable worker available, stop trying
                logger.debug("No suitable workers available, ending scheduling cycle")
                break

        if scheduled_count > 0:
            logger.info(f"Scheduled {scheduled_count} jobs in this cycle")

        return scheduled_count


class WorkerHealthMonitor:
    """
    Monitor worker health via heartbeats and mark stale workers as offline
    """

    def __init__(self, db, heartbeat_timeout: int = 90):
        """
        Args:
            db: SchedulerDB instance
            heartbeat_timeout: Seconds before considering a worker offline
        """
        self.db = db
        self.heartbeat_timeout = heartbeat_timeout
        logger.info(f"Worker health monitor initialized (timeout={heartbeat_timeout}s)")

    def check_worker_health(self):
        """
        Check all workers and mark stale ones as offline
        Reschedule any jobs that were running on failed workers
        """
        # Mark stale workers offline
        offline_count = self.db.mark_stale_workers_offline(self.heartbeat_timeout)

        if offline_count > 0:
            # Find jobs that were running on now-offline workers
            cursor = self.db.conn.cursor()
            cursor.execute('''SELECT j.job_id, j.assigned_worker_id, j.name
                             FROM jobs j
                             JOIN workers w ON j.assigned_worker_id = w.worker_id
                             WHERE j.status IN ('assigned', 'running')
                             AND w.status = 'offline' ''')

            failed_jobs = cursor.fetchall()
            for job_id, worker_id, job_name in failed_jobs:
                logger.warning(f"Worker {worker_id} failed while running job {job_id} ({job_name})")

                # Try to reschedule the job
                if self.db.increment_job_retry(job_id):
                    logger.info(f"Re-queued job {job_id} after worker failure")
                else:
                    logger.error(f"Job {job_id} failed - max retries exceeded")

        return offline_count


class DeadlineEnforcer:
    """
    Monitor job deadlines and mark overdue jobs
    """

    def __init__(self, db):
        self.db = db
        logger.info("Deadline enforcer initialized")

    def check_deadlines(self):
        """
        Check for jobs past their deadline and mark them as failed
        """
        current_time = int(datetime.now().timestamp())
        cursor = self.db.conn.cursor()

        cursor.execute('''SELECT job_id, name, deadline FROM jobs
                         WHERE status IN ('pending', 'assigned', 'running')
                         AND deadline IS NOT NULL
                         AND deadline < ?''', (current_time,))

        overdue_jobs = cursor.fetchall()
        for job_id, name, deadline in overdue_jobs:
            logger.warning(f"Job {job_id} ({name}) missed deadline {deadline}")
            self.db.update_job_status(job_id, "failed", "Missed deadline")

        return len(overdue_jobs)


class SchedulerOrchestrator:
    """
    Main orchestrator that coordinates scheduling, health monitoring, and deadline enforcement
    """

    def __init__(self, db, allocation_strategy: str = "load_aware",
                 heartbeat_timeout: int = 90):
        """
        Args:
            db: SchedulerDB instance
            allocation_strategy: Allocation strategy (load_aware, round_robin, first_fit)
            heartbeat_timeout: Worker heartbeat timeout in seconds
        """
        self.db = db
        self.scheduler = JobScheduler(db)
        self.health_monitor = WorkerHealthMonitor(db, heartbeat_timeout)
        self.deadline_enforcer = DeadlineEnforcer(db)
        self.allocation_strategy = allocation_strategy
        logger.info(f"Scheduler orchestrator initialized (strategy={allocation_strategy})")

    def run_cycle(self):
        """
        Run one complete scheduling cycle:
        1. Check worker health
        2. Enforce deadlines
        3. Schedule pending jobs
        """
        # Check worker health and reschedule failed jobs
        offline_count = self.health_monitor.check_worker_health()

        # Check for missed deadlines
        overdue_count = self.deadline_enforcer.check_deadlines()

        # Schedule pending jobs
        scheduled_count = self.scheduler.run_scheduling_cycle()

        logger.debug(f"Cycle complete: {offline_count} workers offline, "
                    f"{overdue_count} deadlines missed, {scheduled_count} jobs scheduled")

        return {
            "offline_workers": offline_count,
            "overdue_jobs": overdue_count,
            "scheduled_jobs": scheduled_count
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status"""
        job_stats = self.db.get_job_stats()
        worker_stats = self.db.get_worker_stats()
        queue_length = self.db.get_queue_length()

        return {
            "jobs": job_stats,
            "workers": worker_stats,
            "queue_length": queue_length,
            "allocation_strategy": self.allocation_strategy
        }
