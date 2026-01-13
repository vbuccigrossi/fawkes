"""
Fawkes Stack Hasher

Generates unique hashes from crash stack traces for accurate deduplication.
"""

import hashlib
import re
import logging
from typing import List, Dict, Optional


logger = logging.getLogger("fawkes.stack_hasher")


class StackHasher:
    """
    Generates hashes from crash stack traces for deduplication.

    Features:
    - Normalizes stack frames (removes addresses, line numbers)
    - Configurable stack depth
    - Handles inline functions
    - Ignores system libraries (optional)
    """

    def __init__(self,
                 depth: int = 10,
                 ignore_system_libs: bool = True,
                 normalize_templates: bool = True):
        """
        Initialize stack hasher.

        Args:
            depth: Number of stack frames to include in hash (default: 10)
            ignore_system_libs: Skip system library frames (default: True)
            normalize_templates: Normalize C++ template parameters (default: True)
        """
        self.depth = depth
        self.ignore_system_libs = ignore_system_libs
        self.normalize_templates = normalize_templates

        # System library paths to ignore
        self.system_lib_paths = [
            '/lib/', '/usr/lib/', '/lib64/', '/usr/lib64/',
            'libc.so', 'libpthread.so', 'libstdc++.so',
            'libm.so', 'ld-linux', 'linux-vdso.so'
        ]

    def hash_backtrace(self, backtrace: List[Dict]) -> str:
        """
        Generate hash from backtrace.

        Args:
            backtrace: List of stack frames, each a dict with:
                - function: Function name
                - file: Source file (optional)
                - line: Line number (optional)
                - address: Memory address (optional)

        Returns:
            SHA256 hash of normalized stack trace
        """
        if not backtrace:
            return hashlib.sha256(b"empty_stack").hexdigest()

        # Normalize and filter frames
        normalized_frames = []
        for frame in backtrace:
            # Skip system library frames if configured
            if self.ignore_system_libs and self._is_system_lib(frame):
                continue

            # Normalize frame
            normalized = self._normalize_frame(frame)
            if normalized:
                normalized_frames.append(normalized)

            # Stop at configured depth
            if len(normalized_frames) >= self.depth:
                break

        # Generate hash
        return self._hash_frames(normalized_frames)

    def _normalize_frame(self, frame: Dict) -> Optional[str]:
        """
        Normalize a single stack frame.

        Args:
            frame: Stack frame dict

        Returns:
            Normalized frame string or None if should be skipped
        """
        func = frame.get('function', '??')
        file = frame.get('file', '??')

        # Skip frames without function info
        if func == '??' and file == '??':
            return None

        # Normalize function name
        func = self._normalize_function(func)

        # Normalize file path (remove absolute paths, keep basename)
        if file and file != '??':
            file = self._normalize_filepath(file)

        # Don't include line numbers (they change with recompilation)
        # Format: function@file
        return f"{func}@{file}"

    def _normalize_function(self, func: str) -> str:
        """
        Normalize function name.

        - Remove memory addresses in parentheses
        - Normalize C++ template parameters (optional)
        - Remove (clone) suffixes
        """
        if not func or func == '??':
            return '??'

        # Remove addresses like "func (0x12345)"
        func = re.sub(r'\s*\(0x[0-9a-fA-F]+\)', '', func)

        # Remove .clone.N, .cold, .isra suffixes (GCC optimizations)
        func = re.sub(r'\.(clone|cold|isra|constprop|part)\.\d+', '', func)

        # Normalize C++ template parameters if enabled
        if self.normalize_templates:
            func = self._normalize_templates(func)

        return func

    def _normalize_templates(self, func: str) -> str:
        """
        Normalize C++ template parameters.

        Example: std::vector<int, std::allocator<int>> -> std::vector<T>
        """
        # Simple normalization: replace template content with <T>
        # This groups similar templates together
        func = re.sub(r'<[^<>]+>', '<T>', func)

        # Handle nested templates recursively
        while '<' in func and '>' in func:
            old_func = func
            func = re.sub(r'<[^<>]+>', '<T>', func)
            if func == old_func:
                break

        return func

    def _normalize_filepath(self, filepath: str) -> str:
        """
        Normalize file path.

        - Keep only basename (no directories)
        - Remove absolute paths
        """
        if not filepath or filepath == '??':
            return '??'

        # Extract basename
        import os
        basename = os.path.basename(filepath)

        return basename

    def _is_system_lib(self, frame: Dict) -> bool:
        """
        Check if frame is from a system library.

        Args:
            frame: Stack frame dict

        Returns:
            True if frame is from system library
        """
        if not self.ignore_system_libs:
            return False

        file = frame.get('file', '')
        func = frame.get('function', '')

        # Check file path
        if file:
            for lib_path in self.system_lib_paths:
                if lib_path in file:
                    return True

        # Check function name for system library functions
        if func:
            # Common system library function prefixes
            system_prefixes = ['__', '_dl_', '_IO_', 'std::', '__gnu_cxx::']
            for prefix in system_prefixes:
                if func.startswith(prefix):
                    return True

        return False

    def _hash_frames(self, frames: List[str]) -> str:
        """
        Hash list of normalized frames.

        Args:
            frames: List of normalized frame strings

        Returns:
            SHA256 hash
        """
        if not frames:
            return hashlib.sha256(b"empty_stack").hexdigest()

        # Join frames with separator
        stack_str = "||".join(frames)

        # Hash
        return hashlib.sha256(stack_str.encode('utf-8')).hexdigest()

    def get_crash_signature(self, backtrace: List[Dict], crash_type: str = None) -> str:
        """
        Generate crash signature combining stack hash and crash type.

        Args:
            backtrace: Stack backtrace
            crash_type: Type of crash (e.g., "SIGSEGV", "buffer_overflow")

        Returns:
            Crash signature string
        """
        stack_hash = self.hash_backtrace(backtrace)

        if crash_type:
            # Include crash type in signature
            combined = f"{crash_type}_{stack_hash}"
            return hashlib.sha256(combined.encode('utf-8')).hexdigest()

        return stack_hash


# Convenience function
def hash_stack_trace(backtrace: List[Dict],
                     depth: int = 10,
                     crash_type: str = None) -> str:
    """
    Quick function to hash a stack trace.

    Args:
        backtrace: List of stack frames
        depth: Number of frames to include
        crash_type: Optional crash type

    Returns:
        Stack hash

    Example:
        >>> backtrace = [
        ...     {'function': 'vulnerable_func', 'file': 'main.c', 'line': 42},
        ...     {'function': 'caller', 'file': 'main.c', 'line': 100}
        ... ]
        >>> hash_stack_trace(backtrace)
        'a1b2c3d4e5f6...'
    """
    hasher = StackHasher(depth=depth)

    if crash_type:
        return hasher.get_crash_signature(backtrace, crash_type)

    return hasher.hash_backtrace(backtrace)


# Example usage and testing
if __name__ == "__main__":
    # Example backtraces
    backtrace1 = [
        {'function': 'vulnerable_func', 'file': '/home/user/project/main.c', 'line': 42, 'address': '0x401234'},
        {'function': 'process_input', 'file': '/home/user/project/input.c', 'line': 156, 'address': '0x401567'},
        {'function': 'main', 'file': '/home/user/project/main.c', 'line': 200, 'address': '0x401890'},
    ]

    # Same crash, different line numbers (after recompilation)
    backtrace2 = [
        {'function': 'vulnerable_func', 'file': '/home/user/project/main.c', 'line': 45, 'address': '0x401240'},
        {'function': 'process_input', 'file': '/home/user/project/input.c', 'line': 160, 'address': '0x401570'},
        {'function': 'main', 'file': '/home/user/project/main.c', 'line': 205, 'address': '0x401895'},
    ]

    # Different crash
    backtrace3 = [
        {'function': 'different_func', 'file': '/home/user/project/other.c', 'line': 10, 'address': '0x402000'},
        {'function': 'main', 'file': '/home/user/project/main.c', 'line': 200, 'address': '0x401890'},
    ]

    hasher = StackHasher()

    hash1 = hasher.hash_backtrace(backtrace1)
    hash2 = hasher.hash_backtrace(backtrace2)
    hash3 = hasher.hash_backtrace(backtrace3)

    print("Stack Hash Demo")
    print("=" * 60)
    print(f"Hash 1: {hash1[:16]}...")
    print(f"Hash 2: {hash2[:16]}...")
    print(f"Hash 3: {hash3[:16]}...")
    print()
    print(f"Hash 1 == Hash 2: {hash1 == hash2} (same crash, different compilation)")
    print(f"Hash 1 == Hash 3: {hash1 == hash3} (different crash)")
