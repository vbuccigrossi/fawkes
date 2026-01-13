"""
Fawkes Kernel Fuzzing

Specialized support for Linux kernel fuzzing.

Features:
- Syscall fuzzing with type-aware generation
- KASAN (Kernel Address Sanitizer) integration
- Kernel driver fuzzing
- Coverage extraction from KCOV
- Crash analysis for kernel panics and oopses
"""

from .syscall_fuzzer import SyscallFuzzer, SyscallGenerator, ArgType
from .kasan_parser import KASANParser, KASANReport, KASANErrorType
from .kcov_manager import KCOVManager, KCOVCoverageTracker

__all__ = ['SyscallFuzzer', 'SyscallGenerator', 'ArgType', 'KASANParser', 'KASANReport', 'KASANErrorType', 'KCOVManager', 'KCOVCoverageTracker']
