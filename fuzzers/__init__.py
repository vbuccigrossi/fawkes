import importlib
import logging

logger = logging.getLogger("fawkes.fuzzers")

FUZZER_MAP = {
    "file": "file_fuzzer",
    # Add more mappings here as new fuzzers are added (e.g., "network": "network_fuzzer")
}

def load_fuzzer(fuzzer_name: str, input_dir: str, config: dict = None) -> 'Fuzzer':
    module_name = FUZZER_MAP.get(fuzzer_name, fuzzer_name)
    try:
        module = importlib.import_module(f"fawkes.fuzzers.{module_name}")
        # Expect class name to be <Name>Fuzzer (e.g., FileFuzzer for file_fuzzer)
        class_name = f"{module_name.split('_')[0].capitalize()}Fuzzer"
        fuzzer_class = getattr(module, class_name)
        logger.debug(f"Loaded fuzzer: {fuzzer_name} (module: {module_name}, class: {class_name})")
        return fuzzer_class(input_dir, config)
    except (ImportError, AttributeError) as e:
        logger.error(f"Failed to load fuzzer '{fuzzer_name}': {e}")
        raise ValueError(f"Invalid fuzzer plugin: {fuzzer_name}")
