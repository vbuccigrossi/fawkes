"""
KCOV Manager

Manages kernel coverage collection via KCOV (Kernel Coverage).
"""

import os
import struct
import logging
import mmap
from typing import List, Set, Optional
from pathlib import Path


logger = logging.getLogger("fawkes.kernel.kcov")


class KCOVManager:
    """
    Manages KCOV for kernel code coverage collection.

    KCOV is a kernel subsystem that provides code coverage information.
    It requires kernel to be compiled with CONFIG_KCOV=y.

    Usage:
        1. Open /dev/kcov
        2. Configure buffer size with KCOV_INIT_TRACE
        3. mmap() the buffer
        4. Enable tracing with KCOV_ENABLE
        5. Execute syscalls
        6. Read coverage from buffer
        7. Disable tracing with KCOV_DISABLE

    Coverage format:
        - First 64-bit word: number of PCs
        - Remaining words: PC values (64-bit each)
    """

    # KCOV ioctl commands
    KCOV_INIT_TRACE = 0x80086301
    KCOV_ENABLE = 0x6364
    KCOV_DISABLE = 0x6365

    # Coverage modes
    KCOV_TRACE_PC = 0  # Trace program counter
    KCOV_TRACE_CMP = 1  # Trace comparisons

    # Default buffer size (in 64-bit words)
    DEFAULT_BUFFER_SIZE = 256 * 1024  # 2MB

    def __init__(self, kcov_path: str = "/dev/kcov", buffer_size: int = None):
        """
        Initialize KCOV manager.

        Args:
            kcov_path: Path to KCOV device
            buffer_size: Buffer size in 64-bit words
        """
        self.kcov_path = kcov_path
        self.buffer_size = buffer_size or self.DEFAULT_BUFFER_SIZE
        self.logger = logging.getLogger("fawkes.kernel.kcov")

        self.kcov_fd: Optional[int] = None
        self.coverage_buffer: Optional[mmap.mmap] = None
        self.enabled = False

    def is_available(self) -> bool:
        """
        Check if KCOV is available.

        Returns:
            True if /dev/kcov exists
        """
        return os.path.exists(self.kcov_path)

    def initialize(self) -> bool:
        """
        Initialize KCOV device.

        Returns:
            True if initialization successful
        """
        if not self.is_available():
            self.logger.error(f"KCOV not available at {self.kcov_path}")
            self.logger.error("Kernel must be compiled with CONFIG_KCOV=y")
            return False

        try:
            # Open KCOV device
            self.kcov_fd = os.open(self.kcov_path, os.O_RDWR)

            # Configure buffer size
            import fcntl
            fcntl.ioctl(self.kcov_fd, self.KCOV_INIT_TRACE, self.buffer_size)

            # Map coverage buffer
            buffer_bytes = self.buffer_size * 8  # 8 bytes per word
            self.coverage_buffer = mmap.mmap(
                self.kcov_fd,
                buffer_bytes,
                mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE
            )

            self.logger.info(f"KCOV initialized with {self.buffer_size} word buffer")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize KCOV: {e}")
            if self.kcov_fd:
                os.close(self.kcov_fd)
                self.kcov_fd = None
            return False

    def enable(self, mode: int = None) -> bool:
        """
        Enable coverage tracing.

        Args:
            mode: Coverage mode (KCOV_TRACE_PC or KCOV_TRACE_CMP)

        Returns:
            True if enabled successfully
        """
        if not self.kcov_fd:
            self.logger.error("KCOV not initialized")
            return False

        if mode is None:
            mode = self.KCOV_TRACE_PC

        try:
            import fcntl
            fcntl.ioctl(self.kcov_fd, self.KCOV_ENABLE, mode)
            self.enabled = True
            self.logger.debug("KCOV tracing enabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to enable KCOV: {e}")
            return False

    def disable(self) -> bool:
        """
        Disable coverage tracing.

        Returns:
            True if disabled successfully
        """
        if not self.kcov_fd:
            return False

        try:
            import fcntl
            fcntl.ioctl(self.kcov_fd, self.KCOV_DISABLE, 0)
            self.enabled = False
            self.logger.debug("KCOV tracing disabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to disable KCOV: {e}")
            return False

    def get_coverage(self) -> List[int]:
        """
        Read coverage data from buffer.

        Returns:
            List of PC values
        """
        if not self.coverage_buffer:
            return []

        try:
            # Read number of PCs from first word
            self.coverage_buffer.seek(0)
            n_pcs_bytes = self.coverage_buffer.read(8)
            n_pcs = struct.unpack('Q', n_pcs_bytes)[0]

            if n_pcs == 0 or n_pcs > self.buffer_size - 1:
                return []

            # Read PC values
            pcs = []
            for i in range(int(n_pcs)):
                pc_bytes = self.coverage_buffer.read(8)
                pc = struct.unpack('Q', pc_bytes)[0]
                pcs.append(pc)

            return pcs

        except Exception as e:
            self.logger.error(f"Failed to read coverage: {e}")
            return []

    def reset_coverage(self):
        """Reset coverage buffer."""
        if self.coverage_buffer:
            self.coverage_buffer.seek(0)
            self.coverage_buffer.write(b'\x00' * 8)  # Set n_pcs to 0

    def get_coverage_count(self) -> int:
        """
        Get number of covered PCs.

        Returns:
            Number of PCs
        """
        if not self.coverage_buffer:
            return 0

        try:
            self.coverage_buffer.seek(0)
            n_pcs_bytes = self.coverage_buffer.read(8)
            n_pcs = struct.unpack('Q', n_pcs_bytes)[0]
            return int(n_pcs) if n_pcs < self.buffer_size else 0

        except Exception as e:
            self.logger.error(f"Failed to get coverage count: {e}")
            return 0

    def cleanup(self):
        """Cleanup KCOV resources."""
        if self.enabled:
            self.disable()

        if self.coverage_buffer:
            self.coverage_buffer.close()
            self.coverage_buffer = None

        if self.kcov_fd:
            os.close(self.kcov_fd)
            self.kcov_fd = None

    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        self.enable()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()


class KCOVCoverageTracker:
    """
    Tracks unique coverage across multiple executions.

    Features:
    - Deduplicates PC values
    - Tracks new coverage
    - Calculates coverage growth
    """

    def __init__(self):
        """Initialize coverage tracker."""
        self.all_coverage: Set[int] = set()
        self.executions = 0
        self.logger = logging.getLogger("fawkes.kernel.kcov_tracker")

    def update(self, coverage: List[int]) -> int:
        """
        Update coverage with new execution.

        Args:
            coverage: List of PC values

        Returns:
            Number of new PCs discovered
        """
        self.executions += 1

        # Calculate new coverage
        coverage_set = set(coverage)
        new_coverage = coverage_set - self.all_coverage

        # Update total coverage
        self.all_coverage.update(coverage_set)

        if new_coverage:
            self.logger.info(f"New coverage: {len(new_coverage)} PCs (total: {len(self.all_coverage)})")

        return len(new_coverage)

    def get_total_coverage(self) -> int:
        """Get total unique PCs covered."""
        return len(self.all_coverage)

    def get_coverage_pcs(self) -> Set[int]:
        """Get set of all covered PCs."""
        return self.all_coverage.copy()

    def is_interesting(self, coverage: List[int]) -> bool:
        """
        Check if execution has new coverage.

        Args:
            coverage: Coverage to check

        Returns:
            True if has new coverage
        """
        coverage_set = set(coverage)
        new_coverage = coverage_set - self.all_coverage
        return len(new_coverage) > 0

    def reset(self):
        """Reset coverage tracking."""
        self.all_coverage.clear()
        self.executions = 0


# Convenience functions
def is_kcov_available() -> bool:
    """
    Check if KCOV is available.

    Returns:
        True if available

    Example:
        >>> if is_kcov_available():
        ...     manager = KCOVManager()
    """
    return os.path.exists("/dev/kcov")


# Testing
if __name__ == "__main__":
    print("=== KCOV Manager Test ===\n")

    # Check availability
    available = is_kcov_available()
    print(f"KCOV available: {available}")

    if not available:
        print("\nKCOV not available. To enable:")
        print("  1. Compile kernel with CONFIG_KCOV=y")
        print("  2. Boot with kernel parameter: kcov.enabled=1")
        print("  3. Check /dev/kcov exists")
        print("\nSkipping KCOV tests.")
        exit(0)

    # Test manager
    manager = KCOVManager()

    print("\nInitializing KCOV...")
    if manager.initialize():
        print("✓ KCOV initialized")

        print("\nEnabling coverage tracking...")
        if manager.enable():
            print("✓ Coverage tracking enabled")

            # Execute some syscalls to generate coverage
            print("\nExecuting syscalls to generate coverage...")
            import time
            os.getpid()
            os.getppid()
            time.time()

            # Read coverage
            coverage = manager.get_coverage()
            print(f"✓ Coverage collected: {len(coverage)} PCs")

            if coverage:
                print(f"  First 5 PCs: {[hex(pc) for pc in coverage[:5]]}")

            # Disable
            manager.disable()
            print("✓ Coverage tracking disabled")

        manager.cleanup()
        print("✓ KCOV cleaned up")

    else:
        print("❌ Failed to initialize KCOV")

    # Test tracker
    print("\n=== Testing Coverage Tracker ===")
    tracker = KCOVCoverageTracker()

    # Simulate coverage from multiple executions
    exec1 = [0x1000, 0x2000, 0x3000]
    exec2 = [0x2000, 0x3000, 0x4000]
    exec3 = [0x1000, 0x2000, 0x5000]

    new1 = tracker.update(exec1)
    print(f"Execution 1: {new1} new PCs (total: {tracker.get_total_coverage()})")

    new2 = tracker.update(exec2)
    print(f"Execution 2: {new2} new PCs (total: {tracker.get_total_coverage()})")

    new3 = tracker.update(exec3)
    print(f"Execution 3: {new3} new PCs (total: {tracker.get_total_coverage()})")

    assert tracker.get_total_coverage() == 5, "Should have 5 unique PCs"
    print("✓ Coverage tracking works correctly")

    # Test is_interesting
    assert tracker.is_interesting([0x6000]) == True, "New PC should be interesting"
    assert tracker.is_interesting([0x1000, 0x2000]) == False, "Old PCs not interesting"
    print("✓ Interesting testcase detection works")

    print("\n✅ All tests passed!")
