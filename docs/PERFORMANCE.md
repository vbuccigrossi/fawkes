# Fawkes Performance Guide

This guide covers performance optimizations, benchmarking, and tuning for maximum fuzzing throughput.

## Table of Contents

- [Overview](#overview)
- [Key Optimizations](#key-optimizations)
- [Performance Metrics](#performance-metrics)
- [Benchmarking](#benchmarking)
- [Tuning Guide](#tuning-guide)
- [Troubleshooting](#troubleshooting)

## Overview

Fawkes performance is measured primarily in **executions per second (exec/sec)** - how many testcases can be executed per second. Higher exec/sec means faster bug discovery.

### Performance Factors

1. **Snapshot Revert Speed**: How quickly VMs can be reset between testcases
2. **VM Lifecycle**: Time to start/stop VMs
3. **Testcase Generation**: Time to generate fuzzed inputs
4. **Crash Handling**: Time to process and save crashes
5. **Parallelism**: Number of concurrent VMs

### Typical Performance

**Baseline (no optimizations)**:
- Snapshot revert: 2-5 seconds (VM restart)
- Exec/sec: ~0.2-0.5 per VM

**Optimized (with fast snapshot revert)**:
- Snapshot revert: 100-200ms (QEMU monitor)
- Exec/sec: ~5-10 per VM
- **Speedup: 10-25x faster!**

## Key Optimizations

### 1. Fast Snapshot Revert (Implemented)

**Problem**: Original implementation stopped and restarted the VM for every testcase.
- VM shutdown: ~1-2 seconds
- VM startup: ~1-3 seconds
- Total per testcase: ~2-5 seconds

**Solution**: Use QEMU monitor's `loadvm` command to revert snapshot without restarting VM.
- Stop VM (pause): ~10ms
- Load snapshot: ~100-150ms
- Resume VM: ~10ms
- Total per testcase: ~100-200ms

**Performance Improvement**: 10-25x faster snapshot revert

**How It Works**:
```python
# Fawkes automatically uses fast mode by default
qemu_mgr.revert_to_snapshot(vm_id, snapshot_name, fast=True)

# Fast path: QEMU monitor command sequence
# 1. Connect to QEMU monitor on TCP port
# 2. Send "stop" to pause VM
# 3. Send "loadvm <snapshot>" to revert state
# 4. Send "cont" to resume VM
# 5. Disconnect

# Fallback to slow mode if fast fails
qemu_mgr.revert_to_snapshot(vm_id, snapshot_name, fast=False)
```

**Requirements**:
- VM must be started with `-monitor` flag (automatic)
- Snapshot must be a full VM snapshot (not disk-only)
- Monitor port must be accessible

**Measurement**:
```bash
# Benchmark snapshot revert performance
./fawkes-bench snapshot-revert --disk image.qcow2 --snapshot clean --iterations 20
```

### 2. Performance Monitoring (Implemented)

Fawkes now tracks detailed performance metrics:

```python
from fawkes.performance import perf_tracker

# Metrics are automatically tracked during fuzzing
# View statistics at any time
perf_tracker.print_stats()
```

**Tracked Metrics**:
- **Exec/sec**: Average and instantaneous execution rate
- **Timing breakdown**: Per-operation timing (snapshot revert, testcase generation, etc.)
- **Percentiles**: P50, P95, P99 for all operations
- **Counters**: Total testcases, crashes, snapshot reverts, etc.

**Example Output**:
```
================================================================================
FAWKES PERFORMANCE STATISTICS
================================================================================

Overall Metrics:
  Start Time:           2025-11-15T14:30:00
  Elapsed:              120.45s
  Total Testcases:      1234
  Total Crashes:        5
  Exec/sec (average):   10.24
  Exec/sec (recent):    11.50

Timing Breakdown:
  Operation                      Avg (ms)   P50 (ms)   P95 (ms)   P99 (ms)   Count
  ------------------------------ ---------- ---------- ---------- ---------- ----------
  snapshot_revert                150.23     145.00     180.00     200.00     1234
  snapshot_revert_fast           145.67     142.00     175.00     190.00     1230
  snapshot_revert_slow           2450.32    2400.00    2600.00    2800.00    4
  testcase_generation            5.43       5.00       8.00       12.00      1234
  testcase_execution             850.12     820.00     1050.00    1200.00    1234
  crash_handling                 1234.56    1200.00    1400.00    1600.00    5

Snapshot Revert Optimization:
  Fast mode avg:        145.67ms
  Slow mode avg:        2450.32ms
  Speedup:              16.82x
================================================================================
```

### 3. Automatic Fallback

If fast snapshot revert fails, Fawkes automatically falls back to slow mode:

```python
# Fast path attempted first
if fast and monitor_port:
    if self._monitor_loadvm(vm_id, monitor_port, snapshot_name):
        logger.debug("Fast snapshot revert successful")
        return
    else:
        logger.warning("Fast snapshot revert failed, falling back to slow path")

# Slow path fallback
self._slow_revert_to_snapshot(vm_id, snapshot_name)
```

**Common fallback causes**:
- Monitor port not available
- Monitor connection timeout
- Snapshot doesn't exist
- QEMU monitor error

## Performance Metrics

### Viewing Performance Stats

**During Fuzzing**:
Performance stats are automatically printed when fuzzing completes in local mode.

**Programmatic Access**:
```python
from fawkes.performance import perf_tracker

# Get comprehensive stats dictionary
stats = perf_tracker.get_stats()
print(f"Exec/sec: {stats['exec_per_sec']}")
print(f"Total testcases: {stats['total_testcases']}")

# Get one-line summary
summary = perf_tracker.get_summary()
print(summary)  # "Exec/sec: 10.24 | Testcases: 1234 | Crashes: 5 | Elapsed: 120.5s"

# Print detailed stats
perf_tracker.print_stats()
```

### Understanding Metrics

**Exec/sec (Average)**:
- Total testcases / Total elapsed time
- Shows overall throughput

**Exec/sec (Recent)**:
- Recent testcases / Recent time
- Shows current performance (more responsive to changes)

**Timing Percentiles**:
- **P50 (Median)**: 50% of operations complete in this time or less
- **P95**: 95% of operations complete in this time or less
- **P99**: 99% of operations complete in this time or less
- Higher percentiles show worst-case performance

**Snapshot Revert Speedup**:
- Ratio of slow mode to fast mode average time
- Higher is better (indicates successful optimization)

## Benchmarking

### fawkes-bench Tool

Fawkes includes a dedicated benchmarking tool to measure performance.

#### Snapshot Revert Benchmark

Measures snapshot revert performance (fast vs slow):

```bash
# Basic benchmark
./fawkes-bench snapshot-revert --disk image.qcow2 --snapshot clean

# More iterations for accuracy
./fawkes-bench snapshot-revert --disk image.qcow2 --snapshot clean --iterations 20

# Verbose output
./fawkes-bench snapshot-revert --disk image.qcow2 --snapshot clean -v
```

**Example Output**:
```
================================================================================
SNAPSHOT REVERT BENCHMARK
================================================================================
Disk: /path/to/image.qcow2
Snapshot: clean
Iterations: 10

Starting VM...
VM started (ID: 1)

Benchmarking FAST snapshot revert (QEMU monitor)...
  Iteration 1/10: 142.34ms
  Iteration 2/10: 138.21ms
  Iteration 3/10: 145.67ms
  ...

Fast mode statistics:
  Min:     135.12ms
  Max:     152.34ms
  Mean:    142.18ms
  Median:  141.50ms
  Stdev:   4.23ms

Benchmarking SLOW snapshot revert (VM restart)...
  Iteration 1/3: 2456.78ms
  Iteration 2/3: 2401.23ms
  Iteration 3/3: 2478.90ms

Slow mode statistics:
  Min:     2401.23ms
  Max:     2478.90ms
  Mean:    2445.64ms
  Median:  2456.78ms
  Stdev:   32.15ms

--------------------------------------------------------------------------------
PERFORMANCE IMPROVEMENT
--------------------------------------------------------------------------------
Speedup:              17.20x faster
Time saved per exec:  2303.46ms
At 100 exec/sec:      230.35s saved per second
At 1000 execs/day:    2303.46s (38.4min) saved per day
--------------------------------------------------------------------------------
```

#### VM Lifecycle Benchmark

Measures VM start/stop performance:

```bash
# Benchmark VM lifecycle
./fawkes-bench vm-lifecycle --disk image.qcow2 --iterations 5
```

**Example Output**:
```
================================================================================
VM LIFECYCLE BENCHMARK
================================================================================
Disk: /path/to/image.qcow2
Iterations: 5

Iteration 1/5
  VM start: 1234.56ms
  VM stop:  456.78ms

...

--------------------------------------------------------------------------------
VM START STATISTICS
--------------------------------------------------------------------------------
  Min:     1201.23ms
  Max:     1267.89ms
  Mean:    1234.56ms
  Median:  1230.45ms
  Stdev:   23.45ms

--------------------------------------------------------------------------------
VM STOP STATISTICS
--------------------------------------------------------------------------------
  Min:     445.67ms
  Max:     478.90ms
  Mean:    456.78ms
  Median:  454.32ms
  Stdev:   12.34ms

--------------------------------------------------------------------------------
TOTAL LIFECYCLE
--------------------------------------------------------------------------------
  Mean total: 1691.34ms per cycle
--------------------------------------------------------------------------------
```

### Interpreting Benchmark Results

**Good Performance**:
- Fast snapshot revert: 100-200ms
- Slow snapshot revert: 2000-5000ms
- Speedup: 10-25x
- VM start: 1000-2000ms
- VM stop: 200-500ms

**Poor Performance**:
- Fast snapshot revert: >500ms (check monitor connection)
- Slow snapshot revert: >10000ms (check disk I/O)
- Speedup: <5x (fast mode not working properly)
- VM start: >5000ms (check system resources)

**Action Items**:
- Speedup <10x: Investigate fast snapshot revert failures
- Fast revert >300ms: Check system load, disk I/O
- VM start >3000ms: Check available RAM, CPU
- Frequent fallbacks: Check QEMU monitor configuration

## Tuning Guide

### Maximizing Exec/sec

**1. Use Fast Snapshot Revert** (Automatic)
- Ensure VMs start with monitor port (automatic in Fawkes)
- Use full VM snapshots (not disk-only)
- Verify fast mode is working (check perf stats)

**2. Optimize Snapshot Size**
- Use minimal RAM allocation for VM
- Smaller snapshots = faster revert
- Balance: Need enough RAM for target to run

**3. Tune Parallelism**
- More VMs = higher total exec/sec
- But: Too many = resource contention
- Formula: `cores * 2` is a good starting point
- Monitor system resources

**4. Fast Disk I/O**
- Use SSD for disk images
- Use tmpfs/ramdisk for temporary files
- Avoid network-mounted disks

**5. Optimize Testcase Generation**
- Simple mutation strategies are faster
- Complex generation = lower exec/sec
- Balance: Coverage vs speed

### Configuration Examples

**Maximum Performance**:
```yaml
# config-perf.yaml
disk: /path/to/image.qcow2
snapshot_name: fuzzing-ready
memory: 256M  # Minimal RAM
arch: x86_64
max_parallel_vms: 8  # cores * 2
timeout: 5  # Short timeout
```

**Maximum Coverage**:
```yaml
# config-coverage.yaml
disk: /path/to/image.qcow2
snapshot_name: fuzzing-ready
memory: 1G  # More RAM for complex targets
arch: x86_64
max_parallel_vms: 4  # Fewer VMs
timeout: 30  # Longer timeout
```

### System Tuning

**Linux**:
```bash
# Increase file descriptor limit
ulimit -n 65536

# Disable CPU frequency scaling for consistent performance
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Use tmpfs for temporary files
mkdir -p /tmp/fawkes_tmp
mount -t tmpfs -o size=4G tmpfs /tmp/fawkes_tmp
export TMPDIR=/tmp/fawkes_tmp

# Increase shared memory limit for QEMU
sudo sysctl -w kernel.shmmax=17179869184
sudo sysctl -w kernel.shmall=4194304
```

**Resource Monitoring**:
```bash
# Monitor CPU usage
htop

# Monitor disk I/O
iotop -o

# Monitor memory
free -h

# Monitor Fawkes processes
watch -n 1 'ps aux | grep fawkes'
```

## Troubleshooting

### Issue: Low Exec/sec (<1 per VM)

**Symptoms**:
- Performance stats show <1 exec/sec per VM
- Fuzzing feels very slow

**Causes**:
1. Fast snapshot revert not working
2. Slow disk I/O
3. Insufficient resources
4. Target takes long to execute

**Solutions**:

**Check fast snapshot revert**:
```bash
# Run benchmark
./fawkes-bench snapshot-revert --disk image.qcow2 --snapshot clean

# Check if fast mode is working
# Look for "Fast mode avg: <200ms"
# If >500ms or "No monitor port", fast mode isn't working

# Check performance stats during fuzzing
# Look for "snapshot_revert_fast" in timing breakdown
```

**Check disk I/O**:
```bash
# Monitor I/O during fuzzing
iotop -o

# Move disk image to faster storage
cp image.qcow2 /path/to/ssd/image.qcow2

# Use ramdisk (4GB tmpfs)
mkdir -p /tmp/fawkes_ramdisk
mount -t tmpfs -o size=4G tmpfs /tmp/fawkes_ramdisk
cp image.qcow2 /tmp/fawkes_ramdisk/
```

**Check resources**:
```bash
# Check CPU and memory
htop

# Reduce parallel VMs if system is overloaded
# Edit config: max_parallel_vms: 2
```

### Issue: Frequent Fallback to Slow Mode

**Symptoms**:
```
WARNING: Fast snapshot revert failed, falling back to slow path
WARNING: Fast snapshot revert failed, falling back to slow path
...
```

**Causes**:
1. Monitor port not available
2. Monitor connection timeout
3. QEMU monitor errors

**Solutions**:

**Verify monitor port**:
```bash
# Check if VMs have monitor ports
./fawkes tui
# Look at VM info - should show monitor_port

# Test monitor manually
nc localhost <monitor_port>
# Should see QEMU monitor banner
```

**Check QEMU version**:
```bash
qemu-system-x86_64 --version
# Should be 2.5+
# Older versions may have monitor issues
```

**Check logs**:
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
./fawkes --config config.yaml --mode local

# Look for monitor errors in output
# Check /tmp/fawkes_*.log
```

### Issue: Inconsistent Performance

**Symptoms**:
- Exec/sec varies widely
- Sometimes fast, sometimes slow

**Causes**:
1. System resource contention
2. Other processes competing for resources
3. Thermal throttling
4. Network issues (for distributed mode)

**Solutions**:

**Isolate system resources**:
```bash
# Stop unnecessary services
sudo systemctl stop <service>

# Use nice/ionice for other processes
nice -n 19 ionice -c 3 <other-process>

# Use cgroups to limit other processes
# (advanced - see cgroups documentation)
```

**Monitor temperature**:
```bash
# Check CPU temperature
sensors

# If thermal throttling, improve cooling
# Or reduce max_parallel_vms
```

**Check for background processes**:
```bash
# Find CPU-intensive processes
top -o %CPU

# Find I/O-intensive processes
iotop -o
```

### Issue: Performance Degradation Over Time

**Symptoms**:
- Good performance initially
- Degrades after minutes/hours

**Causes**:
1. Memory leaks
2. Disk space exhaustion
3. Log file growth
4. Crash directory growth

**Solutions**:

**Monitor resources over time**:
```bash
# Watch memory usage
watch -n 5 'free -h'

# Watch disk space
watch -n 5 'df -h'

# Watch process memory
watch -n 5 'ps aux | grep fawkes | grep -v grep'
```

**Clean up regularly**:
```bash
# Clean old crashes
find ~/.fawkes/crashes -mtime +7 -delete

# Rotate logs
logrotate /etc/logrotate.d/fawkes

# Clean temporary files
rm -rf /tmp/fawkes_*
```

## Performance Comparison

### Before vs After Optimization

**Before** (Original Implementation):
```
Exec/sec: 0.3 per VM
Testcase execution cycle:
  - Stop VM: 1500ms
  - Start VM: 2000ms
  - Generate testcase: 5ms
  - Execute testcase: 500ms
  - Total: ~4000ms per testcase
```

**After** (With Optimizations):
```
Exec/sec: 5-10 per VM
Testcase execution cycle:
  - Revert snapshot (fast): 150ms
  - Generate testcase: 5ms
  - Execute testcase: 500ms
  - Total: ~650ms per testcase

Improvement: 6-7x faster!
```

### Real-World Impact

**Scenario**: 8 CPU cores, 24-hour fuzzing run

**Before Optimization**:
- VMs: 4 parallel
- Exec/sec: 0.3 per VM = 1.2 total
- 24 hours: 1.2 * 86400 = 103,680 testcases
- Crashes found: ~5 (estimated)

**After Optimization**:
- VMs: 8 parallel
- Exec/sec: 5 per VM = 40 total
- 24 hours: 40 * 86400 = 3,456,000 testcases
- Crashes found: ~150 (estimated)

**Improvement**:
- 33x more testcases
- 30x more crashes discovered
- Same hardware, same time!

## Best Practices

1. **Always use full VM snapshots**
   - Not disk-only snapshots
   - Fast revert requires full VM state

2. **Monitor performance regularly**
   - Check perf stats after fuzzing runs
   - Investigate if exec/sec drops

3. **Benchmark after changes**
   - Use fawkes-bench to verify optimizations
   - Compare before/after results

4. **Start small, scale up**
   - Begin with 1-2 VMs
   - Monitor resources
   - Gradually increase parallelism

5. **Use appropriate timeouts**
   - Short timeouts for fast targets
   - Longer timeouts for complex targets
   - Balance: coverage vs speed

6. **Keep system dedicated**
   - Avoid running other workloads
   - Reduces resource contention
   - More consistent performance

## Summary

Fawkes performance optimizations deliver **6-30x speedup** for most workloads through:

1. **Fast snapshot revert** (100-200ms vs 2-5s)
2. **Automatic fallback** (reliability)
3. **Performance monitoring** (visibility)
4. **Benchmarking tools** (measurement)

**Quick Start**:
```bash
# 1. Verify your snapshot is optimal
./fawkes-snapshot validate --disk image.qcow2 --name fuzzing-ready

# 2. Benchmark performance
./fawkes-bench snapshot-revert --disk image.qcow2 --snapshot fuzzing-ready

# 3. Run fuzzing
./fawkes --config config.yaml --mode local

# 4. Check performance stats (printed at end)
# Look for:
#   - Exec/sec: >5 per VM is good
#   - Snapshot revert speedup: >10x is good
#   - Fast revert success rate: >95% is good
```

For more information:
- Main documentation: `README.md`
- Snapshot management: `docs/SNAPSHOT_MANAGEMENT.md`
- Fuzzing guide: `docs/FUZZING_GUIDE.md`
