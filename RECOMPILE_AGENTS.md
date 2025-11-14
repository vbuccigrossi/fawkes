# Agent Recompilation Guide

The crash agents have been updated with security fixes and need to be recompiled.

## Changes Made

### Linux Agent
- Replaced `system("ulimit -c unlimited")` with `setrlimit(RLIMIT_CORE, RLIM_INFINITY)`
- Added proper headers: `<cerrno>`, `<cstring>`, `<sys/resource.h>`
- Changed port binding from `INADDR_LOOPBACK` to `INADDR_ANY`

### Windows Agent
- Replaced `system(SMB_COMMAND)` with `WNetAddConnection2A()` API
- Added header: `<winnetwk.h>`
- Changed port binding from `INADDR_LOOPBACK` to `INADDR_ANY`
- Updated compile flags to include `-lmpr`

## Compilation Commands

### Linux Agent (on Linux)
```bash
cd agents/
g++ -std=c++17 -O2 -pthread LinuxCrashAgent.cpp -o LinuxCrashAgent
```

### Windows Agent (cross-compile from Linux using MinGW)
```bash
cd agents/
i686-w64-mingw32-g++ -std=c++17 -O2 -static \
    FawkesCrashAgent-Windows.cpp \
    -lws2_32 -lole32 -lpsapi -lmpr \
    -o FawkesCrashAgentWindows.exe
```

### Windows Agent (native Windows build with MSYS2/MinGW)
```bash
cd agents/
g++ -std=c++17 -O2 -static FawkesCrashAgent-Windows.cpp ^
    -lws2_32 -lole32 -lpsapi -lmpr ^
    -o FawkesCrashAgentWindows.exe
```

## Verification

After compilation, verify the agents:

### Linux Agent
```bash
./LinuxCrashAgent &
# Should see: [AGENT] Starting Linux Crash Agent
# Should see: [AGENT] Listening on 0.0.0.0:9999
```

### Windows Agent
```cmd
FawkesCrashAgentWindows.exe
REM Should see: [AGENT] Starting Fawkes Crash Agent with SMB mount...
REM Should see: [AGENT] Listening on 0.0.0.0:9999
```

## Testing

1. **Port binding test**: Verify agent listens on all interfaces
   ```bash
   netstat -tuln | grep 9999
   # Should show: 0.0.0.0:9999 (not 127.0.0.1:9999)
   ```

2. **Connection test**: From QEMU host, test connectivity
   ```bash
   nc -zv <vm-ip> 9999
   # Should connect successfully
   ```

3. **Crash test**: Trigger a crash and verify detection
   - Linux: `kill -SEGV <pid>`
   - Windows: Run a crashing program

## Deployment

Copy compiled agents to VM images:
```bash
# Linux VM
scp agents/LinuxCrashAgent user@vm:/usr/local/bin/

# Windows VM (via SMB share)
cp agents/FawkesCrashAgentWindows.exe /path/to/smb/share/
```

## Troubleshooting

### Linux Compilation Errors

**Error: `rlimit` undeclared**
- Ensure `<sys/resource.h>` is included
- Check compiler supports C++17

**Error: `RLIM_INFINITY` undeclared**
- Verify POSIX compliance: add `-D_POSIX_C_SOURCE=200809L`

### Windows Compilation Errors

**Error: `WNetAddConnection2A` undefined reference**
- Ensure `-lmpr` flag is included
- Check MinGW has Windows networking libraries

**Error: `NETRESOURCEA` undeclared**
- Verify `<winnetwk.h>` is included
- May need Windows SDK headers

## Notes

- The existing `FawkesCrashAgentWindows.exe` in the repository is **not** updated with these fixes
- You must recompile to get the security improvements
- The old binary will still work but has the command injection vulnerability
- Consider setting up CI/CD to automate agent compilation
