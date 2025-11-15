# Fawkes Snapshot Management Guide

This guide covers the snapshot management tools for creating, validating, and managing VM snapshots for Fawkes fuzzing.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Commands](#commands)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

## Overview

VM snapshots are critical for efficient fuzzing in Fawkes. They allow the fuzzer to:
- Quickly restore VMs to a known good state
- Start fuzzing immediately without boot time
- Ensure consistent execution environment
- Recover from VM crashes instantly

### What is a Snapshot?

A QEMU/QCOW2 snapshot captures the complete state of a virtual machine including:
- **Disk state**: All file system changes
- **Memory state**: RAM contents
- **CPU state**: Registers, flags, execution position
- **Device state**: Network, peripherals, etc.

### Snapshot Types

**Full VM Snapshot** (Recommended):
- Created with `savevm` command in QEMU monitor
- Includes disk + memory + CPU + device state
- Can be loaded with `-loadvm` flag
- Required for Fawkes fuzzing

**Disk-Only Snapshot** (Not Recommended):
- Created with `qemu-img snapshot -c`
- Only includes disk state
- Cannot be loaded with `-loadvm`
- NOT suitable for fuzzing

## Quick Start

### Prerequisites

1. **QEMU installed**:
```bash
# Ubuntu/Debian
sudo apt-get install qemu-system-x86

# macOS
brew install qemu
```

2. **QCOW2 disk image**:
```bash
# Create new QCOW2 image
qemu-img create -f qcow2 disk.qcow2 10G

# Or convert existing image
qemu-img convert -f raw -O qcow2 disk.img disk.qcow2
```

3. **VM with Fawkes agent** (for validation):
- Install and configure Fawkes agent in VM
- Agent should auto-start on boot
- Agent listens on port 9999

### Creating Your First Snapshot

```bash
# 1. List existing snapshots (should be empty)
./fawkes-snapshot list --disk disk.qcow2

# 2. Create a new snapshot
./fawkes-snapshot create --disk disk.qcow2 --name fuzzing-ready

# This will:
# - Boot the VM
# - Create full snapshot via QEMU monitor
# - Validate snapshot has VM state
# - Check if Fawkes agent is running
# - Confirm snapshot is ready for fuzzing

# 3. Verify snapshot was created
./fawkes-snapshot list --disk disk.qcow2

# 4. Validate snapshot
./fawkes-snapshot validate --disk disk.qcow2 --name fuzzing-ready
```

### Using Snapshot in Fawkes

```yaml
# fawkes-config.yaml
disk: /path/to/disk.qcow2
snapshot_name: fuzzing-ready  # Use the snapshot
memory: 512M
arch: x86_64
```

## Commands

### list - List Snapshots

List all snapshots in a QCOW2 disk image.

**Syntax**:
```bash
fawkes-snapshot list --disk <path> [options]
```

**Arguments**:
- `--disk PATH`: Path to QCOW2 disk image (required)

**Options**:
- `-v, --verbose`: Enable verbose output

**Example**:
```bash
$ ./fawkes-snapshot list --disk debian.qcow2

Snapshots in debian.qcow2:
ID    Name                 VM Size      Date                 VM Clock
--------------------------------------------------------------------------------
1     pre-fuzzing         145M         2025-11-15 10:30:00  00:02:15.234
2     fuzzing-ready       148M         2025-11-15 11:45:00  00:03:42.567
3     with-symbols        150M         2025-11-15 14:20:00  00:04:01.890

Total: 3 snapshot(s)
```

**Output Fields**:
- **ID**: Snapshot identifier
- **Name**: Snapshot tag/name
- **VM Size**: Memory state size (0B = disk-only, not usable)
- **Date**: When snapshot was created
- **VM Clock**: Virtual machine time at snapshot

### create - Create Snapshot

Create a new VM snapshot with validation.

**Syntax**:
```bash
fawkes-snapshot create --disk <path> --name <name> [options]
```

**Arguments**:
- `--disk PATH`: Path to QCOW2 disk image (required)
- `--name NAME`: Snapshot name/tag (required)

**Options**:
- `--no-boot`: Create disk-only snapshot without booting VM (not recommended)
- `--no-validate`: Skip snapshot validation after creation
- `--timeout SECONDS`: Timeout for VM operations (default: 60)
- `--force`: Overwrite existing snapshot with same name
- `-v, --verbose`: Enable verbose output

**Example**:
```bash
# Standard snapshot creation with validation
$ ./fawkes-snapshot create --disk debian.qcow2 --name fuzzing-ready

INFO: Creating snapshot 'fuzzing-ready' for debian.qcow2
INFO: Booting VM to create live snapshot...
INFO: Waiting for VM to boot (timeout: 60s)...
INFO: Creating snapshot via QEMU monitor on port 45678...
INFO: Shutting down VM...
INFO: ✓ Snapshot 'fuzzing-ready' created successfully
INFO: Validating snapshot 'fuzzing-ready'...
INFO: ✓ Snapshot 'fuzzing-ready' exists (VM Size: 148M)
INFO: ✓ Snapshot has VM state (148M)
INFO: Testing snapshot load...
INFO: ✓ Snapshot loads successfully
INFO: Checking Fawkes agent (timeout: 30s)...
INFO: ✓ Fawkes agent is running and responsive
INFO: ✓ Snapshot 'fuzzing-ready' is valid and ready for fuzzing
```

**Create without agent check** (VM doesn't have agent yet):
```bash
$ ./fawkes-snapshot create --disk debian.qcow2 --name pre-agent --no-validate
```

**Overwrite existing snapshot**:
```bash
$ ./fawkes-snapshot create --disk debian.qcow2 --name fuzzing-ready --force
```

**Disk-only snapshot** (not recommended):
```bash
$ ./fawkes-snapshot create --disk debian.qcow2 --name backup --no-boot
WARNING: Creating disk-only snapshot - will NOT work with Fawkes!
```

### delete - Delete Snapshot

Delete a snapshot from a disk image.

**Syntax**:
```bash
fawkes-snapshot delete --disk <path> --name <name> [options]
```

**Arguments**:
- `--disk PATH`: Path to QCOW2 disk image (required)
- `--name NAME`: Snapshot name/tag to delete (required)

**Options**:
- `--force`: Delete without confirmation
- `-v, --verbose`: Enable verbose output

**Example**:
```bash
# Interactive deletion (prompts for confirmation)
$ ./fawkes-snapshot delete --disk debian.qcow2 --name old-snapshot
Delete snapshot 'old-snapshot' from debian.qcow2? [y/N]: y
INFO: Deleting snapshot 'old-snapshot' from debian.qcow2
INFO: ✓ Snapshot 'old-snapshot' deleted successfully

# Force deletion (no prompt)
$ ./fawkes-snapshot delete --disk debian.qcow2 --name backup --force
INFO: Deleting snapshot 'backup' from debian.qcow2
INFO: ✓ Snapshot 'backup' deleted successfully
```

### validate - Validate Snapshot

Validate that a snapshot is ready for fuzzing.

**Syntax**:
```bash
fawkes-snapshot validate --disk <path> --name <name> [options]
```

**Arguments**:
- `--disk PATH`: Path to QCOW2 disk image (required)
- `--name NAME`: Snapshot name/tag to validate (required)

**Options**:
- `--no-agent-check`: Skip Fawkes agent check
- `--timeout SECONDS`: Timeout for agent check (default: 30)
- `-v, --verbose`: Enable verbose output

**Validation Checks**:
1. ✓ Snapshot exists in disk image
2. ✓ Snapshot has full VM state (not disk-only)
3. ✓ Snapshot can be loaded with -loadvm
4. ✓ Fawkes agent is running and responsive (optional)

**Example**:
```bash
# Full validation with agent check
$ ./fawkes-snapshot validate --disk debian.qcow2 --name fuzzing-ready

INFO: Validating snapshot 'fuzzing-ready' in debian.qcow2
INFO: ✓ Snapshot 'fuzzing-ready' exists (VM Size: 148M)
INFO: ✓ Snapshot has VM state (148M)
INFO: Testing snapshot load...
INFO: ✓ Snapshot loads successfully
INFO: Checking Fawkes agent (timeout: 30s)...
INFO: ✓ Fawkes agent is running and responsive
INFO: ✓ Snapshot 'fuzzing-ready' is valid and ready for fuzzing
```

**Validation without agent check**:
```bash
$ ./fawkes-snapshot validate --disk debian.qcow2 --name test --no-agent-check

INFO: Validating snapshot 'test' in debian.qcow2
INFO: ✓ Snapshot 'test' exists (VM Size: 145M)
INFO: ✓ Snapshot has VM state (145M)
INFO: Testing snapshot load...
INFO: ✓ Snapshot loads successfully
INFO: ✓ Snapshot 'test' is valid and ready for fuzzing
```

**Failed validation example** (disk-only snapshot):
```bash
$ ./fawkes-snapshot validate --disk debian.qcow2 --name bad-snapshot

INFO: Validating snapshot 'bad-snapshot' in debian.qcow2
INFO: ✓ Snapshot 'bad-snapshot' exists (VM Size: 0B)
ERROR: ✗ Snapshot 'bad-snapshot' is disk-only (no VM state)
ERROR:    This snapshot cannot be loaded with -loadvm
ERROR:    Create a proper snapshot by booting the VM and using 'savevm'
```

## Best Practices

### Creating Snapshots

**1. Prepare the VM**:
```bash
# Boot VM and prepare for fuzzing
qemu-system-x86_64 -drive file=disk.qcow2,format=qcow2 \
  -m 512M \
  -net user -net nic

# Inside VM:
# - Install Fawkes agent
# - Configure agent to auto-start
# - Install target binary and dependencies
# - Set up any necessary environment
# - Clear any logs or temporary files
# - Verify everything works
```

**2. Create snapshot at optimal time**:
```bash
# Snapshot when:
# ✓ VM is fully booted
# ✓ Fawkes agent is running
# ✓ Target binary is ready
# ✓ No background processes running
# ✓ System is idle

./fawkes-snapshot create --disk disk.qcow2 --name fuzzing-ready
```

**3. Validate before using**:
```bash
# Always validate before starting fuzzing campaign
./fawkes-snapshot validate --disk disk.qcow2 --name fuzzing-ready
```

### Naming Snapshots

Use descriptive names that indicate:
- **Purpose**: `fuzzing-ready`, `pre-fuzzing`, `with-symbols`
- **Version**: `v1.0-fuzzing`, `v2.0-patched`
- **Configuration**: `gcc-asan`, `debug-build`, `release-build`
- **Date**: `2025-11-15-ready`, `baseline-20251115`

**Good names**:
- `fuzzing-ready`
- `nginx-1.18.0-asan`
- `baseline-2025-11-15`
- `with-debug-symbols`

**Bad names**:
- `snapshot1`
- `test`
- `asdf`
- `final-final-v2-new`

### Managing Multiple Snapshots

```bash
# List all snapshots
./fawkes-snapshot list --disk disk.qcow2

# Keep snapshots organized:
# - fuzzing-ready: Current production snapshot
# - baseline-YYYY-MM-DD: Historical baselines
# - debug-*: Debug/development snapshots
# - test-*: Testing snapshots (can be deleted)

# Clean up old snapshots
./fawkes-snapshot delete --disk disk.qcow2 --name old-snapshot --force
```

### Performance Considerations

**Snapshot Size**:
- Typical snapshot: 100-200 MB (depending on RAM allocation)
- More RAM = larger snapshots
- Larger snapshots = slower restore times
- Balance: Use minimal RAM needed for target

**Snapshot Creation Time**:
- Creating snapshot: 5-10 seconds
- Validation: 30-60 seconds
- Total time: ~1 minute per snapshot

**Disk Space**:
- Multiple snapshots increase disk image size
- Monitor disk usage: `du -h disk.qcow2`
- Clean up unused snapshots regularly

### Snapshot Lifecycle

```
1. CREATE (Development)
   └─> Set up VM with target and agent
   └─> Test everything works
   └─> Create snapshot with validation

2. VALIDATE (Pre-Production)
   └─> Run validation checks
   └─> Test with small fuzzing run
   └─> Verify agent responds correctly

3. USE (Production)
   └─> Run fuzzing campaigns
   └─> Monitor for issues
   └─> Keep snapshot unchanged

4. UPDATE (Maintenance)
   └─> If target changes: Create new snapshot
   └─> If agent updates: Create new snapshot
   └─> Keep old snapshot as backup

5. ARCHIVE/DELETE (Cleanup)
   └─> Delete old snapshots
   └─> Keep baseline snapshots for reference
```

## Troubleshooting

### Common Issues

#### Issue: "Not a QCOW2 image"

**Symptoms**:
```
ERROR: Not a QCOW2 image: disk.img
```

**Cause**: Disk image is not in QCOW2 format

**Solution**:
```bash
# Check image format
qemu-img info disk.img

# Convert to QCOW2
qemu-img convert -f raw -O qcow2 disk.img disk.qcow2

# Use converted image
./fawkes-snapshot list --disk disk.qcow2
```

#### Issue: "Snapshot is disk-only (no VM state)"

**Symptoms**:
```
ERROR: ✗ Snapshot 'name' is disk-only (no VM state)
ERROR:    This snapshot cannot be loaded with -loadvm
```

**Cause**: Snapshot was created with `qemu-img snapshot -c` instead of QEMU monitor `savevm`

**Solution**:
```bash
# Delete bad snapshot
./fawkes-snapshot delete --disk disk.qcow2 --name bad-snapshot --force

# Create proper snapshot (boots VM)
./fawkes-snapshot create --disk disk.qcow2 --name good-snapshot
```

**Manual fix** (if you want to create it yourself):
```bash
# Boot VM with monitor
qemu-system-x86_64 -drive file=disk.qcow2,format=qcow2 \
  -m 512M \
  -monitor stdio

# In QEMU monitor (Ctrl+Alt+2 or stdio):
(qemu) savevm good-snapshot
(qemu) quit

# Verify
./fawkes-snapshot validate --disk disk.qcow2 --name good-snapshot
```

#### Issue: "Fawkes agent is not responding"

**Symptoms**:
```
WARNING: ⚠ Fawkes agent is not responding
WARNING:    The VM may not have the agent installed or configured
```

**Cause**: Agent not installed, not running, or not configured correctly

**Solution**:

1. **Check if agent is installed in VM**:
```bash
# Boot VM manually
qemu-system-x86_64 -drive file=disk.qcow2,format=qcow2 -m 512M

# Inside VM, check:
ps aux | grep fawkes-agent
netstat -tlnp | grep 9999
```

2. **Install/configure agent**:
```bash
# Inside VM:
# Install agent (see Fawkes agent documentation)
# Configure to auto-start
# Test: python3 fawkes-agent.py
```

3. **Create new snapshot**:
```bash
./fawkes-snapshot create --disk disk.qcow2 --name fuzzing-ready
```

4. **Or skip agent check** (if you'll install agent later):
```bash
./fawkes-snapshot validate --disk disk.qcow2 --name test --no-agent-check
```

#### Issue: "VM failed to start"

**Symptoms**:
```
ERROR: VM failed to start: ...
```

**Causes and Solutions**:

**1. Insufficient permissions**:
```bash
# Check KVM permissions (Linux)
ls -l /dev/kvm
sudo usermod -a -G kvm $USER
# Log out and back in
```

**2. QEMU not installed**:
```bash
# Install QEMU
sudo apt-get install qemu-system-x86  # Ubuntu/Debian
brew install qemu                      # macOS
```

**3. Disk image corrupted**:
```bash
# Check and repair image
qemu-img check disk.qcow2
qemu-img check -r all disk.qcow2  # Repair if needed
```

**4. Insufficient RAM**:
```bash
# Check available memory
free -h

# Use smaller memory allocation
# (modify snapshot creation to use less RAM if possible)
```

#### Issue: "Snapshot creation timeout"

**Symptoms**:
```
ERROR: Snapshot creation timed out after 60 seconds
```

**Cause**: VM takes too long to boot

**Solution**:
```bash
# Increase timeout
./fawkes-snapshot create --disk disk.qcow2 --name test --timeout 120

# Or create manually
qemu-system-x86_64 -drive file=disk.qcow2,format=qcow2 \
  -m 512M -monitor stdio
(qemu) savevm test
(qemu) quit
```

#### Issue: "Connection refused" during agent check

**Symptoms**:
```
DEBUG: Agent did not respond within timeout
WARNING: ⚠ Fawkes agent is not responding
```

**Causes**:
1. Agent not started yet (VM still booting)
2. Agent crashed
3. Wrong port (not 9999)
4. Firewall blocking connection

**Solutions**:
```bash
# Increase agent timeout
./fawkes-snapshot validate --disk disk.qcow2 --name test --timeout 60

# Check agent manually
qemu-system-x86_64 -drive file=disk.qcow2,format=qcow2,snapshot=on \
  -loadvm test \
  -net user,hostfwd=tcp::9999-:9999 -net nic

# Try connecting
nc -v localhost 9999
echo '{"type":"ping"}' | nc localhost 9999
```

### Debugging Tips

**Enable verbose logging**:
```bash
./fawkes-snapshot validate --disk disk.qcow2 --name test -v
```

**Test snapshot load manually**:
```bash
# Try loading snapshot directly with QEMU
qemu-system-x86_64 \
  -drive file=disk.qcow2,format=qcow2,snapshot=on \
  -loadvm fuzzing-ready \
  -m 512M

# If this fails, snapshot is broken
# If this works, issue is with validation script
```

**Check QEMU stderr**:
```bash
# Run QEMU with stderr output
qemu-system-x86_64 \
  -drive file=disk.qcow2,format=qcow2 \
  -loadvm fuzzing-ready \
  -m 512M \
  2>&1 | tee qemu-error.log

# Check for errors in qemu-error.log
```

**Verify snapshot with qemu-img**:
```bash
# Get detailed snapshot info
qemu-img snapshot -l disk.qcow2

# Check disk image integrity
qemu-img check disk.qcow2

# Get full image info
qemu-img info disk.qcow2
```

## Advanced Usage

### Scripted Snapshot Creation

Create snapshots in automated workflows:

```bash
#!/bin/bash
# create-fuzzing-snapshot.sh

set -e

DISK="$1"
SNAPSHOT_NAME="$2"

if [ -z "$DISK" ] || [ -z "$SNAPSHOT_NAME" ]; then
    echo "Usage: $0 <disk.qcow2> <snapshot-name>"
    exit 1
fi

echo "Creating snapshot '$SNAPSHOT_NAME' for $DISK..."

# Create snapshot
./fawkes-snapshot create \
    --disk "$DISK" \
    --name "$SNAPSHOT_NAME" \
    --timeout 120 \
    --force

# Validate
./fawkes-snapshot validate \
    --disk "$DISK" \
    --name "$SNAPSHOT_NAME" \
    --timeout 60

echo "Snapshot '$SNAPSHOT_NAME' is ready for fuzzing!"
```

### Snapshot Management Script

Manage multiple snapshots:

```bash
#!/bin/bash
# manage-snapshots.sh

DISK="disk.qcow2"

# List all snapshots
echo "Current snapshots:"
./fawkes-snapshot list --disk "$DISK"

# Delete old test snapshots
echo -e "\nCleaning up old test snapshots..."
for snap in $(./fawkes-snapshot list --disk "$DISK" | grep "^[0-9]" | grep "test-" | awk '{print $2}'); do
    echo "Deleting $snap..."
    ./fawkes-snapshot delete --disk "$DISK" --name "$snap" --force
done

# Create new baseline
DATE=$(date +%Y-%m-%d)
echo -e "\nCreating new baseline snapshot..."
./fawkes-snapshot create --disk "$DISK" --name "baseline-$DATE" --force

echo -e "\nDone!"
./fawkes-snapshot list --disk "$DISK"
```

### CI/CD Integration

Integrate snapshot validation in CI pipeline:

```yaml
# .gitlab-ci.yml
validate-snapshot:
  stage: test
  script:
    - ./fawkes-snapshot validate --disk images/fuzzing.qcow2 --name fuzzing-ready
  allow_failure: false
```

```yaml
# .github/workflows/validate.yml
name: Validate Fuzzing Snapshot
on: [push]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install QEMU
        run: sudo apt-get install -y qemu-system-x86
      - name: Validate Snapshot
        run: ./fawkes-snapshot validate --disk images/fuzzing.qcow2 --name fuzzing-ready
```

### Batch Operations

Operate on multiple disk images:

```bash
#!/bin/bash
# validate-all-snapshots.sh

for disk in images/*.qcow2; do
    echo "Validating snapshots in $disk..."
    ./fawkes-snapshot list --disk "$disk"

    # Validate each snapshot
    for snap in $(./fawkes-snapshot list --disk "$disk" | grep "^[0-9]" | awk '{print $2}'); do
        echo "  Validating $snap..."
        if ./fawkes-snapshot validate --disk "$disk" --name "$snap" --no-agent-check; then
            echo "  ✓ $snap is valid"
        else
            echo "  ✗ $snap is invalid"
        fi
    done
    echo ""
done
```

### Custom Validation

Create custom validation with additional checks:

```bash
#!/bin/bash
# custom-validate.sh

DISK="$1"
SNAPSHOT="$2"

# Standard validation
./fawkes-snapshot validate --disk "$DISK" --name "$SNAPSHOT" || exit 1

# Additional custom checks
echo "Running custom validation checks..."

# Check disk image size
SIZE=$(du -m "$DISK" | cut -f1)
if [ "$SIZE" -gt 50000 ]; then
    echo "WARNING: Disk image is very large ($SIZE MB)"
fi

# Check snapshot age
CREATED=$(./fawkes-snapshot list --disk "$DISK" | grep "$SNAPSHOT" | awk '{print $4" "$5}')
AGE_DAYS=$(( ($(date +%s) - $(date -d "$CREATED" +%s)) / 86400 ))

if [ "$AGE_DAYS" -gt 30 ]; then
    echo "WARNING: Snapshot is $AGE_DAYS days old, consider refreshing"
fi

echo "✓ All custom checks passed"
```

## Integration with Fawkes

### Using Snapshots in Config

```yaml
# fawkes-config.yaml
disk: /path/to/disk.qcow2
snapshot_name: fuzzing-ready  # Load this snapshot
memory: 512M
arch: x86_64
target: /usr/bin/target
```

### Recommended Workflow

```
1. Prepare VM
   └─> Install OS and dependencies
   └─> Install Fawkes agent
   └─> Install target binary
   └─> Configure environment

2. Create baseline snapshot
   └─> ./fawkes-snapshot create --disk disk.qcow2 --name baseline-v1

3. Create fuzzing snapshot
   └─> Start VM from baseline
   └─> Final tweaks and optimizations
   └─> ./fawkes-snapshot create --disk disk.qcow2 --name fuzzing-ready

4. Validate snapshot
   └─> ./fawkes-snapshot validate --disk disk.qcow2 --name fuzzing-ready

5. Start fuzzing
   └─> ./fawkes --config fawkes-config.yaml

6. Monitor and iterate
   └─> If issues: Fix VM and create new snapshot
   └─> If target changes: Create new snapshot with version tag
```

### Multiple Targets

Manage snapshots for different targets:

```
disk-nginx.qcow2
├── baseline-2025-11-15    (Clean Ubuntu + agent)
├── nginx-1.18.0           (nginx 1.18.0 installed)
└── nginx-1.20.0-asan      (nginx 1.20.0 with ASAN)

disk-apache.qcow2
├── baseline-2025-11-15    (Clean Ubuntu + agent)
├── apache-2.4.46          (apache 2.4.46 installed)
└── apache-2.4.48-debug    (apache 2.4.48 with debug symbols)
```

```bash
# Validate all fuzzing snapshots
./fawkes-snapshot validate --disk disk-nginx.qcow2 --name nginx-1.20.0-asan
./fawkes-snapshot validate --disk disk-apache.qcow2 --name apache-2.4.48-debug
```

## Summary

The `fawkes-snapshot` tool provides comprehensive snapshot management for Fawkes fuzzing:

✓ **List** snapshots with detailed information
✓ **Create** snapshots with automatic validation
✓ **Delete** snapshots safely with confirmation
✓ **Validate** snapshots for fuzzing readiness

**Key Points**:
- Always use full VM snapshots (not disk-only)
- Validate snapshots before fuzzing
- Use descriptive snapshot names
- Clean up old snapshots regularly
- Keep baseline snapshots for reference

For more information, see:
- Main Fawkes documentation: `README.md`
- Agent setup guide: `docs/AGENT_SETUP.md`
- Fuzzing guide: `docs/FUZZING_GUIDE.md`
