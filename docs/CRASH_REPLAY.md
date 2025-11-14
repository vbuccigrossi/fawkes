# Fawkes Crash Replay System

Reproduce any crash with a single command, with optional GDB debugging support.

## Quick Start

```bash
# Replay from database
./replay.py --crash-id 123

# Replay from crash archive
./replay.py --crash-zip crashes/unique/crash_20250114_123456.zip

# Replay with automatic GDB attachment
./replay.py --crash-id 123 --attach-gdb

# Non-interactive mode (for automation)
./replay.py --crash-id 123 --non-interactive
```

## Features

### 🎯 Core Features
- **One-command reproduction** - Restore exact crash conditions
- **Database integration** - Load crashes from SQLite database
- **Archive support** - Load from crash zip files
- **GDB debugging** - Automatic or manual debugger attachment
- **Interactive mode** - Step-by-step confirmation
- **Automated mode** - For CI/CD and scripts

### 🔍 What Gets Reproduced
1. **VM State** - Restores to exact snapshot
2. **Testcase** - Places crashing input in share directory
3. **Crash Detection** - Monitors for crash reproduction
4. **Debug Context** - Full GDB access to crashed state

## Usage Examples

### Basic Crash Replay

```bash
# List crashes in database
sqlite3 ~/.fawkes/fawkes.db "SELECT crash_id, crash_type, exploitability FROM crashes"

# Replay specific crash
./replay.py --crash-id 42
```

Output:
```
============================================================
CRASH REPLAY
============================================================

Crash Details:
------------------------------------------------------------
Crash ID: 42
Type: user
Exploitability: High
Details: PID=1234, EXE=target.exe, Exception=0xc0000005
Signature: a3f5d2e9...
Duplicates: 3
Discovered: 2025-01-14 10:23:45
------------------------------------------------------------

Using disk image: ~/fawkes_test/Windows10.qcow2
Using snapshot: clean

Proceed with crash replay? [Y/n]: y

Copying disk image (this may take a moment)...
Testcase copied to share: /tmp/fawkes_replay_vm_12345/share/crash_testcase.bin
Starting VM...
VM started (ID: 1)
Monitoring for crash...

============================================================
CRASH REPRODUCED!
============================================================
Crash Type: user
PID: 1234
EXE: C:\Users\test\target.exe
Exception: 0xc0000005
```

### Replay with GDB

```bash
./replay.py --crash-id 42 --attach-gdb
```

The system will:
1. Start the VM in paused state
2. Show GDB connection details
3. Optionally launch GDB automatically
4. Connect to VM for interactive debugging

```
============================================================
GDB DEBUGGING SESSION
============================================================
VM is paused and waiting for GDB
Debug port: 1234
Testcase: /tmp/fawkes_replay_vm_12345/share/crash_testcase.bin

To attach GDB manually:
  gdb
  (gdb) target remote localhost:1234
  (gdb) continue

Launch GDB automatically? [Y/n]: y

Launching GDB...

====================================
Fawkes Crash Replay - GDB Session
====================================
VM is paused. Use 'continue' to run.

(gdb)
```

### Replay from Crash Archive

```bash
# Find crash archives
ls -lh crashes/unique/

# Replay from zip
./replay.py --crash-zip crashes/unique/crash_20250114_123456_exploitability_High.zip
```

This is useful when:
- Sharing crashes with team members
- Analyzing crashes from different machines
- Long-term crash archival

### Automated Replay

```bash
# Non-interactive replay for automation
./replay.py --crash-id 42 --non-interactive --timeout 120
echo $?  # Exit code: 0 = reproduced, 1 = failed
```

Use in scripts:
```bash
#!/bin/bash
# Verify all high-severity crashes still reproduce

for crash_id in $(sqlite3 ~/.fawkes/fawkes.db \
    "SELECT crash_id FROM crashes WHERE exploitability='High'"); do

    echo "Testing crash $crash_id..."
    if ./replay.py --crash-id $crash_id --non-interactive; then
        echo "✓ Crash $crash_id reproduces"
    else
        echo "✗ Crash $crash_id does NOT reproduce!"
    fi
done
```

## Command Line Options

### Required (one of):
- `--crash-id ID` - Crash ID from database
- `--crash-zip PATH` - Path to crash archive zip

### Optional:
- `--attach-gdb` - Attach GDB for debugging (default: false)
- `--non-interactive` - Skip user prompts (default: false, interactive)
- `--disk-image PATH` - Override disk image path
- `--snapshot NAME` - Override snapshot name
- `--timeout SECONDS` - Crash detection timeout (default: 60)
- `--log-level LEVEL` - Logging level: DEBUG/INFO/WARNING/ERROR

## GDB Debugging Tips

Once in GDB session:

```gdb
# Continue execution to trigger crash
(gdb) continue

# After crash, examine state
(gdb) info registers
(gdb) backtrace
(gdb) x/10i $pc  # Examine instructions at crash point

# Examine memory
(gdb) x/100x $rsp  # Stack contents
(gdb) x/s $rdi     # String at register

# Set breakpoints before crash
(gdb) break *0x401234
(gdb) continue

# Step through execution
(gdb) stepi
(gdb) nexti
```

## Architecture

### Crash Data Sources

#### Database Format
```sql
crashes (
    crash_id INTEGER PRIMARY KEY,
    job_id INTEGER,
    testcase_path TEXT,
    crash_type TEXT,
    details TEXT,
    signature TEXT,
    exploitability TEXT,
    crash_file TEXT,
    timestamp INTEGER,
    duplicate_count INTEGER
)
```

#### Zip Archive Format
```
crash_20250114_123456.zip
├── testcase/
│   └── crash_testcase.bin
├── crash_info.json  (or crash_info.txt)
└── shared/
    └── ... (files from share directory)
```

### Replay Process

1. **Load Crash Data**
   - From database OR zip file
   - Extract testcase
   - Get VM configuration

2. **Prepare Environment**
   - Create temporary disk copy
   - Create share directory
   - Copy testcase to share

3. **Start VM**
   - Load snapshot
   - Attach debugger (optional)
   - Pause on start (if GDB mode)

4. **Monitor Execution**
   - Wait for crash
   - Capture crash details
   - Or provide interactive debugging

5. **Cleanup**
   - Stop VM
   - Remove temporary files
   - Display results

## Troubleshooting

### Crash Does Not Reproduce

**Possible Causes:**
1. **Timing-dependent** - Crash depends on specific timing/race conditions
2. **State mismatch** - Snapshot state differs from original
3. **Timeout too short** - Increase with `--timeout 300`
4. **Environment difference** - Check VM configuration matches original

**Solutions:**
```bash
# Try longer timeout
./replay.py --crash-id 42 --timeout 300

# Check crash details
sqlite3 ~/.fawkes/fawkes.db \
    "SELECT * FROM crashes WHERE crash_id=42"

# Verify snapshot exists
qemu-img snapshot -l ~/fawkes_test/Windows10.qcow2
```

### GDB Won't Connect

**Check:**
1. GDB is installed: `which gdb`
2. Debug port is free: `netstat -tuln | grep <port>`
3. QEMU started correctly (check logs)

**Manual connection:**
```bash
# Find debug port
cat /tmp/fawkes_replay_registry_*.json

# Connect manually
gdb
(gdb) target remote localhost:<port>
```

### Testcase Not Found

**If replaying from database:**
- Testcase file may have been moved/deleted
- Check: `SELECT testcase_path FROM crashes WHERE crash_id=42`

**If replaying from zip:**
- Verify zip contains `testcase/` directory
- Check: `unzip -l crash.zip`

## Integration with Fuzzing Workflow

### 1. During Fuzzing
Crashes are automatically detected and stored:
```python
# In harness.py
if gdb_worker.crash_detected:
    self._handle_crash(gdb_worker.crash_info, testcase_path, job_id)
```

### 2. Triage Phase
Review and prioritize crashes:
```bash
# List high-severity crashes
sqlite3 ~/.fawkes/fawkes.db \
    "SELECT crash_id, crash_type, exploitability, timestamp
     FROM crashes
     WHERE exploitability IN ('High', 'Critical')
     ORDER BY timestamp DESC"
```

### 3. Replay Phase
Reproduce for debugging:
```bash
./replay.py --crash-id <id> --attach-gdb
```

### 4. Fix Phase
- Debug with GDB
- Identify root cause
- Develop patch

### 5. Verification Phase
Confirm fix:
```bash
# After patching, replay should NOT crash
./replay.py --crash-id <id> --non-interactive
```

## Best Practices

### 1. Always Verify Crashes
```bash
# Before spending time debugging, verify it reproduces
./replay.py --crash-id 42 --non-interactive
```

### 2. Save Crash Archives
```bash
# Export crashes for long-term storage
mkdir crash_backups
cp crashes/unique/*.zip crash_backups/
```

### 3. Use Interactive Mode for First Replay
```bash
# See what's happening, confirm settings
./replay.py --crash-id 42
# Then use non-interactive for subsequent replays
```

### 4. Increase Timeout for Complex Crashes
```bash
# Some crashes take time to trigger
./replay.py --crash-id 42 --timeout 300
```

### 5. Keep Snapshots Clean
```bash
# Ensure snapshot is in known-good state
# Bad snapshot = unreliable crash reproduction
```

## Performance Notes

- **Disk copying** - First step copies VM disk (can take 30-60 seconds for large images)
- **VM startup** - Typically 5-10 seconds
- **Crash detection** - Depends on timeout setting
- **Total time** - Usually 1-3 minutes per replay

## Exit Codes

- `0` - Success (crash reproduced)
- `1` - Failure (crash not reproduced or error)
- `130` - Interrupted by user (Ctrl+C)

## See Also

- [Crash Analysis](CRASH_ANALYSIS.md) - Analyzing crash exploitability
- [GDB Guide](GDB_GUIDE.md) - Advanced GDB debugging techniques
- [Fuzzing Guide](FUZZING_GUIDE.md) - Complete fuzzing workflow
