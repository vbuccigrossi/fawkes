from abc import ABC, abstractmethod
import os
import logging
import shutil

class CrashAnalyzer(ABC):
    def __init__(self, crash_dir: str):
        self.crash_dir = os.path.expanduser(crash_dir)
        self.unique_dir = os.path.join(self.crash_dir, "unique")
        self.dupe_dir = os.path.join(self.crash_dir, "dupes")
        os.makedirs(self.unique_dir, exist_ok=True)
        os.makedirs(self.dupe_dir, exist_ok=True)
        self.logger = logging.getLogger(f"fawkes.analyzer.{self.__class__.__name__}")
        self.signatures = {}  # signature -> crash_zip

    def analyze_crash(self, crash_zip: str):
        """Analyze, dedup, and rank a crash."""
        signature = self.get_signature(crash_zip)
        if signature in self.signatures:
            self._handle_duplicate(crash_zip, self.signatures[signature])
        else:
            exploitability = self.rank_exploitability(crash_zip)
            self._store_unique(crash_zip, signature, exploitability)

    @abstractmethod
    def get_signature(self, crash_zip: str) -> str:
        """Generate a unique signature for deduplication."""
        pass

    @abstractmethod
    def rank_exploitability(self, crash_zip: str) -> str:
        """Rank the crash’s exploitability (e.g., Low, Medium, High)."""
        pass

    def _handle_duplicate(self, crash_zip: str, original_zip: str):
        dest = os.path.join(self.dupe_dir, os.path.basename(crash_zip))
        shutil.move(crash_zip, dest)
        self.logger.info(f"Duplicate crash moved to {dest} (matches {original_zip})")

    def _store_unique(self, crash_zip: str, signature: str, exploitability: str):
        base_name = os.path.basename(crash_zip).replace(".zip", "")
        dest_name = f"{base_name}_exploitability_{exploitability}.zip"
        dest = os.path.join(self.unique_dir, dest_name)
        shutil.move(crash_zip, dest)
        self.signatures[signature] = dest
        self.logger.info(f"Unique crash saved to {dest} (exploitability: {exploitability})")
