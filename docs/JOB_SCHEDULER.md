# Fawkes Job Scheduler

Enterprise-grade distributed job scheduling system for large-scale fuzzing operations.

## Features

### 🎯 Priority-Based Scheduling
- **Priority Levels**: 0-100 (higher = more urgent)
- **FIFO Within Priority**: Jobs with equal priority run in submission order
- **Dynamic Re-prioritization**: Update job priorities on the fly
- **Deadline Support**: Set hard deadlines for time-sensitive jobs

### 🧠 Intelligent Worker Allocation
- **Load-Aware Scheduling**: Allocates jobs to least-loaded workers
- **Resource Matching**: Matches job requirements to worker capabilities
- **Multiple Strategies**: load_aware, round_robin, first_fit
- **Capability-Based Filtering**: Workers tagged for specific job types

### 💓 Health Monitoring
- **Automatic Heartbeats**: Workers send periodic status updates
- **Failure Detection**: Stale workers automatically marked offline
- **Job Recovery**: Failed jobs automatically re-queued with retry limits
- **Resource Tracking**: Real-time CPU, RAM, and VM usage monitoring

### 🔄 Advanced Job Management
- **Job Dependencies**: Chain jobs together (Job B runs after Job A completes)
- **Retry Logic**: Automatic retry with configurable limits
- **Job History**: Track all execution attempts and failures
- **Crash Collection**: Automatic crash aggregation from workers

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                   SCHEDULER DATABASE                    │
│  Jobs | Workers | Queue | Assignments | History        │
└────────────────┬───────────────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────────────┐
│              SCHEDULER ORCHESTRATOR                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │ Job          │ │ Health       │ │ Deadline     │   │
│  │ Scheduler    │ │ Monitor      │ │ Enforcer     │   │
│  └──────────────┘ └──────────────┘ └──────────────┘   │
└────────────────┬───────────────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────────────┐
│                   CONTROLLER                            │
│  - Runs scheduling cycles                              │
│  - Pushes jobs to workers                              │
│  - Collects status and crashes                         │
└────────────────┬───────────────────────────────────────┘
                 │
                 │ (Network: TCP port 9999)
                 │
┌────────────────▼───────────────────────────────────────┐
│                    WORKERS                              │
│  Worker 1   Worker 2   Worker 3   ...   Worker N       │
│  - Run fuzzing jobs                                     │
│  - Send heartbeats                                      │
│  - Report crashes                                       │
└─────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Start Controller with Scheduler

```bash
# Update config to use scheduled controller
python3 main.py --config controller_config.json --mode scheduled_controller
```

**Controller Config** (`controller_config.json`):
```json
{
  "mode": "scheduled_controller",
  "controller_db_path": "~/.fawkes/scheduler.db",
  "allocation_strategy": "load_aware",
  "heartbeat_timeout": 90,
  "poll_interval": 30,
  "workers": [
    {
      "ip": "192.168.1.10",
      "hostname": "worker01",
      "capabilities": {
        "cpu_cores": 16,
        "ram_gb": 32,
        "max_vms": 8
      },
      "tags": ["linux", "high-memory"]
    },
    {
      "ip": "192.168.1.11",
      "hostname": "worker02",
      "capabilities": {
        "cpu_cores": 8,
        "ram_gb": 16,
        "max_vms": 4
      },
      "tags": ["windows"]
    }
  ]
}
```

### 2. Start Workers

```bash
# On each worker machine
python3 main.py --config worker_config.json --mode scheduled_worker
```

**Worker Config** (`worker_config.json`):
```json
{
  "mode": "scheduled_worker",
  "controller_host": "0.0.0.0",
  "controller_port": 9999,
  "worker_tags": ["linux", "high-memory"]
}
```

### 3. Submit Jobs

```bash
# Create job config
cat > my_job.json <<EOF
{
  "disk_image": "~/vms/target.qcow2",
  "input_dir": "~/testcases",
  "snapshot_name": "clean",
  "timeout": 60,
  "loop": true
}
EOF

# Submit job with priority 75 (high priority)
./fawkes-scheduler add "Fuzz Target Binary" my_job.json --priority 75

# Submit job with deadline (complete within 24 hours)
./fawkes-scheduler add "Critical Regression Test" my_job.json --priority 90 --deadline 24h

# Submit job with resource requirements
./fawkes-scheduler add "Heavy Workload" my_job.json --resources "cpu=8,ram=16,vms=4"

# Submit job with dependencies (runs after job 42 completes)
./fawkes-scheduler add "Post-Processing" process_job.json --depends-on 42
```

### 4. Monitor Jobs

```bash
# List all jobs
./fawkes-scheduler list

# Filter by status
./fawkes-scheduler list --status running

# Filter by priority
./fawkes-scheduler list --min-priority 70

# Get detailed job status
./fawkes-scheduler status 123

# View scheduler statistics
./fawkes-scheduler stats

# List workers
./fawkes-scheduler workers

# Cancel a job
./fawkes-scheduler cancel 123
```

---

## Usage Guide

### Job Management

#### Adding Jobs

```bash
# Basic job submission
./fawkes-scheduler add "My Fuzzing Job" job_config.json

# High-priority job
./fawkes-scheduler add "Critical CVE Test" job.json --priority 95

# Job with 48-hour deadline
./fawkes-scheduler add "Release Blocker" job.json --deadline 48h

# Job requiring specific resources
./fawkes-scheduler add "Intensive Fuzz" job.json \
  --resources "cpu=16,ram=32,vms=8"

# Job with dependencies (runs after jobs 10,11,12)
./fawkes-scheduler add "Merge Results" merge.json \
  --depends-on "10,11,12"

# Combined example
./fawkes-scheduler add "Production Test" job.json \
  --priority 85 \
  --deadline 72h \
  --resources "vms=4" \
  --depends-on "100"
```

#### Listing Jobs

```bash
# Show all pending jobs
./fawkes-scheduler list --status pending

# Show running jobs
./fawkes-scheduler list --status running

# Show high-priority jobs only
./fawkes-scheduler list --min-priority 70

# Show last 100 jobs
./fawkes-scheduler list --limit 100
```

#### Job Status

```bash
# Detailed status for job 42
./fawkes-scheduler status 42
```

**Output:**
```
================================================================================
JOB STATUS: 42
================================================================================
Name: Fuzz Target Binary
Status: running
Priority: 75/100
Created: 2025-01-14 10:00:00
Started: 2025-01-14 10:05:23
Worker: 3 (192.168.1.10)
Resource Requirements: {'vms': 4, 'ram': 8}

Crashes: 15
================================================================================
```

#### Canceling Jobs

```bash
# Cancel a specific job
./fawkes-scheduler cancel 42
```

### Worker Management

#### Registering Workers

```bash
# Basic registration (auto-detected capabilities)
./fawkes-scheduler register-worker 192.168.1.10

# With hostname
./fawkes-scheduler register-worker 192.168.1.10 --hostname worker01

# With explicit capabilities
./fawkes-scheduler register-worker 192.168.1.10 \
  --capabilities "cpu_cores=16,ram_gb=32,max_vms=8"

# With tags for job targeting
./fawkes-scheduler register-worker 192.168.1.10 \
  --hostname worker01 \
  --tags "linux,high-memory,gpu"
```

#### Listing Workers

```bash
# Show all workers
./fawkes-scheduler workers

# Show only online workers
./fawkes-scheduler workers --status online

# Show only offline workers
./fawkes-scheduler workers --status offline
```

**Output:**
```
╔════╦═════════════════╦══════════╦════════╦═════╦══════╦═════════════════════╗
║ ID ║ IP Address      ║ Hostname ║ Status ║ VMs ║ Jobs ║ Last Heartbeat      ║
╠════╬═════════════════╬══════════╬════════╬═════╬══════╬═════════════════════╣
║  1 ║ 192.168.1.10    ║ worker01 ║ online ║ 6/8 ║    2 ║ 2025-01-14 14:23:15 ║
║  2 ║ 192.168.1.11    ║ worker02 ║ online ║ 3/4 ║    1 ║ 2025-01-14 14:23:10 ║
║  3 ║ 192.168.1.12    ║ worker03 ║ offline║ 0/4 ║    0 ║ 2025-01-14 13:45:00 ║
╚════╩═════════════════╩══════════╩════════╩═════╩══════╩═════════════════════╝
Total: 3 workers
```

### Statistics

```bash
# View comprehensive scheduler statistics
./fawkes-scheduler stats
```

**Output:**
```
================================================================================
SCHEDULER STATISTICS
================================================================================

Jobs:
  assigned       :    5
  completed      :   42
  failed         :    3
  pending        :   12
  running        :   18
  Queue          :   12

Workers:
  offline        :    1
  online         :    5

Total Crashes: 1,247

================================================================================
```

---

## Advanced Features

### Priority Levels

Priority is an integer from 0-100:

- **90-100**: Critical/Emergency
  - Security patches
  - Release blockers
  - Production issues

- **70-89**: High Priority
  - Important features
  - Customer requests
  - Pre-release testing

- **40-69**: Normal Priority
  - Regular development
  - Regression testing
  - General fuzzing

- **10-39**: Low Priority
  - Exploratory testing
  - Research projects
  - Non-urgent work

- **0-9**: Best Effort
  - Background tasks
  - Cleanup jobs
  - Low-value work

### Allocation Strategies

#### Load-Aware (Recommended)
```python
allocation_strategy = "load_aware"
```
- Selects worker with lowest current load
- Scoring formula: `vm_load * 0.6 + cpu_load * 0.3 + ram_load * 0.1`
- Best for balanced workload distribution

#### Round Robin
```python
allocation_strategy = "round_robin"
```
- Cycles through available workers
- Simple and fair
- Doesn't consider current load

#### First Fit
```python
allocation_strategy = "first_fit"
```
- Uses first available worker that meets requirements
- Fastest allocation
- May lead to unbalanced loads

### Resource Requirements

Specify exact resource needs for jobs:

```bash
# Job needs 16 CPU cores, 32GB RAM, and 8 VMs
./fawkes-scheduler add "Heavy Job" job.json \
  --resources "cpu=16,ram=32,vms=8"
```

The scheduler will only assign the job to workers that can satisfy these requirements.

### Job Dependencies

Create job workflows by chaining dependencies:

```bash
# Stage 1: Initial fuzzing
./fawkes-scheduler add "Phase 1 Fuzzing" phase1.json --priority 80
# Output: Job ID: 100

# Stage 2: Depends on job 100
./fawkes-scheduler add "Phase 2 Fuzzing" phase2.json --depends-on 100
# Output: Job ID: 101

# Stage 3: Depends on jobs 100 and 101
./fawkes-scheduler add "Merge and Analyze" merge.json --depends-on "100,101"
# Output: Job ID: 102
```

Jobs with unsatisfied dependencies stay in `pending` state until all dependencies complete.

### Deadlines

Set hard deadlines for time-sensitive jobs:

```bash
# Complete within 6 hours
./fawkes-scheduler add "6hr Test" job.json --deadline 6h

# Complete within 3 days
./fawkes-scheduler add "Weekend Fuzz" job.json --deadline 3d

# Unix timestamp (absolute deadline)
./fawkes-scheduler add "Exact Deadline" job.json --deadline 1705334400
```

The `DeadlineEnforcer` automatically fails jobs that miss their deadlines.

### Retry Logic

Jobs automatically retry on worker failure:

- Default: 3 retries
- Configurable in database
- Exponential backoff between retries
- Failures tracked in job history

### Worker Tags

Tag workers for specific job types:

```bash
# Register worker with tags
./fawkes-scheduler register-worker 192.168.1.10 \
  --tags "windows,gui,gpu"
```

Future enhancement: Match jobs to workers by tags.

---

## Configuration Reference

### Controller Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `controller_db_path` | string | `~/.fawkes/scheduler.db` | Scheduler database location |
| `allocation_strategy` | string | `load_aware` | Worker selection strategy |
| `heartbeat_timeout` | int | `90` | Seconds before marking worker offline |
| `poll_interval` | int | `30` | Seconds between controller cycles |
| `workers` | list | `[]` | Pre-configured worker list |

### Worker Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `controller_host` | string | `0.0.0.0` | Listen address |
| `controller_port` | int | `9999` | Listen port |
| `worker_tags` | list | `[]` | Worker classification tags |

---

## Troubleshooting

### Workers Not Showing as Online

**Symptoms**: Workers appear as `offline` in `./fawkes-scheduler workers`

**Solutions**:
1. Check network connectivity between controller and worker
2. Verify TCP port 9999 is open
3. Check worker logs for connection errors
4. Ensure worker is actually running: `ps aux | grep fawkes`
5. Check heartbeat timeout isn't too aggressive: increase `heartbeat_timeout` in controller config

### Jobs Stuck in Queue

**Symptoms**: Jobs remain in `pending` status

**Solutions**:
1. Check if any workers are online: `./fawkes-scheduler workers --status online`
2. Verify resource requirements can be met: `./fawkes-scheduler status <job_id>`
3. Check for unsatisfied dependencies
4. Review scheduler logs for allocation errors
5. Verify workers have available capacity

### Jobs Failing Immediately

**Symptoms**: Jobs move to `failed` status quickly

**Solutions**:
1. Check job configuration is valid
2. Verify disk image and testcase paths exist on worker
3. Check worker logs for error messages
4. Review job history: `SELECT * FROM job_history WHERE job_id = ?`
5. Ensure worker has required resources available

### High Retry Counts

**Symptoms**: Jobs showing many retries

**Solutions**:
1. Investigate worker stability - may be crashing
2. Check network reliability between controller and workers
3. Review job resource requirements - may be too demanding
4. Increase max_retries if jobs are complex
5. Check worker system logs for hardware/OS issues

---

## Performance Tuning

### Controller Optimization

```json
{
  "poll_interval": 15,       // Faster polling = quicker response
  "heartbeat_timeout": 60,   // Tighter timeout = faster failure detection
  "allocation_strategy": "load_aware"  // Better distribution
}
```

### Worker Optimization

- **CPU Cores**: More cores = more parallel VMs
- **RAM**: 2-4GB per VM recommended
- **Storage**: Fast SSD for VM images
- **Network**: Low latency to controller

### Database Optimization

The scheduler database uses:
- WAL mode for concurrent access
- Indices on frequently-queried columns
- Connection pooling

For very large deployments (>1000 jobs/day):
- Consider PostgreSQL instead of SQLite
- Use separate database server
- Increase `poll_interval` to reduce database load

---

## Integration with Other Tools

### With Crash Triage

```bash
# Submit fuzzing job
./fawkes-scheduler add "Fuzz Parser" job.json --priority 80

# Wait for crashes...

# Triage all crashes from the job
./fawkes-triage --directory ~/.fawkes/crashes/ --min-severity HIGH
```

### With Crash Replay

```bash
# Get crashes from a job
./fawkes-scheduler status 42  # Shows crash count

# Replay a specific crash
./fawkes-replay --crash-id 1234 --attach-gdb
```

### With CI/CD

```bash
#!/bin/bash
# nightly_fuzz.sh - Run nightly fuzzing

JOB_ID=$(./fawkes-scheduler add "Nightly Fuzz $(date +%Y%m%d)" \
    nightly_config.json \
    --priority 60 \
    --deadline 24h | grep "Job ID" | awk '{print $3}')

echo "Started job $JOB_ID"

# Wait for completion
while true; do
    STATUS=$(./fawkes-scheduler status $JOB_ID | grep "Status:" | awk '{print $2}')
    if [[ "$STATUS" == "completed" ]]; then
        echo "Job completed successfully"
        exit 0
    elif [[ "$STATUS" == "failed" ]]; then
        echo "Job failed!"
        exit 1
    fi
    sleep 60
done
```

---

## API Reference

### SchedulerDB Methods

```python
from fawkes.db.scheduler_db import SchedulerDB

db = SchedulerDB("~/.fawkes/scheduler.db")

# Job management
job_id = db.add_job(name, config, priority=50, deadline=None,
                    dependencies=None, resource_requirements=None)
db.update_job_status(job_id, "running")
db.assign_job_to_worker(job_id, worker_id)
job = db.get_job(job_id)
job = db.get_next_job_from_queue()

# Worker management
worker_id = db.register_worker(ip_address, hostname, capabilities, tags)
db.update_worker_heartbeat(worker_id, current_load)
workers = db.get_available_workers(tags=None)

# Statistics
job_stats = db.get_job_stats()
worker_stats = db.get_worker_stats()
queue_length = db.get_queue_length()
```

### Scheduler Classes

```python
from fawkes.scheduler.scheduler import SchedulerOrchestrator

scheduler = SchedulerOrchestrator(db, allocation_strategy="load_aware",
                                 heartbeat_timeout=90)

# Run scheduling cycle
stats = scheduler.run_cycle()
# Returns: {"offline_workers": 0, "overdue_jobs": 0, "scheduled_jobs": 5}

# Get status
status = scheduler.get_status()
```

---

## Best Practices

### Job Submission

1. **Use Descriptive Names**: Include date, target, and purpose
2. **Set Appropriate Priorities**: Don't overuse critical priority
3. **Specify Resources**: Help scheduler make better decisions
4. **Use Deadlines for Time-Sensitive Work**: Ensures completion
5. **Chain Related Jobs**: Use dependencies for workflows

### Worker Management

1. **Register Workers with Capabilities**: Enables smart allocation
2. **Use Tags for Specialization**: Group workers by purpose
3. **Monitor Worker Health**: Watch for offline workers
4. **Balance Worker Capacity**: Avoid under/over-provisioning
5. **Keep Workers Updated**: Ensure compatible Fawkes versions

### Operations

1. **Monitor Queue Length**: Indicates need for more workers
2. **Track Job Statistics**: Identify trends and issues
3. **Review Failed Jobs**: Investigate root causes
4. **Clean Old History**: Archive completed job data
5. **Backup Scheduler DB**: Critical operational data

---

## See Also

- [Crash Triage](AUTOMATED_TRIAGE.md) - Automated vulnerability analysis
- [Crash Replay](CRASH_REPLAY.md) - Reproduce crashes for debugging
- [Fuzzing Guide](FUZZING_GUIDE.md) - Complete fuzzing workflow
