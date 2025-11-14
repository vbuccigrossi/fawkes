#!/bin/bash
# Test script for automated triage functionality

set -e

echo "=========================================="
echo "Fawkes Automated Triage - Test Script"
echo "=========================================="
echo ""

# Check if fawkes-triage exists
if [ ! -f "fawkes-triage" ]; then
    echo "Error: fawkes-triage not found"
    exit 1
fi

echo "✓ fawkes-triage found"
echo ""

# Test 1: CLI Help
echo "Test 1: CLI Help"
echo "----------------"
./fawkes-triage --help > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✓ CLI help works"
else
    echo "✗ CLI help failed"
    exit 1
fi
echo ""

# Test 2: Import Tests
echo "Test 2: Module Imports"
echo "---------------------"
cd .. && python3 << 'EOF'
try:
    from fawkes.analysis.enhanced_triage import EnhancedTriageEngine, Severity, VulnType
    print("✓ EnhancedTriageEngine imports successfully")

    from fawkes.analysis.report_generator import ReportGenerator
    print("✓ ReportGenerator imports successfully")

    # Test instantiation
    engine = EnhancedTriageEngine()
    print("✓ EnhancedTriageEngine instantiates")

    report_gen = ReportGenerator()
    print("✓ ReportGenerator instantiates")

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

# Test 3: Check Vulnerability Patterns
echo "Test 3: Vulnerability Patterns"
echo "------------------------------"
cd .. && python3 << 'EOF'
from fawkes.analysis.enhanced_triage import EnhancedTriageEngine, VulnType

engine = EnhancedTriageEngine()

# Check patterns are loaded
pattern_count = sum(len(patterns) for patterns in engine.vuln_patterns.values())
print(f"✓ Loaded {pattern_count} vulnerability patterns")

# Check indicators
indicator_count = len(engine.exploit_indicators)
print(f"✓ Loaded {indicator_count} exploitability indicators")

# Check vulnerability types
vuln_types = list(engine.vuln_patterns.keys())
print(f"✓ Detecting {len(vuln_types)} vulnerability types:")
for vt in sorted(vuln_types, key=lambda x: x.value):
    print(f"    - {vt.value}")
EOF
TEST_RESULT=$?
cd fawkes

if [ $TEST_RESULT -ne 0 ]; then
    exit 1
fi
echo ""

# Test 4: Test Stack Hash Generation
echo "Test 4: Stack Hash Generation"
echo "-----------------------------"
cd .. && python3 << 'EOF'
from fawkes.analysis.enhanced_triage import EnhancedTriageEngine

engine = EnhancedTriageEngine()

# Test stack hash generation
stack1 = ["func_a", "func_b", "func_c"]
stack2 = ["func_a", "func_b", "func_c"]
stack3 = ["func_x", "func_y", "func_z"]

hash1 = engine._generate_stack_hash(stack1)
hash2 = engine._generate_stack_hash(stack2)
hash3 = engine._generate_stack_hash(stack3)

print(f"Stack 1 hash: {hash1}")
print(f"Stack 2 hash: {hash2}")
print(f"Stack 3 hash: {hash3}")

if hash1 == hash2:
    print("✓ Identical stacks produce same hash")
else:
    print("✗ Identical stacks produce different hashes!")
    exit(1)

if hash1 != hash3:
    print("✓ Different stacks produce different hashes")
else:
    print("✗ Different stacks produce same hash!")
    exit(1)
EOF
TEST_RESULT=$?
cd fawkes

if [ $TEST_RESULT -ne 0 ]; then
    exit 1
fi
echo ""

# Test 5: Test Report Generation
echo "Test 5: Report Generation"
echo "------------------------"
cd .. && python3 << 'EOF'
from fawkes.analysis.enhanced_triage import EnhancedTriageEngine, CrashAnalysis, Severity, VulnType
from fawkes.analysis.report_generator import ReportGenerator
import tempfile

# Create dummy analysis
analysis = CrashAnalysis(
    crash_id="test_crash.zip",
    signature="abc123",
    stack_hash="def456",
    severity=Severity.HIGH,
    exploitability_score=75,
    vuln_type=VulnType.BUFFER_OVERFLOW,
    vuln_class="Memory Corruption",
    control_flow_hijack=True,
    memory_corruption=True,
    controlled_data=True,
    stack_frames=["func1", "func2", "func3"],
    registers={"rip": "0x41414141", "rsp": "0x7fff0000"},
    fault_address="0x41414141",
    crash_instruction="mov rax, [rbx]",
    confidence=0.95,
    indicators=["PC Control", "Stack Corruption"],
    mitigations=["ASLR", "DEP"],
    root_cause="Buffer overflow in input parsing",
    suggested_fix="Use bounds checking",
    similar_cves=["CVE-2020-1234"],
    triage_notes=["High priority", "Remote trigger"]
)

# Test report generation
report_gen = ReportGenerator(tempfile.mkdtemp())

text_report = report_gen.generate_text_report(analysis)
print(f"✓ Generated text report ({len(text_report)} chars)")

json_report = report_gen.generate_json_report(analysis)
print(f"✓ Generated JSON report ({len(json_report)} chars)")

md_report = report_gen.generate_markdown_report(analysis)
print(f"✓ Generated Markdown report ({len(md_report)} chars)")

# Verify report content
if "CRITICAL" not in text_report and "HIGH" in text_report:
    print("✗ Text report missing severity!")
    exit(1)

if "Buffer Overflow" not in text_report:
    print("✗ Text report missing vulnerability type!")
    exit(1)

print("✓ Report content validation passed")
EOF
TEST_RESULT=$?
cd fawkes

if [ $TEST_RESULT -ne 0 ]; then
    exit 1
fi
echo ""

# Test 6: Check if crash directory exists
echo "Test 6: Crash Directory Check"
echo "-----------------------------"
if [ -d "crashes/unique" ]; then
    CRASH_COUNT=$(find crashes/unique -name "*.zip" 2>/dev/null | wc -l)
    echo "✓ Crash directory exists"
    echo "  Found $CRASH_COUNT crash files"

    if [ $CRASH_COUNT -gt 0 ]; then
        SAMPLE_CRASH=$(find crashes/unique -name "*.zip" | head -1)
        echo "  Sample: $(basename $SAMPLE_CRASH)"
        echo ""
        echo "  You can test with:"
        echo "    ./fawkes-triage --crash-zip \"$SAMPLE_CRASH\""
    fi
else
    echo "⚠ Crash directory not found (expected until first crashes found)"
fi
echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo "All core tests passed! ✓"
echo ""
echo "The automated triage system is ready to use."
echo ""
echo "Usage examples:"
echo "  ./fawkes-triage --crash-zip <path>"
echo "  ./fawkes-triage --crash-id <id>"
echo "  ./fawkes-triage --directory crashes/unique/"
echo ""
echo "See docs/AUTOMATED_TRIAGE.md for complete documentation."
echo ""
