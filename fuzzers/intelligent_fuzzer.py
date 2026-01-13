"""
Fawkes Intelligent Crash-Guided Fuzzer

A custom fuzzer designed specifically for Fawkes' snapshot-based VM fuzzing.
Features:
- Crash-guided mutation strategies
- Network multi-packet fuzzing
- Corpus management and minimization
- Format-aware mutations
- Adaptive learning from crash feedback
"""

import os
import random
import struct
import json
import hashlib
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

from fuzzers.base import Fuzzer
from fuzzers.dictionary import Dictionary, DictionaryMutator
from fuzzers.fuzzer_stats import FuzzerStats, EnergyScheduler


logger = logging.getLogger("fawkes.intelligent_fuzzer")


class MutationStrategy:
    """Defines a single mutation strategy with success tracking"""

    def __init__(self, name: str, mutator_func, weight: float = 1.0):
        self.name = name
        self.mutator_func = mutator_func
        self.weight = weight
        self.successes = 0  # Number of times this strategy found a crash
        self.attempts = 0

    def apply(self, data: bytearray, *args, **kwargs) -> bytearray:
        """Apply this mutation strategy"""
        self.attempts += 1
        return self.mutator_func(data, *args, **kwargs)

    def record_success(self):
        """Record that this strategy found a crash"""
        self.successes += 1
        # Increase weight based on success rate
        success_rate = self.successes / max(1, self.attempts)
        self.weight = 1.0 + (success_rate * 10.0)  # Boost successful strategies

    def get_effectiveness(self) -> float:
        """Return effectiveness score (0.0 to 1.0)"""
        if self.attempts == 0:
            return 0.0
        return self.successes / self.attempts


class CrashFeedback:
    """Analyzes crashes and extracts intelligence for fuzzing"""

    def __init__(self, db_connection=None):
        self.db = db_connection
        self.crash_patterns = defaultdict(int)  # byte pattern -> crash count
        self.crash_types = Counter()  # crash type -> count
        self.interesting_offsets = set()  # byte offsets that trigger crashes
        self.magic_values = set()  # interesting values found in crashes

    def analyze_crash(self, crash_info: Dict, testcase_path: str):
        """Extract intelligence from a crash"""
        crash_type = crash_info.get("type", "unknown")
        self.crash_types[crash_type] += 1

        # Read the crashing input
        if os.path.exists(testcase_path):
            with open(testcase_path, "rb") as f:
                data = f.read()

            # Extract patterns (4-byte chunks that might be interesting)
            for i in range(0, len(data) - 3, 4):
                chunk = data[i:i+4]
                self.crash_patterns[chunk] += 1

                # Extract integer values
                try:
                    val = struct.unpack("<I", chunk)[0]
                    if val in [0, 0xFFFFFFFF, 0x41414141, 0xDEADBEEF]:
                        self.magic_values.add(val)
                except:
                    pass

        logger.info(f"Analyzed crash: type={crash_type}, patterns={len(self.crash_patterns)}")

    def get_hot_patterns(self, top_n: int = 10) -> List[bytes]:
        """Get the most crash-inducing byte patterns"""
        return [pattern for pattern, count in
                sorted(self.crash_patterns.items(), key=lambda x: x[1], reverse=True)[:top_n]]

    def should_prefer_strategy(self, strategy_name: str) -> bool:
        """Determine if a strategy should be preferred based on crash types"""
        # If we see lots of buffer overflows, prefer block expansion
        if "buffer" in self.crash_types and strategy_name == "block_insert":
            return True
        # If we see access violations, prefer interesting value mutations
        if "access_violation" in self.crash_types and strategy_name == "interesting_values":
            return True
        return False


class IntelligentFuzzer(Fuzzer):
    """
    Advanced crash-guided fuzzer with adaptive mutation strategies.
    Learns from crashes to improve mutation effectiveness.
    """

    def __init__(self, input_dir: str, config: dict = None):
        super().__init__(input_dir, config or {})

        self.input_dir = Path(input_dir).expanduser().resolve()
        self.config_obj = config

        # Load configuration
        self.fuzzer_config = self._load_fuzzer_config()
        self.output_dir = Path(self.fuzzer_config.get("output_dir", "~/fawkes/testcases")).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Corpus management
        self.corpus = self._load_corpus()
        self.current_seed_idx = 0
        self.current_mutation_idx = 0
        self.mutations_per_seed = self.fuzzer_config.get("mutations_per_seed", 1000)

        # Network fuzzing support
        self.network_mode = self.fuzzer_config.get("network_mode", False)
        self.packets_per_conversation = self.fuzzer_config.get("packets_per_conversation", 1)

        # Crash feedback
        self.crash_feedback = CrashFeedback(db_connection=config.db if config else None)
        self._load_crash_history()

        # Dictionary support
        dict_file = self.fuzzer_config.get("dictionary", None)
        self.dictionary = Dictionary(dict_file) if dict_file else Dictionary()
        self.dict_mutator = DictionaryMutator(self.dictionary)

        # Auto-extract tokens from corpus if enabled
        if self.fuzzer_config.get("auto_extract_tokens", True):
            self.dictionary.extract_from_corpus(str(self.input_dir), min_frequency=2)
            logger.info(f"Dictionary contains {len(self.dictionary)} tokens")

        # Initialize mutation strategies
        self.strategies = self._init_mutation_strategies()

        # Statistics tracking
        stats_file = self.fuzzer_config.get("stats_file", "~/.fawkes/fuzzer_stats.json")
        stats_file = str(Path(stats_file).expanduser())
        self.stats = FuzzerStats(stats_file)
        self.stats.corpus_size = len(self.corpus)

        # Energy scheduling (prioritize seeds that found crashes)
        default_energy = self.mutations_per_seed
        self.energy_scheduler = EnergyScheduler(default_energy=default_energy)

        # Statistics
        self.total_testcases = len(self.corpus) * self.mutations_per_seed
        self.generated_count = 0
        self.last_stats_save = 0  # Track when we last saved stats

        logger.info(f"Initialized IntelligentFuzzer: {len(self.corpus)} seeds, "
                   f"{self.total_testcases} total testcases planned")

    def _load_fuzzer_config(self) -> Dict:
        """Load fuzzer configuration from file"""
        defaults = {
            "mutations_per_seed": 1000,
            "output_dir": "~/fawkes/testcases",
            "network_mode": False,
            "packets_per_conversation": 1,
            "max_mutation_size": 1024 * 1024,  # 1MB max
            "use_format_specs": True,
        }

        config_path = self.config_obj.fuzzer_config if self.config_obj else None
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    user_config = json.load(f)
                    defaults.update(user_config)
                    logger.debug(f"Loaded fuzzer config from {config_path}")
            except Exception as e:
                logger.error(f"Failed to load fuzzer config: {e}")

        return defaults

    def _load_corpus(self) -> List[Path]:
        """Load all seed files from input directory"""
        corpus = []

        if not self.input_dir.exists():
            logger.warning(f"Input directory {self.input_dir} does not exist")
            return corpus

        # Load all non-JSON files as seeds
        for file in self.input_dir.iterdir():
            if file.is_file() and not file.suffix == ".json":
                corpus.append(file)

        if not corpus:
            logger.warning("No seed files found in corpus")
        else:
            logger.info(f"Loaded {len(corpus)} seed files from corpus")

        return corpus

    def _load_crash_history(self):
        """Load previous crashes from database to learn from them"""
        if not self.config_obj or not hasattr(self.config_obj, 'db'):
            return

        try:
            # Query recent crashes from database
            db = self.config_obj.db
            crashes = db._conn.execute(
                "SELECT testcase_path, crash_log FROM crashes ORDER BY timestamp DESC LIMIT 100"
            ).fetchall()

            for testcase_path, crash_log in crashes:
                crash_info = {"type": self._classify_crash(crash_log)}
                self.crash_feedback.analyze_crash(crash_info, testcase_path)

            logger.info(f"Loaded {len(crashes)} historical crashes for analysis")
        except Exception as e:
            logger.error(f"Failed to load crash history: {e}")

    def _classify_crash(self, crash_log: str) -> str:
        """Classify crash type from log"""
        log_lower = crash_log.lower()
        if "buffer" in log_lower or "overflow" in log_lower:
            return "buffer_overflow"
        elif "access violation" in log_lower or "segmentation fault" in log_lower:
            return "access_violation"
        elif "null" in log_lower:
            return "null_pointer"
        elif "heap" in log_lower:
            return "heap_corruption"
        else:
            return "unknown"

    def _init_mutation_strategies(self) -> List[MutationStrategy]:
        """Initialize all mutation strategies"""
        strategies = [
            # Deterministic bit flips
            MutationStrategy("bit_flip_1", self._mutate_bit_flip_1, weight=1.0),
            MutationStrategy("bit_flip_2", self._mutate_bit_flip_2, weight=1.0),
            MutationStrategy("bit_flip_4", self._mutate_bit_flip_4, weight=1.0),

            # Byte flips
            MutationStrategy("byte_flip_1", self._mutate_byte_flip_1, weight=1.5),
            MutationStrategy("byte_flip_2", self._mutate_byte_flip_2, weight=1.5),
            MutationStrategy("byte_flip_4", self._mutate_byte_flip_4, weight=1.5),

            # Arithmetic mutations
            MutationStrategy("arith_add", self._mutate_arith_add, weight=2.0),
            MutationStrategy("arith_sub", self._mutate_arith_sub, weight=2.0),

            # Interesting values
            MutationStrategy("interesting_8", self._mutate_interesting_8, weight=2.5),
            MutationStrategy("interesting_16", self._mutate_interesting_16, weight=2.5),
            MutationStrategy("interesting_32", self._mutate_interesting_32, weight=2.5),

            # Block operations
            MutationStrategy("block_delete", self._mutate_block_delete, weight=1.5),
            MutationStrategy("block_insert", self._mutate_block_insert, weight=2.0),
            MutationStrategy("block_swap", self._mutate_block_swap, weight=1.5),
            MutationStrategy("block_duplicate", self._mutate_block_duplicate, weight=1.5),

            # Havoc (stacked random mutations)
            MutationStrategy("havoc", self._mutate_havoc, weight=3.0),

            # Splice (combine two seeds)
            MutationStrategy("splice", self._mutate_splice, weight=2.0),

            # Dictionary-based mutations
            MutationStrategy("dict_replace", self._mutate_dict_replace, weight=2.5),
            MutationStrategy("dict_insert", self._mutate_dict_insert, weight=2.0),
            MutationStrategy("dict_overwrite", self._mutate_dict_overwrite, weight=2.0),
        ]

        return strategies

    # ========== Mutation Strategy Implementations ==========

    def _mutate_bit_flip_1(self, data: bytearray) -> bytearray:
        """Flip a single random bit"""
        if not data:
            return data
        mutated = bytearray(data)
        byte_idx = random.randint(0, len(mutated) - 1)
        bit_idx = random.randint(0, 7)
        mutated[byte_idx] ^= (1 << bit_idx)
        return mutated

    def _mutate_bit_flip_2(self, data: bytearray) -> bytearray:
        """Flip 2 consecutive bits"""
        if len(data) < 1:
            return data
        mutated = bytearray(data)
        byte_idx = random.randint(0, len(mutated) - 1)
        bit_idx = random.randint(0, 6)
        mutated[byte_idx] ^= (3 << bit_idx)
        return mutated

    def _mutate_bit_flip_4(self, data: bytearray) -> bytearray:
        """Flip 4 consecutive bits (half a byte)"""
        if not data:
            return data
        mutated = bytearray(data)
        byte_idx = random.randint(0, len(mutated) - 1)
        bit_idx = random.randint(0, 4)
        mutated[byte_idx] ^= (0xF << bit_idx)
        return mutated

    def _mutate_byte_flip_1(self, data: bytearray) -> bytearray:
        """Flip a single random byte"""
        if not data:
            return data
        mutated = bytearray(data)
        idx = random.randint(0, len(mutated) - 1)
        mutated[idx] ^= 0xFF
        return mutated

    def _mutate_byte_flip_2(self, data: bytearray) -> bytearray:
        """Flip 2 consecutive bytes"""
        if len(data) < 2:
            return data
        mutated = bytearray(data)
        idx = random.randint(0, len(mutated) - 2)
        mutated[idx] ^= 0xFF
        mutated[idx + 1] ^= 0xFF
        return mutated

    def _mutate_byte_flip_4(self, data: bytearray) -> bytearray:
        """Flip 4 consecutive bytes"""
        if len(data) < 4:
            return data
        mutated = bytearray(data)
        idx = random.randint(0, len(mutated) - 4)
        for i in range(4):
            mutated[idx + i] ^= 0xFF
        return mutated

    def _mutate_arith_add(self, data: bytearray) -> bytearray:
        """Add a small value (1-35) to a random byte/word/dword"""
        if len(data) < 4:
            return data
        mutated = bytearray(data)
        idx = random.randint(0, len(mutated) - 4)
        delta = random.randint(1, 35)

        # Randomly choose size
        size = random.choice([1, 2, 4])
        if idx + size > len(mutated):
            size = 1

        if size == 1:
            mutated[idx] = (mutated[idx] + delta) & 0xFF
        elif size == 2:
            val = struct.unpack("<H", mutated[idx:idx+2])[0]
            val = (val + delta) & 0xFFFF
            struct.pack_into("<H", mutated, idx, val)
        elif size == 4:
            val = struct.unpack("<I", mutated[idx:idx+4])[0]
            val = (val + delta) & 0xFFFFFFFF
            struct.pack_into("<I", mutated, idx, val)

        return mutated

    def _mutate_arith_sub(self, data: bytearray) -> bytearray:
        """Subtract a small value (1-35) from a random byte/word/dword"""
        if len(data) < 4:
            return data
        mutated = bytearray(data)
        idx = random.randint(0, len(mutated) - 4)
        delta = random.randint(1, 35)

        size = random.choice([1, 2, 4])
        if idx + size > len(mutated):
            size = 1

        if size == 1:
            mutated[idx] = (mutated[idx] - delta) & 0xFF
        elif size == 2:
            val = struct.unpack("<H", mutated[idx:idx+2])[0]
            val = (val - delta) & 0xFFFF
            struct.pack_into("<H", mutated, idx, val)
        elif size == 4:
            val = struct.unpack("<I", mutated[idx:idx+4])[0]
            val = (val - delta) & 0xFFFFFFFF
            struct.pack_into("<I", mutated, idx, val)

        return mutated

    def _mutate_interesting_8(self, data: bytearray) -> bytearray:
        """Replace a byte with an interesting 8-bit value"""
        if not data:
            return data
        interesting = [0, 1, 16, 32, 64, 100, 127, 128, 255]
        mutated = bytearray(data)
        idx = random.randint(0, len(mutated) - 1)
        mutated[idx] = random.choice(interesting)
        return mutated

    def _mutate_interesting_16(self, data: bytearray) -> bytearray:
        """Replace a 16-bit value with an interesting value"""
        if len(data) < 2:
            return data
        interesting = [0, 1, 128, 255, 256, 512, 1000, 1024, 4096, 32767, 32768, 65535]
        mutated = bytearray(data)
        idx = random.randint(0, len(mutated) - 2)
        val = random.choice(interesting)
        struct.pack_into("<H", mutated, idx, val)
        return mutated

    def _mutate_interesting_32(self, data: bytearray) -> bytearray:
        """Replace a 32-bit value with an interesting value"""
        if len(data) < 4:
            return data
        interesting = [
            0, 1, 0xFFFFFFFF, 0x7FFFFFFF, 0x80000000,
            0x41414141, 0xDEADBEEF, 0xCAFEBABE, 0x12345678
        ]
        # Add crash-learned magic values
        interesting.extend(self.crash_feedback.magic_values)

        mutated = bytearray(data)
        idx = random.randint(0, len(mutated) - 4)
        val = random.choice(interesting)
        struct.pack_into("<I", mutated, idx, val)
        return mutated

    def _mutate_block_delete(self, data: bytearray) -> bytearray:
        """Delete a random block of bytes"""
        if len(data) < 2:
            return data
        mutated = bytearray(data)
        block_size = random.randint(1, min(len(mutated) // 4, 256))
        start = random.randint(0, len(mutated) - block_size)
        del mutated[start:start + block_size]
        return mutated

    def _mutate_block_insert(self, data: bytearray) -> bytearray:
        """Insert a random block of bytes"""
        mutated = bytearray(data)
        block_size = random.randint(1, 256)
        idx = random.randint(0, len(mutated))

        # Insert random bytes or a crash pattern
        if self.crash_feedback.crash_patterns and random.random() < 0.3:
            # Use a pattern that caused crashes before
            pattern = random.choice(self.crash_feedback.get_hot_patterns())
            block = pattern * (block_size // len(pattern) + 1)
            block = block[:block_size]
        else:
            block = bytes([random.randint(0, 255) for _ in range(block_size)])

        mutated[idx:idx] = block
        return mutated

    def _mutate_block_swap(self, data: bytearray) -> bytearray:
        """Swap two random blocks"""
        if len(data) < 4:
            return data
        mutated = bytearray(data)
        block_size = random.randint(1, len(mutated) // 4)
        idx1 = random.randint(0, len(mutated) - block_size)
        idx2 = random.randint(0, len(mutated) - block_size)

        block1 = mutated[idx1:idx1 + block_size]
        block2 = mutated[idx2:idx2 + block_size]

        mutated[idx1:idx1 + block_size] = block2
        mutated[idx2:idx2 + block_size] = block1
        return mutated

    def _mutate_block_duplicate(self, data: bytearray) -> bytearray:
        """Duplicate a random block"""
        if not data:
            return data
        mutated = bytearray(data)
        block_size = random.randint(1, min(len(mutated), 256))
        src_idx = random.randint(0, len(mutated) - block_size)
        dst_idx = random.randint(0, len(mutated))

        block = mutated[src_idx:src_idx + block_size]
        mutated[dst_idx:dst_idx] = block
        return mutated

    def _mutate_havoc(self, data: bytearray) -> bytearray:
        """Apply multiple random mutations in sequence"""
        mutated = bytearray(data)
        num_mutations = random.randint(2, 8)

        for _ in range(num_mutations):
            # Pick a random strategy (excluding havoc and splice to avoid recursion)
            strategy = random.choice([s for s in self.strategies
                                    if s.name not in ["havoc", "splice"]])
            mutated = strategy.apply(mutated)

        return mutated

    def _mutate_splice(self, data: bytearray) -> bytearray:
        """Combine two random seeds"""
        if len(self.corpus) < 2:
            return data

        # Pick a random second seed
        other_seed = random.choice([s for s in self.corpus if s != self.corpus[self.current_seed_idx]])
        try:
            with open(other_seed, "rb") as f:
                other_data = bytearray(f.read())
        except:
            return data

        if not other_data:
            return data

        # Splice at random points
        split1 = random.randint(0, len(data))
        split2 = random.randint(0, len(other_data))

        return data[:split1] + other_data[split2:]

    def _mutate_dict_replace(self, data: bytearray) -> bytearray:
        """Replace a chunk with a dictionary token"""
        return self.dict_mutator.mutate_token_replace(data)

    def _mutate_dict_insert(self, data: bytearray) -> bytearray:
        """Insert a dictionary token at random position"""
        return self.dict_mutator.mutate_token_insert(data)

    def _mutate_dict_overwrite(self, data: bytearray) -> bytearray:
        """Overwrite with a dictionary token"""
        return self.dict_mutator.mutate_token_overwrite(data)

    # ========== Public Fuzzer Interface ==========

    def generate_testcase(self) -> str:
        """Generate a single mutated testcase"""
        # Record execution
        self.stats.record_execution()

        # Select seed
        if not self.corpus:
            # Generate dummy testcase if no seeds
            testcase_data = bytearray(b"FUZZ" * 64)
            seed_hash = "dummy"
        else:
            seed_path = self.corpus[self.current_seed_idx]
            seed_hash = hashlib.md5(seed_path.name.encode()).hexdigest()

            # Network mode: if this seed is part of a conversation, load the right packet
            if self.network_mode and self.packets_per_conversation > 1:
                testcase_data = self._generate_network_testcase(seed_path)
            else:
                # Regular file fuzzing
                with open(seed_path, "rb") as f:
                    testcase_data = bytearray(f.read())

        # Apply mutation strategy
        strategy = self._select_mutation_strategy()
        self.stats.record_strategy_use(strategy.name)
        mutated_data = strategy.apply(testcase_data)

        # Save to output directory
        testcase_hash = hashlib.md5(mutated_data).hexdigest()[:12]
        testcase_name = f"fuzz_{self.generated_count:06d}_{strategy.name}_{testcase_hash}.bin"
        testcase_path = self.output_dir / testcase_name

        with open(testcase_path, "wb") as f:
            f.write(mutated_data)

        self.generated_count += 1
        self.stats.corpus_processed = self.current_seed_idx + 1

        # Periodically save stats (every 100 testcases)
        if self.generated_count - self.last_stats_save >= 100:
            self.stats.save_to_file()
            self.last_stats_save = self.generated_count

        logger.debug(f"Generated testcase: {testcase_name} using {strategy.name}")

        return str(testcase_path)

    def _generate_network_testcase(self, conversation_dir: Path) -> bytearray:
        """
        For network fuzzing: load a multi-packet conversation and randomly mutate one packet.
        Expects conversation_dir to contain packet files like: packet_001.bin, packet_002.bin, etc.
        """
        # TODO: Implement network conversation loading
        # For now, just load the single file
        with open(conversation_dir, "rb") as f:
            return bytearray(f.read())

    def _select_mutation_strategy(self) -> MutationStrategy:
        """Select a mutation strategy based on weights (crash-guided)"""
        # Build weighted list
        strategies_weighted = []
        for strategy in self.strategies:
            # Boost weight if crash feedback suggests it
            weight = strategy.weight
            if self.crash_feedback.should_prefer_strategy(strategy.name):
                weight *= 2.0

            strategies_weighted.extend([strategy] * int(weight * 10))

        if not strategies_weighted:
            return random.choice(self.strategies)

        return random.choice(strategies_weighted)

    def next(self) -> bool:
        """Advance to next testcase, return True if more exist"""
        self.current_mutation_idx += 1

        # Use energy scheduler to determine mutations for this seed
        if self.corpus:
            seed_path = self.corpus[self.current_seed_idx]
            seed_hash = hashlib.md5(seed_path.name.encode()).hexdigest()
            mutations_for_seed = self.energy_scheduler.get_energy(seed_hash)
        else:
            mutations_for_seed = self.mutations_per_seed

        if self.current_mutation_idx >= mutations_for_seed:
            # Move to next seed
            self.current_mutation_idx = 0
            self.current_seed_idx += 1

            if self.current_seed_idx >= len(self.corpus):
                # Exhausted all seeds
                logger.info("Exhausted all corpus seeds")
                self.stats.save_to_file()  # Final save
                return False

        return True

    def record_crash(self, crash_info: Dict, testcase_path: str):
        """
        Record a crash and update mutation strategy weights.
        Call this when a crash is detected during fuzzing.
        """
        # Analyze the crash
        self.crash_feedback.analyze_crash(crash_info, testcase_path)

        # Create crash signature for deduplication
        crash_type = crash_info.get("type", "unknown")
        crash_location = crash_info.get("crash_address", "0x0")
        crash_sig = f"{crash_type}_{crash_location}"

        # Determine which strategy was used (parse from filename)
        filename = os.path.basename(testcase_path)
        strategy_name = None
        for strategy in self.strategies:
            if strategy.name in filename:
                strategy.record_success()
                strategy_name = strategy.name
                logger.info(f"Strategy '{strategy.name}' found crash! "
                          f"Effectiveness: {strategy.get_effectiveness():.2%}, "
                          f"Weight: {strategy.weight:.2f}")
                break

        # Record crash in statistics
        self.stats.record_crash(crash_type, crash_sig, strategy_name)

        # Boost energy for the seed that found this crash
        if self.corpus and self.current_seed_idx < len(self.corpus):
            seed_path = self.corpus[self.current_seed_idx]
            seed_hash = hashlib.md5(seed_path.name.encode()).hexdigest()
            self.energy_scheduler.record_crash(seed_hash)

        # Extract tokens from crashing input and add to dictionary
        if os.path.exists(testcase_path):
            try:
                with open(testcase_path, "rb") as f:
                    crash_data = f.read()

                # Extract 4 and 8-byte chunks as potential tokens
                for size in [4, 8]:
                    for i in range(0, len(crash_data) - size + 1, size):
                        chunk = crash_data[i:i+size]
                        self.dictionary.add_token(chunk)

                logger.debug(f"Extracted tokens from crash, dictionary now has {len(self.dictionary)} tokens")
            except Exception as e:
                logger.error(f"Failed to extract crash tokens: {e}")

        # Save stats after each crash (important for tracking)
        self.stats.save_to_file()

    def get_statistics(self) -> Dict:
        """Get current fuzzing statistics"""
        stats = self.stats.get_stats()

        # Add fuzzer-specific stats
        stats["fuzzer_info"] = {
            "corpus_size": len(self.corpus),
            "current_seed": self.current_seed_idx,
            "testcases_generated": self.generated_count,
            "dictionary_size": len(self.dictionary),
        }

        # Add strategy rankings
        stats["top_strategies"] = self.stats.get_strategy_rankings()[:10]

        return stats

    def print_statistics(self):
        """Print human-readable statistics summary"""
        self.stats.print_summary()
