"""
Syscall Fuzzer

Type-aware syscall fuzzing for Linux kernel testing.
"""

import random
import struct
import logging
from typing import List, Dict, Any, Optional
from enum import Enum


logger = logging.getLogger("fawkes.kernel.syscall_fuzzer")


class ArgType(Enum):
    """Syscall argument types."""
    INT = "int"
    LONG = "long"
    UINT = "uint"
    ULONG = "ulong"
    PTR = "ptr"
    BUFFER = "buffer"
    STRING = "string"
    FD = "fd"
    PID = "pid"
    FLAGS = "flags"
    SIZE = "size"
    OFFSET = "offset"


class SyscallGenerator:
    """
    Generates type-aware syscall arguments.

    Strategies:
    - Valid values (normal operation)
    - Boundary values (0, -1, MAX, MIN)
    - Invalid values (NULL, huge sizes, negative)
    - Interesting values (special flags, magic numbers)
    """

    # Interesting integer values
    INTERESTING_INTS = [
        0, 1, -1,
        127, 128, -128,
        255, 256, -256,
        32767, 32768, -32768,
        65535, 65536, -65536,
        0x7FFFFFFF, 0x80000000,
        0xFFFFFFFF,
    ]

    # Interesting sizes
    INTERESTING_SIZES = [
        0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024,
        4095, 4096, 4097,  # Page boundaries
        65535, 65536,
        0xFFFFFFFF,
    ]

    def __init__(self, use_interesting: bool = True):
        """
        Initialize syscall generator.

        Args:
            use_interesting: Use interesting values strategy
        """
        self.use_interesting = use_interesting
        self.logger = logging.getLogger("fawkes.kernel.syscall_generator")

        # Track allocated resources for cleanup
        self.allocated_fds: List[int] = []
        self.allocated_buffers: List[int] = []

    def generate_arg(self, arg_type: ArgType, context: Dict = None) -> Any:
        """
        Generate syscall argument of specified type.

        Args:
            arg_type: Argument type
            context: Additional context (e.g., buffer size)

        Returns:
            Generated argument value
        """
        if context is None:
            context = {}

        # Use interesting values sometimes
        if self.use_interesting and random.random() < 0.3:
            return self._generate_interesting(arg_type, context)
        else:
            return self._generate_normal(arg_type, context)

    def _generate_normal(self, arg_type: ArgType, context: Dict) -> Any:
        """Generate normal (valid) argument values."""
        if arg_type == ArgType.INT:
            return random.randint(-1000, 1000)

        elif arg_type == ArgType.LONG:
            return random.randint(-100000, 100000)

        elif arg_type == ArgType.UINT:
            return random.randint(0, 2000)

        elif arg_type == ArgType.ULONG:
            return random.randint(0, 200000)

        elif arg_type == ArgType.PTR:
            # Return valid user-space address
            return random.choice([
                0,  # NULL
                0x10000000 + random.randint(0, 0x10000000),  # Valid user address
            ])

        elif arg_type == ArgType.BUFFER:
            size = context.get('size', random.choice([16, 64, 256, 1024, 4096]))
            # Return address of allocated buffer
            return 0x20000000 + random.randint(0, 0x1000000)

        elif arg_type == ArgType.STRING:
            # Return address of string buffer
            return 0x30000000 + random.randint(0, 0x1000000)

        elif arg_type == ArgType.FD:
            # File descriptors: 0=stdin, 1=stdout, 2=stderr, or random
            return random.choice([0, 1, 2, random.randint(3, 100)])

        elif arg_type == ArgType.PID:
            # Process IDs
            return random.choice([0, 1, -1, random.randint(2, 30000)])

        elif arg_type == ArgType.FLAGS:
            # Random flags
            return random.randint(0, 0xFFFF)

        elif arg_type == ArgType.SIZE:
            return random.choice([0, 16, 64, 256, 1024, 4096, 8192])

        elif arg_type == ArgType.OFFSET:
            return random.randint(0, 0x100000)

        return 0

    def _generate_interesting(self, arg_type: ArgType, context: Dict) -> Any:
        """Generate interesting (boundary/invalid) argument values."""
        if arg_type in [ArgType.INT, ArgType.LONG]:
            return random.choice(self.INTERESTING_INTS)

        elif arg_type in [ArgType.UINT, ArgType.ULONG]:
            return random.choice([v for v in self.INTERESTING_INTS if v >= 0])

        elif arg_type == ArgType.PTR:
            # Interesting pointer values
            return random.choice([
                0,  # NULL
                0xFFFFFFFF,  # Invalid
                0x1000,  # Near NULL
                0xDEADBEEF,  # Uninitialized
                0x7FFFFFFF,  # Max user address
                0x80000000,  # Kernel boundary
            ])

        elif arg_type == ArgType.BUFFER:
            # Invalid buffer addresses
            return random.choice([0, 0xFFFFFFFF, 0x1000, 0xDEADBEEF])

        elif arg_type == ArgType.STRING:
            return random.choice([0, 0xFFFFFFFF, 0x1000])

        elif arg_type == ArgType.FD:
            # Invalid file descriptors
            return random.choice([-1, -100, 99999, 0xFFFFFFFF])

        elif arg_type == ArgType.PID:
            return random.choice([-1, -100, 0, 99999])

        elif arg_type == ArgType.FLAGS:
            # Invalid flag combinations
            return random.choice([0xFFFFFFFF, 0xDEADBEEF, 0x80000000])

        elif arg_type == ArgType.SIZE:
            return random.choice(self.INTERESTING_SIZES)

        elif arg_type == ArgType.OFFSET:
            return random.choice([0, -1, 0x7FFFFFFF, 0xFFFFFFFF])

        return 0


class SyscallFuzzer:
    """
    Fuzzes Linux kernel syscalls.

    Features:
    - Type-aware argument generation
    - Common syscall definitions
    - Resource tracking and cleanup
    - Error handling
    """

    # Common Linux syscalls and their signatures
    SYSCALLS = {
        # File operations
        'open': [ArgType.STRING, ArgType.FLAGS, ArgType.FLAGS],  # path, flags, mode
        'close': [ArgType.FD],
        'read': [ArgType.FD, ArgType.BUFFER, ArgType.SIZE],
        'write': [ArgType.FD, ArgType.BUFFER, ArgType.SIZE],
        'lseek': [ArgType.FD, ArgType.OFFSET, ArgType.INT],
        'ioctl': [ArgType.FD, ArgType.UINT, ArgType.PTR],

        # Process operations
        'fork': [],
        'execve': [ArgType.STRING, ArgType.PTR, ArgType.PTR],
        'exit': [ArgType.INT],
        'wait4': [ArgType.PID, ArgType.PTR, ArgType.INT, ArgType.PTR],
        'kill': [ArgType.PID, ArgType.INT],
        'getpid': [],
        'getppid': [],

        # Memory operations
        'mmap': [ArgType.PTR, ArgType.SIZE, ArgType.INT, ArgType.INT, ArgType.FD, ArgType.OFFSET],
        'munmap': [ArgType.PTR, ArgType.SIZE],
        'mprotect': [ArgType.PTR, ArgType.SIZE, ArgType.INT],
        'brk': [ArgType.PTR],

        # Network operations
        'socket': [ArgType.INT, ArgType.INT, ArgType.INT],
        'bind': [ArgType.FD, ArgType.PTR, ArgType.SIZE],
        'connect': [ArgType.FD, ArgType.PTR, ArgType.SIZE],
        'accept': [ArgType.FD, ArgType.PTR, ArgType.PTR],
        'sendto': [ArgType.FD, ArgType.BUFFER, ArgType.SIZE, ArgType.FLAGS, ArgType.PTR, ArgType.SIZE],
        'recvfrom': [ArgType.FD, ArgType.BUFFER, ArgType.SIZE, ArgType.FLAGS, ArgType.PTR, ArgType.PTR],

        # Filesystem operations
        'stat': [ArgType.STRING, ArgType.PTR],
        'fstat': [ArgType.FD, ArgType.PTR],
        'mkdir': [ArgType.STRING, ArgType.FLAGS],
        'rmdir': [ArgType.STRING],
        'unlink': [ArgType.STRING],
        'rename': [ArgType.STRING, ArgType.STRING],
        'chmod': [ArgType.STRING, ArgType.FLAGS],

        # Time operations
        'nanosleep': [ArgType.PTR, ArgType.PTR],
        'gettimeofday': [ArgType.PTR, ArgType.PTR],
        'settimeofday': [ArgType.PTR, ArgType.PTR],
    }

    def __init__(self, syscalls: List[str] = None):
        """
        Initialize syscall fuzzer.

        Args:
            syscalls: List of syscall names to fuzz (default: all)
        """
        self.generator = SyscallGenerator()
        self.logger = logging.getLogger("fawkes.kernel.syscall_fuzzer")

        if syscalls is None:
            self.syscalls = list(self.SYSCALLS.keys())
        else:
            # Filter to valid syscalls
            self.syscalls = [s for s in syscalls if s in self.SYSCALLS]

        if not self.syscalls:
            raise ValueError("No valid syscalls specified")

        self.iterations = 0
        self.errors = 0

    def generate_syscall(self, syscall_name: str = None) -> Dict:
        """
        Generate random syscall with arguments.

        Args:
            syscall_name: Specific syscall to generate (default: random)

        Returns:
            Dict with syscall name and arguments
        """
        if syscall_name is None:
            syscall_name = random.choice(self.syscalls)

        if syscall_name not in self.SYSCALLS:
            raise ValueError(f"Unknown syscall: {syscall_name}")

        arg_types = self.SYSCALLS[syscall_name]
        args = []

        for arg_type in arg_types:
            arg = self.generator.generate_arg(arg_type)
            args.append(arg)

        return {
            'name': syscall_name,
            'args': args
        }

    def generate_batch(self, count: int = 100, syscall_name: str = None) -> List[Dict]:
        """
        Generate batch of syscalls.

        Args:
            count: Number of syscalls to generate
            syscall_name: Specific syscall (default: random)

        Returns:
            List of syscall dicts
        """
        return [self.generate_syscall(syscall_name) for _ in range(count)]

    def format_syscall_c(self, syscall: Dict) -> str:
        """
        Format syscall as C code.

        Args:
            syscall: Syscall dict

        Returns:
            C code string
        """
        name = syscall['name']
        args = syscall['args']

        # Format arguments
        arg_strs = []
        for arg in args:
            if isinstance(arg, int):
                if arg < 0:
                    arg_strs.append(f"{arg}")
                else:
                    arg_strs.append(f"0x{arg:x}")
            else:
                arg_strs.append(str(arg))

        return f"{name}({', '.join(arg_strs)});"

    def format_syscall_python(self, syscall: Dict) -> str:
        """
        Format syscall as Python ctypes code.

        Args:
            syscall: Syscall dict

        Returns:
            Python code string
        """
        name = syscall['name']
        args = syscall['args']

        arg_strs = [str(arg) for arg in args]
        return f"libc.{name}({', '.join(arg_strs)})"

    def get_syscall_signature(self, syscall_name: str) -> Optional[List[ArgType]]:
        """
        Get syscall argument signature.

        Args:
            syscall_name: Syscall name

        Returns:
            List of argument types or None
        """
        return self.SYSCALLS.get(syscall_name)

    def add_custom_syscall(self, name: str, arg_types: List[ArgType]):
        """
        Add custom syscall definition.

        Args:
            name: Syscall name
            arg_types: List of argument types
        """
        self.SYSCALLS[name] = arg_types
        if name not in self.syscalls:
            self.syscalls.append(name)

    def list_syscalls(self) -> List[str]:
        """List all available syscalls."""
        return sorted(self.syscalls)

    def get_syscall_count(self) -> int:
        """Get number of available syscalls."""
        return len(self.syscalls)


# Convenience functions
def generate_syscall(syscall_name: str = None) -> Dict:
    """
    Quick function to generate syscall.

    Args:
        syscall_name: Syscall name (default: random)

    Returns:
        Syscall dict

    Example:
        >>> syscall = generate_syscall("open")
        >>> print(syscall)
        {'name': 'open', 'args': [0x20000000, 0, 0]}
    """
    fuzzer = SyscallFuzzer()
    return fuzzer.generate_syscall(syscall_name)


# Testing
if __name__ == "__main__":
    print("=== Syscall Fuzzer Test ===\n")

    fuzzer = SyscallFuzzer()

    print(f"Available syscalls: {fuzzer.get_syscall_count()}")
    print(f"Syscalls: {', '.join(fuzzer.list_syscalls()[:10])}...\n")

    # Generate random syscalls
    print("Random syscalls:")
    for i in range(10):
        syscall = fuzzer.generate_syscall()
        c_code = fuzzer.format_syscall_c(syscall)
        print(f"  {i+1}. {c_code}")

    # Generate specific syscall
    print("\nopen() syscalls:")
    for i in range(5):
        syscall = fuzzer.generate_syscall("open")
        c_code = fuzzer.format_syscall_c(syscall)
        print(f"  {i+1}. {c_code}")

    # Generate mmap syscalls
    print("\nmmap() syscalls:")
    for i in range(5):
        syscall = fuzzer.generate_syscall("mmap")
        c_code = fuzzer.format_syscall_c(syscall)
        print(f"  {i+1}. {c_code}")

    # Test custom syscall
    print("\nCustom syscall:")
    fuzzer.add_custom_syscall("my_ioctl", [ArgType.FD, ArgType.UINT, ArgType.PTR])
    syscall = fuzzer.generate_syscall("my_ioctl")
    print(f"  {fuzzer.format_syscall_c(syscall)}")
