import os
import json
import random
import struct
import hashlib
import zlib
import shutil
from typing import Dict, List, Optional
import logging

from fuzzers.base import Fuzzer

logger = logging.getLogger("fawkes")

class FileFuzzer(Fuzzer):
    def __init__(self, input_dir: str, config: dict = None):
        super().__init__(input_dir, config or {})
        self.index = 0

        logger.debug(f"input_dir repr -> {repr(self.input_dir)}")
        self.seed_files = [
            os.path.join(self.input_dir, f)
            for f in os.listdir(self.input_dir)
            if os.path.isfile(os.path.join(self.input_dir, f)) and not f.endswith(".json")
        ]
        self.logger.debug(f"Loaded {len(self.seed_files)} seed files from {input_dir}")

        # Load fuzzer config
        self.fuzzer_config = self._load_fuzzer_config()
        self.mutations_per_seed = self.fuzzer_config.get("mutations_per_seed", 100)
        self.output_dir = os.path.expanduser(self.fuzzer_config.get("output_dir", "~/fawkes/testcases"))
        self.copy_all = self.fuzzer_config.get("copy_all", False)
        self.crash_feedback = self.fuzzer_config.get("crash_feedback", True)
        os.makedirs(self.output_dir, exist_ok=True)

        # Initialize crash feedback
        self.crash_stats = self._load_crash_feedback() if self.crash_feedback else {}

        # Set total testcases
        self.total_testcases = len(self.seed_files) * self.mutations_per_seed
        if not self.seed_files:
            self.logger.warning("No seed files found, generating dummy testcases")
            self.total_testcases = self.mutations_per_seed  # Fallback

        # Update db stats
        if self.config.db and self.config.job_id:
            self.config.db.update_fuzzer_stats(
                self.config.job_id,
                total_testcases=self.total_testcases,
                generated_testcases=self.index
            )
            self.logger.debug(f"Initialized job {self.config.job_id} with {self.total_testcases} testcases")

    def _load_fuzzer_config(self) -> Dict:
        """Load fuzzer-specific config (including a format_spec mapping or single file)."""
        self.logger.debug(f"Loading fuzzer config from file: {self.config.fuzzer_config}")
        config_path = self.config.fuzzer_config
        defaults = {
            "format_spec": "format.json",
            "mutations_per_seed": 100,
            "crash_feedback": True,
            "output_dir": "~/fawkes/testcases",
            "copy_all": False
        }
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    cfg = json.load(f)
                    defaults.update(cfg)
                    # Validate format_spec if it's a mapping
                    if "format_spec" in cfg:
                        if not isinstance(cfg["format_spec"], (str, dict)):
                            raise ValueError(f"format_spec must be string or dict, got {type(cfg['format_spec'])}")
                        if isinstance(cfg["format_spec"], dict):
                            for seed, fmt in cfg["format_spec"].items():
                                if not isinstance(seed, str) or not isinstance(fmt, str):
                                    raise ValueError(f"Invalid format_spec mapping: {seed}: {fmt}")
                    self.logger.debug(f"Loaded fuzzer config from {config_path}")
            except Exception as e:
                self.logger.error(f"Failed to load fuzzer config {config_path}: {e}")
        else:
            self.logger.debug(f"No fuzzer config found at {config_path}, using defaults")
        return defaults

    def _load_format_spec(self, format_file: str) -> Optional[Dict]:
        """Load and validate format specification for a given format file."""
        spec_path = os.path.join(self.input_dir, format_file)
        if not os.path.exists(spec_path):
            self.logger.warning(f"No format spec at {spec_path}, using random mutations")
            return None
        try:
            with open(spec_path, "r") as f:
                spec = json.load(f)
            # Basic validation
            if "fields" not in spec:
                raise ValueError("Format spec missing 'fields'")
            for field in spec["fields"]:
                if "name" not in field or "type" not in field:
                    raise ValueError(f"Invalid field: {field}")
                if field["type"] == "fixed" and "value" not in field:
                    raise ValueError(f"Fixed field {field['name']} missing value")
            self.logger.debug(f"Loaded format spec from {spec_path}")
            return spec
        except Exception as e:
            self.logger.error(f"Failed to load format spec {spec_path}: {e}")
            return None

    def _load_crash_feedback(self) -> Dict:
        """Load crash stats from _analysis.txt files for simple crash-guided weighting."""
        crash_dir = os.path.expanduser("~/fawkes/crashes/unique")
        stats = {}
        try:
            for f in os.listdir(crash_dir):
                if f.endswith("_analysis.txt"):
                    with open(os.path.join(crash_dir, f), "r") as af:
                        content = af.read().lower()
                        # Count fault types
                        if "buffer overflow" in content:
                            stats["buffer_overflow"] = stats.get("buffer_overflow", 0) + 1
                        if "pc_corruption" in content:
                            stats["pc_corruption"] = stats.get("pc_corruption", 0) + 1
                        if "null_pointer" in content:
                            stats["null_pointer"] = stats.get("null_pointer", 0) + 1
            self.logger.debug(f"Loaded crash feedback: {stats}")
        except Exception as e:
            self.logger.error(f"Failed to load crash feedback from {crash_dir}: {e}")
        return stats

    def generate_testcase(self) -> str:
        """Generate a mutated testcase file and optionally copy all seeds."""
        if self.index >= self.total_testcases:
            raise StopIteration("No more testcases in FileFuzzer")

        # Pick a random seed
        seed_file = random.choice(self.seed_files) if self.seed_files else None
        job_id = self.config.get("job_id", "unknown")
        testcase_name = f"{job_id}_{self.index:06d}.bin"
        testcase_path = os.path.join(self.output_dir, testcase_name)

        if not seed_file:
            # Fallback: random bytes
            with open(testcase_path, "wb") as f:
                f.write(os.urandom(1024))
            self.logger.debug(f"Generated fallback testcase: {testcase_path}")
        else:
            # Determine format file for this seed
            seed_basename = os.path.basename(seed_file)
            format_file = None
            if isinstance(self.fuzzer_config["format_spec"], dict):
                format_file = self.fuzzer_config["format_spec"].get(seed_basename)
                if not format_file:
                    self.logger.warning(f"No format specified for seed {seed_basename}, using random mutations")
            else:
                format_file = self.fuzzer_config["format_spec"]

            # Load format spec if we have one
            format_spec = None
            if format_file:
                format_spec = self._load_format_spec(format_file)

            # Read seed content
            with open(seed_file, "rb") as f:
                content = bytearray(f.read())

            # If we have a format spec, do content-aware fuzzing
            if format_spec:
                mutated = self._mutate_file(content, format_spec)
                self.logger.debug(f"Mutated {seed_basename} using {format_file}")
            else:
                # Random fallback
                for _ in range(random.randint(1, 5)):
                    if content:
                        idx = random.randrange(len(content))
                        content[idx] ^= random.randint(1, 255)
                mutated = content
                self.logger.debug(f"Applied random mutations to {seed_basename}")

            with open(testcase_path, "wb") as f:
                f.write(mutated)
            self.logger.debug(f"Generated testcase: {testcase_path}")

        # Copy all seed files if enabled
        if self.copy_all and self.seed_files:
            for sf in self.seed_files:
                if sf != seed_file:
                    base_name = os.path.basename(sf)
                    copy_name = f"{job_id}_{self.index:06d}_{base_name}"
                    copy_path = os.path.join(self.output_dir, copy_name)
                    try:
                        shutil.copyfile(sf, copy_path)
                        self.logger.debug(f"Copied seed {sf} to {copy_path}")
                    except Exception as e:
                        self.logger.error(f"Failed to copy {sf} to {copy_path}: {e}")

        return testcase_path

    def _mutate_file(self, content: bytearray, format_spec: Dict) -> bytearray:
        """Apply content-aware mutations based on format spec (including new checksum logic)."""
        fields = self._parse_fields(content, format_spec)
        mutated_fields = fields.copy()

        # Pick how many fields we mutate this iteration
        num_mutations = random.randint(1, 3)
        possible_field_names = list(fields.keys())
        if not possible_field_names:
            # Edge case: no fields means nothing to do
            return content

        fields_to_mutate = random.sample(possible_field_names, min(num_mutations, len(possible_field_names)))

        # Perform the mutations
        for field_name in fields_to_mutate:
            field_def = next(f for f in format_spec["fields"] if f["name"] == field_name)
            old_value = fields[field_name]["value"]
            new_value = self._mutate_field(field_def, old_value)
            mutated_fields[field_name]["value"] = new_value

        # Re-serialize with updated field values
        mutated_content = self._serialize_fields(mutated_fields, format_spec)
        return mutated_content

    def _parse_fields(self, content: bytearray, format_spec: Dict) -> Dict:
        """
        Parse file into fields based on spec.
        Now logs a warning if a field extends beyond the actual file size.
        """
        fields = {}
        offset = 0

        for field in format_spec["fields"]:
            fname = field["name"]
            ftype = field["type"]
            # If 'offset' is specified, use it; otherwise continue from the current offset
            if "offset" in field and field["offset"] is not None:
                offset = field["offset"]

            # length_field means "the length is stored in another field's value"
            if "length_field" in field:
                len_field = field["length_field"]
                if len_field in fields:
                    flen = fields[len_field]["value"]
                    # If it's int, we trust it. If it's bytes or something else, treat it as 0 or length of that data.
                    if not isinstance(flen, int):
                        flen = len(flen) if isinstance(flen, (bytes, bytearray)) else 0
                else:
                    flen = 0
            else:
                flen = field.get("length", 0)

            # Check if offset+flen goes beyond content
            if offset + flen > len(content):
                self.logger.warning(
                    f"Field '{fname}' extends beyond seed content: offset={offset}, length={flen}, content_size={len(content)}"
                )
                # We'll parse what we can (partial), so let's clamp flen
                flen = max(0, len(content) - offset)

            try:
                if ftype in ("uint8", "uint16", "uint32", "uint64"):
                    value = int.from_bytes(content[offset:offset+flen], "big")
                elif ftype in ("int8", "int16", "int32", "int64"):
                    value = int.from_bytes(content[offset:offset+flen], "big", signed=True)
                elif ftype == "fixed":
                    value = content[offset:offset+flen]
                elif ftype in ("bytes", "string"):
                    value = content[offset:offset+flen]
                elif ftype in ("crc32", "md5", "ip_checksum", "ones_complement_16"):
                    # We'll recalc after mutation, but store existing
                    value = content[offset:offset+flen]
                else:
                    # Unknown type: store raw
                    value = content[offset:offset+flen]

                fields[fname] = {"value": value, "offset": offset, "length": flen}
                offset += flen

            except Exception as e:
                self.logger.error(f"Failed to parse field {fname}: {e}")
                fields[fname] = {"value": b"", "offset": offset, "length": flen}

        return fields

    def _mutate_field(self, field_def: Dict, value: any) -> any:
        """Mutate a single field based on type and crash feedback."""
        ftype = field_def["type"]
        fname = field_def["name"]

        # Crash-guided weighting (70% chance)
        if self.crash_stats and random.random() < 0.7:
            # For example, if we see lots of buffer_overflows, let's do big expansions
            if "buffer_overflow" in self.crash_stats and ftype in ("bytes", "string"):
                return b"A" * random.randint(100, 1000)
            if "pc_corruption" in self.crash_stats and ftype in ("uint32", "uint64"):
                return 0x41414141
            if "null_pointer" in self.crash_stats and ftype in ("bytes", "string"):
                return b"\x00" * random.randint(1, 10)

        # For checksums, skip direct mutation and recalc later
        if ftype in ("crc32", "md5", "ip_checksum", "ones_complement_16"):
            return value  # We'll handle in _serialize_fields

        # Type-specific general mutations
        if ftype in ("uint8", "uint16", "uint32", "uint64", "int8", "int16", "int32", "int64"):
            # Convert 'value' to an int if not already
            if not isinstance(value, int):
                # Possibly partial parse or something unusual
                try:
                    value = int.from_bytes(value, "big", signed=ftype.startswith("int"))
                except:
                    value = 0

            bit_size = int(ftype[-2:])
            # e.g. for uint16 -> bit_size=16
            # Build some interesting mutations
            max_val = (1 << bit_size) - 1 if ftype.startswith("uint") else (1 << (bit_size-1)) - 1
            min_val = 0 if ftype.startswith("uint") else -(1 << (bit_size-1))

            # A few interesting corners and flips
            mutations = [
                0,
                -1 if not ftype.startswith("uint") else max_val,  # might push negative for int, or max for uint
                value ^ (1 << random.randint(0, bit_size-1)),     # flip a random bit
                value + random.randint(-10, 10),                  # small +/- random
            ]

            # Ensure we clamp if we overshoot
            mutated = random.choice(mutations)
            mutated = max(min_val, min(mutated, max_val))
            return mutated

        elif ftype == "fixed":
            new_value = bytearray(value)
            if new_value:
                idx = random.randrange(len(new_value))
                new_value[idx] ^= random.randint(1, 255)
            return bytes(new_value)

        elif ftype == "bytes":
            new_value = bytearray(value)
            for _ in range(random.randint(1, 5)):
                if new_value:
                    idx = random.randrange(len(new_value))
                    new_value[idx] ^= random.randint(1, 255)
            # occasionally expand
            if random.random() < 0.2:
                new_value.extend(b"\x41" * random.randint(10, 100))
            return bytes(new_value)

        elif ftype == "string":
            # string mutation: add some format-string tokens or trailing null, etc.
            # convert to bytes if it isn't
            if not isinstance(value, (bytes, bytearray)):
                value = str(value).encode("utf-8", errors="ignore")

            mutations = [
                value + b"%n%s%x"[:random.randint(1, 6)],
                value + b"A" * random.randint(10, 100),
                value.rstrip(b"\x00") if b"\x00" in value else value + b"\x00"
            ]
            return random.choice(mutations)

        # fallback for unknown/untreated types
        return value

    def _serialize_fields(self, fields: Dict, format_spec: Dict) -> bytearray:
        """
        Serialize fields back into a file, including recalculating length fields and checksums.
        Now with extra logic for one’s complement style checksums, etc.
        """
        # figure out how big we need the final buffer to be
        max_offset = 0
        for fdata in fields.values():
            end_pos = fdata["offset"] + fdata["length"]
            if end_pos > max_offset:
                max_offset = end_pos

        content = bytearray(max_offset)

        # Write fields in straightforward order
        for fname, fdata in fields.items():
            offset = fdata["offset"]
            value = fdata["value"]
            flen = fdata["length"]

            if isinstance(value, int):
                # figure out if it's signed or not by checking original field type
                # We can do a quick lookup in format_spec
                field_def = next((fd for fd in format_spec["fields"] if fd["name"] == fname), None)
                signed = field_def and field_def["type"].startswith("int")
                content[offset:offset+flen] = value.to_bytes(flen, "big", signed=signed)
            else:
                # treat as bytes
                content[offset:offset+flen] = value[:flen]

        # Fix length fields
        for field_def in format_spec["fields"]:
            if "controls" in field_def:
                controller_name = field_def["name"]
                controlled_field = field_def["controls"]
                if controlled_field in fields and controller_name in fields:
                    new_len = fields[controlled_field]["length"]
                    c_offset = fields[controller_name]["offset"]
                    c_len = fields[controller_name]["length"]
                    # assume the controlling field is an unsigned integer
                    # if there's a chance it's 1 or 2 bytes, we can infer from c_len
                    content[c_offset:c_offset+c_len] = new_len.to_bytes(c_len, "big")

        # Fix checksums (crc32, md5, ip_checksum, ones_complement_16, etc.)
        for field_def in format_spec["fields"]:
            ftype = field_def["type"]
            if ftype in ("crc32", "md5", "ip_checksum", "ones_complement_16"):
                fname = field_def["name"]
                offset = fields[fname]["offset"]
                flen = fields[fname]["length"]
                covers = field_def.get("covers", [])

                # gather the covered data
                data = bytearray()
                for cname in covers:
                    if cname in fields:
                        val = fields[cname]["value"]
                        # if it's int, convert to bytes
                        c_len = fields[cname]["length"]
                        c_offset = fields[cname]["offset"]
                        if isinstance(val, int):
                            field_def2 = next((fd for fd in format_spec["fields"] if fd["name"] == cname), None)
                            signed = field_def2 and field_def2["type"].startswith("int")
                            data.extend(val.to_bytes(c_len, "big", signed=signed))
                        else:
                            data.extend(val)

                # Calculate the new checksum
                if ftype == "crc32":
                    checksum = zlib.crc32(data).to_bytes(4, "big")
                    content[offset:offset+4] = checksum

                elif ftype == "md5":
                    digest = hashlib.md5(data).digest()[:flen]
                    content[offset:offset+flen] = digest

                elif ftype in ("ip_checksum", "ones_complement_16"):
                    # typical 16-bit one's complement sum (like IP or ICMP)
                    checksum_16 = self._calc_ones_complement_16(data)
                    # place it
                    content[offset:offset+2] = checksum_16

        return content

    def _calc_ones_complement_16(self, data: bytes) -> bytes:
        """
        Typical 16-bit one’s complement checksum calculation
        (similar to IP header, ICMP, etc.). 
        """
        total = 0
        # Add up 16-bit words
        for i in range(0, len(data), 2):
            word = data[i] << 8
            if i+1 < len(data):
                word += data[i+1]
            total += word
            # fold any overflow
            total = (total & 0xFFFF) + (total >> 16)

        # final invert
        check = ~total & 0xFFFF
        return check.to_bytes(2, "big")

    def next(self) -> bool:
        """Advance to next testcase and update stats."""
        self.index += 1
        if self.index % 100 == 0 and self.crash_feedback:
            self.crash_stats = self._load_crash_feedback()
            self.logger.debug(f"Refreshed crash feedback at index {self.index}")

        if self.config.db  and self.config.job_id:
            self.config.db.update_fuzzer_stats(
                self.config.job_id,
                generated_testcases=self.index
            )
            self.logger.debug(f"Updated job {self.config.job_id} with {self.index} generated testcases")

        more = self.index < self.total_testcases
        self.logger.debug(f"Next testcase, more available: {more}")
        return more

