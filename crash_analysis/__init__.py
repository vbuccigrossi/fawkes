"""
Fawkes Crash Analysis Module

Provides advanced crash analysis capabilities including stack hashing,
deduplication, and crash bucketing.
"""

from .stack_hasher import StackHasher, hash_stack_trace
from .deduplicator import CrashDeduplicator

__all__ = ['StackHasher', 'hash_stack_trace', 'CrashDeduplicator']
