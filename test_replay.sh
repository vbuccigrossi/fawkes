#!/bin/bash
# Test script for crash replay functionality

set -e

echo "=========================================="
echo "Fawkes Crash Replay - Test Script"
echo "=========================================="
echo ""

# Check if fawkes-replay exists
if [ ! -f "fawkes-replay" ]; then
    echo "Error: fawkes-replay not found"
    exit 1
fi

echo "✓ fawkes-replay found"
echo ""

# Test 1: Check CLI help
echo "Test 1: CLI Help"
echo "----------------"
./fawkes-replay --help > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✓ CLI help works"
else
    echo "✗ CLI help failed"
    exit 1
fi
echo ""

# Test 2: Check imports
echo "Test 2: Import Test"
echo "-------------------"
cd .. && python3 << 'EOF'
import sys

try:
    from fawkes.replay import CrashReplay
    print("✓ CrashReplay class imports successfully")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)
EOF
cd fawkes

if [ $? -ne 0 ]; then
    exit 1
fi
echo ""

# Test 3: Check database integration
echo "Test 3: Database Integration"
echo "----------------------------"
cd .. && python3 << 'EOF'
import sys

try:
    from fawkes.replay import CrashReplay
    from fawkes.config import FawkesConfig

    cfg = FawkesConfig.load()
    replayer = CrashReplay(cfg)
    print("✓ CrashReplay instance created successfully")

    # Check methods exist
    assert hasattr(replayer, 'replay_from_crash_id')
    assert hasattr(replayer, 'replay_from_zip')
    assert hasattr(replayer, '_load_crash_from_db')
    assert hasattr(replayer, '_load_crash_from_zip')
    assert hasattr(replayer, '_replay_crash')
    print("✓ All required methods exist")

except Exception as e:
    print(f"✗ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF
TEST_RESULT=$?
cd fawkes

if [ $TEST_RESULT -ne 0 ]; then
    exit 1
fi
echo ""

# Test 4: Check zip file parsing
echo "Test 4: Crash Archive Parsing"
echo "-----------------------------"
if [ -d "crashes/unique" ] && [ -n "$(ls -A crashes/unique/*.zip 2>/dev/null)" ]; then
    CRASH_ZIP=$(ls crashes/unique/*.zip | head -1)
    echo "Found crash archive: $CRASH_ZIP"

    cd .. && python3 << EOF
from fawkes.replay import CrashReplay
from fawkes.config import FawkesConfig

cfg = FawkesConfig.load()
replayer = CrashReplay(cfg)

crash_data = replayer._load_crash_from_zip('fawkes/$CRASH_ZIP')
if crash_data:
    print("✓ Successfully loaded crash from zip")
    print(f"  Source: {crash_data.get('source', 'unknown')}")
    if 'exploitability' in crash_data:
        print(f"  Exploitability: {crash_data['exploitability']}")
else:
    print("⚠ Could not load crash (zip may be empty or malformed)")
EOF
    cd fawkes
else
    echo "⚠ No crash archives found in crashes/unique/"
    echo "  (This is expected if no crashes have been found yet)"
fi
echo ""

# Test 5: Check database schema
echo "Test 5: Database Schema"
echo "----------------------"
if [ -f "$HOME/.fawkes/fawkes.db" ]; then
    echo "Database found: $HOME/.fawkes/fawkes.db"

    # Check if crashes table has get_crashes method's required columns
    python3 << 'EOF'
import sqlite3
import os

db_path = os.path.expanduser("~/.fawkes/fawkes.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check crashes table structure
cursor.execute("PRAGMA table_info(crashes)")
columns = [row[1] for row in cursor.fetchall()]

required_columns = ['crash_id', 'job_id', 'testcase_path', 'crash_type',
                   'details', 'signature', 'exploitability', 'crash_file',
                   'timestamp', 'duplicate_count']

missing = [col for col in required_columns if col not in columns]

if not missing:
    print("✓ Database schema has all required columns")
else:
    print(f"✗ Missing columns: {missing}")

# Check if there are any crashes
cursor.execute("SELECT COUNT(*) FROM crashes")
count = cursor.fetchone()[0]
print(f"  Total crashes in database: {count}")

conn.close()
EOF
else
    echo "⚠ Database not found (will be created on first run)"
fi
echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo "All core tests passed! ✓"
echo ""
echo "To test crash replay:"
echo "  1. Run a fuzzing job that finds crashes"
echo "  2. Use: ./replay.py --crash-id <id>"
echo "  3. Or: ./replay.py --crash-zip crashes/unique/<file>.zip"
echo ""
echo "For GDB debugging:"
echo "  ./replay.py --crash-id <id> --attach-gdb"
echo ""
