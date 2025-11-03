# fawkes/main.py
import argparse
import logging
import sys
import os
import time
import threading 
import signal
import curses
from fawkes.logger import setup_fawkes_logger
from fawkes.config import FawkesConfig, VMRegistry, FawkesConfigError
from fawkes.modes.local import run_local_mode
from fawkes.modes.controller import run_controller_mode
from fawkes.modes.worker import run_worker_mode
from fawkes.globals import shutdown_event, get_max_vms

def signal_handler(sig, frame):
    """Handle SIGINT/SIGTERM for graceful shutdown."""
    print("\nReceived shutdown signal—cleaning up...")
    shutdown_event.set()


def main():
    parser = argparse.ArgumentParser(
        description="Fawkes: Enterprise-Grade QEMU/GDB-based Fuzzing Framework"
    )
    parser.add_argument("--mode", choices=["local", "controller", "worker"], default="local",
                        help="Which mode to run in: local (single-node), controller, or worker.")
    parser.add_argument("--config", default=None,
                        help="Optional path to an alternate config file (otherwise uses default in ~/.fawkes/).")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Set the logging level for Fawkes.")
    parser.add_argument("--db-uri", default=None,
                        help="If in controller/worker mode, specify a DB URI (e.g., postgres://user:pass@host/db).")
    parser.add_argument("--quiet", action="store_true",
                        help="Minimize console output (overrides log-level to WARNING).")
    parser.add_argument("--tui", action="store_true", help="Launch the TUI after starting the mode")
    parser.add_argument("--disk-image", default=None,
                        help="Path to the disk image (e.g., windows_98.qcow2) for local mode.")
    parser.add_argument("--input-dir", default=None,
                        help="Directory containing fuzz test inputs for local mode.")
    parser.add_argument("--snapshot-name", default=None,
                        help="Snapshot name to use for fuzzing (default: 'clean').")
    parser.add_argument("--arch", default="x86_64",
                        choices=["i386", "x86_64", "aarch64", "mips", "mipsel", "sparc", "sparc64", "arm", "ppc", "ppc64"],
                        help="Target architecture for QEMU (default: x86_64).")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout per testcase in seconds")
    parser.add_argument("--parallel", type=int, default=1, help="Number of parallel VMs (0 for auto)")
    parser.add_argument("--loop", action="store_true", default=True, help="Run fuzzing in an infinite loop")
    parser.add_argument("--seed-dir", type=str, help="Directory containing the seed files for fuzzing")
    parser.add_argument("--no-headless", action="store_true", help="Turn off headless mode default")
    parser.add_argument("--vfs", action="store_true", help="Use VirtFS for sharing (Linux/Unix only)")
    parser.add_argument("--smb", action="store_true", help="Use SMB for sharing (Windows only)")
    parser.add_argument("--crash-dir", default="./fawkes/crashes", help="Directory to store crash archives")
    parser.add_argument("--fuzzer", default="file", help="Fuzzer plugin to use (e.g., file, network)")
    parser.add_argument("--fuzzer-config", help="JSON config file for fuzzer")
    parser.add_argument("--analyze-crashes", action="store_true", help="Analyze existing crash zips")
    parser.add_argument("--controller_host", type=str, help="The IP address to bind to in distributed mode (default 0.0.0.0)")
    parser.add_argument("--controller_port", type=int, help="The port to listen on (default 5000)")
    parser.add_argument("--poll-interval", type=int, help="How often the controller pols for results (default 60)")
    parser.add_argument("--job-dir", type=str, help="The location for the job configs for the controller (default ~/.fawkes/jobs/")
    parser.add_argument("--name", type=str, help="The human readable name you assign the fuzz job (default change_me")
    parser.add_argument("--vm-params", type=str, help="The base args to be passed to the VM on start (-smp 4 -cpu Skylake-Client-v3 -enable-kvm -m 4096)")
    
    args = parser.parse_args()

    # For just running the crash analysis on a crash and not the entire system
    if args.analyze_crashes:
        from fawkes.analysis import load_analyzer
        analyzer = load_analyzer(cfg.arch, cfg.crash_dir)
        for crash_zip in glob.glob(os.path.join(cfg.crash_dir, "*.zip")):
            analyzer.analyze_crash(crash_zip)
        return

    # Check to make sure users aren't using exclusive flags
    if args.vfs and args.smb:
        logger.error("Cannot use both --vfs and --smb together—choose one.\n Exiting...")
        return

    # 2) Configure logging
    log_level = logging._nameToLevel.get(args.log_level.upper(), logging.INFO)
    if args.quiet:
        log_level = logging.WARNING
    logger = setup_fawkes_logger(log_level)
    logger.info(f"Starting Fawkes in '{args.mode}' mode...")


    # Register signal handlers, so we can actually quit 
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


    # 3) Load configuration
    try:
        if args.config:
            logger.debug(f"Ignoring --config={args.config} for now; custom config load not implemented.")
        cfg = FawkesConfig.load()

        # Override config with CLI args if provided
        if args.name:
           cfg.job_name=args.name
           logger.info(f"Using name: {cfg.job_name}")
        if args.poll_interval:
           cfg.poll_interval=args.poll_interval
           logger.info(f"Using poll interval: {cfg.poll_interval}")
        if args.job_dir:
           cfg.Job_dir=args.job_dir
           logger.info(f"Using job directory: {cfg.job_dir}")
        if args.controller_port:
           cfg.controller_port=args.controller_port
           logger.info(f"Using port: {cfg.controller_port}")
        if args.controller_host:
           cfg.controller_host=args.controller_host
           logger.info(f"Binging to IP address: {cfg.controller_host}")
        if args.fuzzer:
           cfg.fuzzer=args.fuzzer
           logger.info(f"Using Fuzzer: {cfg.fuzzer}")
        if args.fuzzer_config:
           cfg.fuzzer_config=fuzzer_config
           logger.info(f"Using fuzzer configuration: {cfg.fuzzer_config}")
        if args.crash_dir:
           cfg.crash_dir = args.crash_dir
           logger.info(f"Using Crash output dir: {cfg.crash_dir}")
        if args.vfs:
           cfg.vfs = args.vfs
           logger.info(f"Using VirtFS for mounting system")
        if args.smb:
           cfg.smb = args.smb
           logger.info(f"Using SMB for mounting system")
        if args.no_headless:
            cfg.no_headless = args.no_headless
            logger.info(f"Using headless option from CLI: {cfg.no_headless}")
        if args.loop:
            cfg.loop = args.loop
            logger.info(f"Using loop option from CLI: {cfg.loop}")
        if args.timeout:
            cfg.timeout = args.timeout
            logger.info(f"Using timeout from CLI: {cfg.timeout}")
        if args.disk_image:
            cfg.disk_image = os.path.expanduser(args.disk_image)
            logger.info(f"Using disk image from CLI: {cfg.disk_image}")
        if args.input_dir:
            cfg.input_dir = os.path.expanduser(args.input_dir)
            logger.info(f"Using input directory from CLI: {cfg.input_dir}")
        if args.snapshot_name:
            cfg.snapshot_name = args.snapshot_name
            logger.info(f"Using snapshot name from CLI: {cfg.snapshot_name}")
        if args.db_uri:
            cfg.db_uri = args.db_uri
        if args.arch:
            cfg.arch = args.arch  # Store the architecture
            logger.info(f"Using architecture from CLI: {cfg.arch}")
        cfg.tui = args.tui

    except FawkesConfigError as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    # 4) Initialize or load the VM registry
    try:
        registry = VMRegistry(cfg.get("registry_file"))
    except FawkesConfigError as e:
        logger.error(f"Failed to load VM registry: {e}")
        sys.exit(1)

    # 5) Dispatch to the appropriate mode
    try:
        if args.mode == "local":
            parallel = args.parallel if args.parallel > 0 else get_max_vms()  # Auto if 0
            if args.tui:
                fuzz_thread = threading.Thread(
                    target=run_local_mode,
                    args=(cfg, registry),
                    kwargs={"parallel": parallel, "loop": args.loop, "seed_dir": args.seed_dir},
                    name="FuzzThread"
                )
                fuzz_thread.start()
                fuzz_thread.join()
            else:
                run_local_mode(cfg, registry, parallel=parallel, loop=args.loop, seed_dir=args.seed_dir)
        elif args.mode == "controller":
            run_controller_mode(cfg)
        elif args.mode == "worker":
            run_worker_mode(cfg)

    except Exception as e:
        logger.error(f"Error running {args.mode} mode: {e}", exc_info=True)
        sys.exit(1)

    logger.info("Fawkes has finished execution. Goodbye!")

if __name__ == "__main__":
    main()
