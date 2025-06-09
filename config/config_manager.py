#!/usr/bin/env python3
"""
Configuration manager for persistent settings
"""

import json
import os
from typing import Any, Dict, Optional


class ConfigManager:
    """Manages persistent configuration settings."""

    def __init__(self, config_file_path: str = "config/app_config.json"):
        """Initialize config manager with path to config file."""
        self.config_file_path = config_file_path
        self.config_dir = os.path.dirname(config_file_path)
        self._ensure_config_dir()

    def _ensure_config_dir(self) -> None:
        """Ensure the config directory exists."""
        if self.config_dir and not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if not os.path.exists(self.config_file_path):
            return {}

        try:
            with open(self.config_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load config file {self.config_file_path}: {e}")
            return {}

    def save_config(self, config: Dict[str, Any]) -> bool:
        """Save configuration to file."""
        try:
            with open(self.config_file_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            print(f"Error: Could not save config file {self.config_file_path}: {e}")
            return False

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a specific setting from config."""
        config = self.load_config()
        return config.get(key, default)

    def set_setting(self, key: str, value: Any) -> bool:
        """Set a specific setting in config."""
        config = self.load_config()
        config[key] = value
        return self.save_config(config)

    def get_calibre_db_path(self) -> Optional[str]:
        """Get the saved Calibre database path."""
        return self.get_setting("CALIBRE_DB_PATH")

    def set_calibre_db_path(self, path: str) -> bool:
        """Save the Calibre database path."""
        return self.set_setting("CALIBRE_DB_PATH", path)

    def has_calibre_db_path(self) -> bool:
        """Check if a Calibre database path is configured."""
        path = self.get_calibre_db_path()
        return path is not None and os.path.exists(path)


# Global config manager instance
config_manager = ConfigManager()
