from abc import ABC, abstractmethod
import os
import logging

class Fuzzer(ABC):
    def __init__(self, input_dir: str, config: dict = None):
        self.input_dir = os.path.expanduser(input_dir)
        self.config = config or {}
        self.logger = logging.getLogger(f"fawkes.fuzzer.{self.__class__.__name__}")

    @abstractmethod
    def generate_testcase(self) -> str:
        """Generate a single testcase file, return its path."""
        pass

    @abstractmethod
    def next(self) -> bool:
        """Advance to the next testcase variation, return True if more exist."""
        pass
