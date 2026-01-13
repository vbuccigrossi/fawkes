"""
Fawkes Sanitizer Integration Module

Provides support for various sanitizers to detect memory errors, undefined behavior,
data races, and memory leaks.

Supported Sanitizers:
- AddressSanitizer (ASAN) - Memory errors (buffer overflows, use-after-free, etc.)
- UndefinedBehaviorSanitizer (UBSAN) - Undefined behavior detection
- MemorySanitizer (MSAN) - Uninitialized memory reads
- ThreadSanitizer (TSAN) - Data race detection
"""

from .parser import SanitizerParser, SanitizerReport, SanitizerType
from .detector import SanitizerDetector

__all__ = ['SanitizerParser', 'SanitizerReport', 'SanitizerType', 'SanitizerDetector']
