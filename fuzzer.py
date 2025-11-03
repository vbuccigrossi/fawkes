# fawkes/fuzzers/fuzzer.py
import importlib
import logging
from typing import Type, Optional
from pathlib import Path

from fawkes.fuzzers.base import Fuzzer

logger = logging.getLogger("fawkes.fuzzer")

def load_fuzzer(fuzzer_type: str, input_dir: str, config: Optional[dict] = None) -> Fuzzer:
    """
    Dynamically load a fuzzer based on its type.

    Args:
        fuzzer_type (str): The type of fuzzer (e.g., "file" for FileFuzzer).
        input_dir (str): Directory containing input files or seeds.
        config (dict, optional): Configuration dictionary for the fuzzer.

    Returns:
        Fuzzer: An instance of the specified fuzzer class.

    Raises:
        ImportError: If the fuzzer module cannot be imported.
        AttributeError: If the fuzzer class cannot be found in the module.
    """
    try:
        # Map fuzzer_type to module and class name (e.g., "file" -> "fawkes.fuzzers.file_fuzzer.FileFuzzer")
        module_name = f"fawkes.fuzzers.{fuzzer_type}_fuzzer"
        class_name = f"{fuzzer_type.capitalize()}Fuzzer"
        
        # Import the module
        module = importlib.import_module(module_name)
        
        # Get the fuzzer class
        fuzzer_class = getattr(module, class_name)
        if not issubclass(fuzzer_class, Fuzzer):
            raise ValueError(f"{class_name} is not a subclass of Fuzzer")
        
        # Instantiate the fuzzer
        fuzzer_instance = fuzzer_class(Path(input_dir.strip()).expanduser().resolve(), config)
        logger.debug(f"Loaded fuzzer: {fuzzer_type}")
        return fuzzer_instance
    
    except (ImportError, AttributeError) as e:
        logger.error(f"Failed to load fuzzer '{fuzzer_type}': {e}")
        raise ImportError(f"Cannot load fuzzer '{fuzzer_type}': {e}")
    except Exception as e:
        logger.error(f"Unexpected error loading fuzzer '{fuzzer_type}': {e}")
        raise
