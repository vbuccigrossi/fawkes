#!/bin/bash
# Test script for job scheduler functionality

set -e

echo "=========================================="
echo "Fawkes Job Scheduler - Test Script"
echo "=========================================="
echo ""

# Check if fawkes-scheduler exists
if [ ! -f "fawkes-scheduler" ]; then
    echo "Error: fawkes-scheduler not found"
    exit 1
fi

echo "✓ fawkes-scheduler found"
echo ""

# Test 1: CLI Help
echo "Test 1: CLI Help"
echo "----------------"
./fawkes-scheduler --help > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✓ CLI help works"
else
    echo "✗ CLI help failed"
    exit 1
fi
echo ""

# Test 2: Module Imports
echo "Test 2: Module Imports"
echo "---------------------"
cd .. && python3 << 'EOF'
try:
    from fawkes.db.scheduler_db import SchedulerDB
    print("✓ SchedulerDB imports successfully")

    from fawkes.scheduler.scheduler import (
        JobScheduler,
        WorkerHealthMonitor,
        DeadlineEnforcer,
        SchedulerOrchestrator
    )
    print("✓ Scheduler classes import successfully")

    # Test instantiation
    import tempfile
    import os
    db_path = os.path.join(tempfile.mkdtemp(), "test_scheduler.db")
    db = SchedulerDB(db_path)
    print("✓ SchedulerDB instantiates")

    scheduler = JobScheduler(db)
    print("✓ JobScheduler instantiates")

    health_monitor = WorkerHealthMonitor(db)
    print("✓ WorkerHealthMonitor instantiates")

    deadline_enforcer = DeadlineEnforcer(db)
    print("✓ DeadlineEnforcer instantiates")

    orchestrator = SchedulerOrchestrator(db)
    print("✓ SchedulerOrchestrator instantiates")

    db.close()

except ImportError as e:
    print(f"✗ Import failed: {e}")
    exit(1)
except Exception as e:
    print(f"✗ Error: {e}")
    exit(1)
EOF
TEST_RESULT=$?
cd fawkes

if [ $TEST_RESULT -ne 0 ]; then
    exit 1
fi
echo ""

# Test 3: Database Schema
echo "Test 3: Database Schema"
echo "----------------------"
cd .. && python3 << 'EOF'
import tempfile
import os
from fawkes.db.scheduler_db import SchedulerDB

db_path = os.path.join(tempfile.mkdtemp(), "test_schema.db")
db = SchedulerDB(db_path)

# Verify tables exist
cursor = db.conn.cursor()

tables = ['jobs', 'workers', 'job_queue', 'job_assignments', 'job_history', 'crashes']
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
existing_tables = [row[0] for row in cursor.fetchall()]

for table in tables:
    if table in existing_tables:
        print(f"✓ Table '{table}' exists")
    else:
        print(f"✗ Table '{table}' missing!")
        exit(1)

# Verify indices exist
cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
indices = [row[0] for row in cursor.fetchall()]
print(f"✓ Created {len(indices)} indices")

db.close()
print(f"✓ Database schema created successfully")
EOF
TEST_RESULT=$?
cd fawkes

if [ $TEST_RESULT -ne 0 ]; then
    exit 1
fi
echo ""

# Test 4: Job Management
echo "Test 4: Job Management"
echo "---------------------"
cd .. && python3 << 'EOF'
import tempfile
import os
import time
from fawkes.db.scheduler_db import SchedulerDB

db_path = os.path.join(tempfile.mkdtemp(), "test_jobs.db")
db = SchedulerDB(db_path)

# Add a job
job_id = db.add_job(
    name="Test Job",
    config={"test": "config"},
    priority=75
)
print(f"✓ Added job {job_id}")

# Get the job
job = db.get_job(job_id)
if job and job['name'] == "Test Job" and job['priority'] == 75:
    print(f"✓ Retrieved job {job_id}")
else:
    print(f"✗ Failed to retrieve job {job_id}")
    exit(1)

# Check it's in the queue
next_job = db.get_next_job_from_queue()
if next_job and next_job['job_id'] == job_id:
    print(f"✓ Job {job_id} in queue")
else:
    print(f"✗ Job {job_id} not in queue")
    exit(1)

# Update job status
db.update_job_status(job_id, "running")
job = db.get_job(job_id)
if job['status'] == "running":
    print(f"✓ Updated job {job_id} status to running")
else:
    print(f"✗ Failed to update job status")
    exit(1)

# Test job with dependencies
job_id2 = db.add_job(
    name="Dependent Job",
    config={"test": "config2"},
    dependencies=[job_id]
)
print(f"✓ Added dependent job {job_id2}")

# Dependent job should not be in queue yet
next_job = db.get_next_job_from_queue()
if not next_job or next_job['job_id'] != job_id2:
    print(f"✓ Dependent job {job_id2} correctly waiting")
else:
    print(f"✗ Dependent job {job_id2} incorrectly queued")
    exit(1)

# Complete first job
db.update_job_status(job_id, "completed")
time.sleep(0.1)  # Give it a moment to process

# Now dependent job should be queued
next_job = db.get_next_job_from_queue()
if next_job and next_job['job_id'] == job_id2:
    print(f"✓ Dependent job {job_id2} now queued after dependency completed")
else:
    print(f"✗ Dependent job {job_id2} not queued after dependency completed")
    exit(1)

db.close()
EOF
TEST_RESULT=$?
cd fawkes

if [ $TEST_RESULT -ne 0 ]; then
    exit 1
fi
echo ""

# Test 5: Worker Management
echo "Test 5: Worker Management"
echo "------------------------"
cd .. && python3 << 'EOF'
import tempfile
import os
from fawkes.db.scheduler_db import SchedulerDB

db_path = os.path.join(tempfile.mkdtemp(), "test_workers.db")
db = SchedulerDB(db_path)

# Register a worker
worker_id = db.register_worker(
    ip_address="192.168.1.100",
    hostname="test-worker",
    capabilities={"cpu_cores": 8, "ram_gb": 16, "max_vms": 4},
    tags=["linux", "testing"]
)
print(f"✓ Registered worker {worker_id}")

# Get the worker
worker = db.get_worker(worker_id)
if worker and worker['ip_address'] == "192.168.1.100":
    print(f"✓ Retrieved worker {worker_id}")
else:
    print(f"✗ Failed to retrieve worker {worker_id}")
    exit(1)

# Check capabilities
if worker['capabilities'] == {"cpu_cores": 8, "ram_gb": 16, "max_vms": 4}:
    print(f"✓ Worker capabilities correct")
else:
    print(f"✗ Worker capabilities incorrect: {worker['capabilities']}")
    exit(1)

# Update heartbeat
db.update_worker_heartbeat(worker_id, {"used_vms": 2, "active_jobs": 1})
worker = db.get_worker(worker_id)
if worker['current_load'] == {"used_vms": 2, "active_jobs": 1}:
    print(f"✓ Worker heartbeat updated")
else:
    print(f"✗ Worker heartbeat not updated")
    exit(1)

# Get available workers
available = db.get_available_workers()
if len(available) == 1 and available[0]['worker_id'] == worker_id:
    print(f"✓ Retrieved available workers")
else:
    print(f"✗ Failed to retrieve available workers")
    exit(1)

db.close()
EOF
TEST_RESULT=$?
cd fawkes

if [ $TEST_RESULT -ne 0 ]; then
    exit 1
fi
echo ""

# Test 6: Job Scheduling
echo "Test 6: Job Scheduling"
echo "---------------------"
cd .. && python3 << 'EOF'
import tempfile
import os
from fawkes.db.scheduler_db import SchedulerDB
from fawkes.scheduler.scheduler import JobScheduler

db_path = os.path.join(tempfile.mkdtemp(), "test_scheduling.db")
db = SchedulerDB(db_path)
scheduler = JobScheduler(db)

# Register workers
worker1 = db.register_worker("192.168.1.10", capabilities={"max_vms": 4})
worker2 = db.register_worker("192.168.1.11", capabilities={"max_vms": 8})
print(f"✓ Registered 2 workers")

# Update worker loads
db.update_worker_heartbeat(worker1, {"used_vms": 3, "cpu_usage": 75})
db.update_worker_heartbeat(worker2, {"used_vms": 2, "cpu_usage": 25})
print(f"✓ Updated worker loads")

# Add jobs
job1 = db.add_job("Job 1", {"test": 1}, priority=50)
job2 = db.add_job("Job 2", {"test": 2}, priority=75)
job3 = db.add_job("Job 3", {"test": 3}, priority=25)
print(f"✓ Added 3 jobs with different priorities")

# Schedule next job (should be job2 with priority 75)
next_job = scheduler.schedule_next_job()
if next_job['job_id'] == job2:
    print(f"✓ Scheduler correctly prioritizes job {job2}")
else:
    print(f"✗ Scheduler failed to prioritize correctly")
    exit(1)

# Allocate to worker (should choose worker2 with lower load)
worker_id = scheduler.allocate_job_to_worker(next_job, "load_aware")
if worker_id == worker2:
    print(f"✓ Scheduler allocated to least-loaded worker {worker2}")
else:
    print(f"✗ Scheduler didn't allocate to least-loaded worker (got {worker_id}, expected {worker2})")
    exit(1)

db.close()
EOF
TEST_RESULT=$?
cd fawkes

if [ $TEST_RESULT -ne 0 ]; then
    exit 1
fi
echo ""

# Test 7: Health Monitoring
echo "Test 7: Health Monitoring"
echo "------------------------"
cd .. && python3 << 'EOF'
import tempfile
import os
import time
from datetime import datetime
from fawkes.db.scheduler_db import SchedulerDB
from fawkes.scheduler.scheduler import WorkerHealthMonitor

db_path = os.path.join(tempfile.mkdtemp(), "test_health.db")
db = SchedulerDB(db_path)
health_monitor = WorkerHealthMonitor(db, heartbeat_timeout=2)

# Register worker
worker_id = db.register_worker("192.168.1.100")
print(f"✓ Registered worker {worker_id}")

# Worker should be online
worker = db.get_worker(worker_id)
if worker['status'] == 'online':
    print(f"✓ Worker {worker_id} is online")
else:
    print(f"✗ Worker {worker_id} not online")
    exit(1)

# Wait for heartbeat to go stale
time.sleep(3)

# Check health (should mark worker offline)
offline_count = health_monitor.check_worker_health()
if offline_count == 1:
    print(f"✓ Health monitor detected 1 offline worker")
else:
    print(f"✗ Health monitor failed to detect offline worker")
    exit(1)

worker = db.get_worker(worker_id)
if worker['status'] == 'offline':
    print(f"✓ Worker {worker_id} marked offline")
else:
    print(f"✗ Worker {worker_id} not marked offline")
    exit(1)

db.close()
EOF
TEST_RESULT=$?
cd fawkes

if [ $TEST_RESULT -ne 0 ]; then
    exit 1
fi
echo ""

# Test 8: Deadline Enforcement
echo "Test 8: Deadline Enforcement"
echo "---------------------------"
cd .. && python3 << 'EOF'
import tempfile
import os
import time
from datetime import datetime
from fawkes.db.scheduler_db import SchedulerDB
from fawkes.scheduler.scheduler import DeadlineEnforcer

db_path = os.path.join(tempfile.mkdtemp(), "test_deadlines.db")
db = SchedulerDB(db_path)
deadline_enforcer = DeadlineEnforcer(db)

# Add job with deadline in the past
past_deadline = int(datetime.now().timestamp()) - 3600
job_id = db.add_job("Overdue Job", {"test": 1}, deadline=past_deadline)
db.update_job_status(job_id, "running")  # Simulate running
print(f"✓ Added job {job_id} with past deadline")

# Check deadlines
overdue_count = deadline_enforcer.check_deadlines()
if overdue_count == 1:
    print(f"✓ Deadline enforcer detected 1 overdue job")
else:
    print(f"✗ Deadline enforcer failed (found {overdue_count} overdue jobs)")
    exit(1)

job = db.get_job(job_id)
if job['status'] == 'failed':
    print(f"✓ Overdue job {job_id} marked as failed")
else:
    print(f"✗ Overdue job {job_id} not marked as failed (status: {job['status']})")
    exit(1)

db.close()
EOF
TEST_RESULT=$?
cd fawkes

if [ $TEST_RESULT -ne 0 ]; then
    exit 1
fi
echo ""

# Test 9: Orchestrator Integration
echo "Test 9: Orchestrator Integration"
echo "--------------------------------"
cd .. && python3 << 'EOF'
import tempfile
import os
from fawkes.db.scheduler_db import SchedulerDB
from fawkes.scheduler.scheduler import SchedulerOrchestrator

db_path = os.path.join(tempfile.mkdtemp(), "test_orchestrator.db")
db = SchedulerDB(db_path)
orchestrator = SchedulerOrchestrator(db, allocation_strategy="load_aware")

# Register worker
worker_id = db.register_worker("192.168.1.100", capabilities={"max_vms": 4})
db.update_worker_heartbeat(worker_id, {"used_vms": 0})

# Add job
job_id = db.add_job("Test Job", {"test": 1}, priority=75)

# Run cycle
stats = orchestrator.run_cycle()
print(f"✓ Orchestrator cycle completed: {stats}")

if stats['scheduled_jobs'] == 1:
    print(f"✓ Orchestrator scheduled 1 job")
else:
    print(f"✗ Orchestrator didn't schedule job (scheduled: {stats['scheduled_jobs']})")
    exit(1)

# Get status
status = orchestrator.get_status()
print(f"✓ Orchestrator status: {status}")

db.close()
EOF
TEST_RESULT=$?
cd fawkes

if [ $TEST_RESULT -ne 0 ]; then
    exit 1
fi
echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo "All scheduler tests passed! ✓"
echo ""
echo "The job scheduler system is ready to use."
echo ""
echo "Usage examples:"
echo "  ./fawkes-scheduler add \"My Job\" job.json --priority 75"
echo "  ./fawkes-scheduler list"
echo "  ./fawkes-scheduler status <job_id>"
echo "  ./fawkes-scheduler workers"
echo "  ./fawkes-scheduler stats"
echo ""
echo "See docs/JOB_SCHEDULER.md for complete documentation."
echo ""
