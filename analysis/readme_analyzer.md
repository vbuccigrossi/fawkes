---

### `readme_analyzer.md`

```markdown
# Fawkes Crash Analyzer Plugin Guide

Welcome to Fawkes’ modular crash analysis framework! This guide shows you how to create and integrate your own crash analyzer plugins to deduplicate and rank crashes for any architecture. Whether you’re targeting i386, x86_64, ARM, or beyond, Fawkes makes it easy to plug in your logic.

## Overview

Fawkes uses a plugin-based crash analyzer system tied to the `--arch` flag (e.g., `--arch=i386`). Each analyzer is a Python class that inherits from `CrashAnalyzer` and lives in `fawkes/analysis/`. The framework loads the right analyzer based on the VM’s architecture, passing it the crash directory to process crash zips.

### Key Components
- **Base Class**: `fawkes.analysis.base.CrashAnalyzer`—the contract all analyzers follow.
- **Loader**: `fawkes.analysis.load_analyzer`—maps architectures (e.g., `i386`) to modules (e.g., `i386_analyzer`).
- **CLI**: `--arch=<arch>`—selects the QEMU emulator and crash analyzer.

## Writing an Analyzer

### Step 1: Create Your Analyzer File
Place your analyzer in `fawkes/analysis/`. Name it `<arch>_analyzer.py` (e.g., `x86_64_analyzer.py`).

### Step 2: Implement the Analyzer Class
Inherit from `CrashAnalyzer` and implement two abstract methods:
- `get_signature()`: Generate a unique crash signature for deduplication.
- `rank_exploitability()`: Assess the crash’s exploitability (e.g., Low, Medium, High).

Here’s a skeleton:

```python
from fawkes.analysis.base import CrashAnalyzer
import zipfile

class MyAnalyzer(CrashAnalyzer):
    def get_signature(self, crash_zip: str) -> str:
        """Generate a unique signature for deduplication."""
        with zipfile.ZipFile(crash_zip, "r") as zf:
            # Extract key data (e.g., GDB output, exception details)
            raise NotImplementedError("Implement me!")

    def rank_exploitability(self, crash_zip: str) -> str:
        """Rank the crash’s exploitability."""
        with zipfile.ZipFile(crash_zip, "r") as zf:
            # Analyze crash data for exploit potential
            raise NotImplementedError("Implement me!")
```

### Step 3: Register Your Analyzer
Edit `fawkes/analysis/__init__.py` to map your architecture to your module:

```python
ANALYZER_MAP = {
    "i386": "i386_analyzer",
    "myarch": "my_analyzer",  # Add your analyzer here
}
```

- Key: The `--arch` value (e.g., `myarch`).
- Value: Your module name without `.py` (e.g., `my_analyzer`).

### Example: x86_64 Crash Analyzer
Here’s a simple analyzer for x86_64:

```python
# fawkes/analysis/x86_64_analyzer.py
from fawkes.analysis.base import CrashAnalyzer
import zipfile
import hashlib
import json

class X8664Analyzer(CrashAnalyzer):
    def get_signature(self, crash_zip: str) -> str:
        """Generate a crash signature for x86_64."""
        with zipfile.ZipFile(crash_zip, "r") as zf:
            if "gdb_output.txt" in zf.namelist():
                gdb_output = zf.read("gdb_output.txt").decode(errors="ignore")
                return hashlib.sha256(gdb_output.encode()).hexdigest()
            elif "crash_info.json" in zf.namelist():
                crash_info = json.loads(zf.read("crash_info.json").decode())
                return hashlib.sha256(f"{crash_info['exe']}:{crash_info['exception']}".encode()).hexdigest()
        self.logger.warning(f"No signature data in {crash_zip}, using file hash")
        return hashlib.sha256(crash_zip.encode()).hexdigest()

    def rank_exploitability(self, crash_zip: str) -> str:
        """Rank exploitability for x86_64 crashes."""
        with zipfile.ZipFile(crash_zip, "r") as zf:
            if "gdb_output.txt" in zf.namelist():
                gdb_output = zf.read("gdb_output.txt").decode(errors="ignore")
                if "RIP" in gdb_output or "invalid instruction" in gdb_output:
                    return "High"  # Possible control flow hijack
                return "Medium"  # Generic kernel crash
            elif "crash_info.json" in zf.namelist():
                crash_info = json.loads(zf.read("crash_info.json").decode())
                exc = crash_info["exception"].lower()
                if "segmentation fault" in exc or "overflow" in exc:
                    return "Medium"  # Potential exploit
                return "Low"  # Generic user crash
        return "Unknown"
```

Run it:
```bash
python -m fawkes.main --arch=x86_64 ...
```

## How It Works
- **Crash Zip**: Contains `gdb_output.txt` (kernel) or `crash_info.json` (user), plus testcase and `shared/` files.
- **Deduplication**: `get_signature()` hashes key crash data—identical signatures go to `crash_dir/dupes/`.
- **Ranking**: `rank_exploitability()` tags crashes (e.g., `crash_1_20250405_123456_exploitability_High.zip`) and stores them in `crash_dir/unique/`.

## Tips
- **Crash Dir**: Use `self.crash_dir`, `self.unique_dir`, `self.dupe_dir` for file ops.
- **Logging**: Use `self.logger` to debug your analyzer.
- **Signatures**: Hash stack traces, registers, or exceptions—keep it arch-specific.
- **Ranking**: Start with heuristics (e.g., EIP/RIP overwrite = High), expand later.

## Testing Your Analyzer
1. **Unit Test**:
   ```python
   analyzer = X8664Analyzer("/tmp/crash_test")
   analyzer.analyze_crash("/tmp/crash_test/crash_1_20250405_123456.zip")
   ```
2. **Run in Fawkes**:
   - Use `--log-level=DEBUG` to see your analyzer’s logs.
   - Trigger crashes, check `unique/` and `dupes/` dirs.

## Future Ideas
- **ARM Analyzer**: Check `LR`/`PC` for control hijacks.
- **MIPS Analyzer**: Look at `ra` register or syscall crashes.
- **Advanced Ranking**: Use stack traces or memory corruption patterns.

Happy analyzing! Drop your analyzer in `fawkes/analysis/` and make Fawkes smarter for your architecture.
```

---

### Why This Rocks
- **Simple**: Devs get a plug-and-play template with a real x86_64 example.
- **Modular**: `--arch` drives it, just like QEMU—add an analyzer, update the map, done.
- **Practical**: Covers dedup and ranking with room to grow.

---
