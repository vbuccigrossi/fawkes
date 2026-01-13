"""
Fawkes GDB Backtrace Extractor

Extracts detailed backtraces from GDB for crash analysis.
"""

import re
import subprocess
import tempfile
import logging
from typing import List, Dict, Optional


logger = logging.getLogger("fawkes.gdb_backtrace")


class GDBBacktraceExtractor:
    """
    Extract detailed backtraces from GDB.

    Features:
    - Extract full call stack
    - Parse function names, files, line numbers
    - Handle architecture-specific formats
    - Support for both kernel and user-space crashes
    """

    def __init__(self, arch: str = "auto"):
        """
        Initialize backtrace extractor.

        Args:
            arch: Target architecture (x86_64, i386, arm, etc.)
        """
        self.arch = arch

    def extract_backtrace_from_core(self,
                                     executable: str,
                                     core_file: str,
                                     max_frames: int = 50) -> List[Dict]:
        """
        Extract backtrace from core dump.

        Args:
            executable: Path to executable
            core_file: Path to core file
            max_frames: Maximum number of frames to extract

        Returns:
            List of stack frames
        """
        # Create GDB script
        gdb_script = (
            f"set architecture {self.arch}\n"
            "set pagination off\n"
            f"file {executable}\n"
            f"core {core_file}\n"
            "bt\n"
            "quit\n"
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.gdb', delete=False) as f:
            f.write(gdb_script)
            script_path = f.name

        try:
            # Run GDB
            result = subprocess.run(
                ['gdb', '-q', '-batch', '-x', script_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            # Parse backtrace
            return self._parse_gdb_backtrace(result.stdout)

        except subprocess.TimeoutExpired:
            logger.error("GDB backtrace extraction timed out")
            return []
        except Exception as e:
            logger.error(f"Failed to extract backtrace: {e}")
            return []
        finally:
            import os
            try:
                os.unlink(script_path)
            except:
                pass

    def extract_backtrace_live(self,
                               host: str,
                               port: int,
                               max_frames: int = 50) -> List[Dict]:
        """
        Extract backtrace from live GDB session.

        Args:
            host: GDB server host
            port: GDB server port
            max_frames: Maximum frames to extract

        Returns:
            List of stack frames
        """
        # Create GDB script
        gdb_script = (
            f"target remote {host}:{port}\n"
            f"set architecture {self.arch}\n"
            "set pagination off\n"
            "bt\n"
            "info registers\n"
            "quit\n"
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.gdb', delete=False) as f:
            f.write(gdb_script)
            script_path = f.name

        try:
            # Run GDB
            result = subprocess.run(
                ['gdb', '-q', '-batch', '-x', script_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            # Parse backtrace
            backtrace = self._parse_gdb_backtrace(result.stdout)

            # Also extract register info
            registers = self._parse_registers(result.stdout)

            return backtrace, registers

        except subprocess.TimeoutExpired:
            logger.error("GDB backtrace extraction timed out")
            return [], {}
        except Exception as e:
            logger.error(f"Failed to extract backtrace: {e}")
            return [], {}
        finally:
            import os
            try:
                os.unlink(script_path)
            except:
                pass

    def _parse_gdb_backtrace(self, gdb_output: str) -> List[Dict]:
        """
        Parse GDB backtrace output.

        Args:
            gdb_output: Raw GDB output

        Returns:
            List of stack frames
        """
        frames = []

        # GDB backtrace format:
        # #0  0x00007ffff7a52495 in __GI_raise (sig=sig@entry=6) at ../sysdeps/unix/sysv/linux/raise.c:50
        # #1  0x00007ffff7a3b89b in __GI_abort () at abort.c:79
        # #2  0x0000555555555189 in vulnerable_func () at test.c:10

        # Pattern for stack frames
        frame_pattern = re.compile(
            r'#(\d+)\s+'                       # Frame number
            r'(?:0x[0-9a-fA-F]+\s+in\s+)?'     # Optional address
            r'([^\s(]+)'                        # Function name
            r'(?:\s*\([^)]*\))?'               # Optional arguments
            r'(?:\s+at\s+'                     # "at" keyword
            r'([^:]+)'                         # File path
            r':(\d+))?'                        # Line number
        )

        for line in gdb_output.split('\n'):
            match = frame_pattern.match(line)
            if match:
                frame_num = int(match.group(1))
                function = match.group(2)
                file_path = match.group(3) if match.group(3) else None
                line_num = int(match.group(4)) if match.group(4) else None

                frame = {
                    'frame': frame_num,
                    'function': function,
                    'file': file_path,
                    'line': line_num
                }

                frames.append(frame)

        if not frames:
            # Try alternative format (shorter)
            # #0  vulnerable_func () at test.c:10
            alt_pattern = re.compile(
                r'#(\d+)\s+'
                r'([^\s(]+)'
                r'(?:\s*\([^)]*\))?'
                r'(?:\s+at\s+([^:]+):(\d+))?'
            )

            for line in gdb_output.split('\n'):
                match = alt_pattern.match(line)
                if match:
                    frames.append({
                        'frame': int(match.group(1)),
                        'function': match.group(2),
                        'file': match.group(3) if match.group(3) else None,
                        'line': int(match.group(4)) if match.group(4) else None
                    })

        return frames

    def _parse_registers(self, gdb_output: str) -> Dict:
        """
        Parse register values from GDB output.

        Args:
            gdb_output: Raw GDB output

        Returns:
            Dict of register values
        """
        registers = {}

        # Look for "info registers" output
        in_registers = False
        for line in gdb_output.split('\n'):
            if 'info registers' in line.lower():
                in_registers = True
                continue

            if in_registers:
                # Parse register lines: rax            0x0      0
                match = re.match(r'(\w+)\s+0x([0-9a-fA-F]+)', line)
                if match:
                    reg_name = match.group(1)
                    reg_value = match.group(2)
                    registers[reg_name] = reg_value
                elif line.strip() == '':
                    break  # End of registers

        return registers

    def extract_crash_address(self, gdb_output: str) -> Optional[str]:
        """
        Extract crash address from GDB output.

        Args:
            gdb_output: Raw GDB output

        Returns:
            Crash address or None
        """
        # Look for patterns like:
        # Program received signal SIGSEGV, Segmentation fault.
        # 0x0000555555555189 in vulnerable_func () at test.c:10

        # Pattern 1: After signal message
        match = re.search(
            r'Program received signal.*?\n0x([0-9a-fA-F]+)',
            gdb_output,
            re.MULTILINE
        )
        if match:
            return match.group(1)

        # Pattern 2: From backtrace #0
        match = re.search(r'#0\s+0x([0-9a-fA-F]+)', gdb_output)
        if match:
            return match.group(1)

        return None

    def extract_signal(self, gdb_output: str) -> Optional[str]:
        """
        Extract signal type from GDB output.

        Args:
            gdb_output: Raw GDB output

        Returns:
            Signal name (e.g., "SIGSEGV") or None
        """
        match = re.search(r'Program received signal (\w+)', gdb_output)
        if match:
            return match.group(1)

        return None


# Convenience function
def extract_backtrace(gdb_output: str, arch: str = "auto") -> List[Dict]:
    """
    Quick function to extract backtrace from GDB output.

    Args:
        gdb_output: Raw GDB output containing backtrace
        arch: Target architecture

    Returns:
        List of stack frames

    Example:
        >>> output = '''
        ... #0  0x401234 in vulnerable_func () at test.c:10
        ... #1  0x401567 in main () at test.c:20
        ... '''
        >>> frames = extract_backtrace(output)
        >>> len(frames)
        2
    """
    extractor = GDBBacktraceExtractor(arch=arch)
    return extractor._parse_gdb_backtrace(gdb_output)


# Testing
if __name__ == "__main__":
    # Test backtrace parsing
    test_output = """
#0  0x00007ffff7a52495 in __GI_raise (sig=sig@entry=6) at ../sysdeps/unix/sysv/linux/raise.c:50
#1  0x00007ffff7a3b89b in __GI_abort () at abort.c:79
#2  0x0000555555555189 in vulnerable_func () at test.c:10
#3  0x00005555555551a0 in process_input (data=0x7fffffffd810) at test.c:25
#4  0x00005555555551c5 in main (argc=2, argv=0x7fffffffd958) at test.c:40
"""

    extractor = GDBBacktraceExtractor()
    frames = extractor._parse_gdb_backtrace(test_output)

    print("Parsed Backtrace:")
    print("=" * 60)
    for frame in frames:
        print(f"#{frame['frame']}: {frame['function']}")
        if frame['file']:
            print(f"     at {frame['file']}:{frame['line']}")
    print("=" * 60)

    # Test crash address extraction
    crash_output = """
Program received signal SIGSEGV, Segmentation fault.
0x0000555555555189 in vulnerable_func () at test.c:10
10      *ptr = 0;
"""

    address = extractor.extract_crash_address(crash_output)
    signal = extractor.extract_signal(crash_output)

    print(f"\nCrash Address: {address}")
    print(f"Signal: {signal}")
