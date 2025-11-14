#!/bin/bash
# Fawkes Differential Fuzzing Test Suite

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Test configuration
TEST_DB="/tmp/fawkes_diff_test.db"
TEST_OUTPUT_DIR="/tmp/fawkes_diff_test_output"
TEST_PASSED=0
TEST_FAILED=0

# Python import helper
PYTHON_SETUP="import sys; from pathlib import Path; sys.path.insert(0, str(Path('$SCRIPT_DIR').parent))"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "======================================================================"
echo "Fawkes Differential Fuzzing Test Suite"
echo "======================================================================"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "Cleaning up test artifacts..."
    rm -f "$TEST_DB"
    rm -rf "$TEST_OUTPUT_DIR"
}

trap cleanup EXIT

# Test helper functions
run_test() {
    local test_name="$1"
    local test_func="$2"

    echo -n "TEST: $test_name ... "

    if $test_func > /tmp/test_output.txt 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        TEST_PASSED=$((TEST_PASSED + 1))
        return 0
    else
        echo -e "${RED}FAIL${NC}"
        echo "  Error output:"
        cat /tmp/test_output.txt | sed 's/^/    /'
        TEST_FAILED=$((TEST_FAILED + 1))
        return 1
    fi
}

# Test 1: Import differential modules
test_import_modules() {
    python3 -c "$PYTHON_SETUP
$PYTHON_SETUP
from fawkes.differential.engine import DifferentialEngine, DivergenceType, DivergenceSeverity
from fawkes.differential.harness import DifferentialHarness, DifferentialTarget
from fawkes.differential.db import DifferentialDB
print('All modules imported successfully')
"
}

# Test 2: Create differential database
test_create_database() {
    python3 -c "$PYTHON_SETUP
$PYTHON_SETUP
from fawkes.differential.db import DifferentialDB
db = DifferentialDB('$TEST_DB')
db.close()
import os
assert os.path.exists('$TEST_DB'), 'Database file not created'
print('Database created successfully')
"
}

# Test 3: Add campaign
test_add_campaign() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.db import DifferentialDB
db = DifferentialDB('$TEST_DB')
campaign_id = db.add_campaign(
    name='Test Campaign',
    targets=['target-a', 'target-b'],
    description='Test campaign description'
)
assert campaign_id > 0, 'Invalid campaign ID'
db.close()
print(f'Campaign created with ID: {campaign_id}')
"
}

# Test 4: Get campaign summary
test_get_campaign() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.db import DifferentialDB
db = DifferentialDB('$TEST_DB')
campaign = db.get_campaign_summary(1)
assert campaign is not None, 'Campaign not found'
assert campaign['name'] == 'Test Campaign', 'Campaign name mismatch'
assert 'target-a' in campaign['targets'], 'Target A not in campaign'
assert 'target-b' in campaign['targets'], 'Target B not in campaign'
db.close()
print('Campaign retrieved successfully')
"
}

# Test 5: Create execution results and detect crash divergence
test_crash_divergence() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.engine import (
    DifferentialEngine, ExecutionResult, DivergenceType, DivergenceSeverity
)

engine = DifferentialEngine()

# Target A crashes
result_a = ExecutionResult(
    target_id='target-a',
    target_version='1.0.0',
    testcase_path='/tmp/test.bin',
    crashed=True,
    exit_code=-1,
    timeout=False,
    execution_time=50.0,
    stdout=None,
    stderr=None,
    output_hash=None,
    registers={'rip': '0x401000'},
    signal='SIGSEGV',
    memory_usage=None,
    error_message=None
)

# Target B does not crash
result_b = ExecutionResult(
    target_id='target-b',
    target_version='2.0.0',
    testcase_path='/tmp/test.bin',
    crashed=False,
    exit_code=0,
    timeout=False,
    execution_time=45.0,
    stdout='Success',
    stderr=None,
    output_hash='abc123',
    registers=None,
    signal=None,
    memory_usage=None,
    error_message=None
)

divergences = engine.compare_executions(result_a, result_b)
assert len(divergences) > 0, 'No divergences detected'

crash_divergence = next((d for d in divergences if d.divergence_type == DivergenceType.CRASH), None)
assert crash_divergence is not None, 'Crash divergence not detected'
assert crash_divergence.severity == DivergenceSeverity.CRITICAL, 'Incorrect severity'
assert crash_divergence.confidence == 1.0, 'Incorrect confidence'

print(f'Crash divergence detected: {crash_divergence.description}')
"
}

# Test 6: Detect output divergence
test_output_divergence() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.engine import (
    DifferentialEngine, ExecutionResult, DivergenceType
)

engine = DifferentialEngine()

result_a = ExecutionResult(
    target_id='target-a',
    target_version='1.0.0',
    testcase_path='/tmp/test.bin',
    crashed=False,
    exit_code=0,
    timeout=False,
    execution_time=50.0,
    stdout='Output from version 1',
    stderr=None,
    output_hash='hash_a',
    registers=None,
    signal=None,
    memory_usage=None,
    error_message=None
)

result_b = ExecutionResult(
    target_id='target-b',
    target_version='2.0.0',
    testcase_path='/tmp/test.bin',
    crashed=False,
    exit_code=0,
    timeout=False,
    execution_time=45.0,
    stdout='Output from version 2',
    stderr=None,
    output_hash='hash_b',
    registers=None,
    signal=None,
    memory_usage=None,
    error_message=None
)

divergences = engine.compare_executions(result_a, result_b)
output_divergence = next((d for d in divergences if d.divergence_type == DivergenceType.DIFFERENT_OUTPUT), None)
assert output_divergence is not None, 'Output divergence not detected'

print(f'Output divergence detected: {output_divergence.description}')
"
}

# Test 7: Detect timeout divergence
test_timeout_divergence() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.engine import (
    DifferentialEngine, ExecutionResult, DivergenceType, DivergenceSeverity
)

engine = DifferentialEngine()

result_a = ExecutionResult(
    target_id='target-a',
    target_version='1.0.0',
    testcase_path='/tmp/test.bin',
    crashed=False,
    exit_code=0,
    timeout=True,
    execution_time=60000.0,
    stdout=None,
    stderr=None,
    output_hash=None,
    registers=None,
    signal=None,
    memory_usage=None,
    error_message=None
)

result_b = ExecutionResult(
    target_id='target-b',
    target_version='2.0.0',
    testcase_path='/tmp/test.bin',
    crashed=False,
    exit_code=0,
    timeout=False,
    execution_time=50.0,
    stdout='Success',
    stderr=None,
    output_hash='abc123',
    registers=None,
    signal=None,
    memory_usage=None,
    error_message=None
)

divergences = engine.compare_executions(result_a, result_b)
timeout_div = next((d for d in divergences if d.divergence_type == DivergenceType.TIMEOUT), None)
assert timeout_div is not None, 'Timeout divergence not detected'
assert timeout_div.severity == DivergenceSeverity.HIGH, 'Incorrect severity'

print(f'Timeout divergence detected: {timeout_div.description}')
"
}

# Test 8: Detect return code divergence
test_return_divergence() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.engine import (
    DifferentialEngine, ExecutionResult, DivergenceType
)

engine = DifferentialEngine()

result_a = ExecutionResult(
    target_id='target-a',
    target_version='1.0.0',
    testcase_path='/tmp/test.bin',
    crashed=False,
    exit_code=0,
    timeout=False,
    execution_time=50.0,
    stdout='Success',
    stderr=None,
    output_hash='hash_a',
    registers=None,
    signal=None,
    memory_usage=None,
    error_message=None
)

result_b = ExecutionResult(
    target_id='target-b',
    target_version='2.0.0',
    testcase_path='/tmp/test.bin',
    crashed=False,
    exit_code=1,
    timeout=False,
    execution_time=45.0,
    stdout='Success',
    stderr=None,
    output_hash='hash_a',
    registers=None,
    signal=None,
    memory_usage=None,
    error_message=None
)

divergences = engine.compare_executions(result_a, result_b)
return_div = next((d for d in divergences if d.divergence_type == DivergenceType.DIFFERENT_RETURN), None)
assert return_div is not None, 'Return code divergence not detected'

print(f'Return code divergence detected: {return_div.description}')
"
}

# Test 9: Add divergence to database
test_add_divergence() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.db import DifferentialDB
from fawkes.differential.engine import (
    Divergence, DivergenceType, DivergenceSeverity, ExecutionResult
)
import time

db = DifferentialDB('$TEST_DB')

# Create mock execution results
result_a = ExecutionResult(
    target_id='target-a',
    target_version='1.0.0',
    testcase_path='/tmp/test.bin',
    crashed=True,
    exit_code=-1,
    timeout=False,
    execution_time=50.0,
    stdout=None,
    stderr=None,
    output_hash=None,
    registers={'rip': '0x401000'},
    signal='SIGSEGV',
    memory_usage=None,
    error_message=None
)

result_b = ExecutionResult(
    target_id='target-b',
    target_version='2.0.0',
    testcase_path='/tmp/test.bin',
    crashed=False,
    exit_code=0,
    timeout=False,
    execution_time=45.0,
    stdout='Success',
    stderr=None,
    output_hash='abc123',
    registers=None,
    signal=None,
    memory_usage=None,
    error_message=None
)

divergence = Divergence(
    divergence_id='test_divergence_001',
    testcase_path='/tmp/test.bin',
    divergence_type=DivergenceType.CRASH,
    severity=DivergenceSeverity.CRITICAL,
    target_a=result_a,
    target_b=result_b,
    description='Test crash divergence',
    confidence=1.0,
    details={'crashed_target': 'target-a'},
    timestamp=int(time.time())
)

db.add_divergence(campaign_id=1, divergence=divergence)
db.close()
print('Divergence added to database')
"
}

# Test 10: Query divergences
test_query_divergences() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.db import DifferentialDB

db = DifferentialDB('$TEST_DB')
divergences = db.get_divergences(campaign_id=1)
assert len(divergences) > 0, 'No divergences found'
assert divergences[0]['divergence_id'] == 'test_divergence_001', 'Divergence ID mismatch'
assert divergences[0]['severity'] == 'critical', 'Severity mismatch'
assert divergences[0]['divergence_type'] == 'crash', 'Type mismatch'
db.close()
print(f'Found {len(divergences)} divergence(s)')
"
}

# Test 11: Filter divergences by severity
test_filter_by_severity() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.db import DifferentialDB

db = DifferentialDB('$TEST_DB')
critical = db.get_divergences(severity='critical')
assert len(critical) > 0, 'No critical divergences found'
assert all(d['severity'] == 'critical' for d in critical), 'Non-critical divergence in results'
db.close()
print(f'Found {len(critical)} critical divergence(s)')
"
}

# Test 12: Triage divergence
test_triage_divergence() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.db import DifferentialDB

db = DifferentialDB('$TEST_DB')
db.triage_divergence('test_divergence_001', 'This is a known issue')

divergences = db.get_divergences()
triaged = next((d for d in divergences if d['divergence_id'] == 'test_divergence_001'), None)
assert triaged is not None, 'Divergence not found'
assert triaged['triaged'] == True, 'Divergence not marked as triaged'
assert triaged['notes'] == 'This is a known issue', 'Triage notes mismatch'
db.close()
print('Divergence triaged successfully')
"
}

# Test 13: Get statistics
test_get_stats() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.db import DifferentialDB

db = DifferentialDB('$TEST_DB')
stats = db.get_stats()
assert stats['total_campaigns'] > 0, 'No campaigns in stats'
assert stats['total_divergences'] > 0, 'No divergences in stats'
assert stats['triaged_divergences'] > 0, 'No triaged divergences in stats'
assert 'critical' in stats['divergences_by_severity'], 'No severity breakdown'
assert 'crash' in stats['divergences_by_type'], 'No type breakdown'
db.close()
print(f'Stats: {stats}')
"
}

# Test 14: Generate summary report
test_summary_report() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.engine import (
    DifferentialEngine, ExecutionResult, DivergenceType
)

engine = DifferentialEngine()

# Create some test divergences
result_a = ExecutionResult(
    target_id='target-a', target_version='1.0.0', testcase_path='/tmp/test1.bin',
    crashed=True, exit_code=-1, timeout=False, execution_time=50.0,
    stdout=None, stderr=None, output_hash=None, registers=None,
    signal='SIGSEGV', memory_usage=None, error_message=None
)
result_b = ExecutionResult(
    target_id='target-b', target_version='2.0.0', testcase_path='/tmp/test1.bin',
    crashed=False, exit_code=0, timeout=False, execution_time=45.0,
    stdout='OK', stderr=None, output_hash='abc', registers=None,
    signal=None, memory_usage=None, error_message=None
)

engine.compare_executions(result_a, result_b)
report = engine.generate_summary_report()
assert 'DIFFERENTIAL FUZZING SUMMARY' in report, 'Report header missing'
assert 'Divergences Found' in report, 'Divergences count missing'
assert 'CRITICAL' in report, 'Severity breakdown missing'
print('Summary report generated successfully')
"
}

# Test 15: DifferentialTarget validation
test_differential_target() {
    # Create temporary test files
    mkdir -p /tmp/fawkes_diff_test
    touch /tmp/fawkes_diff_test/test.qcow2

    python3 -c "$PYTHON_SETUP

from fawkes.differential.harness import DifferentialTarget

# Valid target
target = DifferentialTarget(
    target_id='test-target',
    version='1.0.0',
    disk_image='/tmp/fawkes_diff_test/test.qcow2',
    snapshot_name='ready',
    arch='x86_64'
)
assert target.target_id == 'test-target', 'Target ID mismatch'
assert target.version == '1.0.0', 'Version mismatch'
assert target.arch == 'x86_64', 'Architecture mismatch'
print('DifferentialTarget created successfully')
"

    # Cleanup
    rm -rf /tmp/fawkes_diff_test
}

# Test 16: CLI tool exists and is executable
test_cli_executable() {
    test -f "./fawkes-diff" || return 1
    test -x "./fawkes-diff" || return 1
    echo "CLI tool exists and is executable"
}

# Test 17: CLI help command
test_cli_help() {
    ./fawkes-diff --help > /dev/null 2>&1
}

# Test 18: CLI campaigns command
test_cli_campaigns() {
    ./fawkes-diff --db "$TEST_DB" campaigns --limit 10 > /dev/null 2>&1
}

# Test 19: CLI show campaign command
test_cli_show_campaign() {
    ./fawkes-diff --db "$TEST_DB" show 1 > /dev/null 2>&1
}

# Test 20: CLI divergences command
test_cli_divergences() {
    ./fawkes-diff --db "$TEST_DB" divergences --limit 10 > /dev/null 2>&1
}

# Test 21: CLI stats command
test_cli_stats() {
    ./fawkes-diff --db "$TEST_DB" stats > /dev/null 2>&1
}

# Test 22: Update campaign stats
test_update_campaign_stats() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.db import DifferentialDB

db = DifferentialDB('$TEST_DB')
stats = {
    'testcases_executed': 100,
    'divergences_found': 5,
    'crashes_found': 2
}
db.update_campaign_stats(1, stats)

campaign = db.get_campaign_summary(1)
assert campaign['testcases_executed'] == 100, 'Testcases count mismatch'
assert campaign['divergences_found'] == 5, 'Divergences count mismatch'
assert campaign['crashes_found'] == 2, 'Crashes count mismatch'
db.close()
print('Campaign stats updated successfully')
"
}

# Test 23: End campaign
test_end_campaign() {
    python3 -c "$PYTHON_SETUP

from fawkes.differential.db import DifferentialDB

db = DifferentialDB('$TEST_DB')
db.end_campaign(1)

campaign = db.get_campaign_summary(1)
assert campaign['end_time'] is not None, 'Campaign end time not set'
db.close()
print('Campaign ended successfully')
"
}

# Run all tests
echo "Running differential fuzzing tests..."
echo ""

run_test "Import differential modules" test_import_modules
run_test "Create differential database" test_create_database
run_test "Add campaign" test_add_campaign
run_test "Get campaign summary" test_get_campaign
run_test "Detect crash divergence" test_crash_divergence
run_test "Detect output divergence" test_output_divergence
run_test "Detect timeout divergence" test_timeout_divergence
run_test "Detect return code divergence" test_return_divergence
run_test "Add divergence to database" test_add_divergence
run_test "Query divergences" test_query_divergences
run_test "Filter divergences by severity" test_filter_by_severity
run_test "Triage divergence" test_triage_divergence
run_test "Get statistics" test_get_stats
run_test "Generate summary report" test_summary_report
run_test "DifferentialTarget validation" test_differential_target
run_test "CLI tool exists and is executable" test_cli_executable
run_test "CLI help command" test_cli_help
run_test "CLI campaigns command" test_cli_campaigns
run_test "CLI show campaign command" test_cli_show_campaign
run_test "CLI divergences command" test_cli_divergences
run_test "CLI stats command" test_cli_stats
run_test "Update campaign stats" test_update_campaign_stats
run_test "End campaign" test_end_campaign

# Summary
echo ""
echo "======================================================================"
echo "Test Summary"
echo "======================================================================"
echo -e "${GREEN}PASSED: $TEST_PASSED${NC}"
echo -e "${RED}FAILED: $TEST_FAILED${NC}"
echo ""

if [ $TEST_FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
