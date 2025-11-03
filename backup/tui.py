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

# Fawkes specific imports
from fawkes.logger import setup_fawkes_logger
from fawkes.config import FawkesConfig, VMRegistry, FawkesConfigError
from fawkes.modes.local import run_local_mode
from fawkes.modes.controller import run_controller_mode
from fawkes.modes.worker import run_worker_mode
from fawkes.globals import shutdown_event, get_max_vms, SystemResources

# Fawkes Specific imports to collect data from the system
from fawkes.db.db import FawkesDB
from fawkes.monitor import ResourceMonitor
from fawkes.db.controller_db import ControllerDB

##############################################################################
#                               GLOBALS & THEMES
##############################################################################
should_exit = False
in_edit_mode = False  # True when blocking for a field edit

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

# Global pagination variables
args_page = 0         # current page (0-based)
args_per_page = 20    # number of args per page

# Defined group boundaries for left/right navigation
group_boundaries = [0, 10, 15, 20, 21]

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

# Current screen and layout
current_screen = "configuration"  # configuration, dashboard, help
previous_screen = "configuration"  # Track last non-help screen
layouts = {
    "configuration": create_config_layout(),
    "dashboard": create_dashboard_layout(),
    "help": create_help_layout(),
}

mode = "local"
config_file = "~/.fawkes/config.json"
selected_field = 0  # Overall index among fields

reset_config = {
    "max_parallel_vms": 0,
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
    "workers": ["127.0.0.1", "127.0.0.1", "127.0.0.1"],
    "job_dir": "~/.fawkes/jobs/",
    "job_name": "change_me",
    "parallel": True
}

default_config = {
    "max_parallel_vms": 0,
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
    "workers": ["127.0.0.1", "127.0.0.1", "127.0.0.1"],
    "job_dir": "~/.fawkes/jobs/",
    "job_name": "change_me",
    "parallel": True
}

# Fields: (section, config_key, display_label)
fields = [
    ("GENERAL", "job_name",             "Job Name"),
    ("GENERAL", "max_parallel_vms",     "Max VMs"),
    ("GENERAL", "tui",                  "TUI"),
    ("GENERAL", "cleanup_stopped_vms",  "Cleanup VMs"),
    ("GENERAL", "timeout",              "Timeout"),
    ("GENERAL", "loop",                 "Loop"),
    ("GENERAL", "no_headless",          "Headless"),
    ("TARGET + FUZZ", "disk_image",     "Disk Image"),
    ("TARGET + FUZZ", "input_dir",      "Input Dir"),
    ("TARGET + FUZZ", "snapshot_name",  "Snapshot Name"),
    ("TARGET + FUZZ", "arch",           "Arch"),
    ("TARGET + FUZZ", "fuzzer",         "Fuzzer"),
    ("TARGET + FUZZ", "fuzzer_config",  "Fuzzer Config"),
    ("TARGET + FUZZ", "", ""),
    ("SHARING + STORAGE", "vfs",            "VFS"),
    ("SHARING + STORAGE", "smb",            "SMB"),
    ("SHARING + STORAGE", "crash_dir",      "Crash Dir"),
    ("SHARING + STORAGE", "share_dir",      "Share Dir"),
    ("SHARING + STORAGE", "", ""),
    ("SHARING + STORAGE", "", ""),
    ("SHARING + STORAGE", "", ""),
    ("DB + NETWORK", "db_path",             "DB"),
    ("DB + NETWORK", "controller_db_path",  "Controller DB"),
    ("DB + NETWORK", "controller_host",     "Host"),
    ("DB + NETWORK", "controller_port",     "Port"),
    ("DB + NETWORK", "", ""),
    ("DB + NETWORK", "", ""),
    ("DB + NETWORK", "", ""),
    ("WORKERS", "workers", "Workers"),
]

# A list of argument entries: (argument, description)
args_help_entries = [
    ("db", "Sqlite3 db file location (e.g., ~/.fawkes/fawkes.db)."),
    ("controller db", "Sqlite3 db file location (e.g., ~/.fawkes/controller.db)."),
    ("disk-image", "Path to the disk image (e.g., windows_98.qcow2) for local mode."),
    ("input-dir", "Directory containing fuzz test inputs for local mode."),
    ("snapshot-name", "Snapshot name to use for fuzzing (default: 'clean')."),
    ("arch", "Target architecture for QEMU (default: x86_64). Choices: i386, x86_64, aarch64, mips, mipsel, sparc, sparc64, arm, ppc, ppc64."),
    ("timeout", "Timeout per testcase in seconds. Default: 60"),
    ("parallel", "Number of parallel VMs (0 for auto). Default: 0"),
    ("loop", "Run fuzzing in an infinite loop. Default: True"),
    ("seed-dir", "Directory containing the seed files for fuzzing."),
    ("no_headless", "Turn off headless mode default False."),
    ("vfs", "Use VirtFS for sharing (Linux/Unix only)."),
    ("smb", "Use SMB for sharing (Windows only)."),
    ("crash-dir", "Directory to store crash archives. Default: ./fawkes/crashes"),
    ("fuzzer", "Fuzzer plugin to use (e.g., file, network). Default: file"),
    ("fuzzer-config", "JSON config file for fuzzer."),
    ("host", "The IP address to bind to in distributed mode (default: 0.0.0.0)."),
    ("port", "The port to listen on (default: 5000)."),
    ("poll_interval", "How often the controller polls for results (default: 60)."),
    ("job-dir", "The location for the job configs for the controller (default: ~/.fawkes/jobs/)."),
    ("workers", "A comma separated list of IP/Hostnames of the Fuzz Workers")
]

def shutdown_handler(sig, frame):
    shutdown_event.set()

def get_group_index(field_index: int) -> int:
    """Return which group (0 to 3) the field_index belongs to."""
    for g in range(len(group_boundaries) - 1):
        if group_boundaries[g] <= field_index < group_boundaries[g + 1]:
            return g
    return 0

def jump_to_group(g: int):
    """Set selected_field to the start index of group g."""
    global selected_field
    if g < 0:
        g = 0
    if g > 3:
        g = 3
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
            return [
                ("VMs Online", f"{stats['running_vms']} / {total}"),
                ("CPU Usage", f"{stats['cpu_percent']:.1f}%"),
                ("RAM Usage", f"{stats['memory_percent']:.1f}%"),
                ("", ""),
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
    general_fields = [f for f in fields if f[0] == "GENERAL"]
    target_fields = [f for f in fields if f[0] == "TARGET + FUZZ"]
    sharing_fields = [f for f in fields if f[0] == "SHARING + STORAGE"]
    dbnet_fields = [f for f in fields if f[0] == "DB + NETWORK"]
    worker_fields = [f for f in fields if f[0] == "WORKERS"]
    gen_count = len(general_fields)
    tgt_count = len(target_fields)
    share_count = len(sharing_fields)
    db_count = len(dbnet_fields)
    w_count = len(worker_fields)

    def highlight_index(base, count):
        if base <= selected_field < base + count:
            return selected_field - base
        return -1

    general_highlight = highlight_index(0, gen_count)
    target_highlight = highlight_index(7, tgt_count)
    sharing_highlight = highlight_index(14, share_count)
    db_highlight = highlight_index(21, db_count)
    w_highlight = highlight_index(28, w_count)

    gen_panel = config_table("GENERAL", general_fields, highlight_idx=general_highlight)
    tgt_panel = config_table("TARGET + FUZZ", target_fields, highlight_idx=target_highlight)
    sh_panel = config_table("SHARING + STORAGE", sharing_fields, highlight_idx=sharing_highlight)
    db_panel = config_table("DB + NETWORK", dbnet_fields, highlight_idx=db_highlight)
    w_panel = config_table("WORKERS", worker_fields, highlight_idx=w_highlight)

    layout["body"].update(
        Columns([gen_panel, tgt_panel, sh_panel, db_panel, w_panel], equal=True, expand=True)
    )

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


def update_help():
    help_text = f"""[bold bright_blue]HELP PANEL[/bold bright_blue]
                                 
Use [bold yellow][↑][↓][/bold yellow] to move within a section. Use [bold yellow][←][→][/bold yellow] to jump sections.
Press [bold cyan]Enter[/bold cyan] to edit a field, or [bold magenta]Space[/bold magenta] to toggle booleans.
    
[bright_white]Mode:[/] {mode.upper()} - Use [bold green]--mode local[/] or [yellow]--mode controller[/].
[bright_white]Workers:[/] {', '.join(default_config['workers']) if default_config['workers'] else 'None'}
[bright_white]--vfs[/] and [bright_white]--smb[/] are mutually exclusive.
[bright_white]--timeout[/]: Time per testcase (Default: 60s).
    
[dim]Shortcuts:
[d] Dashboard   [c] Config   [t] Theme toggle   [s] Save   [r] Reset   [e] Exit[/dim]
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
    for job in getData.get_active_jobs():
        jobs_table.add_row(job["id"], job["name"], job["vms"], job["status"])
    
    crash_table = Table(title="[bold bright_cyan]CRASH FEED", border_style="bright_blue", expand=True)
    crash_table.add_column("ID", style="bright_white", justify="right")
    crash_table.add_column("Type", style="red")
    crash_table.add_column("Sig", style="magenta")
    crash_table.add_column("EXP", style="cyan")
    crash_table.add_column("VM", style="green", justify="right")
    crash_table.add_column("Path", style="bright_black")
    for c in getData.get_crash_feed():
        crash_table.add_row(c["id"], c["type"], c["sig"], c["exp"], c["vm"], c["path"])
   
    logger.debug(f"Got job data: {job_data}")
    # Build paginated job panels
    try:
        start = job_page * jobs_per_page
        end   = start + jobs_per_page
        paginated_jobs = job_data[start:end]
    except Exception as e:
        logger.error(f"An error occurred building the jobs panel: {e}")
 
    # Combine the JOBS/CRASHES panels and job panels in a Group/Columns
    combined = Group(
        Columns([
            Panel(jobs_table,  title="[bold bright_cyan]JOBS",    border_style="bright_blue"),
            Panel(crash_table, title="[bold bright_cyan]CRASHES", border_style="bright_blue"),
        ], expand=True),
    )

    # Update the help region once with the combined layout
    layout["help"].update(combined)


    # Paginate job list
    try:
        start = job_page * jobs_per_page
        end = start + jobs_per_page
        paginated_jobs = job_data[start:end]
        job_panels = [job_panel(job) for job in paginated_jobs]
    except Exception as e:
        logger.error(f"An error occurred while paginateing the jobs list: {e}")
 
    layout["jobs"].update(Columns(job_panels, equal=True, expand=True))


def update_help_screen(layout):
    layout["body"].update(args_help_panel(args_page, args_per_page))
    layout["help"].update(update_help())

def update_header(layout):
    if current_screen == "help":
        hdr = f"[bold bright_cyan]FAWKES :: HELP[/]\n[green]Profile:[/] {config_file}    [yellow]Mode:[/] {mode.upper()}"
    else:
        hdr = f"[bold bright_cyan]FAWKES :: CORE CONFIG INTERFACE[/]\n[green]Profile:[/] {config_file}    [yellow]Mode:[/] {mode.upper()}"
    layout["header"].update(Panel(Align.center(hdr, vertical="middle"), border_style="bright_blue"))

def update_footer(layout):
    if current_screen == "help":
        ftr = (
            "[bold green][N]/[P][/bold green] Page Nav  "
            "[green][C][/green] Config  "
            "[yellow][D][/yellow] Dashboard  "
            "[magenta][H][/magenta] Back  "
            "[red][E][/red] Exit"
        )
    else:
        ftr = (
            "[bold green][↑][↓][/bold green] Nav Fields  "
            "[bold green][←][→][/bold green] Nav Sections  "
            "[bold yellow][Enter][/bold yellow] Edit  "
            "[bold magenta][Space][/bold magenta] Toggle Bool  "
            "[cyan][S][/cyan] Start  "
            "[red][K][/red] Stop  "
            "[yellow][Q][/yellow] Queue  "
            "[bright_black][R] Reset  "
            "[yellow][D][/yellow] Dashboard  "
            "[green][C][/green] Config  "
            "[magenta][H][/magenta] Help  "
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
        parallel = get_max_vms()
        fuzz_thread = threading.Thread(
            target=run_local_mode_background,
            args=(
                cfg,
                registry,
                parallel,
                default_config["loop"],
                default_config["input_dir"],
            ),
            name=f"FuzzThread-{job_name}",
        )
        logger.debug(
            f"parallel={parallel}, loop={default_config['loop']}, "
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
    global default_config, reset_config
    try:
        logger.debug(f"In on_press with key: {key}")
        if in_edit_mode:
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

        ch = key
        if ch == 's':
            try:
                save_config()
                start_job()
            except Exception as e:
                logger.error(f"An error occurred while starting job: {e}")
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
        elif ch == 'c':
            previous_screen = current_screen
            current_screen = "configuration"
            args_page = 0
        elif ch == 'h':
            if current_screen == "help":
                current_screen = previous_screen
            else:
                previous_screen = current_screen
                current_screen = "help"
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
    global console
    setup_tty()
    with console.screen():
        while not should_exit:
            layout = layouts[current_screen]
            update_header(layout)
            update_footer(layout)
            key = poll_for_keypress()
            if key:
                try:
                    on_press(key)
                except Exception as e:
                    logger.error(f"An Exception occurred calling on_press: {e}")
            if in_edit_mode:
                logger.debug("in_edit_mode set by the user pressing enter")
                termios.tcflush(sys.stdin, termios.TCIOFLUSH)
                _, cfg_key, lbl = fields[selected_field]
                edit_config_field(lbl, cfg_key)
            if current_screen == "configuration":
                layout = layouts["configuration"]
                update_config_body(layout)
                layout["help"].update(update_help())
            elif current_screen == "dashboard":
                layout = layouts["dashboard"]
                update_dashboard(layout)
            elif current_screen == "help":
                layout = layouts["help"]
                layout["body"].update(args_help_panel(args_page, args_per_page))
                layout["help"].update(update_help())
            console.print(layout)
            time.sleep(0.1)
    restore_tty()
    termios.tcflush(sys.stdin, termios.TCIOFLUSH)
    console.clear()
    console.print("[bold green]Exited cleanly![/]")

if __name__ == "__main__":
    main()
