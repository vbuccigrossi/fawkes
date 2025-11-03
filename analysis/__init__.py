import importlib
import logging

logger = logging.getLogger("fawkes.analysis")

ANALYZER_MAP = {
    "i386": "i386_analyzer",
    "x86_64": "i386_analyzer",  # Placeholder—use i386 for now, update later
    "arm32": "i386_analyzer",  # Placeholder
    "arm64": "i386_analyzer",  # Placeholder
    "mips32": "i386_analyzer",  # Placeholder
    "mips64": "i386_analyzer",  # Placeholder
}

def load_analyzer(arch: str, crash_dir: str) -> 'CrashAnalyzer':
    module_name = ANALYZER_MAP.get(arch, "i386_analyzer")  # Default to i386
    try:
        module = importlib.import_module(f"fawkes.analysis.{module_name}")
        class_name = f"{module_name.split('_')[0].capitalize()}Analyzer"
        analyzer_class = getattr(module, class_name)
        logger.debug(f"Loaded analyzer for {arch}: {module_name} (class: {class_name})")
        return analyzer_class(crash_dir)
    except (ImportError, AttributeError) as e:
        logger.error(f"Failed to load analyzer for '{arch}': {e}")
        raise ValueError(f"Invalid crash analyzer for architecture: {arch}")
