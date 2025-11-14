# Fawkes Differential Fuzzing

Differential fuzzing compares behavior across different software versions or implementations to find semantic bugs, security vulnerabilities, and behavioral divergences.

## Overview

Differential fuzzing executes the same testcase across multiple targets (versions/implementations) and detects divergences in:

- **Crashes**: One target crashes while another doesn't
- **Output**: Different outputs for the same input
- **Return Codes**: Different exit codes
- **Timeouts**: One target times out while another completes
- **Memory Usage**: Significant memory usage differences
- **Register States**: Different CPU register states at crash
- **Exceptions**: Different signals or exceptions

## Architecture

```
┌─────────────────┐
│   fawkes-diff   │  CLI Tool
└────────┬────────┘
         │
┌────────▼──────────────┐
│ DifferentialHarness   │  Orchestrates campaign
└────────┬──────────────┘
         │
    ┌────┴─────┐
    │          │
┌───▼──┐  ┌───▼────────────────┐
│ QEMU │  │ DifferentialEngine │  Comparison Logic
│  +   │  └───┬────────────────┘
│ GDB  │      │
└──────┘      │
         ┌────▼─────┐
         │ Database │  Campaigns & Divergences
         └──────────┘
```

## Components

### 1. DifferentialEngine (`differential/engine.py`)

Core comparison engine that analyzes execution results and detects divergences.

**Divergence Types:**
- `CRASH`: One crashes, other doesn't
- `DIFFERENT_OUTPUT`: Different outputs
- `DIFFERENT_RETURN`: Different return codes
- `TIMEOUT`: One times out, other doesn't
- `MEMORY_DIFF`: Different memory usage (>50% difference)
- `REGISTER_DIFF`: Different register states
- `EXCEPTION`: Different exceptions/signals

**Severity Levels:**
- `CRITICAL`: Security-relevant (crash, corruption)
- `HIGH`: Likely bug (different behavior)
- `MEDIUM`: Possible issue (minor differences)
- `LOW`: Expected variation
- `INFO`: Informational

### 2. DifferentialHarness (`differential/harness.py`)

Executes testcases across multiple targets and coordinates comparison.

**Key Features:**
- VM management per target
- Snapshot-based isolation
- Automatic testcase execution
- Result collection and comparison
- Campaign orchestration

### 3. DifferentialDB (`differential/db.py`)

Stores campaigns, execution results, and divergences.

**Schema:**
- `campaigns`: Campaign metadata and statistics
- `executions`: Individual execution results
- `divergences`: Detected divergences with details

### 4. CLI Tool (`fawkes-diff`)

Command-line interface for managing differential fuzzing campaigns.

## Usage

### Step 1: Prepare Targets

Create disk images for each version/implementation you want to compare:

```bash
# Example: Testing different OpenSSL versions
qemu-img create -f qcow2 openssl-1.1.1.qcow2 20G
qemu-img create -f qcow2 openssl-3.0.0.qcow2 20G

# Install each version in its respective VM
# Create snapshots at ready state
```

### Step 2: Create Configuration

Create a JSON configuration file defining your targets:

```json
{
  "description": "OpenSSL 1.1.1 vs 3.0.0 comparison",
  "targets": [
    {
      "id": "openssl-1.1.1",
      "version": "1.1.1w",
      "disk_image": "~/.fawkes/vms/openssl-1.1.1.qcow2",
      "snapshot_name": "ready",
      "arch": "x86_64"
    },
    {
      "id": "openssl-3.0.0",
      "version": "3.0.0",
      "disk_image": "~/.fawkes/vms/openssl-3.0.0.qcow2",
      "snapshot_name": "ready",
      "arch": "x86_64"
    }
  ]
}
```

### Step 3: Prepare Testcases

Create a directory with testcases (inputs to test):

```bash
mkdir testcases/
# Add your testcases (can be any format your target accepts)
cp fuzzing_corpus/* testcases/
```

### Step 4: Run Campaign

```bash
./fawkes-diff run config.json testcases/ \
  --campaign-name "OpenSSL Comparison" \
  --timeout 60 \
  --max-testcases 1000 \
  --output-dir ~/.fawkes/differential
```

**Options:**
- `--campaign-name`: Descriptive name for the campaign
- `--timeout`: Execution timeout per target (seconds, default: 60)
- `--max-testcases`: Limit number of testcases to run
- `--output-dir`: Output directory for results

### Step 5: View Results

**List campaigns:**
```bash
./fawkes-diff campaigns
```

**Show campaign details:**
```bash
./fawkes-diff show <campaign_id>
```

**List divergences:**
```bash
# All divergences
./fawkes-diff divergences

# Filter by campaign
./fawkes-diff divergences --campaign-id 1

# Filter by severity
./fawkes-diff divergences --severity critical

# Filter by type
./fawkes-diff divergences --type crash
```

**Show divergence details:**
```bash
./fawkes-diff show-divergence <divergence_id>
```

**View statistics:**
```bash
# Overall stats
./fawkes-diff stats

# Campaign-specific stats
./fawkes-diff stats --campaign-id 1
```

### Step 6: Triage Divergences

Mark divergences as triaged after investigation:

```bash
./fawkes-diff triage <divergence_id> "Analysis notes here"
```

## Example Configuration Files

### Multi-Version Comparison

Compare three versions of the same software:

```json
{
  "description": "SQLite version comparison",
  "targets": [
    {
      "id": "sqlite-3.35",
      "version": "3.35.0",
      "disk_image": "~/.fawkes/vms/sqlite-3.35.qcow2",
      "snapshot_name": "ready",
      "arch": "x86_64"
    },
    {
      "id": "sqlite-3.40",
      "version": "3.40.0",
      "disk_image": "~/.fawkes/vms/sqlite-3.40.qcow2",
      "snapshot_name": "ready",
      "arch": "x86_64"
    },
    {
      "id": "sqlite-3.45",
      "version": "3.45.0",
      "disk_image": "~/.fawkes/vms/sqlite-3.45.qcow2",
      "snapshot_name": "ready",
      "arch": "x86_64"
    }
  ]
}
```

### Cross-Implementation Comparison

Compare different implementations of the same specification:

```json
{
  "description": "XML parser comparison",
  "targets": [
    {
      "id": "libxml2",
      "version": "2.10.0",
      "disk_image": "~/.fawkes/vms/libxml2.qcow2",
      "snapshot_name": "ready",
      "arch": "x86_64"
    },
    {
      "id": "expat",
      "version": "2.5.0",
      "disk_image": "~/.fawkes/vms/expat.qcow2",
      "snapshot_name": "ready",
      "arch": "x86_64"
    }
  ]
}
```

### Multi-Architecture Comparison

Compare behavior across different architectures:

```json
{
  "description": "Cross-architecture comparison",
  "targets": [
    {
      "id": "target-x86_64",
      "version": "1.0.0",
      "disk_image": "~/.fawkes/vms/app-x86_64.qcow2",
      "snapshot_name": "ready",
      "arch": "x86_64"
    },
    {
      "id": "target-aarch64",
      "version": "1.0.0",
      "disk_image": "~/.fawkes/vms/app-aarch64.qcow2",
      "snapshot_name": "ready",
      "arch": "aarch64"
    }
  ]
}
```

## Database Schema

### campaigns Table

| Column | Type | Description |
|--------|------|-------------|
| campaign_id | INTEGER PRIMARY KEY | Unique campaign ID |
| name | TEXT | Campaign name |
| description | TEXT | Campaign description |
| targets | TEXT | JSON list of target IDs |
| start_time | INTEGER | Unix timestamp |
| end_time | INTEGER | Unix timestamp |
| testcases_executed | INTEGER | Total testcases executed |
| divergences_found | INTEGER | Total divergences found |
| crashes_found | INTEGER | Total crashes found |

### executions Table

| Column | Type | Description |
|--------|------|-------------|
| execution_id | INTEGER PRIMARY KEY | Unique execution ID |
| campaign_id | INTEGER | Campaign reference |
| target_id | TEXT | Target identifier |
| target_version | TEXT | Target version |
| testcase_path | TEXT | Path to testcase |
| crashed | BOOLEAN | Whether execution crashed |
| exit_code | INTEGER | Process exit code |
| timeout | BOOLEAN | Whether execution timed out |
| execution_time | REAL | Execution time (ms) |
| output_hash | TEXT | SHA256 hash of output |
| signal | TEXT | Signal received (if crashed) |
| timestamp | INTEGER | Unix timestamp |

### divergences Table

| Column | Type | Description |
|--------|------|-------------|
| divergence_id | TEXT PRIMARY KEY | Unique divergence ID |
| campaign_id | INTEGER | Campaign reference |
| testcase_path | TEXT | Path to testcase |
| divergence_type | TEXT | Type of divergence |
| severity | TEXT | Severity level |
| target_a_id | TEXT | First target ID |
| target_b_id | TEXT | Second target ID |
| description | TEXT | Human-readable description |
| confidence | REAL | Confidence score (0.0-1.0) |
| details | TEXT | JSON details |
| timestamp | INTEGER | Unix timestamp |
| triaged | BOOLEAN | Whether divergence is triaged |
| notes | TEXT | Triage notes |

## Advanced Usage

### Custom Timeout per Target

For targets with different performance characteristics:

```python
from fawkes.differential.harness import DifferentialHarness, DifferentialTarget

targets = [
    DifferentialTarget("fast", "1.0", "fast.qcow2", "ready"),
    DifferentialTarget("slow", "2.0", "slow.qcow2", "ready"),
]

# Use higher timeout for slower target
harness = DifferentialHarness(targets, timeout=120)
```

### Programmatic Usage

```python
from fawkes.differential.harness import DifferentialHarness, DifferentialTarget
from fawkes.differential.db import DifferentialDB

# Create targets
targets = [
    DifferentialTarget(
        target_id="v1",
        version="1.0.0",
        disk_image="/path/to/v1.qcow2",
        snapshot_name="ready",
        arch="x86_64"
    ),
    DifferentialTarget(
        target_id="v2",
        version="2.0.0",
        disk_image="/path/to/v2.qcow2",
        snapshot_name="ready",
        arch="x86_64"
    ),
]

# Create harness
harness = DifferentialHarness(
    targets=targets,
    timeout=60,
    output_dir="~/.fawkes/differential"
)

# Run campaign
stats = harness.run_campaign(
    testcase_dir="/path/to/testcases",
    max_testcases=100
)

# Get divergences
critical_divergences = harness.get_critical_divergences()

# Save to database
db = DifferentialDB("~/.fawkes/differential.db")
campaign_id = db.add_campaign("My Campaign", ["v1", "v2"])

for divergence in harness.get_divergences():
    db.add_divergence(campaign_id, divergence)

db.close()
```

### Filtering Divergences by Confidence

```python
from fawkes.differential.db import DifferentialDB

db = DifferentialDB("~/.fawkes/differential.db")
divergences = db.get_divergences()

# Filter high-confidence divergences
high_confidence = [d for d in divergences if d['confidence'] > 0.8]

# Filter by severity and confidence
critical_high_conf = [
    d for d in divergences
    if d['severity'] == 'critical' and d['confidence'] > 0.9
]
```

## Best Practices

### 1. Start with Small Testcase Sets

Begin with a small, diverse testcase set to understand divergence patterns:

```bash
# Test with 100 testcases first
./fawkes-diff run config.json testcases/ --max-testcases 100
```

### 2. Use Meaningful Campaign Names

Include version information and date in campaign names:

```bash
--campaign-name "OpenSSL 1.1.1 vs 3.0.0 - 2025-01-14"
```

### 3. Monitor Critical Divergences

Focus on critical and high severity divergences first:

```bash
./fawkes-diff divergences --severity critical
./fawkes-diff divergences --severity high
```

### 4. Triage Divergences Promptly

Mark divergences as triaged after investigation to track progress:

```bash
./fawkes-diff triage abc123 "False positive - timing difference only"
./fawkes-diff triage def456 "CVE-2024-XXXXX - already fixed in 3.0.1"
```

### 5. Use Snapshots Correctly

Ensure snapshots are at a clean, consistent state:
- Application fully loaded
- No background processes running
- Deterministic state

### 6. Consider Performance Differences

Some divergences may be due to legitimate performance improvements:
- Execution time differences
- Memory usage optimizations
- Different algorithmic approaches

### 7. Review Output Similarity Scores

For output divergences, check the similarity score:
- <20% similar: Likely significant issue
- 20-50% similar: Possible issue
- 50-80% similar: Minor difference
- >80% similar: Probably benign

## Troubleshooting

### No Divergences Detected

**Problem**: Campaign completes but finds no divergences.

**Solutions:**
1. Verify targets are actually different versions
2. Check testcases are triggering different code paths
3. Increase testcase diversity
4. Verify VMs are executing correctly

### High False Positive Rate

**Problem**: Many divergences flagged as info/low severity.

**Solutions:**
1. Filter by severity: `--severity critical` or `--severity high`
2. Filter by confidence: Only review divergences with confidence >0.8
3. Adjust timeout if timing-related false positives occur

### VMs Not Starting

**Problem**: Failed to setup target error.

**Solutions:**
1. Verify disk image paths are correct
2. Check snapshot names exist: `qemu-img snapshot -l disk.qcow2`
3. Ensure sufficient resources (memory, CPU cores)
4. Check QEMU installation: `qemu-system-x86_64 --version`

### Execution Timeouts

**Problem**: Many executions timing out.

**Solutions:**
1. Increase timeout: `--timeout 120`
2. Check VM performance (may need more resources)
3. Verify testcases aren't infinite loops

### Database Errors

**Problem**: Database locked or corrupted.

**Solutions:**
1. Ensure no other fawkes-diff instances are running
2. Check database file permissions
3. Backup and recreate database if corrupted

## Performance Considerations

### Execution Time

Differential fuzzing is inherently slower than standard fuzzing:

```
Time = testcases × targets × timeout
```

Example:
- 1000 testcases
- 3 targets
- 60s timeout
- = 50 hours minimum

### Parallelization

Currently, targets are executed sequentially per testcase. Future versions may support parallel execution.

### Resource Usage

Per target:
- 1 QEMU VM (2GB RAM default)
- 1 GDB process
- Disk I/O for snapshots

With 3 targets: ~6GB RAM minimum

## Integration with Other Fawkes Features

### With Crash Replay

Replay divergence-causing inputs:

```bash
# Get divergence testcase
./fawkes-diff show-divergence abc123

# Replay on specific target
./fawkes-replay ~/.fawkes/differential/testcase.bin \
  --disk target-v1.qcow2 \
  --snapshot ready
```

### With Crash Triage

Triage crashes found during differential fuzzing:

```bash
# Extract crash info
./fawkes-diff show-divergence abc123

# Triage with fawkes-triage
./fawkes-triage ~/.fawkes/differential/crashes/
```

### With Job Scheduler

Schedule differential campaigns:

```bash
./fawkes-scheduler add differential-campaign \
  --command "./fawkes-diff run config.json testcases/" \
  --priority 80
```

## API Reference

### DifferentialEngine

```python
class DifferentialEngine:
    def compare_executions(result_a: ExecutionResult,
                          result_b: ExecutionResult) -> List[Divergence]
    def get_critical_divergences() -> List[Divergence]
    def get_divergences_by_type(div_type: DivergenceType) -> List[Divergence]
    def get_stats() -> Dict[str, Any]
    def generate_summary_report() -> str
```

### DifferentialHarness

```python
class DifferentialHarness:
    def __init__(targets: List[DifferentialTarget],
                 timeout: int = 60,
                 output_dir: str = "~/.fawkes/differential")
    def setup_target(target: DifferentialTarget) -> bool
    def execute_on_target(target: DifferentialTarget,
                         testcase_path: str) -> Optional[ExecutionResult]
    def run_differential_testcase(testcase_path: str) -> List[Divergence]
    def run_campaign(testcase_dir: str,
                     max_testcases: Optional[int] = None) -> Dict
    def cleanup()
    def get_divergences() -> List[Divergence]
    def get_critical_divergences() -> List[Divergence]
    def generate_report() -> str
```

### DifferentialDB

```python
class DifferentialDB:
    def __init__(db_path: str)
    def add_campaign(name: str, targets: List[str],
                     description: Optional[str] = None) -> int
    def update_campaign_stats(campaign_id: int, stats: Dict[str, int])
    def end_campaign(campaign_id: int)
    def add_execution(campaign_id: int, result: ExecutionResult) -> int
    def add_divergence(campaign_id: int, divergence: Divergence)
    def get_divergences(campaign_id: Optional[int] = None,
                       severity: Optional[str] = None,
                       div_type: Optional[str] = None) -> List[Dict]
    def get_campaign_summary(campaign_id: int) -> Optional[Dict]
    def triage_divergence(divergence_id: str, notes: str)
    def get_stats(campaign_id: Optional[int] = None) -> Dict[str, Any]
    def close()
```

## Examples

See `examples/differential/` directory for complete examples:
- `compare_openssl_versions.sh`: Compare OpenSSL versions
- `compare_xml_parsers.sh`: Compare different XML parsers
- `cross_arch_comparison.sh`: Compare same software across architectures

## Contributing

When adding new divergence types or severity assessments:

1. Add to `DivergenceType` enum in `engine.py`
2. Implement detection logic in `compare_executions()`
3. Add tests to test suite
4. Update documentation

## License

Part of the Fawkes fuzzing framework.
