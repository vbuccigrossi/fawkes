# Fawkes Automated Crash Triage

Advanced crash analysis system that automatically triages crashes, scores exploitability, and generates comprehensive reports.

## Features

### 🧠 Enhanced Analysis
- **Stack Hash Deduplication** - Sophisticated deduplication beyond simple signatures
- **Exploitability Scoring** - 0-100 score based on multiple indicators
- **Vulnerability Detection** - Automatic pattern matching for common bug classes
- **Root Cause Analysis** - Identify likely source of bugs
- **Severity Assessment** - Critical/High/Medium/Low/Info classification

### 🔍 Vulnerability Types Detected
- Buffer Overflow (Stack/Heap)
- Use-After-Free
- Double Free
- Null Pointer Dereference
- Integer Overflow
- Format String
- Race Conditions
- Type Confusion
- Program Counter Control
- Arbitrary Write/Read

### 📊 Report Generation
- **Text Reports** - Human-readable analysis
- **JSON Reports** - Machine-parseable data
- **Markdown Reports** - Documentation-ready
- **Summary Reports** - Aggregate analysis across multiple crashes

---

## Quick Start

### Analyze Single Crash
```bash
# From crash zip file
./fawkes-triage --crash-zip crashes/unique/crash_20250114_123456.zip

# From database
./fawkes-triage --crash-id 42

# Generate specific formats
./fawkes-triage --crash-zip crash.zip --text --json --markdown
```

### Analyze Directory of Crashes
```bash
# Analyze all crashes in directory
./fawkes-triage --directory crashes/unique/

# Filter by severity
./fawkes-triage --directory crashes/ --min-severity HIGH

# Filter by exploitability score
./fawkes-triage --directory crashes/ --min-score 70
```

### Output
Reports are saved to `~/.fawkes/reports/` by default:
```
~/.fawkes/reports/
├── crash_report_abc123_20250114_123456.txt
├── crash_report_abc123_20250114_123456.json
├── crash_report_abc123_20250114_123456.md
└── crash_summary_25_crashes.txt
```

---

## Understanding the Analysis

### Exploitability Score (0-100)

**Critical (70-100)**:
- Full program counter control
- Arbitrary write capability
- Return address overwrite
- ROP chains possible

**High (50-69)**:
- Partial control flow influence
- Stack corruption detected
- Heap metadata corruption
- Controlled data writes

**Medium (30-49)**:
- Memory corruption without clear exploit path
- Limited data control
- Information leaks

**Low (10-29)**:
- Null pointer dereferences
- Assertion failures
- Crashes without corruption

**Info (0-9)**:
- Expected errors
- Configuration issues

### Severity Levels

**Critical**: Immediate action required
- Active exploitation likely
- Remote code execution possible
- Data corruption/exfiltration risk

**High**: Priority fix needed
- Local privilege escalation possible
- Denial of service trivial
- Security boundary bypass

**Medium**: Standard fix process
- Requires specific conditions
- Limited impact
- Defense-in-depth concern

**Low**: Track and monitor
- Unlikely to be exploitable
- Requires extensive setup
- Edge case scenarios

**Info**: Documentation only
- Not a security issue
- Configuration problem
- Expected behavior

---

## Example Reports

### Text Report Sample
```
================================================================================
FAWKES CRASH TRIAGE REPORT
================================================================================

Crash ID: crash_20250114_123456.zip
Generated: 2025-01-14 14:30:22
Signature: a3f5d2e91c8b...
Stack Hash: 8f4c2a1b

================================================================================
SEVERITY ASSESSMENT
================================================================================

Severity: Critical
Exploitability Score: 85/100
Confidence: 92.3%

================================================================================
VULNERABILITY CLASSIFICATION
================================================================================

Type: Buffer Overflow
Class: Control Flow Hijack
Control Flow Hijack: YES
Memory Corruption: YES
Controlled Data: YES

================================================================================
EXPLOIT INDICATORS
================================================================================

  • PC Control (pattern-based)
  • Stack Corruption
  • Return Address Overwrite

================================================================================
STACK TRACE
================================================================================

  #0: vulnerable_function
  #1: process_input
  #2: main

================================================================================
ROOT CAUSE ANALYSIS
================================================================================

Unsafe string function usage (strcpy/sprintf)

================================================================================
SUGGESTED FIX
================================================================================

Use bounds-checked functions (strncpy, snprintf) and validate buffer sizes

================================================================================
RECOMMENDATIONS
================================================================================

⚠️  CRITICAL: Immediate action required!
  1. Isolate affected systems
  2. Verify exploitability with POC
  3. Develop and test fix immediately
  4. Consider emergency patch release
```

### JSON Report Sample
```json
{
  "generated": "2025-01-14T14:30:22",
  "crash_analysis": {
    "crash_id": "crash_20250114_123456.zip",
    "signature": "a3f5d2e91c8b...",
    "stack_hash": "8f4c2a1b",
    "severity": "Critical",
    "exploitability_score": 85,
    "vuln_type": "Buffer Overflow",
    "control_flow_hijack": true,
    "memory_corruption": true,
    "indicators": [
      "PC Control (pattern-based)",
      "Stack Corruption"
    ],
    "root_cause": "Unsafe string function usage",
    "suggested_fix": "Use bounds-checked functions"
  }
}
```

---

## Integration with Fuzzing Workflow

### 1. During Fuzzing
Crashes are automatically detected and stored by Fawkes.

### 2. Automated Triage
Run triage on all discovered crashes:
```bash
./fawkes-triage --directory ~/.fawkes/crashes/unique/
```

### 3. Review Reports
Check generated reports:
```bash
ls -lh ~/.fawkes/reports/
cat ~/.fawkes/reports/crash_summary_*.txt
```

### 4. Prioritize Fixes
Focus on Critical/High severity crashes first:
```bash
./fawkes-triage --directory crashes/ --min-severity CRITICAL --text
```

### 5. Replay and Debug
Use crash replay for detailed investigation:
```bash
./fawkes-replay --crash-id 42 --attach-gdb
```

---

## Advanced Usage

### Custom Report Directory
```bash
./fawkes-triage --crash-zip crash.zip --report-dir /tmp/my_reports
```

### Quiet Mode (No Console Output)
```bash
./fawkes-triage --crash-zip crash.zip --quiet
```

### Debug Logging
```bash
./fawkes-triage --crash-zip crash.zip --log-level DEBUG
```

### Batch Processing with Filtering
```bash
# Find all critical crashes
./fawkes-triage --directory crashes/ \
    --min-severity CRITICAL \
    --json \
    --quiet > critical_crashes.log

# Find all crashes with high exploitability
./fawkes-triage --directory crashes/ \
    --min-score 70 \
    --markdown \
    --report-dir high_priority/
```

### Integration with CI/CD
```bash
#!/bin/bash
# Fail build if critical crashes found

./fawkes-triage --directory crashes/ --min-severity CRITICAL --quiet

if [ $? -eq 0 ]; then
    echo "CRITICAL vulnerabilities found! Build failed."
    exit 1
fi
```

---

## Customization

### Adding Vulnerability Patterns

Edit `analysis/enhanced_triage.py`:

```python
def _init_vuln_patterns(self):
    return {
        VulnType.MY_VULN: [
            {
                'pattern': r'my_pattern|my_error',
                'weight': 0.9,
                'desc': 'My custom vulnerability'
            }
        ]
    }
```

### Adding Exploitability Indicators

```python
def _init_exploit_indicators(self):
    return [
        {
            'name': 'My Indicator',
            'pattern': r'my_exploit_pattern',
            'score': 25,
            'severity': Severity.HIGH
        }
    ]
```

### Adding CVE Patterns

```python
def _init_cve_patterns(self):
    return [
        {
            'cve': 'CVE-2025-XXXXX',
            'pattern': r'specific.*pattern',
            'similarity_threshold': 0.8
        }
    ]
```

---

## Architecture

### Analysis Pipeline

```
Crash Zip
    ↓
Extract Data (GDB output / crash_info.json)
    ↓
Parse Stack Frames & Registers
    ↓
Generate Stack Hash (Deduplication)
    ↓
Detect Vulnerability Type (Pattern Matching)
    ↓
Analyze Exploitability (Scoring)
    ↓
Calculate Severity (Critical/High/Med/Low)
    ↓
Root Cause Analysis
    ↓
Generate Reports (Text/JSON/Markdown)
```

### Components

**EnhancedTriageEngine** (`analysis/enhanced_triage.py`):
- Core analysis logic
- Vulnerability detection
- Exploitability scoring
- Pattern matching

**ReportGenerator** (`analysis/report_generator.py`):
- Report formatting
- Multiple output formats
- Summary generation

**fawkes-triage** (CLI Tool):
- User interface
- Batch processing
- Filtering and sorting

---

## Troubleshooting

### No Crashes Found
```bash
# Check if crash directory exists
ls -la ~/.fawkes/crashes/unique/

# Verify fuzzing job created crashes
sqlite3 ~/.fawkes/fawkes.db "SELECT COUNT(*) FROM crashes"
```

### Low Confidence Scores
- Crash data may be incomplete (missing GDB output or crash_info.json)
- Increase logging: `--log-level DEBUG`
- Check crash zip contents: `unzip -l crash.zip`

### Missing Reports
- Check report directory: `ls -la ~/.fawkes/reports/`
- Verify permissions: `ls -ld ~/.fawkes/reports`
- Try custom directory: `--report-dir /tmp/reports`

---

## Performance

- **Single Crash**: ~0.1-0.5 seconds
- **100 Crashes**: ~10-50 seconds
- **1000 Crashes**: ~1-5 minutes

Scales linearly with number of crashes.

---

## Best Practices

### 1. Run Triage Regularly
```bash
# Daily cron job
0 2 * * * cd /path/to/fawkes && ./fawkes-triage --directory crashes/ --quiet
```

### 2. Focus on High-Severity First
```bash
./fawkes-triage --directory crashes/ --min-severity HIGH
```

### 3. Keep Reports Organized
```bash
# Organize by date
./fawkes-triage --directory crashes/ \
    --report-dir ~/reports/$(date +%Y-%m-%d)/
```

### 4. Track Progress
```bash
# Keep summary reports
./fawkes-triage --directory crashes/ > summary_$(date +%Y%m%d).txt
```

### 5. Integrate with Bug Tracker
```python
# Parse JSON output and create tickets
import json
with open('report.json') as f:
    data = json.load(f)
    if data['crash_analysis']['severity'] == 'Critical':
        create_jira_ticket(data)
```

---

## See Also

- [Crash Replay](CRASH_REPLAY.md) - Reproduce crashes for debugging
- [Fuzzing Guide](FUZZING_GUIDE.md) - Complete fuzzing workflow
- [Architecture Analyzers](../analysis/readme_analyzer.md) - Custom analyzer development
