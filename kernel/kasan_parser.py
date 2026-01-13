"""
KASAN Parser

Parses Kernel Address Sanitizer (KASAN) reports from kernel logs.
"""

import re
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum


logger = logging.getLogger("fawkes.kernel.kasan")


class KASANErrorType(Enum):
    """KASAN error types."""
    USE_AFTER_FREE = "use-after-free"
    OUT_OF_BOUNDS = "out-of-bounds"
    SLAB_OUT_OF_BOUNDS = "slab-out-of-bounds"
    GLOBAL_OUT_OF_BOUNDS = "global-out-of-bounds"
    STACK_OUT_OF_BOUNDS = "stack-out-of-bounds"
    USE_AFTER_SCOPE = "use-after-scope"
    DOUBLE_FREE = "double-free"
    INVALID_FREE = "invalid-free"
    WILD_MEMORY_ACCESS = "wild-memory-access"
    UNKNOWN = "unknown"


@dataclass
class KASANReport:
    """
    Represents a KASAN error report.

    Attributes:
        error_type: Type of error
        access_type: READ or WRITE
        address: Memory address accessed
        size: Access size in bytes
        ip: Instruction pointer
        function: Function where error occurred
        backtrace: Call stack
        allocation_backtrace: Allocation stack (for UAF)
        free_backtrace: Free stack (for UAF/double-free)
        memory_state: Memory state description
        raw_report: Full raw report text
    """
    error_type: KASANErrorType = KASANErrorType.UNKNOWN
    access_type: str = ""  # READ or WRITE
    address: int = 0
    size: int = 0
    ip: int = 0
    function: str = ""
    backtrace: List[Dict] = field(default_factory=list)
    allocation_backtrace: List[Dict] = field(default_factory=list)
    free_backtrace: List[Dict] = field(default_factory=list)
    memory_state: str = ""
    raw_report: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'error_type': self.error_type.value,
            'access_type': self.access_type,
            'address': hex(self.address) if self.address else None,
            'size': self.size,
            'ip': hex(self.ip) if self.ip else None,
            'function': self.function,
            'backtrace': self.backtrace,
            'allocation_backtrace': self.allocation_backtrace,
            'free_backtrace': self.free_backtrace,
            'memory_state': self.memory_state
        }

    def __str__(self) -> str:
        """String representation."""
        return f"KASAN {self.error_type.value}: {self.access_type} of size {self.size} at {hex(self.address)} in {self.function}"


class KASANParser:
    """
    Parses KASAN reports from kernel output.

    Example KASAN report:
        ==================================================================
        BUG: KASAN: use-after-free in kfree+0x123/0x456
        Write of size 8 at addr ffff8881234567890 by task fuzzer/1234

        CPU: 0 PID: 1234 Comm: fuzzer Not tainted 5.10.0 #1
        Call Trace:
         dump_stack+0x64/0x8c
         print_address_description+0x73/0x280
         kasan_report+0x123/0x456
         kfree+0x123/0x456
         my_function+0x78/0x90

        Allocated by task 1234:
         kasan_save_stack+0x19/0x40
         __kasan_kmalloc+0x7f/0xa0
         kmalloc+0x123/0x456

        Freed by task 1234:
         kasan_save_stack+0x19/0x40
         kasan_set_free_info+0x1b/0x30
         __kasan_slab_free+0x111/0x160
         kfree+0x123/0x456
        ==================================================================
    """

    # Regex patterns
    KASAN_HEADER = re.compile(r'BUG: KASAN: ([\w-]+)')
    ACCESS_INFO = re.compile(r'(Read|Write|Invalid access) of size (\d+) at addr ([0-9a-fA-F]+)')
    FUNCTION_INFO = re.compile(r'in ([^\s+]+)\+0x([0-9a-fA-F]+)/0x([0-9a-fA-F]+)')
    TASK_INFO = re.compile(r'by task ([\w-]+)/(\d+)')
    CPU_INFO = re.compile(r'CPU: (\d+) PID: (\d+)')
    BACKTRACE_FRAME = re.compile(r'\s+([^\s+]+)\+0x([0-9a-fA-F]+)/0x([0-9a-fA-F]+)')

    def __init__(self):
        """Initialize KASAN parser."""
        self.logger = logging.getLogger("fawkes.kernel.kasan_parser")

    def parse(self, output: str) -> Optional[KASANReport]:
        """
        Parse KASAN report from kernel output.

        Args:
            output: Kernel log output

        Returns:
            KASANReport or None if no KASAN report found
        """
        if "BUG: KASAN:" not in output:
            return None

        report = KASANReport()
        report.raw_report = output

        # Extract error type
        header_match = self.KASAN_HEADER.search(output)
        if header_match:
            error_type_str = header_match.group(1)
            report.error_type = self._parse_error_type(error_type_str)

        # Extract access info
        access_match = self.ACCESS_INFO.search(output)
        if access_match:
            report.access_type = access_match.group(1).upper()
            report.size = int(access_match.group(2))
            report.address = int(access_match.group(3), 16)

        # Extract function info
        func_match = self.FUNCTION_INFO.search(output)
        if func_match:
            report.function = func_match.group(1)
            report.ip = int(func_match.group(2), 16)

        # Extract backtraces
        report.backtrace = self._extract_backtrace(output, "Call Trace:")
        report.allocation_backtrace = self._extract_backtrace(output, "Allocated by task")
        report.free_backtrace = self._extract_backtrace(output, "Freed by task")

        # Extract memory state
        report.memory_state = self._extract_memory_state(output)

        self.logger.info(f"Parsed KASAN report: {report}")
        return report

    def _parse_error_type(self, error_str: str) -> KASANErrorType:
        """Parse error type string to enum."""
        error_map = {
            'use-after-free': KASANErrorType.USE_AFTER_FREE,
            'out-of-bounds': KASANErrorType.OUT_OF_BOUNDS,
            'slab-out-of-bounds': KASANErrorType.SLAB_OUT_OF_BOUNDS,
            'global-out-of-bounds': KASANErrorType.GLOBAL_OUT_OF_BOUNDS,
            'stack-out-of-bounds': KASANErrorType.STACK_OUT_OF_BOUNDS,
            'use-after-scope': KASANErrorType.USE_AFTER_SCOPE,
            'double-free': KASANErrorType.DOUBLE_FREE,
            'invalid-free': KASANErrorType.INVALID_FREE,
            'wild-memory-access': KASANErrorType.WILD_MEMORY_ACCESS,
        }
        return error_map.get(error_str, KASANErrorType.UNKNOWN)

    def _extract_backtrace(self, output: str, section_header: str) -> List[Dict]:
        """
        Extract backtrace from section.

        Args:
            output: Full output
            section_header: Section header to look for

        Returns:
            List of stack frames
        """
        backtrace = []

        # Find section
        if section_header not in output:
            return backtrace

        # Get section text
        start_idx = output.find(section_header)
        # Section ends at next empty line or next section
        section_end = output.find("\n\n", start_idx)
        if section_end == -1:
            section_end = len(output)

        section = output[start_idx:section_end]

        # Extract frames
        for match in self.BACKTRACE_FRAME.finditer(section):
            function = match.group(1)
            offset = int(match.group(2), 16)
            size = int(match.group(3), 16)

            backtrace.append({
                'function': function,
                'offset': offset,
                'size': size
            })

        return backtrace

    def _extract_memory_state(self, output: str) -> str:
        """
        Extract memory state description.

        Args:
            output: Full output

        Returns:
            Memory state string
        """
        # Look for lines starting with "The buggy address"
        for line in output.split('\n'):
            if 'buggy address' in line.lower():
                return line.strip()

        # Look for memory dump info
        if 'Memory state around the buggy address:' in output:
            return 'Memory state available in raw report'

        return ''

    def detect_in_output(self, output: str) -> bool:
        """
        Check if output contains KASAN report.

        Args:
            output: Output to check

        Returns:
            True if KASAN report detected
        """
        return "BUG: KASAN:" in output

    def classify_severity(self, report: KASANReport) -> str:
        """
        Classify severity of KASAN report.

        Args:
            report: KASAN report

        Returns:
            Severity: HIGH, MEDIUM, LOW
        """
        # High severity errors
        high_severity = [
            KASANErrorType.USE_AFTER_FREE,
            KASANErrorType.DOUBLE_FREE,
            KASANErrorType.WILD_MEMORY_ACCESS,
        ]

        # Medium severity errors
        medium_severity = [
            KASANErrorType.OUT_OF_BOUNDS,
            KASANErrorType.SLAB_OUT_OF_BOUNDS,
            KASANErrorType.INVALID_FREE,
        ]

        if report.error_type in high_severity:
            return "HIGH"
        elif report.error_type in medium_severity:
            return "MEDIUM"
        else:
            return "LOW"

    def get_exploitability(self, report: KASANReport) -> str:
        """
        Estimate exploitability.

        Args:
            report: KASAN report

        Returns:
            Exploitability: HIGH, MEDIUM, LOW, UNKNOWN
        """
        # Use-after-free is highly exploitable
        if report.error_type == KASANErrorType.USE_AFTER_FREE:
            if report.access_type == "WRITE":
                return "HIGH"
            else:
                return "MEDIUM"

        # Out-of-bounds writes are exploitable
        if "OUT_OF_BOUNDS" in report.error_type.value.upper():
            if report.access_type == "WRITE":
                return "MEDIUM"
            else:
                return "LOW"

        # Double-free can lead to corruption
        if report.error_type == KASANErrorType.DOUBLE_FREE:
            return "HIGH"

        return "UNKNOWN"


# Convenience function
def parse_kasan_report(output: str) -> Optional[KASANReport]:
    """
    Quick function to parse KASAN report.

    Args:
        output: Kernel output

    Returns:
        KASANReport or None

    Example:
        >>> report = parse_kasan_report(kernel_output)
        >>> if report:
        ...     print(f"Error: {report.error_type}")
    """
    parser = KASANParser()
    return parser.parse(output)


# Testing
if __name__ == "__main__":
    # Example KASAN report
    sample_report = """
==================================================================
BUG: KASAN: use-after-free in kfree+0x2b/0x80
Write of size 8 at addr ffff8881f2345678 by task fuzzer/1234

CPU: 0 PID: 1234 Comm: fuzzer Not tainted 5.10.0 #1
Hardware name: QEMU Standard PC (i440FX + PIIX, 1996)
Call Trace:
 dump_stack+0x64/0x8c
 print_address_description.constprop.0+0x1d/0x220
 ? kfree+0x2b/0x80
 kasan_report.cold+0x37/0x7f
 ? kfree+0x2b/0x80
 kfree+0x2b/0x80
 test_function+0x123/0x456
 driver_ioctl+0x789/0xabc

Allocated by task 1234:
 kasan_save_stack+0x19/0x40
 __kasan_kmalloc.constprop.0+0xc6/0xd0
 kmem_cache_alloc_trace+0x151/0x2c0
 test_function+0x45/0x456

Freed by task 1234:
 kasan_save_stack+0x19/0x40
 kasan_set_free_info+0x1b/0x30
 __kasan_slab_free+0x111/0x160
 kfree+0x2b/0x80
 test_function+0x100/0x456

The buggy address belongs to the object at ffff8881f2345000
 which belongs to the cache kmalloc-512 of size 512
==================================================================
"""

    print("=== KASAN Parser Test ===\n")

    parser = KASANParser()

    # Test detection
    assert parser.detect_in_output(sample_report), "Should detect KASAN report"
    print("✓ KASAN report detected")

    # Test parsing
    report = parser.parse(sample_report)
    assert report is not None, "Should parse report"
    print(f"✓ Parsed report: {report}")

    # Test fields
    assert report.error_type == KASANErrorType.USE_AFTER_FREE, "Should be use-after-free"
    assert report.access_type == "WRITE", "Should be WRITE"
    assert report.size == 8, "Size should be 8"
    assert report.address == 0xffff8881f2345678, "Address should match"
    assert report.function == "kfree", "Function should be kfree"
    print("✓ All fields parsed correctly")

    # Test backtraces
    assert len(report.backtrace) > 0, "Should have backtrace"
    assert len(report.allocation_backtrace) > 0, "Should have allocation backtrace"
    assert len(report.free_backtrace) > 0, "Should have free backtrace"
    print(f"✓ Backtraces: {len(report.backtrace)} call, {len(report.allocation_backtrace)} alloc, {len(report.free_backtrace)} free")

    # Test severity
    severity = parser.classify_severity(report)
    assert severity == "HIGH", "Use-after-free should be HIGH severity"
    print(f"✓ Severity: {severity}")

    # Test exploitability
    exploitability = parser.get_exploitability(report)
    assert exploitability == "HIGH", "UAF write should be highly exploitable"
    print(f"✓ Exploitability: {exploitability}")

    # Test to_dict
    report_dict = report.to_dict()
    assert 'error_type' in report_dict, "Should have error_type"
    assert report_dict['error_type'] == 'use-after-free', "Error type should be use-after-free"
    print(f"✓ Dict conversion successful")

    print("\n✅ All KASAN parser tests passed!")
