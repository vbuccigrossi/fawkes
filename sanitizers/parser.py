"""
Sanitizer Output Parser

Parses output from various sanitizers (ASAN, UBSAN, MSAN, TSAN) and extracts
structured crash information.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


logger = logging.getLogger("fawkes.sanitizers.parser")


class SanitizerType(Enum):
    """Types of sanitizers"""
    ASAN = "AddressSanitizer"
    UBSAN = "UndefinedBehaviorSanitizer"
    MSAN = "MemorySanitizer"
    TSAN = "ThreadSanitizer"
    UNKNOWN = "Unknown"


@dataclass
class SanitizerReport:
    """Structured sanitizer report"""
    sanitizer_type: SanitizerType
    error_type: str
    error_message: str
    crash_address: Optional[str] = None
    access_type: Optional[str] = None  # read/write
    access_size: Optional[int] = None
    backtrace: List[Dict] = field(default_factory=list)
    shadow_bytes: Optional[str] = None  # ASAN shadow memory
    thread_info: Optional[Dict] = None  # TSAN thread information
    raw_output: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            'sanitizer_type': self.sanitizer_type.value,
            'error_type': self.error_type,
            'error_message': self.error_message,
            'crash_address': self.crash_address,
            'access_type': self.access_type,
            'access_size': self.access_size,
            'backtrace': self.backtrace,
            'shadow_bytes': self.shadow_bytes,
            'thread_info': self.thread_info,
        }


class SanitizerParser:
    """
    Parser for sanitizer output

    Supports:
    - AddressSanitizer (ASAN)
    - UndefinedBehaviorSanitizer (UBSAN)
    - MemorySanitizer (MSAN)
    - ThreadSanitizer (TSAN)
    """

    def __init__(self):
        self.logger = logging.getLogger("fawkes.sanitizers.parser")

    def parse(self, output: str) -> Optional[SanitizerReport]:
        """
        Parse sanitizer output and extract structured information.

        Args:
            output: Raw sanitizer output (stderr/stdout)

        Returns:
            SanitizerReport or None if no sanitizer output detected
        """
        # Detect sanitizer type
        sanitizer_type = self._detect_sanitizer(output)

        if sanitizer_type == SanitizerType.UNKNOWN:
            return None

        # Parse based on sanitizer type
        if sanitizer_type == SanitizerType.ASAN:
            return self._parse_asan(output)
        elif sanitizer_type == SanitizerType.UBSAN:
            return self._parse_ubsan(output)
        elif sanitizer_type == SanitizerType.MSAN:
            return self._parse_msan(output)
        elif sanitizer_type == SanitizerType.TSAN:
            return self._parse_tsan(output)

        return None

    def _detect_sanitizer(self, output: str) -> SanitizerType:
        """Detect which sanitizer produced the output"""
        if "AddressSanitizer" in output or "ERROR: AddressSanitizer" in output:
            return SanitizerType.ASAN
        elif "UndefinedBehaviorSanitizer" in output or "runtime error:" in output:
            return SanitizerType.UBSAN
        elif "MemorySanitizer" in output or "ERROR: MemorySanitizer" in output:
            return SanitizerType.MSAN
        elif "ThreadSanitizer" in output or "WARNING: ThreadSanitizer" in output:
            return SanitizerType.TSAN

        return SanitizerType.UNKNOWN

    def _parse_asan(self, output: str) -> SanitizerReport:
        """
        Parse AddressSanitizer output.

        ASAN output format:
        =================================================================
        ==12345==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000000014 at pc 0x000000400b4e bp 0x7fffffffdc20 sp 0x7fffffffdc18
        READ of size 4 at 0x602000000014 thread T0
            #0 0x400b4d in main /home/user/test.c:10
            #1 0x7ffff7a3b82f in __libc_start_main (/lib/x86_64-linux-gnu/libc.so.6+0x2082f)
        ...
        """
        report = SanitizerReport(
            sanitizer_type=SanitizerType.ASAN,
            error_type="",
            error_message="",
            raw_output=output
        )

        # Extract error type
        # Pattern: ERROR: AddressSanitizer: <error-type> on address <addr>
        error_match = re.search(
            r'ERROR: AddressSanitizer: ([^\s]+)\s+on address (0x[0-9a-fA-F]+)',
            output
        )
        if error_match:
            report.error_type = error_match.group(1)
            report.crash_address = error_match.group(2)

        # Extract access type and size
        # Pattern: READ/WRITE of size N at 0xADDRESS
        access_match = re.search(
            r'(READ|WRITE) of size (\d+) at (0x[0-9a-fA-F]+)',
            output
        )
        if access_match:
            report.access_type = access_match.group(1).lower()
            report.access_size = int(access_match.group(2))

        # Extract error message (first line)
        lines = output.split('\n')
        for line in lines:
            if 'ERROR: AddressSanitizer:' in line:
                report.error_message = line.strip()
                break

        # Extract backtrace
        report.backtrace = self._extract_backtrace(output)

        # Extract shadow bytes (ASAN memory map)
        shadow_match = re.search(
            r'Shadow bytes around the buggy address:.*?(?:\n\n|\Z)',
            output,
            re.DOTALL
        )
        if shadow_match:
            report.shadow_bytes = shadow_match.group(0)

        self.logger.info(f"Parsed ASAN report: {report.error_type} at {report.crash_address}")
        return report

    def _parse_ubsan(self, output: str) -> SanitizerReport:
        """
        Parse UndefinedBehaviorSanitizer output.

        UBSAN output format:
        test.c:10:5: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'
        """
        report = SanitizerReport(
            sanitizer_type=SanitizerType.UBSAN,
            error_type="undefined_behavior",
            error_message="",
            raw_output=output
        )

        # Extract error message
        # Pattern: file.c:line:col: runtime error: <message>
        error_match = re.search(
            r'([^:]+):(\d+):(\d+): runtime error: (.+)',
            output
        )
        if error_match:
            file_path = error_match.group(1)
            line_num = int(error_match.group(2))
            col_num = int(error_match.group(3))
            error_msg = error_match.group(4)

            report.error_message = error_msg

            # Add source location to backtrace
            report.backtrace.append({
                'frame': 0,
                'function': '??',
                'file': file_path,
                'line': line_num,
                'column': col_num
            })

            # Classify error type
            if 'overflow' in error_msg:
                report.error_type = 'integer_overflow'
            elif 'division by zero' in error_msg:
                report.error_type = 'division_by_zero'
            elif 'null pointer' in error_msg:
                report.error_type = 'null_pointer_dereference'
            elif 'misaligned' in error_msg:
                report.error_type = 'misaligned_access'
            elif 'shift' in error_msg:
                report.error_type = 'invalid_shift'

        # Extract backtrace if present
        if '#0' in output:
            report.backtrace = self._extract_backtrace(output)

        self.logger.info(f"Parsed UBSAN report: {report.error_type}")
        return report

    def _parse_msan(self, output: str) -> SanitizerReport:
        """
        Parse MemorySanitizer output.

        MSAN output format:
        ==12345==WARNING: MemorySanitizer: use-of-uninitialized-value
            #0 0x400b4d in main /home/user/test.c:10
        """
        report = SanitizerReport(
            sanitizer_type=SanitizerType.MSAN,
            error_type="use_of_uninitialized_value",
            error_message="",
            raw_output=output
        )

        # Extract error type
        error_match = re.search(
            r'WARNING: MemorySanitizer: ([^\n]+)',
            output
        )
        if error_match:
            report.error_type = error_match.group(1).strip().replace('-', '_')
            report.error_message = f"MemorySanitizer: {error_match.group(1)}"

        # Extract backtrace
        report.backtrace = self._extract_backtrace(output)

        self.logger.info(f"Parsed MSAN report: {report.error_type}")
        return report

    def _parse_tsan(self, output: str) -> SanitizerReport:
        """
        Parse ThreadSanitizer output.

        TSAN output format:
        ==================
        WARNING: ThreadSanitizer: data race (pid=12345)
          Write of size 4 at 0x7b0400000000 by thread T1:
            #0 thread_func /home/user/test.c:15
          Previous write of size 4 at 0x7b0400000000 by main thread:
            #0 main /home/user/test.c:25
        """
        report = SanitizerReport(
            sanitizer_type=SanitizerType.TSAN,
            error_type="data_race",
            error_message="",
            raw_output=output
        )

        # Extract error type
        error_match = re.search(
            r'WARNING: ThreadSanitizer: ([^(]+)',
            output
        )
        if error_match:
            report.error_type = error_match.group(1).strip().replace('-', '_').replace(' ', '_')
            report.error_message = f"ThreadSanitizer: {error_match.group(1)}"

        # Extract access information
        access_match = re.search(
            r'(Read|Write) of size (\d+) at (0x[0-9a-fA-F]+)',
            output
        )
        if access_match:
            report.access_type = access_match.group(1).lower()
            report.access_size = int(access_match.group(2))
            report.crash_address = access_match.group(3)

        # Extract thread information
        thread_info = {}

        # Current thread
        current_thread_match = re.search(
            r'by thread T(\d+)',
            output
        )
        if current_thread_match:
            thread_info['current_thread'] = int(current_thread_match.group(1))

        # Previous thread
        prev_thread_match = re.search(
            r'by (main thread|thread T(\d+))',
            output
        )
        if prev_thread_match:
            if prev_thread_match.group(1) == 'main thread':
                thread_info['previous_thread'] = 0
            else:
                thread_info['previous_thread'] = int(prev_thread_match.group(2))

        report.thread_info = thread_info

        # Extract backtrace (first one - current thread)
        report.backtrace = self._extract_backtrace(output)

        self.logger.info(f"Parsed TSAN report: {report.error_type}")
        return report

    def _extract_backtrace(self, output: str) -> List[Dict]:
        """
        Extract backtrace from sanitizer output.

        Format: #N 0xADDRESS in function_name file.c:line:col
        """
        backtrace = []

        # Pattern for stack frames
        # #0 0x400b4d in main /home/user/test.c:10:5
        frame_pattern = re.compile(
            r'#(\d+)\s+'                          # Frame number
            r'(?:0x[0-9a-fA-F]+\s+)?'             # Optional address
            r'(?:in\s+)?'                         # Optional "in"
            r'([^\s/]+)'                          # Function name
            r'(?:\s+([^:]+)'                      # File path
            r':(\d+)'                             # Line number
            r'(?::(\d+))?)?'                      # Optional column number
        )

        for line in output.split('\n'):
            match = frame_pattern.match(line.strip())
            if match:
                frame_num = int(match.group(1))
                function = match.group(2)
                file_path = match.group(3) if match.group(3) else None
                line_num = int(match.group(4)) if match.group(4) else None
                col_num = int(match.group(5)) if match.group(5) else None

                frame = {
                    'frame': frame_num,
                    'function': function,
                    'file': file_path,
                    'line': line_num,
                }

                if col_num is not None:
                    frame['column'] = col_num

                backtrace.append(frame)

        return backtrace


# Convenience function
def parse_sanitizer_output(output: str) -> Optional[SanitizerReport]:
    """
    Quick function to parse sanitizer output.

    Args:
        output: Raw sanitizer output

    Returns:
        SanitizerReport or None

    Example:
        >>> output = "ERROR: AddressSanitizer: heap-buffer-overflow..."
        >>> report = parse_sanitizer_output(output)
        >>> print(report.error_type)
        heap-buffer-overflow
    """
    parser = SanitizerParser()
    return parser.parse(output)


# Testing
if __name__ == "__main__":
    # Test ASAN parsing
    asan_output = """
=================================================================
==12345==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000000014 at pc 0x000000400b4e bp 0x7fffffffdc20 sp 0x7fffffffdc18
READ of size 4 at 0x602000000014 thread T0
    #0 0x400b4d in main /home/user/test.c:10
    #1 0x7ffff7a3b82f in __libc_start_main (/lib/x86_64-linux-gnu/libc.so.6+0x2082f)

0x602000000014 is located 0 bytes to the right of 4-byte region [0x602000000010,0x602000000014)
"""

    parser = SanitizerParser()
    report = parser.parse(asan_output)

    if report:
        print("Sanitizer Report:")
        print(f"  Type: {report.sanitizer_type.value}")
        print(f"  Error: {report.error_type}")
        print(f"  Address: {report.crash_address}")
        print(f"  Access: {report.access_type} of size {report.access_size}")
        print(f"  Backtrace frames: {len(report.backtrace)}")
        for frame in report.backtrace:
            print(f"    #{frame['frame']}: {frame['function']} at {frame.get('file', '??')}:{frame.get('line', '??')}")
