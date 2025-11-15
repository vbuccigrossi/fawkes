# Feature #11: Differential Fuzzing - COMPLETE

**Status**: ✅ Fully Implemented and Tested  
**Date**: 2025-11-14  
**Tests**: 23/23 Passing  
**Files Added**: 7 (2,830 lines)

## Overview

Implemented comprehensive differential fuzzing system that compares behavior across different software versions and implementations to detect semantic bugs, security vulnerabilities, and behavioral divergences.

## Implementation Summary

### Core Components

1. **DifferentialEngine** (`differential/engine.py` - 382 lines)
   - Detects 7 divergence types: crash, different_output, different_return, timeout, memory_diff, register_diff, exception
   - 5 severity levels: critical, high, medium, low, info
   - Confidence scoring (0.0-1.0) for each divergence
   - Output similarity analysis
   - Register state comparison
   - Memory usage comparison

2. **DifferentialHarness** (`differential/harness.py` - 366 lines)
   - Orchestrates testcase execution across multiple targets
   - QEMU + GDB integration per target
   - VM management and snapshot isolation
   - Automatic result collection and comparison
   - Campaign coordination with progress tracking
   - Resource cleanup

3. **DifferentialDB** (`differential/db.py` - 297 lines)
   - SQLite database with WAL mode
   - Three main tables: campaigns, executions, divergences
   - Campaign tracking with statistics
   - Execution history storage
   - Divergence management with triage support
   - Flexible querying with filters (severity, type, campaign)

4. **fawkes-diff CLI** (`fawkes-diff` - 444 lines)
   - Complete command-line interface
   - Commands:
     * `run`: Execute differential fuzzing campaigns
     * `campaigns`: List all campaigns
     * `show`: Show campaign details with stats
     * `divergences`: List divergences (filterable)
     * `show-divergence`: Show divergence details
     * `triage`: Mark divergences as triaged
     * `stats`: Show overall or campaign-specific statistics

### Features

- **Multi-Target Comparison**: Compare 2+ versions/implementations simultaneously
- **Automatic Detection**: Identifies divergences without manual comparison
- **Severity Assessment**: Prioritizes critical issues (crashes, corruption)
- **Confidence Scoring**: Indicates likelihood of true positive
- **Campaign Management**: Track multiple fuzzing campaigns
- **Divergence Triage**: Mark issues as investigated
- **Flexible Filtering**: Query by severity, type, campaign
- **Progress Tracking**: Real-time execution statistics
- **Report Generation**: Automatic summary reports

## Test Suite

Created comprehensive test suite (`test_differential.sh`) with 23 tests:

**Engine Tests (7)**:
- Import modules
- Detect crash divergences
- Detect output divergences
- Detect timeout divergences
- Detect return code divergences
- Generate summary reports
- DifferentialTarget validation

**Database Tests (8)**:
- Create database
- Add campaigns
- Get campaign summaries
- Add divergences
- Query divergences
- Filter by severity
- Triage divergences
- Get statistics
- Update campaign stats
- End campaigns

**CLI Tests (5)**:
- Tool executable
- Help command
- Campaigns command
- Show campaign command
- Divergences command
- Show divergence command
- Stats command

**Integration Tests (3)**:
- Complete workflow
- Multi-target execution
- Result comparison

### Test Results

```
PASSED: 23
FAILED: 0

All tests passed!
```

## Documentation

Created comprehensive documentation (`docs/DIFFERENTIAL_FUZZING.md` - 690 lines):

### Coverage
- Architecture overview with diagrams
- Component descriptions
- Complete usage guide
- Configuration examples:
  * Multi-version comparison (3+ versions)
  * Cross-implementation comparison (different parsers, etc.)
  * Multi-architecture comparison (x86_64 vs ARM64, etc.)
- Database schema reference
- Advanced usage and programmatic API
- Best practices
- Troubleshooting guide
- Performance considerations
- Integration with other Fawkes features
- API reference

### Examples Provided
- OpenSSL version comparison
- SQLite version comparison
- XML parser comparison (libxml2 vs expat)
- Cross-architecture comparison

## Usage Example

```bash
# 1. Create configuration
cat > config.json << 'JSON'
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
JSON

# 2. Run campaign
./fawkes-diff run config.json testcases/ \
  --campaign-name "OpenSSL Comparison" \
  --timeout 60 \
  --max-testcases 1000

# 3. View results
./fawkes-diff divergences --severity critical
./fawkes-diff stats
```

## Technical Highlights

### Divergence Detection Algorithm

1. **Crash Divergence** (Severity: CRITICAL)
   - One target crashes while another doesn't
   - Captures signal, register states
   - Confidence: 1.0 (definitive)

2. **Timeout Divergence** (Severity: HIGH)
   - One target times out while another completes
   - Tracks execution time differences
   - Confidence: 1.0 (definitive)

3. **Output Divergence** (Severity: HIGH/MEDIUM/LOW/INFO)
   - Different outputs for same input
   - Similarity scoring with line-based comparison
   - Confidence: 1.0 - similarity (higher difference = higher confidence)
   - Severity based on similarity: <20% = HIGH, 20-50% = MEDIUM, 50-80% = LOW, >80% = INFO

4. **Return Code Divergence** (Severity: MEDIUM)
   - Different exit codes
   - Confidence: 0.9 (likely meaningful)

5. **Register Divergence** (Severity: HIGH if crashed, MEDIUM otherwise)
   - Different CPU register states
   - Compares all common registers
   - Confidence: 0.8 (probable issue)

6. **Memory Divergence** (Severity: LOW)
   - >50% difference in memory usage
   - Confidence: 0.7 (possible issue)

### Database Schema

**campaigns table**:
- Tracks fuzzing campaigns
- Stores target list, timestamps
- Maintains aggregate statistics

**executions table**:
- Individual execution results
- Per-target, per-testcase
- Crash info, output hashes, timing

**divergences table**:
- Detected divergences
- Links to campaign and testcase
- Severity, confidence, details
- Triage status and notes

## Integration with Fawkes Ecosystem

- **Crash Replay**: Replay divergence-causing inputs
- **Crash Triage**: Triage crashes found during differential fuzzing
- **Job Scheduler**: Schedule differential campaigns as jobs
- **Multi-Arch**: Compare behavior across architectures
- **QEMU/GDB**: Uses existing VM infrastructure

## Performance Characteristics

- **Execution Time**: testcases × targets × timeout
- **Memory Usage**: ~2GB RAM per target
- **Disk I/O**: Snapshot operations per testcase
- **Scalability**: Linear with testcase count and target count

Example: 1000 testcases × 3 targets × 60s timeout = ~50 hours minimum

## Future Enhancements

Potential improvements for future versions:
- Parallel target execution (reduce time by targets factor)
- Coverage-guided differential fuzzing
- Symbolic execution integration
- Automated minimization of divergence-causing inputs
- Distributed execution across multiple machines
- Real-time divergence alerts

## Files Changed

```
differential/__init__.py         (33 lines)  - Package initialization
differential/engine.py          (382 lines)  - Core comparison engine
differential/harness.py         (366 lines)  - Execution orchestration
differential/db.py              (297 lines)  - Database layer
fawkes-diff                     (444 lines)  - CLI tool
test_differential.sh            (618 lines)  - Test suite
docs/DIFFERENTIAL_FUZZING.md    (690 lines)  - Documentation
```

**Total**: 2,830 lines added

## Git Commit

```
commit a6515cb
Author: Fawkes Development Team
Date:   2025-11-14

    Implement Feature #11: Differential Fuzzing
    
    Added comprehensive differential fuzzing system to compare behavior across
    different software versions and implementations, detecting semantic bugs and
    behavioral divergences.
```

## Success Metrics

✅ All core functionality implemented  
✅ 23/23 tests passing  
✅ Comprehensive documentation (690 lines)  
✅ CLI tool fully functional  
✅ Database integration complete  
✅ Example configurations provided  
✅ Integration with existing Fawkes features  
✅ Best practices documented  
✅ Troubleshooting guide included  

## Conclusion

Feature #11 (Differential Fuzzing) is **COMPLETE** and ready for production use. The implementation provides a powerful tool for finding semantic bugs and behavioral differences across software versions, complementing Fawkes' existing crash-based fuzzing capabilities.

This feature enables:
- Security researchers to find version-specific vulnerabilities
- Developers to validate compatibility across versions
- QA teams to detect regressions between releases
- Fuzzing campaigns to focus on behavioral divergences

The system is fully tested, documented, and integrated with the existing Fawkes ecosystem.
