# FileFuzzer Documentation

`FileFuzzer` is a content-aware file fuzzer for the Fawkes fuzzing framework, designed to generate intelligent test cases by understanding file formats and optionally using crash feedback. Unlike the basic `FileFuzzer`, which cycles through static files, `SmartFileFuzzer` mutates files based on a user-defined format specification, targeting specific fields like numbers, strings, or checksums. It supports features like length field fixups, checksum recalculation, and crash-guided mutations to increase the likelihood of finding meaningful bugs. Additionally, it offers a `copy_all` mode to output both mutated and original seed files, ideal for scenarios like network fuzzing.

This document explains how `SmartFileFuzzer` works, how to configure it, and how to write format specifications for content-aware fuzzing.

## Table of Contents
- [Overview](#overview)
- [How It Works](#how-it-works)
- [Configuring the Fuzzer](#configuring-the-fuzzer)
  - [Fuzzer Configuration File](#fuzzer-configuration-file)
  - [Configuration Fields](#configuration-fields)
- [Writing a Format Specification](#writing-a-format-specification)
  - [Format Specification Structure](#format-specification-structure)
  - [Supported Field Types](#supported-field-types)
  - [Example Format Specification](#example-format-specification)
- [Using the Fuzzer](#using-the-fuzzer)
- [Integration with Fawkes](#integration-with-fawkes)
- [Troubleshooting](#troubleshooting)

## Overview

`FileFuzzer` is part of the Fawkes fuzzing framework and resides in `fawkes/fuzzers/file_fuzzer.py`. It extends the `Fuzzer` base class, maintaining compatibility with Fawkes’ fuzzing harness and crash analysis pipeline (e.g., `MIPSAnalyzer`, `I386Analyzer`). Key features include:

- **Content-Aware Fuzzing**: Mutates files based on a JSON format specification, targeting fields like integers, strings, or checksums intelligently.
- **Crash Feedback**: Optionally uses crash data (`_analysis.txt` files) to bias mutations toward high-impact bugs (e.g., buffer overflows).
- **Copy All Mode**: Outputs both the mutated test case and all original seed files per test case, useful for network fuzzing.
- **Modularity**: Integrates seamlessly with Fawkes’ configuration, database stats, and TUI crash display.

The fuzzer is designed to be more effective than random bit-flipping fuzzers without requiring heavy instrumentation, making it suitable for both local and distributed fuzzing tasks.

## How It Works

`SmartFileFuzzer` operates in the following steps:

1. **Initialization**:
   - Loads a fuzzer-specific configuration from `input_dir/fuzzer_config.json` (or a path specified in the harness config).
   - Reads a format specification (e.g., `input_dir/format.json`) to understand the file structure.
   - Collects seed files from `input_dir` (e.g., `sample1.bin`).
   - Optionally scans `~/fawkes/crashes/unique/` for `_analysis.txt` files to build crash feedback stats.
   - Sets `total_testcases` as `number of seeds × mutations_per_seed` (default: 100 mutations per seed).

2. **Test Case Generation**:
   - Selects a random seed file.
   - Parses the seed into fields using the format specification (e.g., magic bytes, length fields).
   - Applies 1–3 mutations to fields, choosing strategies based on field type and crash feedback:
     - Numeric: Boundary values (0, max), bit flips, arithmetic tweaks.
     - Bytes/String: Random flips, overflow patterns (`0x41414141`), format strings (`%n`).
     - Checksums: Recalculated or corrupted.
     - Crash-guided: Favors mutations linked to crashes (e.g., long strings for buffer overflows).
   - Fixes dependent fields (e.g., updates `data_length` for `data`).
   - Writes the mutated file to `output_dir/<job_id>_<index>.bin` (e.g., `~/fawkes/testcases/job123_000001.bin`).
   - If `copy_all` is enabled, copies all seed files to `output_dir/<job_id>_<index>_<filename>` (e.g., `job123_000001_file1.bin`).
   - Returns the mutated file’s path for the harness.

3. **Advancing**:
   - Increments the test case index.
   - Updates database stats (`generated_testcases`) for tracking progress.
   - Refreshes crash feedback every 100 test cases (if enabled).
   - Continues until `total_testcases` is reached.

4. **Output**:
   - Generates test case files in `output_dir`.
   - Logs mutations and copies for debugging (in `~/.fawkes/fawkes.log`).
   - Supports Fawkes’ crash pipeline, where crashes are analyzed and displayed in the TUI.

The fuzzer avoids full instrumentation, keeping it lightweight while being significantly smarter than random fuzzing.

## Configuring the Fuzzer

`SmartFileFuzzer` uses a dedicated configuration file to define its behavior, separate from Fawkes’ main `config.json`. This leverages the existing `Fuzzer` base class mechanism, where a config dictionary is passed to the fuzzer during initialization.

### Fuzzer Configuration File

- **Location**: By default, the fuzzer looks for `fuzzer_config.json` in the `input_dir`. Alternatively, the harness can specify a path via the `config` dictionary’s `fuzzer_config` key.
- **Format**: JSON, with fields controlling fuzzing parameters.
- **Example**:
  ```json
  {
    "format_spec": "format.json",
    "mutations_per_seed": 100,
    "crash_feedback": true,
    "output_dir": "~/fawkes/testcases",
    "copy_all": true
  }
  ```

### Configuration Fields

| Field               | Type    | Default                   | Description                                                                 |
|---------------------|---------|---------------------------|-----------------------------------------------------------------------------|
| `format_spec`       | String  | `"format.json"`           | Path to the format specification file, relative to `input_dir` or absolute. If missing or invalid, the fuzzer falls back to random byte flips. |
| `mutations_per_seed` | Integer | `100`                     | Number of test cases to generate per seed file. Total test cases = `len(seeds) × mutations_per_seed`. |
| `crash_feedback`    | Boolean | `true`                    | If `true`, uses crash data from `~/fawkes/crashes/unique/` to bias mutations (e.g., longer strings for buffer overflows). |
| `output_dir`        | String  | `"~/fawkes/testcases"`    | Directory where test cases are written. Created if it doesn’t exist.        |
| `copy_all`          | Boolean | `false`                   | If `true`, copies all seed files to `output_dir` alongside each mutated test case, named `<job_id>_<index>_<filename>`. Useful for network fuzzing. |

**Notes**:
- If `fuzzer_config.json` is missing, the fuzzer uses the default values above.
- Errors in the config (e.g., invalid JSON) are logged, and defaults are applied.
- The `output_dir` is expanded (e.g., `~` becomes the user’s home directory).

## Writing a Format Specification

The format specification tells `SmartFileFuzzer` how to parse and mutate files, enabling content-aware fuzzing. It defines fields within the file, their types, and relationships like length dependencies or checksums.

### Format Specification Structure

- **File**: Typically `input_dir/format.json`, specified in `fuzzer_config.json`.
- **Format**: JSON, with a top-level `format_name` and a `fields` array.
- **Field Properties**:
  - `name` (string, required): Unique identifier for the field.
  - `type` (string, required): Data type (e.g., `uint32`, `bytes`). See [Supported Field Types](#supported-field-types).
  - `offset` (integer or null, optional): Byte offset in the file. If `null`, computed from previous fields.
  - `length` (integer, optional): Fixed length in bytes. Required unless `length_field` is used.
  - `length_field` (string, optional): Name of another field that defines this field’s length (for variable-length fields like `bytes`).
  - `value` (string or bytes, required for `fixed`): Expected value for `fixed` fields (e.g., `"MAGC"`).
  - `controls` (string, optional): Name of a field whose length this field controls (e.g., `data_length` for `data`).
  - `covers` (array of strings, optional): Field names included in a checksum computation (for `crc32`, `md5`).

### Supported Field Types

| Type           | Description                                                                 | Mutation Strategies                                              |
|----------------|-----------------------------------------------------------------------------|------------------------------------------------------------------|
| `fixed`        | Static bytes (e.g., magic header). Requires `value`.                         | Minimal byte flips (e.g., one byte changed in `MAGC`).            |
| `uint8/16/32/64` | Unsigned integer (8, 16, 32, or 64 bits).                                  | Boundaries (0, max), bit flips, arithmetic (+/- small values).    |
| `int8/16/32/64`  | Signed integer (8, 16, 32, or 64 bits).                                    | Boundaries (min, max), bit flips, arithmetic (+/- small values).  |
| `bytes`        | Raw byte sequence (fixed or variable length).                                | Random flips, patterns (`0x41414141`), extend/truncate.           |
| `string`       | ASCII or UTF-8 string (null-terminated or length-based).                    | Format strings (`%n`, `%s`), overflows (`A`’s), null byte toggles.|
| `crc32`        | 32-bit CRC checksum over specified fields (`covers`).                        | Recalculated after mutations; optionally corrupted.               |
| `md5`          | MD5 hash (up to 16 bytes) over specified fields (`covers`).                  | Recalculated after mutations; optionally corrupted.               |

### Example Format Specification

Below is a sample `format.json` for a simple file format with a magic header, a length field, variable-length data, and a checksum.

```json
{
  "format_name": "simple_format",
  "fields": [
    {
      "name": "magic",
      "offset": 0,
      "length": 4,
      "type": "fixed",
      "value": "TEST"
    },
    {
      "name": "data_length",
      "offset": 4,
      "length": 2,
      "type": "uint16",
      "controls": "data"
    },
    {
      "name": "data",
      "offset": 6,
      "length_field": "data_length",
      "type": "bytes"
    },
    {
      "name": "checksum",
      "offset": null,
      "length": 4,
      "type": "crc32",
      "covers": ["data_length", "data"]
    }
  ]
}
```

**Explanation**:
- `magic`: Fixed 4-byte header `"TEST"`, minimally mutated to preserve validity.
- `data_length`: 16-bit unsigned integer, controls the length of `data`. Mutated with boundaries (e.g., 0, 0xFFFF).
- `data`: Variable-length bytes, sized by `data_length`. Mutated with patterns or extensions.
- `checksum`: CRC32 over `data_length` and `data`, recalculated after mutations.
- `offset: null` for `checksum` means it follows the previous field (`data`).

**Sample Seed File** (`sample.bin`):
```
TEST\x00\x04beef
```
- `TEST`: Magic.
- `\x00\x04`: `data_length` = 4.
- `beef`: `data` (4 bytes).
- (Checksum appended after `data`).

**Mutated Output**:
- Might become `TEST\xFF\xFF41414141...` with `data_length` updated and checksum fixed.

## Using the Fuzzer

To use `SmartFileFuzzer`, follow these steps:

1. **Prepare Input Directory**:
   - Create `input_dir` (e.g., `~/fawkes/inputs`).
   - Add seed files (e.g., `sample1.bin`, `sample2.bin`).
   - Add `format.json` (see [Example Format Specification](#example-format-specification)).
   - Add `fuzzer_config.json` (see [Fuzzer Configuration File](#fuzzer-configuration-file)).

2. **Configure Fawkes**:
   - In `config.json`, set the fuzzer:
     ```json
     {
       "fuzzer": "SmartFileFuzzer",
       "input_dir": "~/fawkes/inputs",
       "job_id": "test123"
     }
     ```
   - The harness passes `job_id` and `db` to the fuzzer.

3. **Run the Fuzzer**:
   - Start Fawkes in local mode:
     ```bash
     python -m fawkes.tui --mode=local
     ```
   - The fuzzer generates test cases in `output_dir` (e.g., `~/fawkes/testcases/job123_000001.bin`).
   - If `copy_all: true`, seed files are copied (e.g., `job123_000001_sample1.bin`).

4. **Monitor Crashes**:
   - Crashes appear in `~/fawkes/crashes/unique/`.
   - View in the TUI Crashes screen (`[X]`), with details via `[V]`.
   - Crash feedback (if enabled) influences future mutations.

5. **Example Output**:
   - Input: `sample1.bin`, `sample2.bin`.
   - Config: `copy_all: true`, `crash_feedback: true`.
   - Output:
     ```
     ~/fawkes/testcases/job123_000001.bin          # Mutated sample1.bin
     ~/fawkes/testcases/job123_000001_sample1.bin  # Original sample1.bin
     ~/fawkes/testcases/job123_000001_sample2.bin  # Original sample2.bin
     ```
   - Logs (`~/.fawkes/fawkes.log`):
     ```
     [DEBUG] Loaded 2 seed files from ~/fawkes/inputs
     [DEBUG] Generated testcase: ~/fawkes/testcases/job123_000001.bin
     [DEBUG] Copied seed ~/fawkes/inputs/sample1.bin to ~/fawkes/testcases/job123_000001_sample1.bin
     ```

## Integration with Fawkes

`SmartFileFuzzer` integrates seamlessly with Fawkes:

- **Harness**: The Fawkes harness calls `generate_testcase()` to get test case paths, feeding them to the target (e.g., QEMU for `mips`, `x86_64`).
- **Crash Pipeline**: Crashes are processed by analyzers (`I386Analyzer`, `MIPSAnalyzer`, etc.), generating `_analysis.txt` files used for crash feedback.
- **TUI**: The Crashes screen (`[X]`) displays crash details, including exploitability and analysis from `_analysis.txt`.
- **Database**: Tracks `total_testcases` and `generated_testcases` via the `db` object (passed in `config`).
- **Configuration**: Uses `fuzzer_config.json` for fuzzer-specific settings, keeping `config.json` focused on global options.

For network fuzzing, enable `copy_all` to output all seed files, allowing the harness to process them as a group (e.g., as a packet sequence).

## Troubleshooting

- **No Test Cases Generated**:
  - Check `input_dir` for seed files and `fuzzer_config.json`.
  - Ensure `format.json` exists and is valid.
  - Verify `output_dir` is writable.
  - Review logs in `~/.fawkes/fawkes.log`.

- **Invalid Format Specification**:
  - Ensure `fields` includes `name` and `type`.
  - For `fixed` fields, provide `value`.
  - Check for overlapping offsets or missing `length`/`length_field`.
  - The fuzzer falls back to random byte flips if the spec is invalid.

- **No Crash Feedback**:
  - Verify `crash_feedback: true` in `fuzzer_config.json`.
  - Ensure crashes exist in `~/fawkes/crashes/unique/` with `_analysis.txt` files.
  - Feedback refreshes every 100 test cases—generate more test cases if needed.

- **Copy All Issues**:
  - Confirm `copy_all: true` in `fuzzer_config.json`.
  - Check `output_dir` for copied files (named `<job_id>_<index>_<filename>`).
  - Ensure seed files are readable and `output_dir` has space.

- **Performance**:
  - For large seed files (>1MB), mutations are limited to key fields to maintain speed.
  - Reduce `mutations_per_seed` if fuzzing is too slow.

For further help, consult the Fawkes documentation or check logs for detailed error messages.
