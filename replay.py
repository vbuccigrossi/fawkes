#!/usr/bin/env python3
"""
Fawkes Crash Replay System

Reproduce crashes with a single command, optionally with GDB attached.
"""

import os
import sys
import time
import logging
import zipfile
import tempfile
import shutil
import json
from pathlib import Path
from typing import Optional, Dict, Any

# Handle imports whether run as script or module
try:
    from config import FawkesConfig, VMRegistry
    from qemu import QemuManager
    from gdb import GdbFuzzManager
    from db.db import FawkesDB
except ModuleNotFoundError:
    # If running from different directory, add to path
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from config import FawkesConfig, VMRegistry
    from qemu import QemuManager
    from gdb import GdbFuzzManager
    from db.db import FawkesDB

logger = logging.getLogger("fawkes.replay")


class CrashReplay:
    """Handles crash reproduction and debugging."""

    def __init__(self, config: FawkesConfig):
        self.config = config
        self.logger = logging.getLogger("fawkes.CrashReplay")

    def replay_from_crash_id(self, crash_id: int, attach_gdb: bool = False, interactive: bool = True) -> bool:
        """Replay a crash from the database by crash ID."""
        self.logger.info(f"Loading crash {crash_id} from database")

        # Load crash from database
        db = FawkesDB(self.config.db_path)
        try:
            crash_data = self._load_crash_from_db(db, crash_id)
            if not crash_data:
                self.logger.error(f"Crash {crash_id} not found in database")
                return False

            return self._replay_crash(crash_data, attach_gdb, interactive)
        finally:
            db.close()

    def replay_from_zip(self, crash_zip_path: str, attach_gdb: bool = False, interactive: bool = True) -> bool:
        """Replay a crash from a crash archive zip file."""
        self.logger.info(f"Loading crash from zip: {crash_zip_path}")

        if not os.path.exists(crash_zip_path):
            self.logger.error(f"Crash zip not found: {crash_zip_path}")
            return False

        crash_data = self._load_crash_from_zip(crash_zip_path)
        if not crash_data:
            return False

        return self._replay_crash(crash_data, attach_gdb, interactive)

    def _load_crash_from_db(self, db: FawkesDB, crash_id: int) -> Optional[Dict[str, Any]]:
        """Load crash details from database."""
        try:
            cursor = db._conn.cursor()
            cursor.execute("""
                SELECT crash_id, job_id, testcase_path, crash_type, details,
                       signature, exploitability, crash_file, timestamp, duplicate_count
                FROM crashes WHERE crash_id = ?
            """, (crash_id,))

            row = cursor.fetchone()
            if not row:
                return None

            crash_data = {
                'crash_id': row[0],
                'job_id': row[1],
                'testcase_path': row[2],
                'crash_type': row[3],
                'details': row[4],
                'signature': row[5],
                'exploitability': row[6],
                'crash_file': row[7],
                'timestamp': row[8],
                'duplicate_count': row[9]
            }

            # Load job info to get disk image and snapshot
            cursor.execute("SELECT disk, snapshot FROM jobs WHERE job_id = ?", (crash_data['job_id'],))
            job_row = cursor.fetchone()
            if job_row:
                crash_data['disk_image'] = job_row[0]
                crash_data['snapshot_name'] = job_row[1]

            self.logger.debug(f"Loaded crash data: {crash_data}")
            return crash_data

        except Exception as e:
            self.logger.error(f"Error loading crash from database: {e}", exc_info=True)
            return None

    def _load_crash_from_zip(self, zip_path: str) -> Optional[Dict[str, Any]]:
        """Extract crash details from zip archive."""
        try:
            crash_data = {}

            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Look for crash_info.json or crash_info.txt
                if 'crash_info.json' in zf.namelist():
                    with zf.open('crash_info.json') as f:
                        crash_data = json.load(f)
                elif 'crash_info.txt' in zf.namelist():
                    # Parse text format
                    with zf.open('crash_info.txt') as f:
                        content = f.read().decode('utf-8')
                        crash_data = self._parse_crash_info_text(content)

                # Extract testcase
                testcase_files = [name for name in zf.namelist() if name.startswith('testcase/')]
                if testcase_files:
                    # Create temp directory for extracted files
                    temp_dir = tempfile.mkdtemp(prefix='fawkes_replay_')
                    testcase_name = os.path.basename(testcase_files[0])
                    testcase_path = os.path.join(temp_dir, testcase_name)

                    with zf.open(testcase_files[0]) as src:
                        with open(testcase_path, 'wb') as dst:
                            dst.write(src.read())

                    crash_data['testcase_path'] = testcase_path
                    crash_data['temp_dir'] = temp_dir
                    self.logger.debug(f"Extracted testcase to: {testcase_path}")

            # Add metadata from filename if available
            # Format: crash_<job>_<timestamp>_exploitability_<level>.zip
            basename = os.path.basename(zip_path)
            if '_exploitability_' in basename:
                parts = basename.split('_exploitability_')
                if len(parts) == 2:
                    exploitability = parts[1].replace('.zip', '')
                    crash_data['exploitability'] = exploitability

            crash_data['source'] = 'zip'
            crash_data['zip_path'] = zip_path

            return crash_data

        except Exception as e:
            self.logger.error(f"Error loading crash from zip: {e}", exc_info=True)
            return None

    def _parse_crash_info_text(self, content: str) -> Dict[str, Any]:
        """Parse crash_info.txt format."""
        crash_data = {}
        lines = content.split('\n')

        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()

                if key == 'signal':
                    crash_data['crash_type'] = value
                elif key == 'desc':
                    crash_data['details'] = value

        return crash_data

    def _replay_crash(self, crash_data: Dict[str, Any], attach_gdb: bool, interactive: bool) -> bool:
        """Reproduce the crash."""
        self.logger.info("=" * 60)
        self.logger.info("CRASH REPLAY")
        self.logger.info("=" * 60)

        # Display crash information
        self._display_crash_info(crash_data)

        # Check if we have required data
        if 'testcase_path' not in crash_data or not os.path.exists(crash_data['testcase_path']):
            self.logger.error("Testcase file not found - cannot replay")
            return False

        # Get disk image and snapshot
        disk_image = crash_data.get('disk_image') or self.config.disk_image
        snapshot_name = crash_data.get('snapshot_name') or self.config.snapshot_name

        if not os.path.exists(disk_image):
            self.logger.error(f"Disk image not found: {disk_image}")
            return False

        self.logger.info(f"Using disk image: {disk_image}")
        self.logger.info(f"Using snapshot: {snapshot_name}")

        # Confirm if interactive
        if interactive:
            response = input("\nProceed with crash replay? [Y/n]: ")
            if response.lower() in ('n', 'no'):
                self.logger.info("Replay cancelled by user")
                return False

        # Create temporary VM registry
        temp_registry_path = os.path.join(tempfile.gettempdir(), f"fawkes_replay_registry_{os.getpid()}.json")
        registry = VMRegistry(temp_registry_path)

        try:
            # Create QEMU manager
            qemu_mgr = QemuManager(self.config, registry)

            # Create temporary disk copy
            temp_dir = tempfile.mkdtemp(prefix='fawkes_replay_vm_')
            temp_disk = os.path.join(temp_dir, 'replay_disk.qcow2')

            self.logger.info("Copying disk image (this may take a moment)...")
            shutil.copy2(disk_image, temp_disk)

            # Create share directory and copy testcase
            share_dir = os.path.join(temp_dir, 'share')
            os.makedirs(share_dir, exist_ok=True)

            testcase_name = os.path.basename(crash_data['testcase_path'])
            dest_testcase = os.path.join(share_dir, testcase_name)
            shutil.copy2(crash_data['testcase_path'], dest_testcase)

            self.logger.info(f"Testcase copied to share: {dest_testcase}")

            # Start VM
            self.logger.info("Starting VM...")
            vm_id = qemu_mgr.start_vm(
                disk=temp_disk,
                debug=True,
                pause_on_start=True if attach_gdb else False
            )

            if not vm_id:
                self.logger.error("Failed to start VM")
                return False

            self.logger.info(f"VM started (ID: {vm_id})")

            # Get VM info for GDB connection
            vm_info = registry.get_vm(vm_id)
            debug_port = vm_info['debug_port']

            if attach_gdb:
                self.logger.info("=" * 60)
                self.logger.info("GDB DEBUGGING SESSION")
                self.logger.info("=" * 60)
                self.logger.info(f"VM is paused and waiting for GDB")
                self.logger.info(f"Debug port: {debug_port}")
                self.logger.info(f"Testcase: {dest_testcase}")
                self.logger.info("")
                self.logger.info("To attach GDB manually:")
                self.logger.info(f"  gdb")
                self.logger.info(f"  (gdb) target remote localhost:{debug_port}")
                self.logger.info(f"  (gdb) continue")
                self.logger.info("")

                if interactive:
                    response = input("Launch GDB automatically? [Y/n]: ")
                    if response.lower() not in ('n', 'no'):
                        self._launch_gdb(debug_port)
                else:
                    self._launch_gdb(debug_port)
            else:
                # Start GDB fuzz manager to monitor crash
                self.logger.info("Monitoring for crash...")
                gdb_mgr = GdbFuzzManager(qemu_mgr, self.config.timeout)
                gdb_mgr.start_fuzz_worker(vm_id, fuzz_loop=False)

                # Wait for worker to complete
                worker_thread = gdb_mgr.workers.get(vm_id)
                if worker_thread:
                    worker_thread.join()

                    # Check if crash was detected
                    gdb_worker = gdb_mgr.get_worker(vm_id)
                    if gdb_worker and gdb_worker.crash_detected:
                        self.logger.info("=" * 60)
                        self.logger.info("CRASH REPRODUCED!")
                        self.logger.info("=" * 60)
                        self.logger.info(f"Crash Type: {gdb_worker.crash_info.get('type')}")
                        if gdb_worker.crash_info.get('type') == 'user':
                            self.logger.info(f"PID: {gdb_worker.crash_info.get('pid')}")
                            self.logger.info(f"EXE: {gdb_worker.crash_info.get('exe')}")
                            self.logger.info(f"Exception: {gdb_worker.crash_info.get('exception')}")
                        return True
                    else:
                        self.logger.warning("Crash was not reproduced within timeout")
                        self.logger.warning("This could mean:")
                        self.logger.warning("  - Crash is timing-dependent")
                        self.logger.warning("  - Snapshot state is different")
                        self.logger.warning("  - Timeout too short")
                        return False

            # Keep VM running if in GDB mode
            if attach_gdb and interactive:
                input("\nPress Enter to stop VM and cleanup...")

            # Cleanup
            self.logger.info("Stopping VM and cleaning up...")
            qemu_mgr.stop_vm(vm_id, force=True)

            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

            return True

        except Exception as e:
            self.logger.error(f"Error during replay: {e}", exc_info=True)
            return False
        finally:
            # Cleanup temp registry
            if os.path.exists(temp_registry_path):
                os.remove(temp_registry_path)

            # Cleanup temp dir from zip extraction
            if 'temp_dir' in crash_data and os.path.exists(crash_data['temp_dir']):
                shutil.rmtree(crash_data['temp_dir'], ignore_errors=True)

    def _display_crash_info(self, crash_data: Dict[str, Any]):
        """Display crash information."""
        self.logger.info("")
        self.logger.info("Crash Details:")
        self.logger.info("-" * 60)

        if 'crash_id' in crash_data:
            self.logger.info(f"Crash ID: {crash_data['crash_id']}")

        if 'crash_type' in crash_data:
            self.logger.info(f"Type: {crash_data['crash_type']}")

        if 'exploitability' in crash_data and crash_data['exploitability']:
            exploitability = crash_data['exploitability']
            self.logger.info(f"Exploitability: {exploitability}")

        if 'details' in crash_data:
            self.logger.info(f"Details: {crash_data['details']}")

        if 'signature' in crash_data:
            self.logger.info(f"Signature: {crash_data['signature'][:16]}...")

        if 'duplicate_count' in crash_data and crash_data['duplicate_count'] > 0:
            self.logger.info(f"Duplicates: {crash_data['duplicate_count']}")

        if 'timestamp' in crash_data:
            from datetime import datetime
            ts = datetime.fromtimestamp(crash_data['timestamp'])
            self.logger.info(f"Discovered: {ts.strftime('%Y-%m-%d %H:%M:%S')}")

        self.logger.info("-" * 60)
        self.logger.info("")

    def _launch_gdb(self, debug_port: int):
        """Launch GDB and attach to the VM."""
        import subprocess

        # Create GDB initialization script
        gdb_script = f"""
target remote localhost:{debug_port}
set confirm off
set pagination off
echo \\n
echo ====================================\\n
echo Fawkes Crash Replay - GDB Session\\n
echo ====================================\\n
echo VM is paused. Use 'continue' to run.\\n
echo \\n
"""

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gdb', delete=False) as f:
            f.write(gdb_script)
            gdb_init_file = f.name

        try:
            # Launch GDB
            self.logger.info(f"Launching GDB...")
            subprocess.run(['gdb', '-q', '-x', gdb_init_file])
        except FileNotFoundError:
            self.logger.error("GDB not found. Please install gdb.")
        except Exception as e:
            self.logger.error(f"Error launching GDB: {e}")
        finally:
            # Cleanup
            if os.path.exists(gdb_init_file):
                os.remove(gdb_init_file)


def main():
    """CLI entry point for crash replay."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fawkes Crash Replay - Reproduce crashes with debugging support"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--crash-id', type=int, help='Crash ID from database')
    group.add_argument('--crash-zip', type=str, help='Path to crash archive zip file')

    parser.add_argument('--attach-gdb', action='store_true', help='Attach GDB for interactive debugging')
    parser.add_argument('--non-interactive', action='store_true', help='Run without user prompts')
    parser.add_argument('--disk-image', type=str, help='Override disk image path')
    parser.add_argument('--snapshot', type=str, help='Override snapshot name')
    parser.add_argument('--timeout', type=int, default=60, help='Timeout in seconds (default: 60)')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])

    args = parser.parse_args()

    # Setup logging
    from logger import setup_fawkes_logger
    log_level = getattr(logging, args.log_level.upper())
    logger = setup_fawkes_logger(log_level)

    # Load config
    from config import FawkesConfig
    cfg = FawkesConfig.load()

    # Override with CLI args
    if args.disk_image:
        cfg.disk_image = os.path.expanduser(args.disk_image)
    if args.snapshot:
        cfg.snapshot_name = args.snapshot
    cfg.timeout = args.timeout

    # Create replay instance
    replayer = CrashReplay(cfg)

    # Execute replay
    try:
        if args.crash_id:
            success = replayer.replay_from_crash_id(
                args.crash_id,
                attach_gdb=args.attach_gdb,
                interactive=not args.non_interactive
            )
        else:
            success = replayer.replay_from_zip(
                args.crash_zip,
                attach_gdb=args.attach_gdb,
                interactive=not args.non_interactive
            )

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("\nReplay interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
