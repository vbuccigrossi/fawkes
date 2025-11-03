---

### `readme_fuzzer.md`

```markdown
# Fawkes Fuzzer Plugin Guide

Welcome to Fawkes’ extensible fuzzer framework! This guide shows you how to create and integrate your own fuzzer plugins to power up your fuzzing game. Whether you’re fuzzing files, network packets, or something wilder, Fawkes makes it plug-and-play.

## Overview

Fawkes uses a plugin-based fuzzer system. Each fuzzer is a Python class that inherits from `Fuzzer` and lives in `fawkes/fuzzers/`. The framework loads your fuzzer dynamically based on the `--fuzzer` CLI flag, passing it the input directory and optional config.

### Key Components
- **Base Class**: `fawkes.fuzzers.base.Fuzzer`—the contract all fuzzers follow.
- **Loader**: `fawkes.fuzzers.load_fuzzer`—maps names (e.g., `file`) to modules (e.g., `file_fuzzer`).
- **CLI**: `--fuzzer=<name>` and `--fuzzer-config=<json_file>`—how users select your fuzzer.

## Writing a Fuzzer

### Step 1: Create Your Fuzzer File
Place your fuzzer in `fawkes/fuzzers/`. Name it `<your_fuzzer_name>_fuzzer.py` (e.g., `network_fuzzer.py`).

### Step 2: Implement the Fuzzer Class
Inherit from `Fuzzer` and implement two abstract methods:
- `generate_testcase()`: Produce a testcase file or data, return its path.
- `next()`: Move to the next variation, return `True` if more testcases exist.

Here’s a skeleton:

```python
from fawkes.fuzzers.base import Fuzzer

class MyFuzzer(Fuzzer):
    def __init__(self, input_dir: str, config: dict = None):
        super().__init__(input_dir, config)
        # Initialize your state (e.g., load seeds, set counters)
        self.logger.debug(f"Initialized with input_dir={input_dir}, config={config}")

    def generate_testcase(self) -> str:
        # Generate a testcase (e.g., write to a temp file)
        # Return the path to the testcase file
        raise NotImplementedError("Implement me!")

    def next(self) -> bool:
        # Advance to the next testcase
        # Return True if more testcases are available, False if done
        raise NotImplementedError("Implement me!")
```

### Step 3: Register Your Fuzzer
Edit `fawkes/fuzzers/__init__.py` to map a user-friendly name to your module:

```python
FUZZER_MAP = {
    "file": "file_fuzzer",
    "myfuzzer": "my_fuzzer",  # Add your fuzzer here
}
```

- Key: What users type with `--fuzzer` (e.g., `myfuzzer`).
- Value: Your module name without `.py` (e.g., `my_fuzzer`).

### Example: Network Packet Fuzzer
Here’s a simple fuzzer that mutates one packet in a conversation:

```python
# fawkes/fuzzers/network_fuzzer.py
from fawkes.fuzzers.base import Fuzzer
import os

class NetworkFuzzer(Fuzzer):
    def __init__(self, input_dir: str, config: dict = None):
        super().__init__(input_dir, config)
        self.packets = config.get("packets", ["GET /", "Host: example.com", "Accept: */*"])
        self.fuzz_index = 0

    def generate_testcase(self) -> str:
        output = []
        for i, packet in enumerate(self.packets):
            if i == self.fuzz_index:
                output.append(packet + "FUZZ")  # Simple mutation
            else:
                output.append(packet)
        temp_file = f"/tmp/network_fuzz_{self.fuzz_index}.txt"
        with open(temp_file, "w") as f:
            f.write("\n".join(output))
        self.logger.debug(f"Generated testcase: {temp_file}")
        return temp_file

    def next(self) -> bool:
        self.fuzz_index += 1
        more = self.fuzz_index < len(self.packets)
        self.logger.debug(f"Next testcase, more available: {more}")
        return more
```

Config file (`network_config.json`):
```json
{
    "packets": ["GET /", "Host: example.com", "Accept: */*"]
}
```

Run it:
```bash
python -m fawkes.main --fuzzer=network --fuzzer-config=network_config.json ...
```

---

- **Optional Stats**: In `fawkes/fuzzers/file_fuzzer.py`:
  ```python
  def __init__(self, input_dir: str, config: dict = None):
      super().__init__(input_dir, config)
      self.files = [os.path.join(self.input_dir, f) for f in os.listdir(self.input_dir) if os.path.isfile(os.path.join(self.input_dir, f))]
      self.index = 0
      self.logger.debug(f"Loaded {len(self.files)} files from {self.input_dir}")
      if "db" in config:  # Pass db via config in main.py if needed
          config["db"].update_fuzzer_stats(config.get("job_id"), total_testcases=len(self.files), generated_testcases=self.index)
  ```

- **Update on Next**:
  ```python
  def next(self) -> bool:
      self.index += 1
      if "db" in self.config:
          self.config["db"].update_fuzzer_stats(self.config.get("job_id"), generated_testcases=self.index)
      more = self.index < len(self.files)
      return more
  ```

Pass `db` and `job_id` via `cfg.fuzzer_config` in `main.py`.

---

## Tips
- **Input Dir**: Use `self.input_dir` for seed files if needed.
- **Config**: Access `self.config` for custom settings (e.g., mutation rates).
- **Logging**: Use `self.logger` to debug your fuzzer.
- **Temp Files**: Write testcases to `/tmp/` or similar—Fawkes handles cleanup.

## Testing Your Fuzzer
1. **Unit Test**:
   ```python
   fuzzer = NetworkFuzzer("/path/to/seeds", {"packets": ["A", "B"]})
   print(fuzzer.generate_testcase())  # First testcase
   fuzzer.next()
   print(fuzzer.generate_testcase())  # Second testcase
   ```
2. **Run in Fawkes**:
   - Use `--log-level=DEBUG` to see your fuzzer’s logs.
   - Check that testcases hit the VM’s `fawkes_shared` dir.

## Future Ideas
- **Mutation Fuzzer**: Randomly tweak bytes in a seed file.
- **Protocol Fuzzer**: Craft packets for HTTP, DNS, etc.
- **Stateful Fuzzer**: Track VM responses to guide fuzzing.

Happy fuzzing! Drop your fuzzer in `fawkes/fuzzers/` and take Fawkes to the next level.
```

---
