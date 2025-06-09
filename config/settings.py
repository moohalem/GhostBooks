#!/usr/bin/env python3
"""
Configuration settings for Calibre Library Monitor
"""

import os
from typing import Any, Dict


class Config:
    """Base configuration class."""

    # Database settings
    DB_PATH = os.environ.get("DB_PATH", "data/authors_books.db")
    CALIBRE_DB_PATH = os.environ.get("CALIBRE_DB_PATH", "metadata.db")

    # Flask settings
    SECRET_KEY = os.environ.get(
        "SECRET_KEY", "calibre_monitor_secret_key_change_in_production"
    )
    DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

    # IRC settings
    IRC_SERVER = os.environ.get("IRC_SERVER", "irc.irchighway.net")
    IRC_PORT = int(os.environ.get("IRC_PORT", "6667"))
    IRC_CHANNEL = os.environ.get("IRC_CHANNEL", "#ebooks")
    IRC_NICKNAME = os.environ.get("IRC_NICKNAME", "WebDarkHorse")

    # API rate limiting
    OPENLIBRARY_DELAY = float(os.environ.get("OPENLIBRARY_DELAY", "0.5"))
    IRC_TIMEOUT = int(os.environ.get("IRC_TIMEOUT", "60"))

    # Download settings
    DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "downloads")


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    DB_PATH = ":memory:"  # Use in-memory database for tests


def get_config(config_name: str | None = None) -> Dict[str, Any]:
    """Get configuration based on environment."""
    config_name = config_name or os.environ.get("FLASK_ENV", "development")

    configs = {
        "development": DevelopmentConfig,
        "production": ProductionConfig,
        "testing": TestingConfig,
    }

    config_class = configs.get(config_name, DevelopmentConfig)

    # Convert class attributes to dictionary
    config_dict = {}
    for attr in dir(config_class):
        if not attr.startswith("_"):
            config_dict[attr] = getattr(config_class, attr)

    return config_dict
