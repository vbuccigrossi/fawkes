// LinuxCrashAgent.cpp
//
// A Linux Crash Agent that:
// 1) Sets /proc/sys/kernel/core_pattern => /mnt/virtfs/fawkes/crashes/core.%p
// 2) Sets unlimited core dumps using setrlimit
// 3) Watches /mnt/virtfs/fawkes/crashes for new core.* files
// 4) Keeps a single "last crash" record with fields analogous to the Windows agent:
//    { "crash": true, "pid": <pid>, "exe": "...", "exception": "0xC0000005", "file": "<corefile>" }
// 5) Runs a small TCP server at 0.0.0.0:9999 returning the above JSON.
//
// This approach ensures the harness sees the exact same JSON protocol as on Windows.

#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <csignal>
#include <cerrno>
#include <cstring>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <sys/resource.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <mutex>
#include <atomic>
#include <thread>
#include <chrono>

static const char* CORE_PATTERN_FILE = "/proc/sys/kernel/core_pattern";
// We store core dumps here:
static const char* CRASH_DIR  = "/mnt/virtfs/fawkes/crashes";
static const char* CORE_PATTERN_VALUE  = "/mnt/virtfs/fawkes/crashes/core.%p";

// We'll store only one crash record, matching Windows agent fields:
struct CrashInfo {
    bool haveCrash;
    std::string exePath;       // we'll store "unknown" since we can't easily get the exe
    unsigned long pid;         // parse from core filename if possible
    unsigned long exceptionCode; // We'll assume "0xc0000005" for segfault or generic
    std::string crashFile;     // full path to the core file
};

// Global shared state
static std::atomic<bool> g_crashHappened(false);
static CrashInfo g_lastCrash;
static std::mutex g_crashMutex;

// Forward declarations
bool ConfigureCorePattern();
void CrashWatcherLoop();
void StartTCPServer();
int parsePID(const std::string& filename);

// 1) Main
int main(int argc, char* argv[]) {
    std::cout << "[AGENT] Starting Linux Crash Agent (Windows-protocol style)\n";

    // Must be root typically to set core_pattern
    if (!ConfigureCorePattern()) {
        std::cerr << "[AGENT] Could not set /proc/sys/kernel/core_pattern. Are we root?\n";
    }

    // ensure crash dir
    std::filesystem::create_directories(CRASH_DIR);

    // Start a watcher thread that sees new core.* files
    std::thread watcher(CrashWatcherLoop);

    // Start TCP server on 127.0.0.1:9999
    StartTCPServer();

    watcher.join();
    return 0;
}

// 2) Configure core_pattern => /mnt/virtfs/fawkes/crashes/core.%p + setrlimit for unlimited cores
bool ConfigureCorePattern() {
    // Write /proc/sys/kernel/core_pattern
    {
        std::ofstream ofs(CORE_PATTERN_FILE);
        if (!ofs) {
            std::cerr << "[AGENT] Failed to open " << CORE_PATTERN_FILE << " for write.\n";
            return false;
        }
        ofs << CORE_PATTERN_VALUE << "\n";
        ofs.close();
        std::cout << "[AGENT] core_pattern => " << CORE_PATTERN_VALUE << "\n";
    }
    // Set unlimited core dumps using setrlimit (safer than system())
    struct rlimit core_limit;
    core_limit.rlim_cur = RLIM_INFINITY;
    core_limit.rlim_max = RLIM_INFINITY;
    if (setrlimit(RLIMIT_CORE, &core_limit) != 0) {
        std::cerr << "[AGENT] setrlimit(RLIMIT_CORE, unlimited) failed: " << strerror(errno) << "\n";
        return false;
    }
    std::cout << "[AGENT] Core dump size set to unlimited\n";
    return true;
}

// 3) The crash watcher: poll CRASH_DIR every 2s, find newest core.* 
//    If found, set g_crashHappened = true and fill g_lastCrash
void CrashWatcherLoop() {
    using namespace std::chrono_literals;
    std::string lastCore;
    while (true) {
        std::this_thread::sleep_for(2s);

        namespace fs = std::filesystem;
        fs::path dir(CRASH_DIR);
        if (!fs::exists(dir) || !fs::is_directory(dir)) {
            continue;
        }

        fs::path newestPath;
        auto newestTime = fs::file_time_type::min();

        for (auto& entry : fs::directory_iterator(dir)) {
            if (!entry.is_regular_file()) continue;
            auto fname = entry.path().filename().string();
            if (fname.rfind("core.", 0) == 0) {
                auto ftime = fs::last_write_time(entry.path());
                if (ftime > newestTime) {
                    newestTime = ftime;
                    newestPath = entry.path();
                }
            }
        }

        if (!newestPath.empty()) {
            std::string newestFull = newestPath.string();
            if (newestFull != lastCore) {
                // new crash
                lastCore = newestFull;
                unsigned long pidVal = parsePID(newestPath.filename().string());
                // We mirror the Windows agent's approach: store "unknown" for exe,
                // store 0xC0000005 for exception
                std::cerr << "[AGENT] Detected new core dump: " << newestFull
                          << ", pid=" << pidVal << "\n";

                {
                    std::lock_guard<std::mutex> lk(g_crashMutex);
                    g_crashHappened.store(true, std::memory_order_relaxed);
                    g_lastCrash.haveCrash = true;
                    g_lastCrash.exePath = "unknown";  // we can't easily get the actual exe path
                    g_lastCrash.pid = pidVal;
                    g_lastCrash.exceptionCode = 0xC0000005;  // typical segfault code, just a placeholder
                    g_lastCrash.crashFile = newestFull;
                }
            }
        }
    }
}

// 4) parsePID from "core.<pid>" 
int parsePID(const std::string& filename) {
    // e.g. "core.1234"
    const std::string prefix = "core.";
    if (filename.rfind(prefix, 0) == 0) {
        std::string pidStr = filename.substr(prefix.size());
        try {
            return std::stoi(pidStr);
        } catch (...) {
            return -1;
        }
    }
    return -1;
}

// 5) Start a minimal single-thread TCP server on 127.0.0.1:9999
void StartTCPServer() {
    int serverSock = ::socket(AF_INET, SOCK_STREAM, 0);
    if (serverSock < 0) {
        std::cerr << "[AGENT] socket() failed\n";
        return;
    }
    int opt = 1;
    setsockopt(serverSock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    sockaddr_in addr;
    addr.sin_family      = AF_INET;
    addr.sin_port        = htons(9999);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);  // Bind to all interfaces so QEMU host can reach

    if (bind(serverSock, (sockaddr*)&addr, sizeof(addr)) < 0) {
        std::cerr << "[AGENT] bind() failed\n";
        close(serverSock);
        return;
    }
    if (listen(serverSock, 5) < 0) {
        std::cerr << "[AGENT] listen() failed\n";
        close(serverSock);
        return;
    }
    std::cout << "[AGENT] Listening on 127.0.0.1:9999\n";

    while (true) {
        sockaddr_in caddr;
        socklen_t caddrLen = sizeof(caddr);
        int client = accept(serverSock, (sockaddr*)&caddr, &caddrLen);
        if (client < 0) {
            std::cerr << "[AGENT] accept() error\n";
            continue;
        }
        // read something from the client
        char buf[1024];
        int ret = recv(client, buf, 1023, 0);
        if (ret > 0) {
            buf[ret] = '\0';
        }

        // Build same JSON as the Windows agent
        bool crash = g_crashHappened.load(std::memory_order_relaxed);
        std::string response;
        {
            std::lock_guard<std::mutex> lk(g_crashMutex);
            if (crash && g_lastCrash.haveCrash) {
                // same structure:
                // { "crash": true, "pid": <pid>, "exe": "...", "exception": "0x123", "file": "..." }
                response = "{ \"crash\": true, \"pid\": " + std::to_string(g_lastCrash.pid) +
                           ", \"exe\": \"" + g_lastCrash.exePath + "\", \"exception\": \"0x" +
                           std::to_string(std::hex) + std::to_string(g_lastCrash.exceptionCode) + std::dec +
                           "\", \"file\": \"" + g_lastCrash.crashFile + "\" }\n";
            } else {
                response = "{ \"crash\": false }\n";
            }
        }
        // naive HTTP
        std::string http = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + response;
        send(client, http.c_str(), http.size(), 0);
        close(client);
    }

    close(serverSock);
}

