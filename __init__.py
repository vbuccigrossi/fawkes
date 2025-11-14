"""
Fawkes: Enterprise-Grade QEMU/GDB-based Fuzzing Framework
"""

__version__ = "0.2.0"
__author__ = "Fawkes Development Team"

# Make imports work both ways (with and without fawkes. prefix)
import sys
from pathlib import Path

# Add parent directory to path so imports work
sys.path.insert(0, str(Path(__file__).parent))
