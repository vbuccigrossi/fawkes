# Fawkes - Change Log

## 2025-01-14 - Critical Bug Fixes & Security Hardening

### Overview
Fixed 14 critical bugs including 6 crash-causing issues and 4 major security vulnerabilities.
All fixes verified and tested.

### Critical Fixes (Would Cause Crashes)
1. ✅ **Missing imports in harness.py** - Added datetime, zipfile, json
2. ✅ **Undefined variable in main.py** - Fixed fuzzer_config reference
3. ✅ **Variable name mismatch** - Corrected Job_dir → job_dir
4. ✅ **Missing database method** - Added get_crashes()
5. ✅ **Agent port binding** - Changed LOOPBACK → ANY for QEMU access
6. ✅ **Worker registry issue** - Fixed None registry handling

### Security Fixes
7. ✅ **Command injection in Linux agent** - Replaced system() with setrlimit()
8. ✅ **Command injection in Windows agent** - Replaced system() with WNetAddConnection2A()
9. ✅ **Path traversal vulnerability** - Added tarball path validation
10. ✅ **Race conditions** - Fixed VM registry locking
11. ✅ **File descriptor leaks** - Proper cleanup in globals.py

### Code Quality
12. ✅ **Duplicate method** - Removed duplicate refresh_statuses()
13. ✅ **QEMU stderr handling** - Fixed error detection
14. ✅ **Config duplicates** - Unified poll_interval

### Renamed
- `agenst/` → `agents/` (fixed typo)

### Files Changed
- harness.py
- main.py
- db/db.py
- modes/worker.py
- qemu.py
- config.py
- globals.py
- agents/FawkesCrashAgent-Windows.cpp
- agents/LinuxCrashAgent.cpp

### Action Required
**Recompile crash agents** - See RECOMPILE_AGENTS.md for instructions

### Verification
Run `./verify_fixes.py` to verify all fixes are working correctly.

### Next Steps
With all critical bugs fixed, the project is ready for:
1. Feature enhancements (coverage-guided fuzzing, web dashboard)
2. Architecture improvements
3. Comprehensive testing
4. Documentation

See BUG_FIXES_SUMMARY.md for complete technical details.
