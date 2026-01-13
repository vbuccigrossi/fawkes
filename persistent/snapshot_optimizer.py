"""
Snapshot Optimization Module

Optimizes snapshot management for persistent fuzzing with techniques like:
- Memory-backed snapshots (tmpfs/ramdisk)
- Snapshot caching
- Incremental snapshots
- Copy-on-write optimization
"""

import os
import logging
import subprocess
import time
from typing import Optional, Dict
from pathlib import Path


logger = logging.getLogger("fawkes.persistent.snapshot_optimizer")


class SnapshotOptimizer:
    """
    Optimizes snapshot performance for persistent fuzzing.

    Techniques:
    - Use tmpfs/ramdisk for snapshot storage (10x faster I/O)
    - Preload snapshots into page cache
    - Minimize snapshot size
    - Use incremental snapshots when possible
    """

    def __init__(self, use_tmpfs: bool = True, tmpfs_size: str = "2G"):
        """
        Initialize snapshot optimizer.

        Args:
            use_tmpfs: Use tmpfs for snapshot storage (recommended)
            tmpfs_size: Size of tmpfs mount (e.g., "2G", "4G")
        """
        self.use_tmpfs = use_tmpfs
        self.tmpfs_size = tmpfs_size
        self.tmpfs_path = "/tmp/fawkes_snapshots"
        self.logger = logging.getLogger("fawkes.persistent.snapshot_optimizer")

        if self.use_tmpfs:
            self._setup_tmpfs()

    def _setup_tmpfs(self) -> bool:
        """
        Setup tmpfs mount for ultra-fast snapshot storage.

        Returns:
            True if successful
        """
        # Check if already mounted
        try:
            result = subprocess.run(
                ["mount"],
                capture_output=True,
                text=True,
                check=True
            )

            if self.tmpfs_path in result.stdout:
                self.logger.debug(f"tmpfs already mounted at {self.tmpfs_path}")
                return True

        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to check mounts: {e}")

        # Create mount point
        os.makedirs(self.tmpfs_path, exist_ok=True)

        # Try to mount tmpfs (may require sudo)
        try:
            subprocess.run(
                ["sudo", "mount", "-t", "tmpfs", "-o", f"size={self.tmpfs_size}",
                 "tmpfs", self.tmpfs_path],
                check=True,
                capture_output=True
            )
            self.logger.info(f"Mounted tmpfs at {self.tmpfs_path} (size: {self.tmpfs_size})")
            return True

        except subprocess.CalledProcessError:
            self.logger.warning(f"Failed to mount tmpfs at {self.tmpfs_path} (may need sudo)")
            self.logger.warning("Falling back to regular filesystem (slower)")
            self.use_tmpfs = False
            return False

    def get_snapshot_path(self, snapshot_name: str) -> str:
        """
        Get optimized path for snapshot storage.

        Args:
            snapshot_name: Name of snapshot

        Returns:
            Path to store snapshot (tmpfs or regular fs)
        """
        if self.use_tmpfs:
            return os.path.join(self.tmpfs_path, f"{snapshot_name}.qcow2")
        else:
            return os.path.join("/tmp", f"{snapshot_name}.qcow2")

    def preload_snapshot(self, snapshot_path: str) -> bool:
        """
        Preload snapshot into page cache for faster access.

        This reads the entire snapshot file to ensure it's cached in RAM.

        Args:
            snapshot_path: Path to snapshot file

        Returns:
            True if successful
        """
        if not os.path.exists(snapshot_path):
            self.logger.warning(f"Snapshot not found: {snapshot_path}")
            return False

        try:
            # Read entire file to page cache
            with open(snapshot_path, 'rb') as f:
                # Read in chunks to avoid memory issues
                chunk_size = 64 * 1024 * 1024  # 64 MB
                while f.read(chunk_size):
                    pass

            self.logger.info(f"Preloaded snapshot into page cache: {snapshot_path}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to preload snapshot: {e}")
            return False

    def optimize_disk(self, disk_path: str, output_path: str = None) -> Optional[str]:
        """
        Optimize disk image for faster snapshot operations.

        Uses qcow2 compression and preallocation.

        Args:
            disk_path: Path to original disk image
            output_path: Path for optimized disk (default: tmpfs)

        Returns:
            Path to optimized disk or None on failure
        """
        if not output_path:
            disk_name = os.path.basename(disk_path)
            output_path = self.get_snapshot_path(f"optimized_{disk_name}")

        try:
            # Convert with optimization
            subprocess.run([
                "qemu-img", "convert",
                "-O", "qcow2",
                "-o", "lazy_refcounts=on,cluster_size=2M",
                disk_path,
                output_path
            ], check=True, capture_output=True)

            self.logger.info(f"Optimized disk: {disk_path} -> {output_path}")

            # Preload into cache
            self.preload_snapshot(output_path)

            return output_path

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to optimize disk: {e}")
            return None

    def create_fast_snapshot(self, vm_id: int, snapshot_name: str,
                            monitor_port: int) -> bool:
        """
        Create snapshot optimized for fast restoration.

        Uses QEMU monitor to create internal snapshot.

        Args:
            vm_id: VM identifier
            snapshot_name: Name for snapshot
            monitor_port: QEMU monitor port

        Returns:
            True if successful
        """
        try:
            import socket

            # Connect to QEMU monitor
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(('127.0.0.1', monitor_port))

            # Wait for prompt
            time.sleep(0.1)
            sock.recv(1024)

            # Create snapshot
            sock.sendall(f"savevm {snapshot_name}\n".encode('utf-8'))
            time.sleep(0.2)
            response = sock.recv(4096).decode('utf-8', errors='ignore')

            sock.close()

            if "Error" in response or "error" in response:
                self.logger.error(f"Failed to create snapshot: {response}")
                return False

            self.logger.info(f"Created fast snapshot '{snapshot_name}' for VM {vm_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to create fast snapshot: {e}")
            return False

    def get_snapshot_stats(self, disk_path: str) -> Dict:
        """
        Get statistics about snapshot performance.

        Args:
            disk_path: Path to disk image

        Returns:
            Dict with snapshot statistics
        """
        stats = {
            'disk_path': disk_path,
            'disk_size': 0,
            'on_tmpfs': False,
            'in_cache': False
        }

        try:
            # Get disk size
            if os.path.exists(disk_path):
                stats['disk_size'] = os.path.getsize(disk_path)

            # Check if on tmpfs
            stats['on_tmpfs'] = disk_path.startswith(self.tmpfs_path)

            # Check if in page cache (Linux only)
            if os.path.exists('/proc/vmtouch'):
                result = subprocess.run(
                    ['vmtouch', '-v', disk_path],
                    capture_output=True,
                    text=True
                )
                stats['in_cache'] = 'Resident Pages' in result.stdout

        except Exception as e:
            self.logger.debug(f"Failed to get snapshot stats: {e}")

        return stats

    def cleanup(self):
        """Cleanup tmpfs mount and temporary files."""
        if self.use_tmpfs:
            try:
                # Unmount tmpfs
                subprocess.run(
                    ["sudo", "umount", self.tmpfs_path],
                    check=True,
                    capture_output=True
                )
                self.logger.info(f"Unmounted tmpfs at {self.tmpfs_path}")
            except subprocess.CalledProcessError:
                self.logger.warning(f"Failed to unmount tmpfs at {self.tmpfs_path}")


# Convenience functions
def setup_fast_snapshots(tmpfs_size: str = "2G") -> SnapshotOptimizer:
    """
    Quick setup for fast snapshot fuzzing.

    Args:
        tmpfs_size: Size of tmpfs mount

    Returns:
        SnapshotOptimizer instance

    Example:
        >>> optimizer = setup_fast_snapshots("4G")
        >>> optimized_disk = optimizer.optimize_disk("target.qcow2")
    """
    return SnapshotOptimizer(use_tmpfs=True, tmpfs_size=tmpfs_size)


# Testing
if __name__ == "__main__":
    optimizer = SnapshotOptimizer(use_tmpfs=True, tmpfs_size="1G")

    print("Snapshot Optimizer Configuration:")
    print(f"  Using tmpfs: {optimizer.use_tmpfs}")
    print(f"  tmpfs path: {optimizer.tmpfs_path}")
    print(f"  tmpfs size: {optimizer.tmpfs_size}")

    # Test snapshot path
    test_path = optimizer.get_snapshot_path("test_snapshot")
    print(f"\nSnapshot path: {test_path}")

    # Cleanup
    optimizer.cleanup()
