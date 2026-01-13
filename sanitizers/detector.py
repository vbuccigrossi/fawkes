"""
Sanitizer Detection Module

Detects sanitizer output in program output (stdout/stderr) and log files.
"""

import os
import re
import logging
from typing import Optional, List, Tuple
from .parser import SanitizerParser, SanitizerReport, SanitizerType


logger = logging.getLogger("fawkes.sanitizers.detector")


class SanitizerDetector:
    """
    Detects sanitizer errors in program output and log files.

    Features:
    - Monitor stdout/stderr for sanitizer output
    - Parse log files for sanitizer reports
    - Filter false positives
    """

    # Patterns that indicate sanitizer output
    SANITIZER_PATTERNS = [
        r'ERROR: AddressSanitizer',
        r'WARNING: ThreadSanitizer',
        r'ERROR: MemorySanitizer',
        r'runtime error:',  # UBSAN
        r'ERROR: LeakSanitizer',
    ]

    def __init__(self):
        self.logger = logging.getLogger("fawkes.sanitizers.detector")
        self.parser = SanitizerParser()

    def detect_in_output(self, output: str) -> Optional[SanitizerReport]:
        """
        Detect sanitizer error in program output.

        Args:
            output: Program stdout/stderr output

        Returns:
            SanitizerReport if detected, None otherwise
        """
        if not self._has_sanitizer_output(output):
            return None

        return self.parser.parse(output)

    def detect_in_file(self, file_path: str) -> Optional[SanitizerReport]:
        """
        Detect sanitizer error in log file.

        Args:
            file_path: Path to log file

        Returns:
            SanitizerReport if detected, None otherwise
        """
        if not os.path.exists(file_path):
            self.logger.warning(f"File not found: {file_path}")
            return None

        try:
            with open(file_path, 'r', errors='ignore') as f:
                content = f.read()

            return self.detect_in_output(content)

        except Exception as e:
            self.logger.error(f"Failed to read file {file_path}: {e}")
            return None

    def detect_multiple(self, output: str) -> List[SanitizerReport]:
        """
        Detect multiple sanitizer errors in output.

        Some sanitizers may report multiple errors before exiting.

        Args:
            output: Program output

        Returns:
            List of SanitizerReports
        """
        reports = []

        # Split output into segments (each starting with ERROR/WARNING)
        segments = self._split_sanitizer_output(output)

        for segment in segments:
            report = self.parser.parse(segment)
            if report:
                reports.append(report)

        return reports

    def _has_sanitizer_output(self, output: str) -> bool:
        """Check if output contains sanitizer patterns"""
        for pattern in self.SANITIZER_PATTERNS:
            if re.search(pattern, output):
                return True
        return False

    def _split_sanitizer_output(self, output: str) -> List[str]:
        """
        Split output into individual sanitizer reports.

        Sanitizer reports typically start with:
        - ==PID==ERROR: ...
        - ==PID==WARNING: ...
        """
        segments = []
        current_segment = []

        for line in output.split('\n'):
            # Check if this is the start of a new sanitizer report
            if re.match(r'==\d+==(?:ERROR|WARNING):', line):
                # Save previous segment
                if current_segment:
                    segments.append('\n'.join(current_segment))
                    current_segment = []

            current_segment.append(line)

        # Add last segment
        if current_segment:
            segments.append('\n'.join(current_segment))

        return segments

    def classify_severity(self, report: SanitizerReport) -> str:
        """
        Classify sanitizer error severity.

        Returns:
            "critical", "high", "medium", or "low"
        """
        if report.sanitizer_type == SanitizerType.ASAN:
            # ASAN errors are generally critical
            critical_errors = [
                'heap-buffer-overflow',
                'stack-buffer-overflow',
                'global-buffer-overflow',
                'use-after-free',
                'double-free',
            ]

            if report.error_type in critical_errors:
                return "critical"

            return "high"

        elif report.sanitizer_type == SanitizerType.UBSAN:
            # UBSAN severity varies
            critical_errors = [
                'null_pointer_dereference',
                'division_by_zero',
            ]

            if report.error_type in critical_errors:
                return "high"

            return "medium"

        elif report.sanitizer_type == SanitizerType.MSAN:
            # Uninitialized memory use can be exploitable
            return "high"

        elif report.sanitizer_type == SanitizerType.TSAN:
            # Data races are important but less immediately exploitable
            return "medium"

        return "low"

    def get_exploitability(self, report: SanitizerReport) -> str:
        """
        Estimate exploitability of sanitizer error.

        Returns:
            "HIGH", "MEDIUM", "LOW", or "UNKNOWN"
        """
        if report.sanitizer_type == SanitizerType.ASAN:
            # Check error type
            high_exploitability = [
                'heap-buffer-overflow',
                'use-after-free',
                'double-free',
            ]

            medium_exploitability = [
                'stack-buffer-overflow',
                'global-buffer-overflow',
            ]

            if report.error_type in high_exploitability:
                return "HIGH"
            elif report.error_type in medium_exploitability:
                return "MEDIUM"
            else:
                return "LOW"

        elif report.sanitizer_type == SanitizerType.UBSAN:
            # Integer overflows can be exploitable
            if 'overflow' in report.error_type:
                return "MEDIUM"
            elif 'null_pointer' in report.error_type:
                return "LOW"
            else:
                return "LOW"

        elif report.sanitizer_type == SanitizerType.MSAN:
            # Uninitialized memory use can leak secrets or cause exploitable behavior
            return "MEDIUM"

        elif report.sanitizer_type == SanitizerType.TSAN:
            # Data races typically not directly exploitable
            return "LOW"

        return "UNKNOWN"


# Convenience functions
def detect_sanitizer_error(output: str) -> Optional[SanitizerReport]:
    """
    Quick function to detect sanitizer error.

    Args:
        output: Program output

    Returns:
        SanitizerReport or None

    Example:
        >>> output = get_program_output()
        >>> report = detect_sanitizer_error(output)
        >>> if report:
        ...     print(f"Found {report.sanitizer_type.value} error!")
    """
    detector = SanitizerDetector()
    return detector.detect_in_output(output)


def is_sanitizer_crash(output: str) -> bool:
    """
    Quick check if output contains sanitizer crash.

    Args:
        output: Program output

    Returns:
        True if sanitizer crash detected

    Example:
        >>> if is_sanitizer_crash(stderr):
        ...     handle_crash()
    """
    detector = SanitizerDetector()
    return detector._has_sanitizer_output(output)


# Testing
if __name__ == "__main__":
    # Test detection
    test_output = """
Some normal output...
=================================================================
==25123==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x60200000001c at pc 0x0000004008f3 bp 0x7ffe6d1e0a10 sp 0x7ffe6d1e0a08
READ of size 4 at 0x60200000001c thread T0
    #0 0x4008f2 in main /home/user/vulnerable.c:15:10
    #1 0x7f8e5c5a082f in __libc_start_main /build/glibc-S9d2JN/glibc-2.27/csu/../csu/libc-start.c:310
    #2 0x400788 in _start (/home/user/vulnerable+0x400788)

0x60200000001c is located 0 bytes to the right of 12-byte region [0x602000000010,0x60200000001c)
allocated by thread T0 here:
    #0 0x7f8e5ca29b50 in __interceptor_malloc (/usr/lib/x86_64-linux-gnu/libasan.so.4+0xdeb50)
    #1 0x4008c3 in main /home/user/vulnerable.c:13:18
"""

    detector = SanitizerDetector()
    report = detector.detect_in_output(test_output)

    if report:
        print("=" * 60)
        print("SANITIZER ERROR DETECTED")
        print("=" * 60)
        print(f"Sanitizer: {report.sanitizer_type.value}")
        print(f"Error Type: {report.error_type}")
        print(f"Message: {report.error_message}")
        print(f"Address: {report.crash_address}")
        print(f"Access: {report.access_type} of size {report.access_size}")
        print(f"\nSeverity: {detector.classify_severity(report)}")
        print(f"Exploitability: {detector.get_exploitability(report)}")
        print(f"\nBacktrace ({len(report.backtrace)} frames):")
        for frame in report.backtrace:
            print(f"  #{frame['frame']}: {frame['function']} "
                  f"at {frame.get('file', '??')}:{frame.get('line', '??')}")
