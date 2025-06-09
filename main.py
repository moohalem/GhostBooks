#!/usr/bin/env python3
"""
Gunicorn WSGI Entry Point for Calibre Library Monitor
Production deployment starter using Gunicorn
"""

import multiprocessing
import os
import sys

# Import the Flask app factory
from app import create_app
from config import get_config

# Import Gunicorn application
try:
    from gunicorn.app.wsgiapp import WSGIApplication
except ImportError:
    print("Gunicorn is not installed. Please install it with: pip install gunicorn")
    sys.exit(1)


class GunicornApp(WSGIApplication):
    """Custom Gunicorn application class."""

    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        """Load Gunicorn configuration."""
        # Make sure config is initialized
        if self.cfg is None:
            return

        config = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        """Load the Flask application."""
        return self.application


def get_gunicorn_options():
    """Get Gunicorn configuration options."""
    # Calculate optimal number of workers
    workers = int(
        os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1)
    )

    # Get configuration from environment variables with defaults
    options = {
        "bind": os.environ.get("GUNICORN_BIND", "0.0.0.0:5001"),
        "workers": workers,
        "worker_class": os.environ.get("GUNICORN_WORKER_CLASS", "sync"),
        "worker_connections": int(os.environ.get("GUNICORN_WORKER_CONNECTIONS", 1000)),
        "max_requests": int(os.environ.get("GUNICORN_MAX_REQUESTS", 1000)),
        "max_requests_jitter": int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", 100)),
        "timeout": int(os.environ.get("GUNICORN_TIMEOUT", 30)),
        "keepalive": int(os.environ.get("GUNICORN_KEEPALIVE", 2)),
        "preload_app": os.environ.get("GUNICORN_PRELOAD_APP", "true").lower() == "true",
        "access_logfile": os.environ.get("GUNICORN_ACCESS_LOG", "-"),
        "error_logfile": os.environ.get("GUNICORN_ERROR_LOG", "-"),
        "log_level": os.environ.get("GUNICORN_LOG_LEVEL", "info"),
        "capture_output": True,
        "enable_stdio_inheritance": True,
    }

    return options


def initialize_application():
    """Initialize the application and database if needed."""
    from app.services.database import (
        ensure_author_olid_table,
        initialize_database,
        migrate_database_schema,
    )

    print("🚀 Starting Calibre Library Monitor...")

    # Get configuration
    config = get_config()
    db_path = config.get("DB_PATH", "authors_books.db")
    calibre_db_path = config.get("CALIBRE_DB_PATH", "metadata.db")

    # Initialize database if it doesn't exist
    if not os.path.exists(db_path):
        print("📊 Database not found. Initializing from Calibre metadata...")
        result = initialize_database(db_path, calibre_db_path)
        if result["success"]:
            print(f"✅ {result['message']}")
        else:
            print(f"❌ Database initialization failed: {result['message']}")
            print("⚠️  The application will start but some features may not work.")
    else:
        print("✅ Database found and ready")
        # Ensure OLID table exists and migrate schema for existing databases
        try:
            ensure_author_olid_table(db_path)
            migration_result = migrate_database_schema(db_path)
            if migration_result["success"] and migration_result["migrations_applied"]:
                print(
                    f"✅ Applied database migrations: {', '.join(migration_result['migrations_applied'])}"
                )
            else:
                print("✅ Database schema is up to date")
        except Exception as e:
            print(f"⚠️  Warning: Could not ensure OLID table or migrate schema: {e}")


def main():
    """Main entry point for Gunicorn deployment."""
    # Initialize application
    initialize_application()

    # Create Flask app
    config = get_config()
    app = create_app(config)

    # Get Gunicorn options
    options = get_gunicorn_options()

    # Print startup information
    print("🔧 Gunicorn Configuration:")
    print(f"   • Bind: {options['bind']}")
    print(f"   • Workers: {options['workers']}")
    print(f"   • Worker Class: {options['worker_class']}")
    print(f"   • Timeout: {options['timeout']}s")
    print(f"   • Log Level: {options['log_level']}")

    # Create and run Gunicorn application
    try:
        gunicorn_app = GunicornApp(app, options)
        print("🌐 Starting Gunicorn server...")
        gunicorn_app.run()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down gracefully...")
    except Exception as e:
        print(f"❌ Error starting Gunicorn: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
