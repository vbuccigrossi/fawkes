"""
Fawkes Dictionary Manager

Manages fuzzing dictionaries (tokens, keywords, magic values) for format-aware fuzzing.
Automatically extracts tokens from crashes and corpus.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import List, Set, Dict
from collections import Counter


logger = logging.getLogger("fawkes.dictionary")


class Dictionary:
    """
    Fuzzing dictionary containing tokens, keywords, and magic values.

    Features:
    - Load from file
    - Auto-extract from corpus
    - Learn from crashes
    - Token replacement mutations
    """

    def __init__(self, dict_file: str = None):
        self.tokens: Set[bytes] = set()
        self.token_sizes: Dict[int, List[bytes]] = {}  # size -> [tokens]

        if dict_file and os.path.exists(dict_file):
            self.load_from_file(dict_file)
        else:
            # Initialize with common tokens
            self._add_default_tokens()

    def _add_default_tokens(self):
        """Add common protocol/format tokens"""
        # HTTP tokens
        http_tokens = [
            b"GET ", b"POST ", b"PUT ", b"DELETE ", b"HEAD ", b"OPTIONS ",
            b"HTTP/1.0", b"HTTP/1.1", b"HTTP/2.0",
            b"Content-Length: ", b"Content-Type: ", b"Host: ",
            b"User-Agent: ", b"Accept: ", b"Cookie: ",
            b"text/html", b"application/json", b"application/xml",
            b"\r\n\r\n",
        ]

        # Common file format tokens
        format_tokens = [
            b"%PDF-", b"<?xml", b"<html", b"<body>",
            b"<!DOCTYPE", b"PNG\r\n", b"JFIF", b"GIF89a",
        ]

        # Common magic values
        magic_tokens = [
            b"\x00\x00\x00\x00",  # NULL
            b"\xFF\xFF\xFF\xFF",  # -1
            b"\x41\x41\x41\x41",  # AAAA
            b"\x42\x42\x42\x42",  # BBBB
            b"\xDE\xAD\xBE\xEF",  # DEADBEEF
            b"\xCA\xFE\xBA\xBE",  # CAFEBABE
        ]

        for token in http_tokens + format_tokens + magic_tokens:
            self.add_token(token)

    def add_token(self, token: bytes):
        """Add a token to the dictionary"""
        if not token or len(token) > 1024:  # Skip empty or huge tokens
            return

        self.tokens.add(token)

        # Index by size for efficient lookups
        size = len(token)
        if size not in self.token_sizes:
            self.token_sizes[size] = []
        if token not in self.token_sizes[size]:
            self.token_sizes[size].append(token)

    def add_tokens(self, tokens: List[bytes]):
        """Add multiple tokens"""
        for token in tokens:
            self.add_token(token)

    def get_tokens_by_size(self, size: int, tolerance: int = 2) -> List[bytes]:
        """
        Get tokens of approximately the given size.

        Args:
            size: Target size
            tolerance: Allow tokens within +/- tolerance bytes

        Returns:
            List of matching tokens
        """
        matches = []
        for s in range(max(1, size - tolerance), size + tolerance + 1):
            matches.extend(self.token_sizes.get(s, []))
        return matches

    def load_from_file(self, dict_file: str):
        """
        Load dictionary from file.

        File format (one token per line):
            GET /
            POST /api
            Content-Type: application/json
            @hex:41414141  # Hex-encoded token
        """
        logger.info(f"Loading dictionary from {dict_file}")
        count = 0

        try:
            with open(dict_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    # Handle hex-encoded tokens
                    if line.startswith("@hex:"):
                        hex_str = line[5:]
                        try:
                            token = bytes.fromhex(hex_str)
                            self.add_token(token)
                            count += 1
                        except ValueError:
                            logger.warning(f"Invalid hex token: {line}")
                    else:
                        # ASCII token
                        token = line.encode("utf-8")
                        self.add_token(token)
                        count += 1

            logger.info(f"Loaded {count} tokens from dictionary")
        except Exception as e:
            logger.error(f"Failed to load dictionary: {e}")

    def save_to_file(self, dict_file: str):
        """Save dictionary to file"""
        logger.info(f"Saving dictionary to {dict_file}")

        try:
            with open(dict_file, "w") as f:
                f.write("# Fawkes Fuzzing Dictionary\n")
                f.write("# Auto-generated tokens\n\n")

                for token in sorted(self.tokens, key=len):
                    # Try to write as ASCII if possible
                    try:
                        ascii_str = token.decode("ascii")
                        if all(32 <= ord(c) < 127 or c in "\r\n\t" for c in ascii_str):
                            f.write(f"{ascii_str}\n")
                        else:
                            raise UnicodeDecodeError("not-ascii", b"", 0, 0, "")
                    except (UnicodeDecodeError, AttributeError):
                        # Write as hex
                        f.write(f"@hex:{token.hex()}\n")

            logger.info(f"Saved {len(self.tokens)} tokens")
        except Exception as e:
            logger.error(f"Failed to save dictionary: {e}")

    def extract_from_corpus(self, corpus_dir: str, min_frequency: int = 2):
        """
        Auto-extract common tokens from corpus files.

        Args:
            corpus_dir: Directory containing seed files
            min_frequency: Minimum occurrences to consider a token
        """
        logger.info(f"Extracting tokens from corpus: {corpus_dir}")

        corpus_path = Path(corpus_dir).expanduser().resolve()
        ngram_counter = Counter()

        # Scan all corpus files
        for seed_file in corpus_path.rglob("*"):
            if not seed_file.is_file() or seed_file.suffix == ".json":
                continue

            try:
                with open(seed_file, "rb") as f:
                    data = f.read()

                # Extract n-grams (2, 4, 8, 16 bytes)
                for n in [2, 4, 8, 16]:
                    for i in range(len(data) - n + 1):
                        ngram = data[i:i+n]
                        # Skip all-null or all-0xFF
                        if ngram == b"\x00" * n or ngram == b"\xFF" * n:
                            continue
                        ngram_counter[ngram] += 1

            except Exception as e:
                logger.error(f"Failed to extract from {seed_file}: {e}")

        # Add frequent n-grams to dictionary
        extracted = 0
        for ngram, count in ngram_counter.items():
            if count >= min_frequency:
                self.add_token(ngram)
                extracted += 1

        logger.info(f"Extracted {extracted} tokens from corpus")

    def extract_from_crashes(self, crash_dir: str):
        """
        Extract tokens from crashing inputs.
        These are high-value tokens that triggered bugs.

        Args:
            crash_dir: Directory containing crash files
        """
        logger.info(f"Extracting tokens from crashes: {crash_dir}")

        crash_path = Path(crash_dir).expanduser().resolve()
        extracted = 0

        # Look for testcase files in crash zips
        import zipfile
        for crash_zip in crash_path.glob("crash_*.zip"):
            try:
                with zipfile.ZipFile(crash_zip, "r") as zf:
                    # Find testcase file
                    testcase_files = [f for f in zf.namelist() if "testcase" in f]
                    if not testcase_files:
                        continue

                    testcase_data = zf.read(testcase_files[0])

                    # Extract 4-byte chunks (common pointer/integer size)
                    for i in range(0, len(testcase_data) - 3, 4):
                        chunk = testcase_data[i:i+4]
                        self.add_token(chunk)
                        extracted += 1

            except Exception as e:
                logger.error(f"Failed to extract from crash {crash_zip}: {e}")

        logger.info(f"Extracted {extracted} tokens from crashes")

    def get_random_token(self) -> bytes:
        """Get a random token from the dictionary"""
        import random
        if not self.tokens:
            return b""
        return random.choice(list(self.tokens))

    def __len__(self):
        return len(self.tokens)

    def __contains__(self, token: bytes):
        return token in self.tokens


class DictionaryMutator:
    """
    Provides dictionary-based mutation strategies.
    """

    def __init__(self, dictionary: Dictionary):
        self.dict = dictionary

    def mutate_token_replace(self, data: bytearray) -> bytearray:
        """
        Replace a random chunk with a dictionary token.
        Uses size-matched tokens when possible.
        """
        if not data or len(self.dict) == 0:
            return data

        import random

        mutated = bytearray(data)

        # Pick random offset
        offset = random.randint(0, len(mutated) - 1)

        # Pick a token that fits
        max_size = len(mutated) - offset
        candidates = self.dict.get_tokens_by_size(min(max_size, 16), tolerance=4)

        if not candidates:
            # No good candidates, use any token
            token = self.dict.get_random_token()
        else:
            token = random.choice(candidates)

        # Replace bytes at offset
        end = min(offset + len(token), len(mutated))
        mutated[offset:end] = token[:end - offset]

        return mutated

    def mutate_token_insert(self, data: bytearray) -> bytearray:
        """Insert a dictionary token at a random position"""
        if len(self.dict) == 0:
            return data

        import random

        mutated = bytearray(data)
        offset = random.randint(0, len(mutated))
        token = self.dict.get_random_token()

        mutated[offset:offset] = token
        return mutated

    def mutate_token_overwrite(self, data: bytearray) -> bytearray:
        """Overwrite a chunk with a dictionary token (can extend size)"""
        if len(self.dict) == 0:
            return data

        import random

        mutated = bytearray(data)
        offset = random.randint(0, len(mutated) - 1)
        token = self.dict.get_random_token()

        # Overwrite, potentially extending past end
        for i, byte in enumerate(token):
            if offset + i < len(mutated):
                mutated[offset + i] = byte
            else:
                mutated.append(byte)

        return mutated


# Convenience functions

def create_dictionary_from_corpus(corpus_dir: str, output_file: str, min_freq: int = 2):
    """
    Create a dictionary by analyzing corpus files.

    Usage:
        create_dictionary_from_corpus("~/fuzz_inputs", "~/my_dict.txt")
    """
    dict_obj = Dictionary()
    dict_obj.extract_from_corpus(corpus_dir, min_frequency=min_freq)
    dict_obj.save_to_file(output_file)
    return dict_obj


def create_dictionary_from_crashes(crash_dir: str, output_file: str):
    """
    Create a dictionary from crash samples.

    Usage:
        create_dictionary_from_crashes("~/fawkes/crashes", "~/crash_dict.txt")
    """
    dict_obj = Dictionary()
    dict_obj.extract_from_crashes(crash_dir)
    dict_obj.save_to_file(output_file)
    return dict_obj
