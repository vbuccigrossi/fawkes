# Fawkes

**Enterprise-Grade QEMU/GDB-based Fuzzing Framework**

Fawkes is a powerful, snapshot-based fuzzing framework that leverages QEMU virtualization and GDB debugging to find security vulnerabilities in applications across multiple architectures. It supports local single-node fuzzing, distributed fuzzing clusters, and includes both a TUI and web interface for monitoring.

---


<img width="1101" height="667" alt="Screen Shot 2026-01-13 at 4 02 49 PM" src="https://github.com/user-attachments/assets/6b1260a5-23a6-4df7-a524-9417d7a44990" />

---

## Features

- **Snapshot-based Fuzzing** - Fast iteration using QEMU VM snapshots
- **Multi-Architecture Support** - x86, x86_64, ARM, AArch64, MIPS, SPARC, PowerPC
- **Intelligent Mutation Engine** - Crash-guided, adaptive fuzzing strategies
- **Distributed Fuzzing** - Controller/worker architecture for cluster fuzzing
- **Crash Triage & Deduplication** - Automatic crash analysis with stack-based deduplication
- **Network Protocol Fuzzing** - Fuzz network services with conversation-aware mutations
- **Kernel Fuzzing** - Support for kernel-level vulnerability discovery
- **Differential Fuzzing** - Compare behavior across different versions/implementations
- **Real-time Monitoring** - TUI and Web UI for live fuzzing statistics
- **Cross-Platform Agents** - Windows and Linux guest agents for crash detection

---


<img width="1666" height="838" alt="Screen Shot 2026-01-13 at 4 03 06 PM" src="https://github.com/user-attachments/assets/f988076a-f4dc-4d19-9043-76a3a5690047" />

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Fawkes Controller                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │   Web UI    │  │     TUI     │  │   REST API  │          │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │
│         └────────────────┼────────────────┘                  │
│                          ▼                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Job Scheduler & Corpus Manager            │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │  Worker 1  │  │  Worker 2  │  │  Worker N  │
    │ ┌────────┐ │  │ ┌────────┐ │  │ ┌────────┐ │
    │ │QEMU VM │ │  │ │QEMU VM │ │  │ │QEMU VM │ │
    │ │+ Agent │ │  │ │+ Agent │ │  │ │+ Agent │ │
    │ └────────┘ │  │ └────────┘ │  │ └────────┘ │
    └────────────┘  └────────────┘  └────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.8+
- QEMU (with system emulation for target architecture)
- GDB (with Python scripting support)
- Linux host (recommended) or macOS

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/fawkes.git
cd fawkes

# Install Python dependencies
pip install -r requirements.txt

# Install TUI dependencies
pip install rich pynput

# Create default configuration directory
mkdir -p ~/.fawkes/{images,corpus,crashes,jobs,shared,screenshots}
```

### Setting Up a VM Image

```bash
# Create a QEMU disk image
qemu-img create -f qcow2 ~/.fawkes/images/target.qcow2 20G

# Install your target OS, then create a clean snapshot
qemu-system-x86_64 \
  -drive file=~/.fawkes/images/target.qcow2,format=qcow2 \
  -m 4096 -enable-kvm \
  -monitor stdio

# Inside QEMU monitor, save a clean snapshot
(qemu) savevm clean
(qemu) quit
```

### Running Your First Fuzz Job

```bash
# Basic local fuzzing
python main.py --mode local \
  --disk-image ~/.fawkes/images/target.qcow2 \
  --input-dir ~/seeds/ \
  --snapshot-name clean \
  --arch x86_64

# With TUI monitoring
python main.py --mode local --tui \
  --disk-image ~/.fawkes/images/target.qcow2 \
  --input-dir ~/seeds/

# With intelligent fuzzer
python main.py --mode local \
  --fuzzer intelligent \
  --fuzzer-config ~/.fawkes/intelligent_fuzzer.json \
  --input-dir ~/seeds/
```

---

## Modes of Operation

### Local Mode (Single Node)

Run fuzzing on a single machine with one or more parallel VMs:

```bash
python main.py --mode local \
  --parallel 4 \
  --disk-image target.qcow2 \
  --input-dir ./corpus/
```

### Controller Mode (Distributed)

Start a controller to coordinate multiple workers:

```bash
python main.py --mode controller \
  --controller_host 0.0.0.0 \
  --controller_port 5000 \
  --job-dir ~/.fawkes/jobs/
```

### Worker Mode (Distributed)

Connect workers to a controller:

```bash
python main.py --mode worker \
  --controller_host 192.168.1.100 \
  --controller_port 5000
```

---

## Fuzzer Types

### File Fuzzer (Default)

Mutates files and delivers them to the target VM via shared directory:

```bash
python main.py --fuzzer file --input-dir ./pdf_samples/
```

### Intelligent Fuzzer

Crash-guided fuzzer that adapts mutation strategies based on results:

```json
{
  "mutations_per_seed": 1000,
  "output_dir": "~/.fawkes/testcases",
  "network_mode": false
}
```

```bash
python main.py --fuzzer intelligent \
  --fuzzer-config intelligent_fuzzer.json
```

### Network Fuzzer

Fuzz network protocols with conversation-aware mutations:

```bash
python main.py --fuzzer network \
  --fuzzer-config network_fuzzer.json \
  --input-dir ./pcap_conversations/
```

---

## Guest Agents

Fawkes uses lightweight agents inside VMs to detect crashes and collect information.

### Windows Agent

```bash
# Copy agent to shared directory
cp agents/FawkesCrashAgentWindows.exe ~/.fawkes/shared/

# Inside Windows VM, run from shared drive
Z:\FawkesCrashAgentWindows.exe
```

### Linux Agent

```bash
# Compile the Linux agent
g++ -o FawkesAgent agents/LinuxCrashAgent.cpp -lpthread

# Run on target system
./FawkesAgent
```

---

## Project Structure

```
fawkes/
├── main.py                 # Entry point
├── config.py               # Configuration management
├── qemu.py                 # QEMU VM management
├── gdb.py                  # GDB integration
├── harness.py              # Fuzzing harness
├── tui.py                  # Terminal UI
├── replay.py               # Crash replay functionality
├── agents/                 # Guest VM agents
│   ├── FawkesCrashAgent-Windows.cpp
│   ├── FawkesCrashAgentWindows.exe
│   └── LinuxCrashAgent.cpp
├── fuzzers/                # Fuzzer implementations
│   ├── file_fuzzer.py
│   ├── intelligent_fuzzer.py
│   ├── corpus_manager.py
│   └── dictionary.py
├── fawkes/                 # Core modules
│   ├── modes/              # Operating modes
│   │   ├── local.py
│   │   ├── controller.py
│   │   └── worker.py
│   └── logger.py
├── analysis/               # Crash analysis
├── crash_analysis/         # Crash deduplication
├── scheduler/              # Job scheduling
├── differential/           # Differential fuzzing
├── network/                # Network fuzzing support
├── kernel/                 # Kernel fuzzing support
├── sanitizers/             # Sanitizer integration
├── web/                    # Web UI
│   ├── api/                # REST API (FastAPI)
│   └── frontend/           # React frontend
└── tests/                  # Test suite
```

---

## Command Line Reference

```bash
python main.py [OPTIONS]

Options:
  --mode {local,controller,worker}  Operating mode (default: local)
  --config PATH                     Path to config file
  --disk-image PATH                 QEMU disk image path
  --input-dir PATH                  Seed/corpus directory
  --snapshot-name NAME              VM snapshot name (default: clean)
  --arch ARCH                       Target architecture (default: x86_64)
  --timeout SECONDS                 Timeout per test case (default: 60)
  --parallel N                      Number of parallel VMs (0=auto)
  --fuzzer TYPE                     Fuzzer plugin (file, intelligent, network)
  --fuzzer-config PATH              Fuzzer configuration JSON
  --crash-dir PATH                  Directory for crash archives
  --tui                             Launch TUI interface
  --no-headless                     Show VM display (not headless)
  --vfs                             Use VirtFS sharing (Linux guests)
  --smb                             Use SMB sharing (Windows guests)
  --analyze-crashes                 Analyze existing crash archives
  --log-level LEVEL                 Logging level (DEBUG, INFO, WARNING, ERROR)
```

---

## CLI Tools

Fawkes includes several standalone CLI tools:

| Tool | Description |
|------|-------------|
| `fawkes-arch` | Architecture-specific QEMU configuration |
| `fawkes-auth` | Authentication and access control |
| `fawkes-bench` | Performance benchmarking |
| `fawkes-corpus` | Corpus management and minimization |
| `fawkes-diff` | Differential fuzzing launcher |
| `fawkes-replay` | Replay crashes for analysis |
| `fawkes-scheduler` | Job scheduling utilities |
| `fawkes-snapshot` | Snapshot management |
| `fawkes-stats` | Statistics and reporting |
| `fawkes-triage` | Crash triage and classification |

---

## Web UI

Fawkes includes a web interface for monitoring and management.

### Starting the Web UI

```bash
cd web

# Install API dependencies
cd api && pip install -e . && cd ..

# Install frontend dependencies
cd frontend && npm install && cd ..

# Start API server
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Start frontend (development)
cd frontend && npm run dev
```

### Web UI Features

- Real-time fuzzing statistics dashboard
- Crash viewer with deduplication
- Corpus management
- Job configuration and control
- Worker status monitoring

---

## Supported Architectures

| Architecture | QEMU System | Status |
|--------------|-------------|--------|
| x86_64 | qemu-system-x86_64 | Full Support |
| i386 | qemu-system-i386 | Full Support |
| ARM | qemu-system-arm | Full Support |
| AArch64 | qemu-system-aarch64 | Full Support |
| MIPS | qemu-system-mips | Full Support |
| MIPS (LE) | qemu-system-mipsel | Full Support |
| SPARC | qemu-system-sparc | Full Support |
| SPARC64 | qemu-system-sparc64 | Full Support |
| PowerPC | qemu-system-ppc | Full Support |
| PowerPC64 | qemu-system-ppc64 | Full Support |

---

## Configuration

Configuration is stored in `~/.fawkes/` by default:

```
~/.fawkes/
├── config.json         # Main configuration
├── registry.json       # VM registry
├── fawkes.db           # Local database
├── controller.db       # Controller database
├── images/             # VM disk images
├── corpus/             # Seed corpus
├── crashes/            # Crash archives
├── jobs/               # Job configurations
├── shared/             # Shared directory for VMs
└── screenshots/        # VM screenshots
```

---

## Crash Analysis

Fawkes automatically:
- Captures crash dumps with full context
- Deduplicates crashes by stack hash
- Classifies crash types (buffer overflow, null deref, etc.)
- Generates reproducible test cases

View crashes:
```bash
# List crashes
ls ~/.fawkes/crashes/

# Replay a crash
python replay.py --crash ~/.fawkes/crashes/crash_001.zip

# Analyze all crashes
python main.py --analyze-crashes
```

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/new-feature`)
3. Commit your changes (`git commit -m 'feat: add new feature'`)
4. Push to the branch (`git push origin feat/new-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [QEMU](https://www.qemu.org/) - Machine emulator and virtualizer
- [GDB](https://www.gnu.org/software/gdb/) - GNU Debugger
- [AFL](https://lcamtuf.coredump.cx/afl/) - Inspiration for mutation strategies
- [Rich](https://github.com/Textualize/rich) - TUI framework
