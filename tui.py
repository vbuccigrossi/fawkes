from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.align import Align
from rich.columns import Columns
from rich.table import Table
from rich.theme import Theme
from rich.prompt import Prompt
from rich.padding import Padding
from rich.console import Group
import termios
import time
import argparse
import json
import os
import sys
import logging
import threading
import select
import tty
import shutil
import zipfile
from io import BytesIO
from datetime import datetime

# Fawkes specific imports
from logger import setup_fawkes_logger
from config import FawkesConfig, VMRegistry, FawkesConfigError
from modes.local import run_local_mode
from modes.controller import run_controller_mode
from modes.worker import run_worker_mode
from globals import shutdown_event, get_max_vms, SystemResources

# Fawkes Specific imports to collect data from the system
from db.db import FawkesDB
from monitor import ResourceMonitor
from db.controller_db import ControllerDB

# Performance tracking
from fawkes.performance import perf_tracker

##############################################################################
#                               GLOBALS & THEMES
##############################################################################
should_exit = False
in_edit_mode = False  # True when blocking for a field edit
in_crash_detail = False  # True when viewing crash details

# Define two themes with obvious differences
console = Console()

# A list of the running local jobs so we can find them to stop them if needed
local_jobs = []

# Save the original TTY Settings so we can reset them properly
STDIN_FILENO = sys.stdin.fileno()
original_tty_settings = termios.tcgetattr(STDIN_FILENO)

# Controls for the job page
job_page = 0
jobs_per_page = 6

# Controls for the crash page
crash_page = 0
crashes_per_page = 10
selected_crash = 0
crash_filters = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}  # Default: show all

# Global pagination variables
args_page = 0         # current page (0-based)
args_per_page = 20    # number of args per page

# Defined group boundaries for left/right navigation
# GENERAL (0-9), TARGET+FUZZ (10-17), SHARING+STORAGE (18-22), DB+NETWORK (23-28),
# AUTHENTICATION (29-34), SCHEDULER (35-36), WORKERS (37), ADVANCED (38-54)
group_boundaries = [0, 10, 18, 23, 29, 35, 37, 38, 55]

# Layout definitions
def create_config_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="body", ratio=2),
        Layout(name="help", size=9),
        Layout(name="footer", size=3),
    )
    return layout

def create_dashboard_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="body", ratio=2),
        Layout(name="jobs", size=20),
        Layout(name="help", size=9),
        Layout(name="footer", size=3),
    )
    return layout

def create_help_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="body", size=30),
        Layout(name="help", size=9),
        Layout(name="footer", size=3),
    )
    return layout

def create_crashes_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="body", size=30),
        Layout(name="help", size=9),
        Layout(name="footer", size=3),
    )
    return layout

def create_performance_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="body", size=30),
        Layout(name="help", size=9),
        Layout(name="footer", size=3),
    )
    return layout

def create_snapshots_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="body", size=30),
        Layout(name="help", size=9),
        Layout(name="footer", size=3),
    )
    return layout

def create_auth_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="body", size=30),
        Layout(name="help", size=9),
        Layout(name="footer", size=3),
    )
    return layout

def create_fuzzer_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="body", size=30),
        Layout(name="help", size=9),
        Layout(name="footer", size=3),
    )
    return layout

def create_login_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=4),
        Layout(name="body", size=30),
        Layout(name="footer", size=3),
    )
    return layout

# Authentication state
is_authenticated = False
current_user = None
session_token = None
login_error = None

# Current screen and layout
current_screen = "configuration"  # configuration, dashboard, help, crashes, performance, snapshots, auth, login
previous_screen = "configuration"  # Track last non-help screen
layouts = {
    "configuration": create_config_layout(),
    "dashboard": create_dashboard_layout(),
    "help": create_help_layout(),
    "crashes": create_crashes_layout(),
    "performance": create_performance_layout(),
    "snapshots": create_snapshots_layout(),
    "auth": create_auth_layout(),
    "fuzzer": create_fuzzer_layout(),
    "login": create_login_layout(),
}

mode = "local"
config_file = "~/.fawkes/config.json"
selected_field = 0  # Overall index among fields

reset_config = {
    "max_parallel": 3,
    "controller_host": "0.0.0.0",
    "controller_port": 5000,
    "disk_image": "~/fawkes_test/target.qcow2",
    "input_dir": "~/fuzz_inputs",
    "share_dir": "~/fawkes_shared",
    "poll_interval": 1.0,
    "max_retries": 3,
    "db_path": "~/.fawkes/fawkes.db",
    "controller_db_path": "~/.fawkes/controller.db",
    "snapshot_name": "clean",
    "tui": False,
    "arch": "x86_64",
    "cleanup_stopped_vms": True,
    "timeout": 60,
    "loop": True,
    "no_headless": False,
    "vfs": False,
    "smb": True,
    "crash_dir": "./fawkes/crashes",
    "fuzzer": "file",
    "fuzzer_config": None,
    "fuzzer_stats_file": "~/.fawkes/fuzzer_stats.json",
    "fuzzer_dictionary": None,
    "workers": ["127.0.0.1", "127.0.0.1", "127.0.0.1"],
    "job_dir": "~/.fawkes/jobs/",
    "job_name": "change_me",
    "vm_params": "",
    "log_level": "ERROR",
    # Authentication options
    "auth_enabled": False,
    "tls_enabled": False,
    "controller_api_key": "",
    "auth_db_path": "~/.fawkes/auth.db",
    "tls_cert": "~/.fawkes/certs/fawkes.crt",
    "tls_key": "~/.fawkes/certs/fawkes.key",
    # Scheduler options
    "allocation_strategy": "load_aware",
    "heartbeat_timeout": 90,
    "worker_tags": [],
    # Performance options
    "memory": "512M",
    "max_parallel_vms": 0,
    # Advanced Fuzzing Features
    # Persistent Mode / Snapshot Fuzzing
    "enable_persistent": False,
    "tmpfs_path": "/tmp/fawkes_snapshots",
    "tmpfs_size": "2G",
    # Corpus Synchronization
    "enable_corpus_sync": False,
    "sync_mode": "filesystem",
    "sync_interval": 60,
    # Grammar-Based Fuzzing
    "enable_grammar": False,
    "grammar_file": "",
    # Network Protocol Fuzzing
    "enable_network_fuzzing": False,
    "network_protocol": "http",
    # Kernel Fuzzing
    "enable_kernel_fuzzing": False,
    "kernel_syscalls": "open,read,write,close,mmap",
    # Stack Deduplication
    "enable_stack_dedup": True,
    # Time Compression
    "enable_time_compression": False,
    "time_compression_shift": "auto",
    "skip_idle_loops": True,
}

default_config = {
    "max_parallel": 3,
    "controller_host": "0.0.0.0",
    "controller_port": 5000,
    "disk_image": "~/fawkes_test/target.qcow2",
    "input_dir": "~/fuzz_inputs",
    "share_dir": "~/fawkes_shared",
    "poll_interval": 1.0,
    "max_retries": 3,
    "db_path": "~/.fawkes/fawkes.db",
    "controller_db_path": "~/.fawkes/controller.db",
    "snapshot_name": "clean",
    "tui": False,
    "arch": "x86_64",
    "cleanup_stopped_vms": True,
    "timeout": 60,
    "loop": True,
    "no_headless": False,
    "vfs": False,
    "smb": True,
    "crash_dir": "./fawkes/crashes",
    "fuzzer": "file",
    "fuzzer_config": None,
    "fuzzer_stats_file": "~/.fawkes/fuzzer_stats.json",
    "fuzzer_dictionary": None,
    "workers": ["127.0.0.1", "127.0.0.1", "127.0.0.1"],
    "job_dir": "~/.fawkes/jobs/",
    "job_name": "change_me",
    "vm_params": "",
    "log_level": "ERROR",
    # Authentication options
    "auth_enabled": False,
    "tls_enabled": False,
    "controller_api_key": "",
    "auth_db_path": "~/.fawkes/auth.db",
    "tls_cert": "~/.fawkes/certs/fawkes.crt",
    "tls_key": "~/.fawkes/certs/fawkes.key",
    # Scheduler options
    "allocation_strategy": "load_aware",
    "heartbeat_timeout": 90,
    "worker_tags": [],
    # Performance options
    "memory": "512M",
    "max_parallel_vms": 0,
    # Advanced Fuzzing Features
    # Persistent Mode / Snapshot Fuzzing
    "enable_persistent": False,
    "tmpfs_path": "/tmp/fawkes_snapshots",
    "tmpfs_size": "2G",
    # Corpus Synchronization
    "enable_corpus_sync": False,
    "sync_mode": "filesystem",
    "sync_interval": 60,
    # Grammar-Based Fuzzing
    "enable_grammar": False,
    "grammar_file": "",
    # Network Protocol Fuzzing
    "enable_network_fuzzing": False,
    "network_protocol": "http",
    # Kernel Fuzzing
    "enable_kernel_fuzzing": False,
    "kernel_syscalls": "open,read,write,close,mmap",
    # Stack Deduplication
    "enable_stack_dedup": True,
    # Time Compression
    "enable_time_compression": False,
    "time_compression_shift": "auto",
    "skip_idle_loops": True,
}

# Fields: (section, config_key, display_label)
fields = [
    ("GENERAL", "job_name",             "Job Name"),
    ("GENERAL", "max_parallel",         "Max VMs"),
    ("GENERAL", "max_parallel_vms",     "Max Parallel VMs"),
    ("GENERAL", "memory",               "VM Memory"),
    ("GENERAL", "tui",                  "TUI"),
    ("GENERAL", "cleanup_stopped_vms",  "Cleanup VMs"),
    ("GENERAL", "timeout",              "Timeout"),
    ("GENERAL", "loop",                 "Loop"),
    ("GENERAL", "no_headless",          "No Headless"),
    ("GENERAL", "vm_params",            "VM Params"),
    ("TARGET + FUZZ", "disk_image",          "Disk Image"),
    ("TARGET + FUZZ", "input_dir",           "Input Dir"),
    ("TARGET + FUZZ", "snapshot_name",       "Snapshot Name"),
    ("TARGET + FUZZ", "arch",                "Arch"),
    ("TARGET + FUZZ", "fuzzer",              "Fuzzer"),
    ("TARGET + FUZZ", "fuzzer_config",       "Fuzzer Config"),
    ("TARGET + FUZZ", "fuzzer_stats_file",   "Fuzzer Stats"),
    ("TARGET + FUZZ", "fuzzer_dictionary",   "Fuzzer Dictionary"),
    ("SHARING + STORAGE", "vfs",            "VFS"),
    ("SHARING + STORAGE", "smb",            "SMB"),
    ("SHARING + STORAGE", "crash_dir",      "Crash Dir"),
    ("SHARING + STORAGE", "share_dir",      "Share Dir"),
    ("SHARING + STORAGE", "log_level",      "Log Level"),
    ("DB + NETWORK", "db_path",             "DB"),
    ("DB + NETWORK", "controller_db_path",  "Controller DB"),
    ("DB + NETWORK", "controller_host",     "Host"),
    ("DB + NETWORK", "controller_port",     "Port"),
    ("DB + NETWORK", "poll_interval",       "Poll Interval"),
    ("DB + NETWORK", "job_dir",             "Job Dir"),
    ("AUTHENTICATION", "auth_enabled",      "Auth Enabled"),
    ("AUTHENTICATION", "tls_enabled",       "TLS Enabled"),
    ("AUTHENTICATION", "controller_api_key","API Key"),
    ("AUTHENTICATION", "auth_db_path",      "Auth DB"),
    ("AUTHENTICATION", "tls_cert",          "TLS Cert"),
    ("AUTHENTICATION", "tls_key",           "TLS Key"),
    ("SCHEDULER", "allocation_strategy",    "Strategy"),
    ("SCHEDULER", "heartbeat_timeout",      "Heartbeat Timeout"),
    ("WORKERS", "workers", "Workers"),
    # Advanced Fuzzing Features
    ("ADVANCED", "enable_persistent",       "Persistent Mode"),
    ("ADVANCED", "tmpfs_path",              "tmpfs Path"),
    ("ADVANCED", "tmpfs_size",              "tmpfs Size"),
    ("ADVANCED", "enable_corpus_sync",      "Corpus Sync"),
    ("ADVANCED", "sync_mode",               "Sync Mode"),
    ("ADVANCED", "sync_interval",           "Sync Interval (s)"),
    ("ADVANCED", "enable_grammar",          "Grammar Fuzzing"),
    ("ADVANCED", "grammar_file",            "Grammar File"),
    ("ADVANCED", "enable_network_fuzzing",  "Network Fuzzing"),
    ("ADVANCED", "network_protocol",        "Network Protocol"),
    ("ADVANCED", "enable_kernel_fuzzing",   "Kernel Fuzzing"),
    ("ADVANCED", "kernel_syscalls",         "Kernel Syscalls"),
    ("ADVANCED", "enable_stack_dedup",      "Stack Dedup"),
    ("ADVANCED", "enable_time_compression", "Time Compression"),
    ("ADVANCED", "time_compression_shift",  "icount Shift"),
    ("ADVANCED", "skip_idle_loops",         "Skip Idle Loops"),
]

# A list of argument entries: (argument, description)
args_help_entries = [
    ("db", "Sqlite3 db file location (e.g., ~/.fawkes/fawkes.db)."),
    ("controller db", "Sqlite3 db file location (e.g., ~/.fawkes/controller.db)."),
    ("disk image", "Path to the disk image (e.g., windows_98.qcow2) for local mode."),
    ("input dir", "Directory containing fuzz test inputs for local mode."),
    ("snapshot name", "Snapshot name to use for fuzzing (default: 'clean')."),
    ("arch", "Target architecture for QEMU (default: x86_64). Choices: i386, x86_64, aarch64, mips, mipsel, sparc, sparc64, arm, ppc, ppc64."),
    ("timeout", "Timeout per testcase in seconds. Default: 60"),
    ("Max VMs", "Number of parallel VMs (0 for auto). Default: 0"),
    ("Max Parallel VMs", "Maximum parallel VMs for performance control. Default: 0 (no limit)"),
    ("VM Memory", "Memory allocation for VMs (e.g., 256M, 512M, 1G). Default: 512M"),
    ("loop", "Run fuzzing in an infinite loop. Default: True"),
    ("seed dir", "Directory containing the seed files for fuzzing."),
    ("no_headless", "Turn off headless mode default False."),
    ("vfs", "Use VirtFS for sharing (Linux/Unix only)."),
    ("smb", "Use SMB for sharing (Windows only)."),
    ("crash dir", "Directory to store crash archives. Default: ./fawkes/crashes"),
    ("fuzzer", "Fuzzer plugin to use (file, network, intelligent). Default: file"),
    ("fuzzer config", "JSON config file for intelligent fuzzer (mutations, strategies, etc.)."),
    ("Fuzzer Stats", "Statistics file path for intelligent fuzzer. Default: ~/.fawkes/fuzzer_stats.json"),
    ("Fuzzer Dictionary", "Dictionary file for format-aware fuzzing. Auto-generated if not specified."),
    ("host", "The IP address to bind to in distributed mode (default: 0.0.0.0)."),
    ("port", "The port to listen on (default: 5000)."),
    ("poll interval", "How often the controller polls for results (default: 60)."),
    ("job dir", "The location for the job configs for the controller (default: ~/.fawkes/jobs/)."),
    ("workers", "A comma separated list of IP/Hostnames of the Fuzz Workers"),
    ("VM Params", "The base args to be passed to the VM on start (-smp 4 -cpu Skylake-Client-v3 -enable-kvm -m 4096)"),
    ("Auth Enabled", "Enable authentication for distributed mode. Default: False"),
    ("TLS Enabled", "Enable TLS encryption for network communication. Default: False"),
    ("API Key", "Controller API key for authentication in distributed mode."),
    ("Auth DB", "Path to authentication database. Default: ~/.fawkes/auth.db"),
    ("TLS Cert", "Path to TLS certificate file. Default: ~/.fawkes/certs/fawkes.crt"),
    ("TLS Key", "Path to TLS private key file. Default: ~/.fawkes/certs/fawkes.key"),
    ("Strategy", "Scheduler allocation strategy: load_aware, round_robin, first_fit. Default: load_aware"),
    ("Heartbeat Timeout", "Worker heartbeat timeout in seconds. Default: 90"),
    # Advanced Fuzzing Features
    ("Persistent Mode", "Enable persistent mode fuzzing for 10-400x speedup. Uses fast snapshot restoration. Default: False"),
    ("tmpfs Path", "Path to tmpfs mount for snapshot storage. RAM-based storage for 5-10x I/O speedup. Default: /tmp/fawkes_snapshots"),
    ("tmpfs Size", "Size of tmpfs mount (e.g., 1G, 2G, 4G). Stores snapshots in RAM. Default: 2G"),
    ("Corpus Sync", "Enable distributed corpus synchronization between workers. Shares interesting testcases. Default: False"),
    ("Sync Mode", "Corpus sync mode: filesystem, network, redis. Default: filesystem"),
    ("Sync Interval (s)", "How often to sync corpus in seconds. Default: 60"),
    ("Grammar Fuzzing", "Enable grammar-based fuzzing for structured inputs (JSON, XML, SQL, etc.). Default: False"),
    ("Grammar File", "Path to BNF/EBNF grammar file. Use builtin grammars: json, xml, sql, url, arithmetic, email."),
    ("Network Fuzzing", "Enable stateful network protocol fuzzing. Multi-stage protocol sequences. Default: False"),
    ("Network Protocol", "Protocol to fuzz: http, ftp, smtp, pop3, imap, ssh, telnet. Default: http"),
    ("Kernel Fuzzing", "Enable kernel fuzzing with syscall generation and KASAN integration. Default: False"),
    ("Kernel Syscalls", "Comma-separated list of syscalls to fuzz (e.g., open,read,write,ioctl,mmap). Default: open,read,write,close,mmap"),
    ("Stack Dedup", "Enable stack hash deduplication to identify unique crashes accurately. Default: True"),
    ("Time Compression", "Skip idle time, sleep() calls, and delays for 3-10x speedup. Uses QEMU icount mode. Works on Linux and Windows VMs. Default: False"),
    ("icount Shift", "QEMU icount shift parameter controlling time advancement rate. 'auto' lets QEMU optimize automatically. Options: auto, 0-10. Default: auto"),
    ("Skip Idle Loops", "Skip sleep() calls and idle loops (QEMU align=off,sleep=off). Maximizes speedup but may affect timing-sensitive apps. Default: True"),
    ("[F] Performance", "View real-time performance metrics including exec/sec, timing breakdowns, and snapshot optimization stats."),
    ("[M] Snapshots", "Manage QEMU snapshots. View available snapshots and their details. Use fawkes-snapshot CLI for management."),
    ("[A] Authentication", "View users and API keys. Manage authentication using the fawkes-auth CLI tool."),
    ("[Z] Fuzzer", "View intelligent fuzzer statistics including exec/sec, crashes by type, and mutation strategy effectiveness."),
    ("[D] Dashboard", "View active fuzzing jobs, VM status, and campaign statistics."),
    ("[X] Crashes", "Browse and filter crash reports. View crash details and navigate through crash history."),
    ("[C] Configuration", "Edit all Fawkes configuration options including auth, TLS, scheduler, and performance settings."),
]

def shutdown_handler(sig, frame):
    shutdown_event.set()

def get_group_index(field_index: int) -> int:
    """Return which group (0 to 6) the field_index belongs to."""
    for g in range(len(group_boundaries) - 1):
        if group_boundaries[g] <= field_index < group_boundaries[g + 1]:
            return g
    return 0

def jump_to_group(g: int):
    """Set selected_field to the start index of group g."""
    global selected_field
    if g < 0:
        g = 0
    if g > 6:  # We now have 7 groups (0-6)
        g = 6
    selected_field = group_boundaries[g]

##############################################################################
#                         ARGPARSE & CONFIG LOAD
##############################################################################

parser = argparse.ArgumentParser(description="Fawkes TUI")
parser.add_argument("--mode", choices=["local", "controller", "worker"], default="local",
                    help="Run in local or controller mode")
parser.add_argument("--log-level", default="ERROR", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                    help="Set the logging level for Fawkes.")
parser.add_argument("--quiet", action="store_true",
                    help="Minimize console output (overrides log-level to WARNING).")

args = parser.parse_args()
mode = args.mode

##############################################################################
#                               GLOBAL LOGGING
##############################################################################

if args.mode == "worker":
    log_level = logging._nameToLevel.get(args.log_level.upper(), logging.INFO)
    if args.quiet:
        log_level = logging.WARNING
    logger = setup_fawkes_logger(log_level,
                                 log_to_file=False,
                                 log_to_console=True,
                                 max_bytes=5 * 1024 * 1024,
                                 backup_count=2,
                                 use_color=True)
    logger.info(f"Starting Fawkes in '{args.mode}' mode...")
else:
    log_level = logging._nameToLevel.get(args.log_level.upper(), logging.INFO)
    if args.quiet:
        log_level = logging.WARNING
    logger = setup_fawkes_logger(log_level)
    logger.info(f"Starting Fawkes in '{args.mode}' mode...")

##############################################################################
#                            SETUP SYSTEM MODE
##############################################################################

if mode == "controller" and not default_config["workers"]:
    worker_ips = Prompt.ask("Enter worker IPs (comma-separated)", default="127.0.0.1,127.0.0.1,127.0.0.1")
    default_config["workers"] = [ip.strip() for ip in worker_ips.split(",")]

if mode == "worker":
    cfg = FawkesConfig.load()
    try:
        registry = VMRegistry(cfg.get("registry_file"))
    except FawkesConfigError as e:
        logger.error(f"Failed to load VM registry: {e}")
        sys.exit(1)
    try:
        run_worker_mode(cfg)
    except Exception as e:
        logger.error(f"Failed to start Fawkes in worker mode with error: {e}")

def load_config():
    config_path = os.path.expanduser(config_file)
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            default_config.update(json.load(f))

def save_config():
    config_path = os.path.expanduser(config_file)
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(default_config, f, indent=4)
    console.log("Configuration saved.")

def save_config_controller():
    global default_config
    config_path = os.path.expanduser(default_config["job_dir"])
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(default_config, f, indent=4)
    console.log("Configuration saved.")

load_config()

##############################################################################
#                     DASHBOARD DATA COLLECTION CLASS
##############################################################################

class FawkesDataCollection:
    def __init__(self, cfg: FawkesConfig, registry: VMRegistry, shutdown_event):
        self.cfg = cfg
        self.registry = registry
        self.shutdown_event = shutdown_event

        try:
            if mode == "local":
                self.local_db = FawkesDB(cfg.db_path)
                logger.debug(f"Connected to database: {cfg.db_path} in local mode")
        except Exception as e:
            logger.error(f"Failed to open local mode database, current mode: {mode}")

        try:
            if mode == "controller":
                self.controller_db = ControllerDB(cfg.controller_db_path)
                logger.debug(f"Connected to database: {cfg.controller_db_path} in controller mode")
        except Exception as e:
            logger.error(f"Failed to open controller database, current mode: {mode}")

        self.monitor = ResourceMonitor(cfg, registry)
        self.system_resources = SystemResources()

    def get_system_metrics(self):
        """Pull system metrics, adapted for mode."""
        if mode == "local":
            stats = self.monitor.update()
            max_vms = self.system_resources.get_max_vms()
            total = stats['running_vms'] + max_vms

            # Check time compression status
            time_comp_status = "[green]ON[/]" if default_config.get('enable_time_compression', False) else "[dim]OFF[/]"

            return [
                ("VMs Online", f"{stats['running_vms']} / {total}"),
                ("CPU Usage", f"{stats['cpu_percent']:.1f}%"),
                ("RAM Usage", f"{stats['memory_percent']:.1f}%"),
                ("Time Compress", time_comp_status),
                ("", ""),
                ("", ""),
            ]
        elif mode == "controller":
            workers = self.controller_db.get_workers()
            online = sum(1 for w in workers if w["status"] == "online")
            total = len(workers)
            return [
                ("Workers Online", f"{online} / {total}"),
                ("CPU Usage", "N/A"),
                ("RAM Usage", "N/A"),
                ("", ""),
                ("", ""),
                ("", ""),
            ]

    def get_test_stats(self):
        """Get testcase stats, adapted for mode."""
        if mode == "local":
            jobs = self.local_db._conn.execute(
                "SELECT job_id, name, total_testcases, generated_testcases FROM jobs WHERE status='running'"
            ).fetchall()
            total_jobs = len(jobs)
            total_tc = sum(job[2] or 0 for job in jobs)
            gen_tc = sum(job[3] or 0 for job in jobs)
            if total_jobs > 0:
                job_ids = tuple(job[0] for job in jobs)
                total_time = self.local_db._conn.execute(
                    "SELECT SUM(execution_time) FROM testcases WHERE job_id IN (SELECT job_id FROM jobs WHERE status='running')"
                ).fetchone()[0] or 0
                total_time /= 1000
            else:
                total_time = 0
            fuzz_rate = f"{(gen_tc / total_time) * 3600:.1f}/h" if total_time > 0 else "N/A"
            return [
                ("Total Jobs", str(total_jobs)),
                ("Testcases", f"{gen_tc:,} / {total_tc:,}"),
                ("Fuzz Rate", fuzz_rate),
                ("", ""),
                ("", ""),
                ("", ""),
            ]
        elif mode == "controller":
            jobs = self.controller_db.conn.execute(
                "SELECT job_id, status FROM jobs"
            ).fetchall()
            total_jobs = len(jobs)
            running = sum(1 for j in jobs if j[1] == "running")
            return [
                ("Total Jobs", str(total_jobs)),
                ("Running Jobs", str(running)),
                ("Fuzz Rate", "N/A"),
                ("", ""),
                ("", ""),
                ("", ""),
            ]

    def get_crash_stats(self):
        """Aggregate crash stats, adapted for mode."""
        if mode == "local":
            crashes = self.local_db._conn.execute(
                "SELECT crash_type, exploitability, COUNT(*) FROM crashes GROUP BY crash_type, exploitability"
            ).fetchall()
            total = sum(c[2] for c in crashes)
            unique = len(set(c[0] + (c[1] or "UNKNOWN") for c in crashes))
            high = sum(c[2] for c in crashes if c[1] == "HIGH")
            medium = sum(c[2] for c in crashes if c[1] == "MEDIUM")
            low = sum(c[2] for c in crashes if c[1] == "LOW")
            return [
                ("Crashes", str(total)),
                ("Unique", str(unique)),
                ("[red]High[/]", str(high)),
                ("[yellow]Medium[/]", str(medium)),
                ("[blue]Low[/]", str(low)),
                ("[white]Unknown[/]", str(total - high - medium - low)),
            ]
        elif mode == "controller":
            crashes = self.controller_db.conn.execute(
                "SELECT exploitability, COUNT(*) FROM crashes GROUP BY exploitability"
            ).fetchall()
            total = sum(c[1] for c in crashes)
            unique = len(crashes)
            high = sum(c[1] for c in crashes if c[0] == "HIGH")
            medium = sum(c[1] for c in crashes if c[0] == "MEDIUM")
            low = sum(c[1] for c in crashes if c[0] == "LOW")
            return [
                ("Crashes", str(total)),
                ("Unique", str(unique)),
                ("[red]High[/]", str(high)),
                ("[yellow]Medium[/]", str(medium)),
                ("[blue]Low[/]", str(low)),
                ("[white]Unknown[/]", str(total - high - medium - low)),
            ]

    def get_active_jobs(self):
        """List active jobs with detailed stats, adapted for mode."""
        if mode == "local":
            jobs = self.local_db._conn.execute(
                """
                SELECT job_id, name, status, vm_count, total_testcases
                FROM jobs
                WHERE status IN ('running', 'queued', 'pending', 'completed')
                """
            ).fetchall()
            job_data = []
            for job in jobs:
                job_id, name, status, vm_count, total_tc = job
                crashes = self.local_db._conn.execute(
                    "SELECT exploitability, COUNT(*) FROM crashes WHERE job_id = ? GROUP BY exploitability",
                    (job_id,)
                ).fetchall()
                total_crashes = sum(c[1] for c in crashes)
                exploits = {exp or "Unknown": count for exp, count in crashes}
                for exp in ["High", "Medium", "Low", "Unknown"]:
                    if exp not in exploits:
                        exploits[exp] = 0
                job_data.append({
                    "id": str(job_id),
                    "name": str(name),
                    "status": str(status.upper()),
                    "vms": str(vm_count or 0),
                    "total_tc": str(total_tc or 0),
                    "crashes": str(total_crashes),
                    "exploits": exploits
                })
            return job_data
        elif mode == "controller":
            jobs = self.controller_db.conn.execute(
                """
                SELECT j.job_id, j.config, j.status, ja.worker_id
                FROM jobs j
                LEFT JOIN job_assignments ja ON j.job_id = ja.job_id
                WHERE j.status IN ('running', 'pending', 'queued', 'completed')
                """
            ).fetchall()
            job_data = []
            for job in jobs:
                job_id, config_json, status, worker_id = job
                config = json.loads(config_json)
                name = config.get("name", f"Job SPRINKLES {job_id}")
                vms = 1 if worker_id else 0
                total_tc = config.get("total_testcases", 0)
                crashes = self.controller_db.conn.execute(
                    "SELECT exploitability, COUNT(*) FROM crashes WHERE job_id = ? GROUP BY exploitability",
                    (job_id,)
                ).fetchall()
                total_crashes = sum(c[1] for c in crashes)
                exploits = {exp or "Unknown": count for exp, count in crashes}
                for exp in ["High", "Medium", "Low", "Unknown"]:
                    if exp not in exploits:
                        exploits[exp] = 0
                job_data.append({
                    "id": str(job_id),
                    "name": str(name),
                    "status": str(status.upper()),
                    "vms": str(vms),
                    "total_tc": str(total_tc),
                    "crashes": str(total_crashes),
                    "exploits": exploits
                })
            return job_data

    def get_crash_feed(self):
        """Show recent crashes, adapted for mode."""
        if mode == "local":
            crashes = self.local_db._conn.execute(
                "SELECT crash_id, crash_type, signature, exploitability, job_id FROM crashes ORDER BY timestamp DESC LIMIT 5"
            ).fetchall()
            return [
                {
                    "id": str(c[0]),
                    "type": c[1] or "Unknown",
                    "sig": (c[2] or "N/A")[:8],
                    "exp": f"[{self._exp_color(c[3])}]{c[3] or 'N/A'}",
                    "job": str(c[4] or "N/A"),
                    "path": f"/crashes/{c[0]}.zip"
                }
                for c in crashes
            ]
        elif mode == "controller":
            crashes = self.controller_db.conn.execute(
                "SELECT crash_id, job_id, worker_id, crash_type, signature, exploitability, timestamp FROM crashes ORDER BY timestamp DESC LIMIT 5"
            ).fetchall()
            return [
                {
                    "id": str(c[0]),
                    "type": c[3] or "Unknown",
                    "sig": (c[4] or "N/A")[:8],
                    "exp": f"[{self._exp_color(c[5])}]{c[5] or 'N/A'}",
                    "job": str(c[1] or "N/A"),
                    "path": f"/crashes/{c[0]}.zip"
                }
                for c in crashes
            ]

    def get_crash_feed_filtered(self, exploitability_levels, page=0, per_page=10):
        """Get paginated crashes filtered by exploitability."""
        offset = page * per_page
        if not exploitability_levels:
            return []
        levels = tuple(level for level in exploitability_levels)
        if mode == "local":
            query = """
                SELECT crash_id, crash_type, signature, exploitability, job_id, timestamp
                FROM crashes
                WHERE exploitability IN ({})
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """.format(','.join('?' for _ in levels))
            crashes = self.local_db._conn.execute(query, levels + (per_page, offset)).fetchall()
            return [
                {
                    "id": str(c[0]),
                    "type": c[1] or "Unknown",
                    "sig": (c[2] or "N/A")[:8],
                    "exp": c[3] or "UNKNOWN",
                    "exp_colored": f"[{self._exp_color(c[3])}]{c[3] or 'UNKNOWN'}[/]",
                    "job": str(c[4] or "N/A"),
                    "path": f"/crashes/{c[0]}.zip",
                    "timestamp": c[5] or "N/A"
                }
                for c in crashes
            ]
        elif mode == "controller":
            query = """
                SELECT crash_id, job_id, worker_id, crash_type, signature, exploitability, timestamp
                FROM crashes
                WHERE exploitability IN ({})
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """.format(','.join('?' for _ in levels))
            crashes = self.controller_db.conn.execute(query, levels + (per_page, offset)).fetchall()
            return [
                {
                    "id": str(c[0]),
                    "type": c[3] or "Unknown",
                    "sig": (c[4] or "N/A")[:8],
                    "exp": c[5] or "UNKNOWN",
                    "exp_colored": f"[{self._exp_color(c[5])}]{c[5] or 'UNKNOWN'}[/]",
                    "job": str(c[1] or "N/A"),
                    "path": f"/crashes/{c[0]}.zip",
                    "timestamp": c[6] or "N/A"
                }
                for c in crashes
            ]

    def get_crash_details(self, crash_id):
        """Fetch detailed info for a specific crash."""
        crash_data = {}
        if mode == "local":
            crash = self.local_db._conn.execute(
                "SELECT crash_id, crash_type, signature, exploitability, job_id, timestamp FROM crashes WHERE crash_id = ?",
                (crash_id,)
            ).fetchone()
            if crash:
                crash_data = {
                    "id": str(crash[0]),
                    "type": crash[1] or "Unknown",
                    "sig": crash[2] or "N/A",
                    "exp": crash[3] or "UNKNOWN",
                    "job": str(crash[4] or "N/A"),
                    "path": f"/crashes/{crash[0]}.zip",
                    "timestamp": crash[5] or "N/A"
                }
        elif mode == "controller":
            crash = self.controller_db.conn.execute(
                "SELECT crash_id, job_id, worker_id, crash_type, signature, exploitability, timestamp FROM crashes WHERE crash_id = ?",
                (crash_id,)
            ).fetchone()
            if crash:
                crash_data = {
                    "id": str(crash[0]),
                    "type": crash[3] or "Unknown",
                    "sig": crash[4] or "N/A",
                    "exp": crash[5] or "UNKNOWN",
                    "job": str(crash[1] or "N/A"),
                    "path": f"/crashes/{crash[0]}.zip",
                    "timestamp": crash[6] or "N/A"
                }
        
        # Attempt to read crash log from package
        crash_log = "Not available"
        if crash_data.get("path"):
            crash_path = os.path.expanduser(crash_data["path"])
            try:
                with zipfile.ZipFile(crash_path, 'r') as z:
                    if "crash.log" in z.namelist():
                        with z.open("crash.log") as f:
                            crash_log = f.read().decode('utf-8', errors='ignore')[:1000]  # Limit to 1000 chars
                    else:
                        crash_log = "No crash.log found in package"
            except Exception as e:
                logger.error(f"Failed to read crash package {crash_path}: {e}")
                crash_log = f"Error reading package: {e}"
        
        crash_data["crash_log"] = crash_log
        return crash_data

    def _exp_color(self, exp):
        """Return color for exploitability."""
        if exp == "HIGH":
            return "red"
        elif exp == "MEDIUM":
            return "yellow"
        elif exp == "LOW":
            return "blue"
        return "white"

##############################################################################
#                   For resetting back to install
##############################################################################

def clear_fawkes_dir():
    fawkes_dir = os.path.expanduser("~/.fawkes")
    try:
        if os.path.exists(fawkes_dir):
            shutil.rmtree(fawkes_dir)
            logger.info(f"Successfully cleared {fawkes_dir}")
        else:
            logger.debug(f"Directory {fawkes_dir} does not exist, nothing to clear")
    except Exception as e:
        logger.error(f"Failed to clear {fawkes_dir}: {e}", exc_info=True)
        raise

##############################################################################
#                   For reading raw input from the TTY
##############################################################################

def prompt_user(prompt: str = "> ") -> str:
    sys.stdout.write(prompt)
    sys.stdout.flush()
    buffer_chars = []
    while True:
        ready, _, _ = select.select([sys.stdin], [], [], 0.1)
        if ready:
            ch = sys.stdin.read(1)
            if ch in ('\r', '\n'):
                sys.stdout.write("\n")
                sys.stdout.flush()
                break
            elif ch == '\x7f':
                if buffer_chars:
                    buffer_chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            else:
                buffer_chars.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()
        else:
            pass
    return "".join(buffer_chars)

##############################################################################
#                         UI BUILDING FUNCTIONS
##############################################################################

def config_table(title: str, row_info: list[tuple[str, str, str]], highlight_idx: int = -1):
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="left", style="bold bright_white", ratio=1)
    table.add_column(justify="left", style="bright_cyan", ratio=2)
    for i, (section, cfg_key, display_label) in enumerate(row_info):
        if cfg_key:
            value = str(default_config[cfg_key])
        else:
            value = " "
        if not value:
            value = "Not set"
        style = "reverse" if i == highlight_idx else ""
        if value and display_label:
            table.add_row(f"{display_label}:", f"{value}", style=style)
        else:
            table.add_row(f"{display_label} ", f"{value}", style=style)
    return Panel(table, title=f"[bold bright_blue]{title}", border_style="bright_blue")

def update_config_body(layout):
    # Group all fields by their section
    general_fields = [f for f in fields if f[0] == "GENERAL"]
    target_fields = [f for f in fields if f[0] == "TARGET + FUZZ"]
    sharing_fields = [f for f in fields if f[0] == "SHARING + STORAGE"]
    dbnet_fields = [f for f in fields if f[0] == "DB + NETWORK"]
    auth_fields = [f for f in fields if f[0] == "AUTHENTICATION"]
    scheduler_fields = [f for f in fields if f[0] == "SCHEDULER"]
    worker_fields = [f for f in fields if f[0] == "WORKERS"]

    def highlight_index(base, count):
        """Return the local index if selected_field is in this group's range"""
        if base <= selected_field < base + count:
            return selected_field - base
        return -1

    # Calculate highlights using the correct group_boundaries
    # GENERAL: 0-9 (10 fields)
    general_highlight = highlight_index(0, len(general_fields))
    # TARGET+FUZZ: 10-17 (8 fields)
    target_highlight = highlight_index(10, len(target_fields))
    # SHARING+STORAGE: 18-22 (5 fields)
    sharing_highlight = highlight_index(18, len(sharing_fields))
    # DB+NETWORK: 23-28 (6 fields)
    db_highlight = highlight_index(23, len(dbnet_fields))
    # AUTHENTICATION: 29-34 (6 fields)
    auth_highlight = highlight_index(29, len(auth_fields))
    # SCHEDULER: 35-36 (2 fields)
    scheduler_highlight = highlight_index(35, len(scheduler_fields))
    # WORKERS: 37 (1 field)
    w_highlight = highlight_index(37, len(worker_fields))

    # Create panels for all groups
    gen_panel = config_table("GENERAL", general_fields, highlight_idx=general_highlight)
    tgt_panel = config_table("TARGET + FUZZ", target_fields, highlight_idx=target_highlight)
    sh_panel = config_table("SHARING + STORAGE", sharing_fields, highlight_idx=sharing_highlight)
    db_panel = config_table("DB + NETWORK", dbnet_fields, highlight_idx=db_highlight)
    auth_panel = config_table("AUTHENTICATION", auth_fields, highlight_idx=auth_highlight)
    sched_panel = config_table("SCHEDULER", scheduler_fields, highlight_idx=scheduler_highlight)
    w_panel = config_table("WORKERS", worker_fields, highlight_idx=w_highlight)

    # Display in two rows to fit all 7 groups
    # Row 1: GENERAL, TARGET+FUZZ, SHARING+STORAGE, DB+NETWORK
    # Row 2: AUTHENTICATION, SCHEDULER, WORKERS
    row1 = Columns([gen_panel, tgt_panel, sh_panel, db_panel], equal=True, expand=True)
    row2 = Columns([auth_panel, sched_panel, w_panel], equal=True, expand=True)

    layout["body"].update(Group(row1, row2))

def args_help_panel(page: int, per_page: int) -> Panel:
    start = page * per_page
    end = start + per_page
    paginated_entries = args_help_entries[start:end]
    table = Table(expand=True, show_header=True, header_style="bold magenta")
    table.add_column("Argument", style="bold cyan", no_wrap=True, width=20)
    table.add_column("Description", style="white")
    for arg, desc in paginated_entries:
        table.add_row(arg, desc)
    total_pages = (len(args_help_entries) + per_page - 1) // per_page
    title = f"[bold green]Arguments Help (Page {page+1} of {total_pages})[/]"
    return Panel(table, title=title, border_style="bright_blue")

def crashes_table(crashes, selected_idx=-1):
    """Create a table of crashes with optional highlighting."""
    table = Table(title=f"[bold green]Crashes (Filters: {', '.join(crash_filters or ['None'])}) (Page {crash_page+1})[/]",
                  border_style="bright_blue", expand=True)
    table.add_column("ID", style="bright_white", justify="right", width=6)
    table.add_column("Type", style="red", width=10)
    table.add_column("EXP", style="cyan", width=8)
    table.add_column("Sev", style="yellow", width=6)
    table.add_column("San", style="magenta", width=8)
    table.add_column("Uniq", style="green", width=4)
    table.add_column("Job", style="green", justify="right", width=6)
    table.add_column("Path", style="bright_black", width=25)
    table.add_column("Time", style="yellow", width=16)
    for i, crash in enumerate(crashes):
        style = "reverse" if i == selected_idx else ""

        # Severity with color
        severity = crash.get("severity", "?")
        severity_colored = {"HIGH": "[red]HIGH[/]", "MEDIUM": "[yellow]MED[/]", "LOW": "[green]LOW[/]"}.get(severity, "?")

        # Sanitizer type (abbreviated)
        sanitizer = crash.get("sanitizer_type", "")
        san_abbrev = {"ASAN": "ASAN", "UBSAN": "UBSAN", "MSAN": "MSAN", "TSAN": "TSAN"}.get(sanitizer, "-")

        # Unique indicator
        is_unique = crash.get("is_unique", 1)
        unique_str = "✓" if is_unique else "×"

        table.add_row(
            crash["id"],
            crash["type"][:10],  # Truncate type
            crash["exp_colored"][:8],  # Truncate exploitability
            severity_colored,
            san_abbrev,
            unique_str,
            crash["job"],
            crash["path"][:24],  # Truncate path
            crash["timestamp"],
            style=style
        )
    return Panel(table, border_style="bright_blue")

def crash_details_panel(crash_data):
    """Create a modal panel for crash details."""
    tbl = Table.grid(padding=(0, 1))
    tbl.add_column(style="bold bright_white", width=18)
    tbl.add_column(style="bright_cyan")
    tbl.add_row("ID:", crash_data["id"])
    tbl.add_row("Type:", crash_data["type"])
    tbl.add_row("Signature:", crash_data["sig"])
    tbl.add_row("Exploitability:", crash_data["exp"])

    # Advanced fuzzing fields
    if crash_data.get("stack_hash"):
        tbl.add_row("Stack Hash:", crash_data["stack_hash"][:16] + "...")
    if crash_data.get("sanitizer_type"):
        tbl.add_row("Sanitizer:", crash_data["sanitizer_type"])
    if crash_data.get("severity"):
        severity_color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(crash_data["severity"], "white")
        tbl.add_row("Severity:", f"[{severity_color}]{crash_data['severity']}[/]")
    if crash_data.get("is_unique") is not None:
        unique_str = "Yes" if crash_data["is_unique"] else "No"
        tbl.add_row("Unique:", unique_str)
    if crash_data.get("duplicate_count") and crash_data["duplicate_count"] > 0:
        tbl.add_row("Duplicates:", str(crash_data["duplicate_count"]))

    tbl.add_row("Job ID:", crash_data["job"])
    tbl.add_row("Path:", crash_data["path"])
    tbl.add_row("Timestamp:", crash_data["timestamp"])
    tbl.add_row("", "")
    tbl.add_row("Crash Log:", crash_data["crash_log"])
    return Panel(
        tbl,
        title=f"[bold bright_blue]Crash {crash_data['id']} Details[/]",
        border_style="bright_blue",
        width=90,
        height=25,
        padding=(1, 2)
    )

def update_help():
    help_text = f"""[bold bright_blue]HELP PANEL[/bold bright_blue]
                                 
Use [bold yellow][↑][↓][/bold yellow] to move within a section. Use [bold yellow][←][→][/bold yellow] to jump sections.
Press [bold cyan]Enter[/bold cyan] to edit a field, or [bold magenta]Space[/bold magenta] to toggle booleans.
"""
    if current_screen == "crashes":
        help_text += """
Use [bold yellow][↑][↓][/bold yellow] to select crash. [bold green][1-4][/bold green] to toggle HIGH/MEDIUM/LOW/UNKNOWN.
Press [bold cyan][V][/bold cyan] to view crash details. [bold green][N][P][/bold green] to page crashes.
"""
    help_text += f"""
[bright_white]Mode:[/] {mode.upper()} - Use [bold green]--mode local[/] or [yellow]--mode controller[/].
[bright_white]Workers:[/] {', '.join(default_config['workers']) if default_config['workers'] else 'None'}
[bright_white]--vfs[/] and [bright_white]--smb[/] are mutually exclusive.
[bright_white]--timeout[/]: Time per testcase (Default: 60s).

[dim]Shortcuts:
[d] Dashboard   [c] Config   [x] Crashes   [h] Help   [s] Save   [r] Reset   [e] Exit[/dim]
"""
    return Panel(Align.left(help_text), border_style="bright_blue")

def update_dashboard(layout):
    global job_page
    cfg = FawkesConfig.load()
    for key in default_config:
        try:
            setattr(cfg, key, default_config[key])
        except Exception as e:
            logger.error(f"An Error occurred setting up cfg: {e}, on key: {key}")
            continue

    # Initialize or load the VM registry
    try:
        registry = VMRegistry(cfg.get("registry_file"))
    except FawkesConfigError as e:
        logger.error(f"Failed to load VM registry: {e}")

    getData = FawkesDataCollection(cfg, registry, shutdown_event)

    def stats_panel(title, entries, color="bright_cyan"):
        tbl = Table.grid(expand=True)
        tbl.add_column(justify="right", style="bold bright_white")
        tbl.add_column(justify="left", style=f"bold {color}")
        for k, v in entries:
            if not k and not v:
                tbl.add_row(f"{k}", f"{v}")
            else:
                tbl.add_row(f"{k}:", f"{v}")
        return Panel(tbl, title=f"[bold {color}]{title}", border_style="bright_blue", expand=True)

    def job_panel(job):
        exploits_str = ", ".join([f"{k} ({v})" for k, v in job["exploits"].items()]) or "None"
        tbl = Table.grid(expand=True)
        tbl.add_column(justify="left", style="bold white")
        tbl.add_column(justify="left", style="cyan")
        tbl.add_row("Status: ", job["status"])
        tbl.add_row("VMs: ", str(job["vms"]))
        tbl.add_row("Total TC: ", str(job["total_tc"]))
        tbl.add_row("Crashes: ", str(job["crashes"]))
        tbl.add_row("Crash Ranking: ", exploits_str)
        return Panel(tbl, title=f"[bold bright_blue]{job['name']}", border_style="bright_blue")
    
    system_stats = stats_panel("SYSTEM METRICS", getData.get_system_metrics())
    test_stats   = stats_panel("TEST STATS", getData.get_test_stats())
    crash_stats  = stats_panel("CRASH STATS", getData.get_crash_stats())
    metrics_row  = Columns([system_stats, test_stats, crash_stats], equal=True, expand=True)
    layout["body"].update(
        Columns([
            Panel(metrics_row, border_style="bright_blue", title="[bold bright_blue]SYSTEM STATUS"),
        ], expand=True)
    )

    # Build the tables for active jobs and crashes
    job_data = getData.get_active_jobs()
    jobs_table = Table(title="[bold bright_cyan]ACTIVE JOBS", border_style="bright_blue", expand=True)
    jobs_table.add_column("ID", justify="right", style="bright_white")
    jobs_table.add_column("Name", style="bright_cyan")
    jobs_table.add_column("VMs", justify="right", style="green")
    jobs_table.add_column("Status", style="yellow")
    for job in job_data:
        jobs_table.add_row(job["id"], job["name"], job["vms"], job["status"])
    
    crash_table = Table(title="[bold bright_cyan]CRASH FEED", border_style="bright_blue", expand=True)
    crash_table.add_column("ID", style="bright_white", justify="right")
    crash_table.add_column("Type", style="red")
    crash_table.add_column("Sig", style="magenta")
    crash_table.add_column("EXP", style="cyan")
    crash_table.add_column("Job", style="green", justify="right")
    crash_table.add_column("Path", style="bright_black")
    for c in getData.get_crash_feed():
        crash_table.add_row(c["id"], c["type"], c["sig"], c["exp"], c["job"], c["path"])
   
    # Combine the JOBS/CRASHES panels and job panels in a Group/Columns
    layout["help"].update(
        Group(
            Columns([
                Panel(jobs_table, title="[bold bright_cyan]JOBS", border_style="bright_blue"),
                Panel(crash_table, title="[bold bright_cyan]CRASHES", border_style="bright_blue"),
            ], expand=True),
        )
    )

    # Paginate job list
    try:
        start = job_page * jobs_per_page
        end = start + jobs_per_page
        paginated_jobs = job_data[start:end]
        job_panels = [job_panel(job) for job in paginated_jobs]
    except Exception as e:
        logger.error(f"An error occurred while paginateing the jobs list: {e}")
        job_panels = []
 
    layout["jobs"].update(Columns(job_panels, equal=True, expand=True))

def update_crashes(layout):
    """Update the crashes screen."""
    global crash_page, selected_crash
    cfg = FawkesConfig.load()
    for key in default_config:
        try:
            setattr(cfg, key, default_config[key])
        except Exception as e:
            logger.error(f"An Error occurred setting up cfg: {e}, on key: {key}")
            continue
    try:
        registry = VMRegistry(cfg.get("registry_file"))
    except FawkesConfigError as e:
        logger.error(f"Failed to load VM registry: {e}")

    data = FawkesDataCollection(cfg, registry, shutdown_event)
    crashes = data.get_crash_feed_filtered(crash_filters, crash_page, crashes_per_page)

    # Adjust selected_crash to stay in bounds
    selected_crash = max(0, min(selected_crash, len(crashes) - 1))

    if in_crash_detail and crashes:
        # Show modal with details for selected crash
        crash_data = data.get_crash_details(crashes[selected_crash]["id"])
        layout["body"].update(
            Group(
                crashes_table(crashes, selected_crash),
                crash_details_panel(crash_data)
            )
        )
    else:
        # Show crash table only
        layout["body"].update(crashes_table(crashes, selected_crash))

    layout["help"].update(update_help())

def update_performance(layout):
    """Update performance metrics page."""
    from fawkes.performance import perf_tracker

    stats = perf_tracker.get_stats()

    # Create performance table
    perf_table = Table(title="Performance Metrics", border_style="green", show_header=True)
    perf_table.add_column("Metric", style="cyan", width=30)
    perf_table.add_column("Value", style="yellow", width=20)

    # Overall metrics
    perf_table.add_row("Exec/sec (average)", f"{stats.get('exec_per_sec', 0):.2f}")
    perf_table.add_row("Exec/sec (recent)", f"{stats.get('exec_per_sec_recent', 0):.2f}")
    perf_table.add_row("Total Testcases", str(stats.get('total_testcases', 0)))
    perf_table.add_row("Total Crashes", str(stats.get('total_crashes', 0)))
    perf_table.add_row("Elapsed Time", f"{stats.get('elapsed_seconds', 0):.1f}s")

    # Time compression status
    perf_table.add_row("", "")  # Separator
    perf_table.add_row("[bold]Time Compression[/]", "")

    time_comp_enabled = default_config.get('enable_time_compression', False)
    if time_comp_enabled:
        shift = default_config.get('time_compression_shift', 'auto')
        skip_idle = default_config.get('skip_idle_loops', True)

        perf_table.add_row("  Status", "[green]ENABLED[/]")
        perf_table.add_row("  icount shift", f"{shift}")
        perf_table.add_row("  Skip idle loops", "[green]Yes[/]" if skip_idle else "[yellow]No[/]")
        perf_table.add_row("  Expected speedup", "[green]3-10x[/]")

        # Show QEMU command snippet
        icount_cmd = f"shift={shift}"
        if skip_idle:
            icount_cmd += ",align=off,sleep=off"
        perf_table.add_row("  QEMU icount", f"{icount_cmd}")
    else:
        perf_table.add_row("  Status", "[red]DISABLED[/]")
        perf_table.add_row("  Note", "[dim]Enable in Config > ADVANCED[/]")
        perf_table.add_row("  Potential speedup", "[yellow]3-10x available[/]")

    # Timing breakdown if available
    if stats.get('timings'):
        perf_table.add_row("", "")  # Separator
        perf_table.add_row("[bold]Timing Breakdown[/]", "[bold]Avg (ms)[/]")
        for operation, timing in sorted(stats['timings'].items())[:10]:  # Show top 10
            avg_ms = timing.get('avg_ms', 0)
            perf_table.add_row(f"  {operation}", f"{avg_ms:.2f}")

    # Snapshot revert optimization stats if available
    if 'snapshot_revert_fast' in stats.get('timings', {}) and 'snapshot_revert_slow' in stats.get('timings', {}):
        fast_avg = stats['timings']['snapshot_revert_fast'].get('avg_ms', 0)
        slow_avg = stats['timings']['snapshot_revert_slow'].get('avg_ms', 0)
        speedup = slow_avg / fast_avg if fast_avg > 0 else 0

        perf_table.add_row("", "")  # Separator
        perf_table.add_row("[bold]Snapshot Optimization[/]", "")
        perf_table.add_row("  Fast mode avg", f"{fast_avg:.2f}ms")
        perf_table.add_row("  Slow mode avg", f"{slow_avg:.2f}ms")
        perf_table.add_row("  Speedup", f"{speedup:.2f}x")

    # Add padding rows to maintain consistent height
    perf_table.add_row("", "")
    perf_table.add_row("", "")

    layout["body"].update(Panel(perf_table, border_style="green"))
    layout["help"].update(update_help())

def update_snapshots(layout):
    """Update snapshot management page."""
    import subprocess

    # Get disk image from config
    cfg = FawkesConfig.load()
    disk_path = os.path.expanduser(cfg.get("disk_image", ""))

    # Create snapshots table
    snap_table = Table(title=f"Snapshots in {disk_path}", border_style="cyan", show_header=True)
    snap_table.add_column("ID", style="yellow", width=5)
    snap_table.add_column("Name", style="cyan", width=20)
    snap_table.add_column("VM Size", style="green", width=12)
    snap_table.add_column("Date", style="white", width=20)

    # List snapshots using qemu-img
    try:
        if os.path.exists(disk_path):
            result = subprocess.run(
                ["qemu-img", "snapshot", "-l", disk_path],
                capture_output=True,
                text=True,
                check=True
            )

            lines = result.stdout.strip().split('\n')
            for line in lines[2:]:  # Skip header
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 5:
                    snap_id = parts[0]
                    snap_name = parts[1]
                    vm_size = parts[2]
                    date_str = f"{parts[3]} {parts[4]}"

                    # Highlight current snapshot
                    if snap_name == cfg.get("snapshot_name"):
                        snap_name = f"[bold green]{snap_name}[/] (current)"

                    snap_table.add_row(snap_id, snap_name, vm_size, date_str)
        else:
            snap_table.add_row("", f"Disk not found: {disk_path}", "", "")

    except FileNotFoundError:
        snap_table.add_row("", "qemu-img not found", "", "")
    except subprocess.CalledProcessError as e:
        snap_table.add_row("", f"Error: {e.stderr[:50]}", "", "")
    except Exception as e:
        snap_table.add_row("", f"Error: {str(e)[:50]}", "", "")

    # Add help text with padding
    help_text = (
        "\n[cyan]Use the fawkes-snapshot CLI tool for snapshot management:[/]\n\n"
        "  fawkes-snapshot list --disk <path>\n"
        "  fawkes-snapshot create --disk <path> --name <name>\n"
        "  fawkes-snapshot validate --disk <path> --name <name>\n"
        "  fawkes-snapshot delete --disk <path> --name <name>\n\n\n\n"
    )

    layout["body"].update(Panel(Group(snap_table, help_text), border_style="cyan"))
    layout["help"].update(update_help())

def update_auth(layout):
    """Update authentication/user management page."""
    cfg = FawkesConfig.load()
    auth_enabled = cfg.get("auth_enabled", False)
    auth_db_path = os.path.expanduser(cfg.get("auth_db_path", "~/.fawkes/auth.db"))

    if not auth_enabled:
        no_auth_msg = (
            "[yellow]Authentication is currently DISABLED[/]\n\n"
            "To enable authentication:\n"
            "1. Set 'auth_enabled' to true in configuration\n"
            "2. Optionally enable TLS with 'tls_enabled'\n"
            "3. Configure 'auth_db_path' if needed\n\n"
            "Use the fawkes-auth CLI tool to manage users and API keys.\n\n\n\n\n\n\n"
        )
        layout["body"].update(Panel(no_auth_msg, title="Authentication Disabled", border_style="yellow"))
        layout["help"].update(update_help())
        return

    # Try to load auth database
    try:
        from db.auth_db import AuthDB
        auth_db = AuthDB(auth_db_path)

        # Create users table
        users_table = Table(title="Users", border_style="green", show_header=True)
        users_table.add_column("ID", style="yellow", width=5)
        users_table.add_column("Username", style="cyan", width=15)
        users_table.add_column("Role", style="green", width=10)
        users_table.add_column("Enabled", style="white", width=8)
        users_table.add_column("Last Login", style="white", width=20)

        users = auth_db.list_users()
        for user in users[:10]:  # Show up to 10 users
            last_login = "Never"
            if user.get("last_login"):
                last_login = datetime.fromtimestamp(user["last_login"]).strftime("%Y-%m-%d %H:%M")

            enabled_str = "[green]Yes[/]" if user["enabled"] else "[red]No[/]"
            users_table.add_row(
                str(user["user_id"]),
                user["username"],
                user["role"],
                enabled_str,
                last_login
            )

        if not users:
            users_table.add_row("", "No users found", "", "", "")

        # Create API keys table
        api_table = Table(title="API Keys", border_style="cyan", show_header=True)
        api_table.add_column("ID", style="yellow", width=5)
        api_table.add_column("Name", style="cyan", width=20)
        api_table.add_column("Type", style="green", width=10)
        api_table.add_column("Worker ID", style="white", width=15)
        api_table.add_column("Enabled", style="white", width=8)

        api_keys = auth_db.list_api_keys()
        for key in api_keys[:10]:  # Show up to 10 keys
            enabled_str = "[green]Yes[/]" if key["enabled"] else "[red]No[/]"
            worker_id = key.get("worker_id") or "-"
            api_table.add_row(
                str(key["key_id"]),
                key["key_name"],
                key["key_type"],
                worker_id,
                enabled_str
            )

        if not api_keys:
            api_table.add_row("", "No API keys found", "", "", "")

        # Help text with padding
        help_text = (
            "\n[cyan]Use the fawkes-auth CLI tool for user management:[/]\n\n"
            "  fawkes-auth user create <username> --role <admin|operator|viewer>\n"
            "  fawkes-auth user list\n"
            "  fawkes-auth user disable <username>\n"
            "  fawkes-auth key create <name> --type worker\n"
            "  fawkes-auth key list\n"
            "  fawkes-auth key revoke <key_id>\n\n\n"
        )

        auth_db.close()
        layout["body"].update(Panel(Group(users_table, api_table, help_text), border_style="green"))

    except FileNotFoundError:
        error_msg = (
            f"[red]Auth database not found:[/] {auth_db_path}\n\n"
            "Use the fawkes-auth CLI tool to initialize:\n"
            "  fawkes-auth init\n\n\n\n\n\n\n\n"
        )
        layout["body"].update(Panel(error_msg, title="Database Not Found", border_style="red"))
    except Exception as e:
        error_msg = f"[red]Error loading auth database:[/]\n{str(e)}\n\n\n\n\n\n\n\n"
        layout["body"].update(Panel(error_msg, title="Error", border_style="red"))

    layout["help"].update(update_help())


def update_fuzzer(layout):
    """Update fuzzer statistics and configuration page."""
    cfg = FawkesConfig.load()

    # Check if intelligent fuzzer is enabled
    fuzzer_type = cfg.get("fuzzer", "file")
    stats_file = os.path.expanduser(cfg.get("fuzzer_stats_file", "~/.fawkes/fuzzer_stats.json"))

    if fuzzer_type != "intelligent":
        no_fuzzer_msg = (
            "[yellow]Intelligent Fuzzer is not enabled[/]\n\n"
            "Current fuzzer: [cyan]" + fuzzer_type + "[/]\n\n"
            "To enable the Intelligent Fuzzer:\n"
            "1. Set 'fuzzer' to 'intelligent' in configuration\n"
            "2. Optionally configure 'fuzzer_config' path\n"
            "3. Set 'fuzzer_stats_file' for statistics\n\n"
            "The Intelligent Fuzzer provides:\n"
            "  • Crash-guided mutations\n"
            "  • 17 adaptive mutation strategies\n"
            "  • Dictionary-based fuzzing\n"
            "  • Energy scheduling\n"
            "  • Real-time statistics\n\n\n\n"
        )
        layout["body"].update(Panel(no_fuzzer_msg, title="Fuzzer Status", border_style="yellow"))
        layout["help"].update(update_help())
        return

    # Try to load fuzzer statistics
    try:
        from fuzzers.fuzzer_stats import FuzzerStats
        from pathlib import Path

        if not Path(stats_file).exists():
            no_stats_msg = (
                "[cyan]Intelligent Fuzzer Enabled[/]\n\n"
                f"Statistics file: [yellow]{stats_file}[/]\n\n"
                "[yellow]No statistics available yet.[/]\n"
                "Statistics will appear once fuzzing starts.\n\n"
                "Start fuzzing to see:\n"
                "  • Execution speed (exec/sec)\n"
                "  • Crash statistics\n"
                "  • Strategy effectiveness\n"
                "  • Corpus progress\n\n\n\n\n\n"
            )
            layout["body"].update(Panel(no_stats_msg, title="Fuzzer Statistics", border_style="cyan"))
            layout["help"].update(update_help())
            return

        # Load and display statistics
        stats = FuzzerStats()
        stats.load_from_file(stats_file)
        stats_data = stats.get_stats()

        # Create statistics table
        stats_table = Table(title="Fuzzing Statistics", border_style="green", show_header=False, box=None)
        stats_table.add_column("Metric", style="cyan", width=25)
        stats_table.add_column("Value", style="white", width=20)
        stats_table.add_column("Metric", style="cyan", width=25)
        stats_table.add_column("Value", style="white", width=20)

        # Format elapsed time
        elapsed = int(stats_data.get("elapsed_time", 0))
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        elapsed_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        # Row 1
        stats_table.add_row(
            "Elapsed Time",
            f"[green]{elapsed_str}[/]",
            "Total Executions",
            f"[green]{stats_data.get('total_execs', 0):,}[/]"
        )

        # Row 2
        stats_table.add_row(
            "Exec/sec (current)",
            f"[yellow]{stats_data.get('execs_per_sec_current', 0):.2f}[/]",
            "Exec/sec (average)",
            f"[yellow]{stats_data.get('execs_per_sec_avg', 0):.2f}[/]"
        )

        # Row 3
        stats_table.add_row(
            "Crashes Found",
            f"[red]{stats_data.get('crashes_total', 0)}[/]",
            "Unique Crashes",
            f"[red bold]{stats_data.get('crashes_unique', 0)}[/]"
        )

        # Row 4
        stats_table.add_row(
            "Corpus Size",
            f"[cyan]{stats_data.get('corpus_size', 0)}[/]",
            "Corpus Progress",
            f"[cyan]{stats_data.get('corpus_progress', 0):.1f}%[/]"
        )

        # Create crashes by type table
        crashes_by_type = stats_data.get("crashes_by_type", {})
        crash_table = Table(title="Crashes by Type", border_style="red", show_header=True)
        crash_table.add_column("Type", style="yellow", width=30)
        crash_table.add_column("Count", style="red", width=10, justify="right")

        if crashes_by_type:
            for crash_type, count in sorted(crashes_by_type.items(), key=lambda x: -x[1])[:10]:
                crash_table.add_row(crash_type, str(count))
        else:
            crash_table.add_row("No crashes yet", "-")

        # Create top strategies table
        strategy_rankings = stats.get_strategy_rankings()
        strategy_table = Table(title="Top Mutation Strategies", border_style="cyan", show_header=True)
        strategy_table.add_column("Strategy", style="cyan", width=25)
        strategy_table.add_column("Crash Rate", style="yellow", width=12, justify="right")
        strategy_table.add_column("Crashes", style="red", width=10, justify="right")
        strategy_table.add_column("Attempts", style="white", width=10, justify="right")

        if strategy_rankings:
            for strategy, crash_rate, attempts, crashes in strategy_rankings[:8]:
                strategy_table.add_row(
                    strategy,
                    f"{crash_rate:.2f}%",
                    str(crashes),
                    str(attempts)
                )
        else:
            strategy_table.add_row("No strategy data yet", "-", "-", "-")

        # Layout: stats on top, crashes and strategies side by side below
        top_section = stats_table
        bottom_section = Columns([crash_table, strategy_table], equal=True, expand=True)

        layout["body"].update(Panel(
            Group(top_section, "", bottom_section),
            title="[bold green]Intelligent Fuzzer Statistics[/]",
            border_style="green"
        ))

    except FileNotFoundError:
        error_msg = (
            f"[red]Statistics file not found:[/] {stats_file}\n\n"
            "Statistics will be created when fuzzing starts.\n\n\n\n\n\n\n\n"
        )
        layout["body"].update(Panel(error_msg, title="Statistics Not Found", border_style="yellow"))
    except Exception as e:
        error_msg = f"[red]Error loading fuzzer statistics:[/]\n{str(e)}\n\n\n\n\n\n\n\n"
        layout["body"].update(Panel(error_msg, title="Error", border_style="red"))

    layout["help"].update(update_help())

def update_login(layout):
    """Update login screen."""
    global login_error

    # Create login form
    login_form = Table.grid(padding=1)
    login_form.add_column(style="bold cyan", justify="right")
    login_form.add_column(style="white")

    login_form.add_row("", "")
    login_form.add_row("", "[bold bright_cyan]FAWKES AUTHENTICATION[/]")
    login_form.add_row("", "")
    login_form.add_row("", "")

    if login_error:
        login_form.add_row("", f"[bold red]{login_error}[/]")
        login_form.add_row("", "")

    login_form.add_row("Username:", "[Enter username and press Enter]")
    login_form.add_row("Password:", "[Enter password and press Enter]")
    login_form.add_row("", "")
    login_form.add_row("", "[dim]Press Enter to input credentials[/]")
    login_form.add_row("", "[dim]Press 'q' to quit[/]")
    login_form.add_row("", "")
    login_form.add_row("", "")

    # Add padding
    for _ in range(10):
        login_form.add_row("", "")

    layout["body"].update(Panel(
        Align.center(login_form, vertical="middle"),
        title="Login Required",
        border_style="bright_cyan"
    ))

def update_help_screen(layout):
    layout["body"].update(args_help_panel(args_page, args_per_page))
    layout["help"].update(update_help())

def update_header(layout):
    if current_screen == "login":
        hdr = f"[bold bright_cyan]FAWKES :: LOGIN[/]\n[yellow]Mode:[/] {mode.upper()}"
    elif current_screen == "help":
        hdr = f"[bold bright_cyan]FAWKES :: HELP[/]\n[green]Profile:[/] {config_file}    [yellow]Mode:[/] {mode.upper()}"
    elif current_screen == "crashes":
        hdr = f"[bold bright_cyan]FAWKES :: CRASHES[/]\n[green]Profile:[/] {config_file}    [yellow]Mode:[/] {mode.upper()}"
    elif current_screen == "performance":
        hdr = f"[bold bright_cyan]FAWKES :: PERFORMANCE METRICS[/]\n[green]Profile:[/] {config_file}    [yellow]Mode:[/] {mode.upper()}"
    elif current_screen == "snapshots":
        hdr = f"[bold bright_cyan]FAWKES :: SNAPSHOT MANAGEMENT[/]\n[green]Profile:[/] {config_file}    [yellow]Mode:[/] {mode.upper()}"
    elif current_screen == "auth":
        hdr = f"[bold bright_cyan]FAWKES :: AUTHENTICATION & USERS[/]\n[green]Profile:[/] {config_file}    [yellow]Mode:[/] {mode.upper()}"
    else:
        hdr = f"[bold bright_cyan]FAWKES :: CORE CONFIG INTERFACE[/]\n[green]Profile:[/] {config_file}    [yellow]Mode:[/] {mode.upper()}"

    # Add user info if authenticated
    if is_authenticated and current_user:
        hdr += f"    [green]User:[/] {current_user.get('username', 'Unknown')}"

    layout["header"].update(Panel(Align.center(hdr, vertical="middle"), border_style="bright_blue"))

def update_footer(layout):
    if current_screen == "login":
        ftr = "[bold yellow][Enter][/bold yellow] Login  [bold red][Q][/bold red] Quit"
    elif current_screen == "help":
        ftr = (
            "[bold green][N]/[P][/bold green] Page Nav  "
            "[green][C][/green] Config  "
            "[yellow][D][/yellow] Dashboard  "
            "[cyan][X][/cyan] Crashes  "
            "[blue][F][/blue] Perf  "
            "[magenta][M][/magenta] Snaps  "
            "[white][A][/white] Auth  "
            "[bright_cyan][Z][/bright_cyan] Fuzzer  "
            "[bright_blue][H][/bright_blue] Back  "
            "[red][E][/red] Exit"
        )
    elif current_screen == "crashes":
        ftr = (
            "[bold green][↑][↓][/bold green] Select  "
            "[bold green][1-4][/bold green] Filter  "
            "[bold cyan][V][/bold cyan] View  "
            "[bold green][N]/[P][/bold green] Page  "
            "[green][C][/green] Config  "
            "[yellow][D][/yellow] Dashboard  "
            "[blue][F][/blue] Perf  "
            "[magenta][M][/magenta] Snaps  "
            "[white][A][/white] Auth  "
            "[bright_cyan][Z][/bright_cyan] Fuzzer  "
            "[bright_blue][H][/bright_blue] Help  "
            "[red][E][/red] Exit"
        )
    elif current_screen == "performance":
        ftr = (
            "[green][C][/green] Config  "
            "[yellow][D][/yellow] Dashboard  "
            "[cyan][X][/cyan] Crashes  "
            "[magenta][M][/magenta] Snapshots  "
            "[white][A][/white] Auth  "
            "[bright_cyan][Z][/bright_cyan] Fuzzer  "
            "[bright_blue][H][/bright_blue] Help  "
            "[red][E][/red] Exit"
        )
    elif current_screen == "snapshots":
        ftr = (
            "[green][C][/green] Config  "
            "[yellow][D][/yellow] Dashboard  "
            "[cyan][X][/cyan] Crashes  "
            "[blue][F][/blue] Performance  "
            "[white][A][/white] Auth  "
            "[bright_cyan][Z][/bright_cyan] Fuzzer  "
            "[bright_blue][H][/bright_blue] Help  "
            "[red][E][/red] Exit"
        )
    elif current_screen == "auth":
        ftr = (
            "[green][C][/green] Config  "
            "[yellow][D][/yellow] Dashboard  "
            "[cyan][X][/cyan] Crashes  "
            "[blue][F][/blue] Performance  "
            "[magenta][M][/magenta] Snapshots  "
            "[bright_cyan][Z][/bright_cyan] Fuzzer  "
            "[bright_blue][H][/bright_blue] Help  "
            "[red][E][/red] Exit"
        )
    elif current_screen == "fuzzer":
        ftr = (
            "[green][C][/green] Config  "
            "[yellow][D][/yellow] Dashboard  "
            "[cyan][X][/cyan] Crashes  "
            "[blue][F][/blue] Performance  "
            "[magenta][M][/magenta] Snapshots  "
            "[white][A][/white] Auth  "
            "[bright_blue][H][/bright_blue] Help  "
            "[red][E][/red] Exit"
        )
    else:
        ftr = (
            "[bold green][↑][↓][/bold green] Nav Fields  "
            "[bold green][←][→][/bold green] Nav Sections  "
            "[bold yellow][Enter][/bold yellow] Edit  "
            "[bold magenta][Space][/bold magenta] Toggle  "
            "[cyan][S][/cyan] Start  "
            "[red][K][/red] Stop  "
            "[yellow][Q][/yellow] Queue  "
            "[bright_black][R] Reset  "
            "[yellow][D][/yellow] Dashboard  "
            "[cyan][X][/cyan] Crashes  "
            "[blue][F][/blue] Perf  "
            "[magenta][M][/magenta] Snaps  "
            "[white][A][/white] Auth  "
            "[bright_cyan][Z][/bright_cyan] Fuzzer  "
            "[green][C][/green] Config  "
            "[bright_blue][H][/bright_blue] Help  "
            "[red][E][/red] Exit"
        )
    layout["footer"].update(Panel(ftr, border_style="bright_blue"))

##############################################################################
#                          RUN_LOCAL_MODE RICH SAFE
##############################################################################

def run_local_mode_background(cfg, registry, parallel, loop, seed_dir):
    for handler in logger.root.handlers[:]:
        if isinstance(handler, logging.StreamHandler):
            logger.root.removeHandler(handler)
    run_local_mode(cfg, registry, parallel=parallel, loop=loop, seed_dir=seed_dir)

##############################################################################
#                     RUN_CONTROLLER_MODE RICH SAFE
##############################################################################

def run_controller_mode_background(cfg):
    for handler in logger.root.handlers[:]:
        if isinstance(handler, logging.StreamHandler):
            logger.root.removeHandler(handler)
    run_controller_mode(cfg)

##############################################################################
#                             JOB CONTROL
##############################################################################

def start_job():
    job_name = default_config["job_name"]
    logger.debug(f"Starting new job: {job_name}, in mode: {mode}")
    cfg = FawkesConfig.load()
    for key in default_config:
        try:
            setattr(cfg, key, default_config[key])
        except Exception as e:
            logger.error(f"An Error occurred setting up cfg: {e}, on key: {key}")
            continue
    try:
        registry = VMRegistry(cfg.get("registry_file"))
    except FawkesConfigError as e:
        logger.error(f"Failed to load VM registry: {e}")
        return
    if mode == "local":
        fuzz_thread = threading.Thread(
            target=run_local_mode_background,
            args=(
                cfg,
                registry,
                int(default_config["max_parallel"]),
                default_config["loop"],
                default_config["input_dir"],
            ),
            name=f"FuzzThread-{job_name}",
        )
        logger.debug(
            f"parallel={default_config['max_parallel']}, loop={default_config['loop']}, "
            f"seed_dir={default_config['input_dir']}"
        )
        fuzz_thread.start()
        local_jobs.append({"job_name": job_name, "thread": fuzz_thread})
        logger.debug(f"Job '{job_name}' started with thread: {fuzz_thread}")
    elif mode == "controller":
        fuzz_thread = threading.Thread(
            target=run_controller_mode_background,
            args=(cfg,),
            name=f"FuzzThread-{job_name}",
        )
        fuzz_thread.start()
        local_jobs.append({"job_name": job_name, "thread": fuzz_thread})
        logger.debug(f"Job '{job_name}' started with thread: {fuzz_thread}")

##############################################################################
#             EDIT CONFIG: STOP LISTENER & USE BLOCKING INPUT
##############################################################################

def edit_config_field(display_label, config_key):
    global in_edit_mode
    in_edit_mode = True
    if not config_key:
        in_edit_mode = False
        logger.debug(f"In edit_config_field with an empty value: {config_key}")
        return
    console.clear()
    old_val = default_config[config_key]
    console.print(f"[bold cyan]Editing {display_label}[/bold cyan] (config key: {config_key} current: [yellow]{old_val}[/yellow])")
    sys.stdout.flush()
    new_value = prompt_user()
    logger.debug(f"Got new field updated value: {new_value}")
    typed_value = new_value.strip()
    try:
        if isinstance(old_val, bool):
            lv = typed_value.lower()
            if lv in ("true", "yes", "1"):
                default_config[config_key] = True
            elif lv in ("false", "no", "0"):
                default_config[config_key] = False
            else:
                console.log(f"Invalid boolean input: {new_value}, keeping old value.")
        elif isinstance(old_val, int):
            try:
                default_config[config_key] = int(typed_value)
            except ValueError:
                console.log(f"Invalid int input: {new_value}, keeping old value.")
        elif isinstance(old_val, float):
            try:
                default_config[config_key] = float(typed_value)
            except ValueError:
                console.log(f"Invalid float input: {new_value}, keeping old value.")
        else:
            if config_key == "workers":
                default_config[config_key] = [ip.strip() for ip in typed_value.split(",") if ip.strip()]
            else:
                default_config[config_key] = typed_value
    except Exception as e:
        logger.debug(f"An error occurred in edit_config_field: {e}")
    in_edit_mode = False

##############################################################################
#                             KEYBOARD HANDLER
##############################################################################

def on_press(key):
    global selected_field, current_screen, previous_screen, should_exit, job_page, in_edit_mode, args_page
    global default_config, reset_config, crash_page, selected_crash, crash_filters, in_crash_detail
    global is_authenticated, current_user, session_token, login_error
    try:
        logger.debug(f"In on_press with key: {key}")
        if in_edit_mode or in_crash_detail:
            if in_crash_detail and key in ('q', '\x1b'):  # Esc or q to close crash details
                in_crash_detail = False
            return False

        # Handle login screen
        if current_screen == "login":
            if key in ('\r', '\n'):  # Enter key
                # Perform login
                restore_tty()
                console.print("\n[cyan]Username:[/] ", end="")
                username = input().strip()
                console.print("[cyan]Password:[/] ", end="")
                import getpass
                password = getpass.getpass("")
                setup_tty()

                # Authenticate
                cfg = FawkesConfig.load()
                auth_db_path = os.path.expanduser(cfg.get("auth_db_path", "~/.fawkes/auth.db"))
                try:
                    from db.auth_db import AuthDB
                    auth_db = AuthDB(auth_db_path)
                    user_info = auth_db.authenticate_user(username, password)
                    auth_db.close()

                    if user_info:
                        is_authenticated = True
                        current_user = user_info
                        session_token = None  # TODO: implement session tokens if needed
                        login_error = None
                        current_screen = "configuration"
                        logger.info(f"User {username} logged in successfully")
                    else:
                        login_error = "Invalid username or password"
                        logger.warning(f"Failed login attempt for user: {username}")
                except Exception as e:
                    login_error = f"Authentication error: {str(e)}"
                    logger.error(f"Login error: {e}")
            elif key in ('q', 'Q'):
                should_exit = True
            return False

        if current_screen == "configuration":
            if key == '\x1b':
                end_key = sys.stdin.read(1)
                next_key = sys.stdin.read(1)
                logger.debug(f"key: {key}, next_key: {next_key}, end_key: {end_key}")
                if end_key == '[':
                    if next_key == 'A':
                        selected_field = max(0, selected_field - 1)
                    elif next_key == 'B':
                        selected_field = min(len(fields) - 1, selected_field + 1)
                    elif next_key == 'D':
                        current_group = get_group_index(selected_field)
                        jump_to_group(current_group - 1)
                    elif next_key == 'C':
                        current_group = get_group_index(selected_field)
                        jump_to_group(current_group + 1)
            if key in ('\r', '\n'):
                logger.debug("Set in_edit_mode to True")
                in_edit_mode = True
                termios.tcflush(sys.stdin, termios.TCIOFLUSH)
                return False
            if key == ' ':
                _, cfg_key, _ = fields[selected_field]
                if cfg_key in default_config and isinstance(default_config[cfg_key], bool):
                    default_config[cfg_key] = not default_config[cfg_key]
        elif current_screen == "dashboard":
            if key == '\x1b':
                cfg = FawkesConfig.load()
                try:
                    registry = VMRegistry(cfg.get("registry_file"))
                except FawkesConfigError:
                    registry = None
                job_data = FawkesDataCollection(cfg, registry, shutdown_event).get_active_jobs()
                max_page = (len(job_data) - 1) // jobs_per_page
                end_key = sys.stdin.read(1)
                next_key = sys.stdin.read(1)
                logger.debug(f"key: {key}, next_key: {next_key}, end_key: {end_key}")
                if end_key == '[':
                    if next_key == 'A':
                        job_page = max(0, job_page - 1)
                    elif next_key == 'B':
                        job_page = min(max_page, job_page + 1)
        elif current_screen == "help":
            max_args_page = (len(args_help_entries) - 1) // args_per_page
            if key == 'n':
                args_page = min(max_args_page, args_page + 1)
            elif key == 'p':
                args_page = max(0, args_page - 1)
        elif current_screen == "crashes":
            cfg = FawkesConfig.load()
            try:
                registry = VMRegistry(cfg.get("registry_file"))
            except FawkesConfigError:
                registry = None
            data = FawkesDataCollection(cfg, registry, shutdown_event)
            crashes = data.get_crash_feed_filtered(crash_filters, crash_page, crashes_per_page)
            max_crash_page = (data.local_db._conn.execute("SELECT COUNT(*) FROM crashes").fetchone()[0] - 1) // crashes_per_page if mode == "local" else 0
            if mode == "controller":
                max_crash_page = (data.controller_db.conn.execute("SELECT COUNT(*) FROM crashes").fetchone()[0] - 1) // crashes_per_page
            if key == '\x1b':
                end_key = sys.stdin.read(1)
                next_key = sys.stdin.read(1)
                logger.debug(f"key: {key}, next_key: {next_key}, end_key: {end_key}")
                if end_key == '[':
                    if next_key == 'A':
                        selected_crash = max(0, selected_crash - 1)
                    elif next_key == 'B':
                        selected_crash = min(len(crashes) - 1, selected_crash + 1)
            elif key == 'n':
                crash_page = min(max_crash_page, crash_page + 1)
                selected_crash = 0
            elif key == 'p':
                crash_page = max(0, crash_page - 1)
                selected_crash = 0
            elif key == 'v' and crashes:
                in_crash_detail = True
            elif key == '1':
                if "HIGH" in crash_filters:
                    crash_filters.discard("HIGH")
                else:
                    crash_filters.add("HIGH")
                crash_page = 0
                selected_crash = 0
            elif key == '2':
                if "MEDIUM" in crash_filters:
                    crash_filters.discard("MEDIUM")
                else:
                    crash_filters.add("MEDIUM")
                crash_page = 0
                selected_crash = 0
            elif key == '3':
                if "LOW" in crash_filters:
                    crash_filters.discard("LOW")
                else:
                    crash_filters.add("LOW")
                crash_page = 0
                selected_crash = 0
            elif key == '4':
                if "UNKNOWN" in crash_filters:
                    crash_filters.discard("UNKNOWN")
                else:
                    crash_filters.add("UNKNOWN")
                crash_page = 0
                selected_crash = 0

        ch = key
        if ch == 's':
            if mode == "local":
                try:
                    save_config()
                    start_job()
                except Exception as e:
                    logger.error(f"An error occurred while starting job: {e}")
            elif mode == "controller":
                save_config_controller()
        elif ch == 'k':
            logger.debug("Received kill command stopping jobs...")
            shutdown_event.set()
        elif ch == 'q':
            console.log("Queueing job... (placeholder)")
        elif ch == 'r':
            clear_fawkes_dir()
            default_config.update(reset_config)
            save_config()
            load_config()
        elif ch == 'd':
            previous_screen = current_screen
            current_screen = "dashboard"
            args_page = 0
            crash_filters = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}  # Reset filters
        elif ch == 'c':
            previous_screen = current_screen
            current_screen = "configuration"
            args_page = 0
            crash_filters = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}  # Reset filters
        elif ch == 'h':
            if current_screen == "help":
                current_screen = previous_screen
            else:
                previous_screen = current_screen
                current_screen = "help"
            args_page = 0
            crash_filters = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}  # Reset filters
        elif ch == 'x':
            previous_screen = current_screen
            current_screen = "crashes"
            args_page = 0
            crash_page = 0
            selected_crash = 0
            in_crash_detail = False
        elif ch == 'f':
            previous_screen = current_screen
            current_screen = "performance"
            args_page = 0
        elif ch == 'm':
            previous_screen = current_screen
            current_screen = "snapshots"
            args_page = 0
        elif ch == 'a':
            previous_screen = current_screen
            current_screen = "auth"
            args_page = 0
        elif ch == 'z':
            previous_screen = current_screen
            current_screen = "fuzzer"
            args_page = 0
        elif ch == 'e':
            should_exit = True
    except Exception as ex:
        logger.error(f"[red]Error in on_press:[/] {ex}")
    termios.tcflush(sys.stdin, termios.TCIOFLUSH)

##############################################################################
#                     KEYBOARD INPUT HANDLER FUNCTIONS
##############################################################################

def setup_tty():
    global STDIN_FILENO, original_tty_settings
    tty.setcbreak(STDIN_FILENO)
    return True

def restore_tty():
    global STDIN_FILENO, original_tty_settings
    termios.tcsetattr(STDIN_FILENO, termios.TCSADRAIN, original_tty_settings)

def poll_for_keypress():
    dr, dw, de = select.select([sys.stdin], [], [], 0)
    if dr:
        return sys.stdin.read(1)
    return None

##############################################################################
#                              MAIN LOOP
##############################################################################

def main():
    logger.debug("Starting fawkes system TUI")
    global console, current_screen, is_authenticated
    setup_tty()

    # Check if authentication is required
    cfg = FawkesConfig.load()
    auth_enabled = cfg.get("auth_enabled", False)

    if auth_enabled and not is_authenticated:
        current_screen = "login"
        logger.info("Authentication required - showing login screen")
    else:
        is_authenticated = True  # No auth required or already authenticated
        logger.info("Authentication not required or already authenticated")

    # Track when to refresh screen
    last_screen = current_screen
    refresh_counter = 0
    refresh_interval = 5  # Refresh every 5 iterations (0.5 seconds)
    needs_refresh = True

    with console.screen():
        while not should_exit:
            layout = layouts[current_screen]

            # Check if screen changed
            if current_screen != last_screen:
                needs_refresh = True
                last_screen = current_screen
                refresh_counter = 0

            # Poll for input (this is fast)
            key = poll_for_keypress()
            if key:
                try:
                    on_press(key)
                    needs_refresh = True  # Refresh on user input
                except Exception as e:
                    logger.error(f"An Exception occurred calling on_press: {e}")

            if in_edit_mode:
                logger.debug("in_edit_mode set by the user pressing enter")
                termios.tcflush(sys.stdin, termios.TCIOFLUSH)
                _, cfg_key, lbl = fields[selected_field]
                edit_config_field(lbl, cfg_key)
                needs_refresh = True

            # Only update screen content periodically or when needed
            refresh_counter += 1
            if needs_refresh or refresh_counter >= refresh_interval:
                update_header(layout)
                update_footer(layout)

                if current_screen == "configuration":
                    layout = layouts["configuration"]
                    update_config_body(layout)
                    layout["help"].update(update_help())
                elif current_screen == "dashboard":
                    layout = layouts["dashboard"]
                    update_dashboard(layout)
                elif current_screen == "help":
                    layout = layouts["help"]
                    update_help_screen(layout)
                elif current_screen == "crashes":
                    layout = layouts["crashes"]
                    update_crashes(layout)
                elif current_screen == "performance":
                    layout = layouts["performance"]
                    update_performance(layout)
                elif current_screen == "snapshots":
                    layout = layouts["snapshots"]
                    update_snapshots(layout)
                elif current_screen == "auth":
                    layout = layouts["auth"]
                    update_auth(layout)
                elif current_screen == "fuzzer":
                    layout = layouts["fuzzer"]
                    update_fuzzer(layout)
                elif current_screen == "login":
                    layout = layouts["login"]
                    update_login(layout)

                console.print(layout)
                refresh_counter = 0
                needs_refresh = False

            time.sleep(0.1)
    restore_tty()
    termios.tcflush(sys.stdin, termios.TCIOFLUSH)
    console.clear()
    console.print("[bold green]Exited cleanly![/]")

if __name__ == "__main__":
    main()
