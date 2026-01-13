"""
Fawkes Centralized Paths Configuration.

This module provides standard locations for all Fawkes files and directories.
All components (TUI, Web API, CLI) should import paths from here to ensure consistency.

Default base directory: ~/.fawkes/
All paths are resolved relative to the base directory unless overridden by config.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional


# Environment variable to override base directory
FAWKES_HOME_ENV = "FAWKES_HOME"


def get_base_dir() -> Path:
    """
    Get the Fawkes base directory.

    Priority:
    1. FAWKES_HOME environment variable
    2. ~/.fawkes/ (default)
    """
    env_home = os.environ.get(FAWKES_HOME_ENV)
    if env_home:
        return Path(env_home).expanduser().resolve()
    return Path.home() / ".fawkes"


def get_paths_config_file() -> Path:
    """Get the path to the paths configuration file."""
    return get_base_dir() / "paths.json"


def load_paths_config() -> Dict[str, str]:
    """Load custom path overrides from paths.json if it exists."""
    config_file = get_paths_config_file()
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_paths_config(config: Dict[str, str]) -> None:
    """Save path configuration to paths.json."""
    config_file = get_paths_config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)


class FawkesPaths:
    """
    Centralized path management for Fawkes.

    All paths are lazily created when accessed (directories are auto-created).
    Custom paths can be set via paths.json configuration file.

    Standard directory structure:
    ~/.fawkes/
    ├── config.json          # Main configuration
    ├── paths.json           # Custom path overrides
    ├── registry.json        # VM registry
    ├── fawkes.db           # Main database
    ├── controller.db       # Controller database
    ├── isos/               # ISO files for VM installation
    ├── images/             # QCOW2 disk images
    ├── snapshots/          # Exported snapshots (backup)
    ├── corpus/             # Fuzzing corpus files
    ├── crashes/            # Crash files and analysis
    ├── jobs/               # Job definitions and state
    ├── logs/               # Log files
    ├── screenshots/        # VM screenshots
    ├── shared/             # Shared folder for VMs
    ├── firmware/           # UEFI/BIOS firmware files
    └── tmp/                # Temporary files
    """

    _instance: Optional['FawkesPaths'] = None
    _config: Dict[str, str] = {}

    def __new__(cls):
        """Singleton pattern - only one instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = load_paths_config()
        return cls._instance

    def _get_path(self, key: str, default_subdir: str, create: bool = True) -> Path:
        """Get a path from config or use default, optionally creating it."""
        if key in self._config:
            path = Path(self._config[key]).expanduser().resolve()
        else:
            path = get_base_dir() / default_subdir

        if create and not path.exists():
            path.mkdir(parents=True, exist_ok=True)

        return path

    def _get_file_path(self, key: str, default_subpath: str) -> Path:
        """Get a file path from config or use default."""
        if key in self._config:
            return Path(self._config[key]).expanduser().resolve()
        return get_base_dir() / default_subpath

    # === Base Directory ===

    @property
    def base_dir(self) -> Path:
        """Base Fawkes directory (~/.fawkes by default)."""
        path = get_base_dir()
        path.mkdir(parents=True, exist_ok=True)
        return path

    # === Configuration Files ===

    @property
    def config_file(self) -> Path:
        """Main configuration file."""
        return self._get_file_path("config_file", "config.json")

    @property
    def paths_config_file(self) -> Path:
        """Paths configuration file."""
        return get_paths_config_file()

    @property
    def registry_file(self) -> Path:
        """VM registry file."""
        return self._get_file_path("registry_file", "registry.json")

    # === Database Files ===

    @property
    def database_file(self) -> Path:
        """Main SQLite database."""
        return self._get_file_path("database_file", "fawkes.db")

    @property
    def controller_database_file(self) -> Path:
        """Controller SQLite database."""
        return self._get_file_path("controller_database_file", "controller.db")

    # === VM Files ===

    @property
    def iso_dir(self) -> Path:
        """Directory for ISO files."""
        return self._get_path("iso_dir", "isos")

    @property
    def images_dir(self) -> Path:
        """Directory for QCOW2 disk images."""
        return self._get_path("images_dir", "images")

    @property
    def snapshots_dir(self) -> Path:
        """Directory for exported/backup snapshots."""
        return self._get_path("snapshots_dir", "snapshots")

    @property
    def firmware_dir(self) -> Path:
        """Directory for UEFI/BIOS firmware files."""
        return self._get_path("firmware_dir", "firmware")

    # === Fuzzing Directories ===

    @property
    def corpus_dir(self) -> Path:
        """Directory for fuzzing corpus files."""
        return self._get_path("corpus_dir", "corpus")

    @property
    def crashes_dir(self) -> Path:
        """Directory for crash files and analysis."""
        return self._get_path("crashes_dir", "crashes")

    @property
    def jobs_dir(self) -> Path:
        """Directory for job definitions and state."""
        return self._get_path("jobs_dir", "jobs")

    # === Working Directories ===

    @property
    def logs_dir(self) -> Path:
        """Directory for log files."""
        return self._get_path("logs_dir", "logs")

    @property
    def screenshots_dir(self) -> Path:
        """Directory for VM screenshots."""
        return self._get_path("screenshots_dir", "screenshots")

    @property
    def shared_dir(self) -> Path:
        """Shared folder for VM file sharing."""
        return self._get_path("shared_dir", "shared")

    @property
    def tmp_dir(self) -> Path:
        """Temporary files directory."""
        return self._get_path("tmp_dir", "tmp")

    @property
    def vm_configs_dir(self) -> Path:
        """Directory for saved VM configuration files."""
        return self._get_path("vm_configs_dir", "vm_configs")

    # === Additional Search Paths ===

    @property
    def iso_search_paths(self) -> list:
        """Additional paths to search for ISO files."""
        if "iso_search_paths" in self._config:
            return [Path(p).expanduser().resolve() for p in self._config["iso_search_paths"]]
        # Default common ISO locations
        return [
            Path.home() / "Downloads",
            Path("/var/lib/libvirt/images"),
        ]

    @property
    def images_search_paths(self) -> list:
        """Additional paths to search for disk images."""
        if "images_search_paths" in self._config:
            return [Path(p).expanduser().resolve() for p in self._config["images_search_paths"]]
        # Default common image locations
        return [
            Path.home() / "VMs",
            Path("/var/lib/libvirt/images"),
        ]

    # === Helper Methods ===

    def set_path(self, key: str, path: str) -> None:
        """Set a custom path override."""
        self._config[key] = path
        save_paths_config(self._config)

    def reset_path(self, key: str) -> None:
        """Reset a path to its default."""
        self._config.pop(key, None)
        save_paths_config(self._config)

    def reset_all_paths(self) -> None:
        """Reset all paths to defaults."""
        self._config = {}
        save_paths_config(self._config)

    def get_all_paths(self) -> Dict[str, str]:
        """Get all paths as a dictionary."""
        return {
            # Base
            "base_dir": str(self.base_dir),

            # Config files
            "config_file": str(self.config_file),
            "paths_config_file": str(self.paths_config_file),
            "registry_file": str(self.registry_file),

            # Databases
            "database_file": str(self.database_file),
            "controller_database_file": str(self.controller_database_file),

            # VM files
            "iso_dir": str(self.iso_dir),
            "images_dir": str(self.images_dir),
            "snapshots_dir": str(self.snapshots_dir),
            "firmware_dir": str(self.firmware_dir),

            # Fuzzing
            "corpus_dir": str(self.corpus_dir),
            "crashes_dir": str(self.crashes_dir),
            "jobs_dir": str(self.jobs_dir),

            # Working
            "logs_dir": str(self.logs_dir),
            "screenshots_dir": str(self.screenshots_dir),
            "shared_dir": str(self.shared_dir),
            "tmp_dir": str(self.tmp_dir),
            "vm_configs_dir": str(self.vm_configs_dir),

            # Search paths
            "iso_search_paths": [str(p) for p in self.iso_search_paths],
            "images_search_paths": [str(p) for p in self.images_search_paths],
        }

    def ensure_all_directories(self) -> None:
        """Create all standard directories if they don't exist."""
        # Access each property to trigger directory creation
        _ = self.base_dir
        _ = self.iso_dir
        _ = self.images_dir
        _ = self.snapshots_dir
        _ = self.firmware_dir
        _ = self.corpus_dir
        _ = self.crashes_dir
        _ = self.jobs_dir
        _ = self.logs_dir
        _ = self.screenshots_dir
        _ = self.shared_dir
        _ = self.tmp_dir
        _ = self.vm_configs_dir


# Global singleton instance
paths = FawkesPaths()


# Convenience functions for backward compatibility and quick access
def get_iso_dir() -> Path:
    """Get ISO directory."""
    return paths.iso_dir


def get_images_dir() -> Path:
    """Get disk images directory."""
    return paths.images_dir


def get_corpus_dir() -> Path:
    """Get corpus directory."""
    return paths.corpus_dir


def get_crashes_dir() -> Path:
    """Get crashes directory."""
    return paths.crashes_dir


def get_jobs_dir() -> Path:
    """Get jobs directory."""
    return paths.jobs_dir


def get_shared_dir() -> Path:
    """Get shared directory."""
    return paths.shared_dir


def get_screenshots_dir() -> Path:
    """Get screenshots directory."""
    return paths.screenshots_dir


def get_logs_dir() -> Path:
    """Get logs directory."""
    return paths.logs_dir


def get_config_file() -> Path:
    """Get config file path."""
    return paths.config_file


def get_database_file() -> Path:
    """Get database file path."""
    return paths.database_file


# Initialize directories on import if running as main module
if __name__ == "__main__":
    # Print all paths when run directly
    import pprint
    print("Fawkes Paths Configuration")
    print("=" * 50)
    pprint.pprint(paths.get_all_paths())

    print("\nEnsuring all directories exist...")
    paths.ensure_all_directories()
    print("Done!")
