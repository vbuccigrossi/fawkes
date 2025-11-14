// FawkesCrashAgent-Windows.cpp
// 
// mount a SMB share at Z: \\10.0.2.4\qemu
// then store user-mode crashes in Z:\qemu.
//
// Compile (using MinGW on Linux):
//   i686-w64-mingw32-g++ -std=c++17 -O2 -static FawkesCrashAgent-Windows.cpp -lws2_32 -lole32 -lpsapi -lmpr -o FawkesCrashAgentWindows.exe

#include <winsock2.h>
#include <windows.h>
#include <ws2tcpip.h>

#include <psapi.h>
#include <shlwapi.h>
#include <winnetwk.h>  // For WNetAddConnection2

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <iostream>
#include <sstream>
#include <filesystem>
#include <fstream>
#include <chrono>
#include <thread>
#include <atomic>
#include <vector>
#include <mutex>

#pragma comment(lib, "ws2_32.lib")

// 1) Our SMB share info (no longer using system() command)
// Using WNetAddConnection2 for safer mounting

// The path we actually store crashes
static const char* CRASH_SUBDIR = "Z:\\qemu";
static const char* WER_KEY = "SOFTWARE\\Microsoft\\Windows\\Windows Error Reporting\\LocalDumps";

static std::atomic<bool> g_crashHappened(false);
static std::mutex g_crashMutex;

struct CrashInfo {
    bool haveCrash;
    std::string exePath;
    DWORD pid;
    DWORD exceptionCode;
    std::string crashFile; // path to the .json record
};

static CrashInfo g_lastCrash;

static LPTOP_LEVEL_EXCEPTION_FILTER g_originalFilter = nullptr;

// Forward declarations
bool ConfigureWER();
LONG WINAPI MyUnhandledExceptionFilter(EXCEPTION_POINTERS* pExp);
std::string CreateCrashJSON(const std::string& exe, DWORD pid, DWORD code);
bool IsDriveMounted(const char* drivePath);
void MountShareLoop();
bool InitializeWinsock();
void StartTCPServer();

int main() {
    std::cout << "[AGENT] Starting Fawkes Crash Agent with SMB mount...\n";

    // Start a thread that periodically ensures Z: is mounted
    std::thread mountThread(MountShareLoop);

    // Configure WER to dump user-mode crashes to Z:\Fawkes\crashes
    if (!ConfigureWER()) {
        std::cerr << "[AGENT] WER config might not be set.\n";
    }

    // Create subdirectory if needed
    std::filesystem::create_directories(CRASH_SUBDIR);

    // Install our global unhandled exception filter
    g_originalFilter = SetUnhandledExceptionFilter(MyUnhandledExceptionFilter);

    // Start the TCP server for the host harness to poll
    StartTCPServer();

    // we should never get here in typical usage
    mountThread.join();
    return 0;
}

//
// Configure WER to dump user-mode crashes to CRASH_SUBDIR
//
bool ConfigureWER() {
    HKEY hKey;
    LONG res = RegCreateKeyExA(HKEY_LOCAL_MACHINE, WER_KEY, 0, NULL,
                               REG_OPTION_NON_VOLATILE, KEY_SET_VALUE, NULL, &hKey, NULL);
    if (res != ERROR_SUCCESS) {
        std::cerr << "[AGENT] Failed to open/create WER registry key: " << res << "\n";
        return false;
    }
    // set DumpFolder => CRASH_SUBDIR
    res = RegSetValueExA(hKey, "DumpFolder", 0, REG_SZ,
                         reinterpret_cast<const BYTE*>(CRASH_SUBDIR),
                         (DWORD)strlen(CRASH_SUBDIR) + 1);
    if (res != ERROR_SUCCESS) {
        std::cerr << "[AGENT] Failed to set DumpFolder in registry: " << res << "\n";
        RegCloseKey(hKey);
        return false;
    }

    DWORD dumpType = 2; // 2 => Full dump
    res = RegSetValueExA(hKey, "DumpType", 0, REG_DWORD,
                         reinterpret_cast<const BYTE*>(&dumpType), sizeof(dumpType));
    RegCloseKey(hKey);

    std::cout << "[AGENT] WER set to dump in " << CRASH_SUBDIR << "\n";
    return true;
}

//
// Global unhandled exception filter
//
LONG WINAPI MyUnhandledExceptionFilter(EXCEPTION_POINTERS* pExp) {
    DWORD code = pExp->ExceptionRecord->ExceptionCode;
    DWORD pid = GetCurrentProcessId();
    char exePath[MAX_PATH];
    if (GetModuleFileNameA(NULL, exePath, MAX_PATH) == 0) {
        strcpy_s(exePath, "unknown");
    }

    std::cerr << "[AGENT] User-mode crash! PID=" << pid
              << ", code=0x" << std::hex << code
              << ", exe=" << exePath << std::dec << "\n";

    // Create a small JSON describing the crash
    std::string jsonFile = CreateCrashJSON(exePath, pid, code);

    {
        std::lock_guard<std::mutex> lk(g_crashMutex);
        g_crashHappened.store(true, std::memory_order_relaxed);
        g_lastCrash.haveCrash = true;
        g_lastCrash.exePath = exePath;
        g_lastCrash.pid = pid;
        g_lastCrash.exceptionCode = code;
        g_lastCrash.crashFile = jsonFile;
    }

    // chain to original filter if present
    if (g_originalFilter) {
        return g_originalFilter(pExp);
    }
    return EXCEPTION_EXECUTE_HANDLER;
}

//
// Create a small JSON record in CRASH_SUBDIR
//    e.g. "crash_1234_20230601_120000.json"
//
std::string CreateCrashJSON(const std::string& exe, DWORD pid, DWORD code) {
    namespace fs = std::filesystem;
    fs::path crashDir(CRASH_SUBDIR);
    if (!fs::exists(crashDir)) {
        fs::create_directories(crashDir);
    }
    auto now = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
    char buf[64];
    strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", localtime(&now));
    std::string fname = "crash_" + std::to_string(pid) + "_" + buf + ".json";

    fs::path fullPath = crashDir / fname;
    std::ofstream ofs(fullPath);
    if (!ofs) {
        std::cerr << "[AGENT] Failed to create " << fullPath.string() << "\n";
        return "";
    }
    // JSON
    ofs << "{\n";
    ofs << "  \"crash\": true,\n";
    ofs << "  \"pid\": " << pid << ",\n";
    ofs << "  \"exe\": \"" << exe << "\",\n";
    ofs << "  \"exception\": \"0x" << std::hex << code << std::dec << "\"\n";
    ofs << "}\n";
    ofs.close();

    return fullPath.string();
}

//
//    SMB share mounting
//    We do "net use Z: \\10.0.2.4\qemu /persistent:no"
//    every few seconds if we see Z:\ is not accessible
//
bool IsDriveMounted(const char* drivePath) {
    // Check if e.g. "Z:\" is accessible
    // check if drive type != DRIVE_NO_ROOT_DIR
    UINT type = GetDriveTypeA(drivePath);
    if (type == DRIVE_NO_ROOT_DIR || type == DRIVE_UNKNOWN) {
        return false;
    }
    return true;
}

void MountShareLoop() {
    while (true) {
        // Check every 5 seconds
        std::this_thread::sleep_for(std::chrono::seconds(5));

        // If Z:\ not accessible, mount using WNetAddConnection2 (safer than system())
        if (!IsDriveMounted("Z:\\")) {
            std::cout << "[AGENT] Attempting to mount SMB share...\n";

            NETRESOURCEA netResource;
            memset(&netResource, 0, sizeof(netResource));
            netResource.dwType = RESOURCETYPE_DISK;
            netResource.lpLocalName = "Z:";
            netResource.lpRemoteName = "\\\\10.0.2.4\\qemu";
            netResource.lpProvider = NULL;

            // Try to add network connection (no credentials for now)
            DWORD result = WNetAddConnection2A(&netResource, NULL, NULL, 0);
            if (result == NO_ERROR) {
                std::cout << "[AGENT] SMB share mounted successfully.\n";
            } else if (result == ERROR_ALREADY_ASSIGNED) {
                std::cout << "[AGENT] Share already mounted.\n";
            } else {
                std::cerr << "[AGENT] Failed to mount share, error code: " << result << "\n";
            }
        }
    }
}

//
// Minimal TCP server on 127.0.0.1:9999
//
bool InitializeWinsock() {
    WSADATA wsa;
    int ret = WSAStartup(MAKEWORD(2,2), &wsa);
    if (ret != 0) {
        std::cerr << "[AGENT] WSAStartup failed: " << ret << "\n";
        return false;
    }
    return true;
}

void StartTCPServer() {
    if (!InitializeWinsock()) {
        return;
    }
    SOCKET serverSock = socket(AF_INET, SOCK_STREAM, 0);
    if (serverSock == INVALID_SOCKET) {
        std::cerr << "[AGENT] socket() failed\n";
        WSACleanup();
        return;
    }
    sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_port = htons(9999);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);  // Bind to all interfaces so QEMU host can reach

    if (bind(serverSock, (sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR) {
        std::cerr << "[AGENT] bind() failed\n";
        closesocket(serverSock);
        WSACleanup();
        return;
    }
    if (listen(serverSock, SOMAXCONN) == SOCKET_ERROR) {
        std::cerr << "[AGENT] listen() failed\n";
        closesocket(serverSock);
        WSACleanup();
        return;
    }
    std::cout << "[AGENT] Listening on 127.0.0.1:9999\n";

    while (true) {
        SOCKET client = accept(serverSock, NULL, NULL);
        if (client == INVALID_SOCKET) {
            std::cerr << "[AGENT] accept() failed\n";
            break;
        }
        char buf[1024];
        int ret = recv(client, buf, 1023, 0);
        if (ret > 0) {
            buf[ret] = '\0';
            // We ignore the actual request; we just respond
        }
        // Build response
        bool crash = g_crashHappened.load(std::memory_order_relaxed);
        std::string response;
        {
            std::lock_guard<std::mutex> lk(g_crashMutex);
            if (crash && g_lastCrash.haveCrash)
            {
                /* build 0xXXXXXXXX string */
                std::stringstream ss;
                ss << "0x" << std::hex << g_lastCrash.exceptionCode;   // hex format
                std::string excStr = ss.str();

                response = "{ \"crash\": true, \"pid\": " + std::to_string(g_lastCrash.pid) +
                           ", \"exe\": \"" + g_lastCrash.exePath +
                           "\", \"exception\": \"" + excStr +
                           "\", \"file\": \"" + g_lastCrash.crashFile + "\" }\n";
            }
            else
            {
                response = "{ \"crash\": false }\n";
            }
        }

        // naive HTTP response
        std::string httpResp =
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n\r\n" +
            response;
        send(client, httpResp.c_str(), (int)httpResp.size(), 0);
        closesocket(client);
    }

    closesocket(serverSock);
    WSACleanup();
}


