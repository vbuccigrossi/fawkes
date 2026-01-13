"""
Fawkes Corpus Manager

Handles corpus minimization, deduplication, and seed management.
Ensures the corpus only contains unique, valuable test cases.
"""

import os
import hashlib
import shutil
import logging
from pathlib import Path
from typing import List, Set, Dict, Tuple
from collections import defaultdict


logger = logging.getLogger("fawkes.corpus_manager")


class CorpusManager:
    """
    Manages fuzzing corpus with minimization and deduplication.

    Features:
    - Remove duplicate seeds (by content hash)
    - Minimize seeds (keep smallest per unique feature)
    - Organize by file type/format
    - Track corpus statistics
    """

    def __init__(self, corpus_dir: str):
        self.corpus_dir = Path(corpus_dir).expanduser().resolve()
        self.stats = {
            "total_seeds": 0,
            "unique_seeds": 0,
            "duplicates_removed": 0,
            "total_size_bytes": 0,
        }

    def minimize(self, output_dir: str = None, keep_largest: bool = False) -> Dict:
        """
        Minimize corpus by removing duplicates and keeping only unique seeds.

        Args:
            output_dir: Where to save minimized corpus (default: corpus_dir + "_min")
            keep_largest: If True, keep largest seed per hash; otherwise keep smallest

        Returns:
            Dictionary with minimization statistics
        """
        if output_dir is None:
            output_dir = str(self.corpus_dir) + "_minimized"

        output_path = Path(output_dir).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Minimizing corpus: {self.corpus_dir} → {output_path}")

        # Track seeds by content hash
        seed_map: Dict[str, List[Path]] = defaultdict(list)

        # Scan all seeds
        all_seeds = list(self.corpus_dir.rglob("*"))
        all_seeds = [s for s in all_seeds if s.is_file() and not s.suffix == ".json"]

        self.stats["total_seeds"] = len(all_seeds)
        logger.info(f"Found {len(all_seeds)} total seeds")

        # Hash all seeds
        for seed_path in all_seeds:
            try:
                content_hash = self._hash_file(seed_path)
                seed_map[content_hash].append(seed_path)
                self.stats["total_size_bytes"] += seed_path.stat().st_size
            except Exception as e:
                logger.error(f"Failed to hash {seed_path}: {e}")

        # For each unique hash, keep only one seed
        kept_seeds = []
        for content_hash, seeds in seed_map.items():
            if len(seeds) == 1:
                # Unique seed, keep it
                kept_seeds.append(seeds[0])
            else:
                # Duplicates found, keep one based on size preference
                if keep_largest:
                    keeper = max(seeds, key=lambda s: s.stat().st_size)
                else:
                    keeper = min(seeds, key=lambda s: s.stat().st_size)

                kept_seeds.append(keeper)
                self.stats["duplicates_removed"] += len(seeds) - 1

                logger.debug(f"Hash {content_hash[:8]}: kept {keeper.name}, "
                           f"removed {len(seeds) - 1} duplicates")

        self.stats["unique_seeds"] = len(kept_seeds)

        # Copy kept seeds to output directory
        for seed_path in kept_seeds:
            # Preserve relative directory structure
            rel_path = seed_path.relative_to(self.corpus_dir)
            dest_path = output_path / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(seed_path, dest_path)
            logger.debug(f"Kept: {rel_path}")

        # Calculate size reduction
        minimized_size = sum(s.stat().st_size for s in kept_seeds)
        size_reduction = (1 - minimized_size / max(1, self.stats["total_size_bytes"])) * 100

        logger.info(f"Minimization complete:")
        logger.info(f"  Total seeds: {self.stats['total_seeds']}")
        logger.info(f"  Unique seeds: {self.stats['unique_seeds']}")
        logger.info(f"  Duplicates removed: {self.stats['duplicates_removed']}")
        logger.info(f"  Size reduction: {size_reduction:.1f}%")

        self.stats["output_dir"] = str(output_path)
        self.stats["size_reduction_percent"] = size_reduction

        return self.stats

    def deduplicate_testcases(self, testcase_dir: str, output_dir: str = None) -> Dict:
        """
        Deduplicate generated testcases by content hash.
        Useful for cleaning up fuzzer output directories.

        Args:
            testcase_dir: Directory containing testcase files
            output_dir: Where to save unique testcases

        Returns:
            Deduplication statistics
        """
        if output_dir is None:
            output_dir = str(testcase_dir) + "_unique"

        testcase_path = Path(testcase_dir).expanduser().resolve()
        output_path = Path(output_dir).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Deduplicating testcases: {testcase_path} → {output_path}")

        # Track testcases by content hash
        testcase_hashes: Dict[str, Path] = {}
        total_testcases = 0
        duplicates = 0

        # Scan all testcase files
        for testcase_file in testcase_path.glob("fuzz_*.bin"):
            total_testcases += 1

            try:
                content_hash = self._hash_file(testcase_file)

                if content_hash in testcase_hashes:
                    duplicates += 1
                    logger.debug(f"Duplicate testcase: {testcase_file.name}")
                else:
                    testcase_hashes[content_hash] = testcase_file
                    # Copy unique testcase
                    shutil.copy2(testcase_file, output_path / testcase_file.name)

            except Exception as e:
                logger.error(f"Failed to process testcase {testcase_file}: {e}")

        unique_testcases = len(testcase_hashes)

        logger.info(f"Testcase deduplication complete:")
        logger.info(f"  Total testcases: {total_testcases}")
        logger.info(f"  Unique testcases: {unique_testcases}")
        logger.info(f"  Duplicates removed: {duplicates}")

        return {
            "total_testcases": total_testcases,
            "unique_testcases": unique_testcases,
            "duplicates_removed": duplicates,
            "output_dir": str(output_path),
        }

    def deduplicate_crashes(self, crash_dir: str, output_dir: str = None) -> Dict:
        """
        Deduplicate crash samples by crash signature.
        Keeps only unique crashes based on crash type and location.

        Args:
            crash_dir: Directory containing crash .zip files
            output_dir: Where to save unique crashes

        Returns:
            Deduplication statistics
        """
        if output_dir is None:
            output_dir = str(crash_dir) + "_unique"

        crash_path = Path(crash_dir).expanduser().resolve()
        output_path = Path(output_dir).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Deduplicating crashes: {crash_path} → {output_path}")

        # Track crashes by signature
        crash_sigs: Dict[str, Path] = {}
        total_crashes = 0
        duplicates = 0

        # Scan all crash files
        for crash_file in crash_path.glob("crash_*.zip"):
            total_crashes += 1

            # Extract crash signature from filename or content
            # For now, use content hash as signature
            try:
                content_hash = self._hash_file(crash_file)

                if content_hash in crash_sigs:
                    duplicates += 1
                    logger.debug(f"Duplicate crash: {crash_file.name}")
                else:
                    crash_sigs[content_hash] = crash_file
                    # Copy unique crash
                    shutil.copy2(crash_file, output_path / crash_file.name)

            except Exception as e:
                logger.error(f"Failed to process crash {crash_file}: {e}")

        unique_crashes = len(crash_sigs)

        logger.info(f"Crash deduplication complete:")
        logger.info(f"  Total crashes: {total_crashes}")
        logger.info(f"  Unique crashes: {unique_crashes}")
        logger.info(f"  Duplicates removed: {duplicates}")

        return {
            "total_crashes": total_crashes,
            "unique_crashes": unique_crashes,
            "duplicates_removed": duplicates,
            "output_dir": str(output_path),
        }

    def organize_by_type(self, output_dir: str = None) -> Dict:
        """
        Organize corpus seeds by file type (based on magic bytes).

        Args:
            output_dir: Where to save organized corpus

        Returns:
            Organization statistics
        """
        if output_dir is None:
            output_dir = str(self.corpus_dir) + "_organized"

        output_path = Path(output_dir).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Organizing corpus by type: {self.corpus_dir} → {output_path}")

        type_counts = defaultdict(int)

        # Scan all seeds
        for seed_path in self.corpus_dir.rglob("*"):
            if not seed_path.is_file() or seed_path.suffix == ".json":
                continue

            # Detect file type
            file_type = self._detect_file_type(seed_path)
            type_counts[file_type] += 1

            # Copy to type-specific subdirectory
            type_dir = output_path / file_type
            type_dir.mkdir(parents=True, exist_ok=True)

            dest_path = type_dir / seed_path.name
            shutil.copy2(seed_path, dest_path)

        logger.info(f"Organization complete:")
        for file_type, count in sorted(type_counts.items()):
            logger.info(f"  {file_type}: {count} files")

        return {
            "type_counts": dict(type_counts),
            "output_dir": str(output_path),
        }

    def analyze(self) -> Dict:
        """
        Analyze corpus and return statistics.

        Returns:
            Detailed corpus statistics
        """
        all_seeds = list(self.corpus_dir.rglob("*"))
        all_seeds = [s for s in all_seeds if s.is_file() and not s.suffix == ".json"]

        total_size = sum(s.stat().st_size for s in all_seeds)

        # Size distribution
        sizes = [s.stat().st_size for s in all_seeds]
        sizes.sort()

        if sizes:
            min_size = sizes[0]
            max_size = sizes[-1]
            avg_size = sum(sizes) / len(sizes)
            median_size = sizes[len(sizes) // 2]
        else:
            min_size = max_size = avg_size = median_size = 0

        # Type distribution
        type_counts = defaultdict(int)
        for seed in all_seeds:
            file_type = self._detect_file_type(seed)
            type_counts[file_type] += 1

        stats = {
            "total_seeds": len(all_seeds),
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "min_size": min_size,
            "max_size": max_size,
            "avg_size": avg_size,
            "median_size": median_size,
            "type_distribution": dict(type_counts),
        }

        logger.info(f"Corpus analysis:")
        logger.info(f"  Total seeds: {stats['total_seeds']}")
        logger.info(f"  Total size: {stats['total_size_mb']:.2f} MB")
        logger.info(f"  Size range: {min_size} - {max_size} bytes")
        logger.info(f"  Average size: {avg_size:.0f} bytes")
        logger.info(f"  File types: {len(type_counts)}")

        return stats

    def _hash_file(self, path: Path) -> str:
        """Compute SHA256 hash of file content"""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _detect_file_type(self, path: Path) -> str:
        """
        Detect file type based on magic bytes.

        Returns:
            File type string (e.g., "pdf", "png", "binary", etc.)
        """
        try:
            with open(path, "rb") as f:
                magic = f.read(16)
        except:
            return "unknown"

        # Common file signatures
        if magic.startswith(b"%PDF"):
            return "pdf"
        elif magic.startswith(b"\x89PNG"):
            return "png"
        elif magic.startswith(b"GIF87a") or magic.startswith(b"GIF89a"):
            return "gif"
        elif magic.startswith(b"\xFF\xD8\xFF"):
            return "jpeg"
        elif magic.startswith(b"PK\x03\x04"):
            return "zip"
        elif magic.startswith(b"\x1f\x8b"):
            return "gzip"
        elif magic.startswith(b"BM"):
            return "bmp"
        elif magic.startswith(b"RIFF") and b"WAVE" in magic:
            return "wav"
        elif magic.startswith(b"MZ"):
            return "exe"
        elif magic.startswith(b"\x7fELF"):
            return "elf"
        elif magic[:4] in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
                           b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"):
            return "mach-o"
        elif all(32 <= b < 127 or b in (9, 10, 13) for b in magic[:100] if b != 0):
            return "text"
        else:
            return "binary"


def minimize_corpus(input_dir: str, output_dir: str = None, keep_largest: bool = False):
    """
    Convenience function to minimize a corpus.

    Usage:
        from fuzzers.corpus_manager import minimize_corpus
        minimize_corpus("~/fuzz_inputs", "~/fuzz_inputs_min")
    """
    manager = CorpusManager(input_dir)
    return manager.minimize(output_dir, keep_largest)


def analyze_corpus(input_dir: str):
    """
    Convenience function to analyze a corpus.

    Usage:
        from fuzzers.corpus_manager import analyze_corpus
        stats = analyze_corpus("~/fuzz_inputs")
    """
    manager = CorpusManager(input_dir)
    return manager.analyze()
