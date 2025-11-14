"""
Fawkes Multi-Architecture Support

Provides comprehensive support for all QEMU architectures.
"""

from arch.architectures import (
    SupportedArchitectures,
    ArchitectureInfo,
    RegisterSet
)

__all__ = [
    "SupportedArchitectures",
    "ArchitectureInfo",
    "RegisterSet"
]
