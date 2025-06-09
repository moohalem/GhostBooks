#!/usr/bin/env python3
"""
Flask App Factory for Calibre Library Monitor
Production-ready Single Page Application
"""

import logging
import os

from flask import Flask


def create_app(config=None):
    """Flask application factory."""
    app = Flask(__name__)

    # Configure the application
    app.config.update(
        {
            "SECRET_KEY": os.environ.get(
                "SECRET_KEY", "calibre_monitor_secret_key_change_in_production"
            ),
            "DEBUG": os.environ.get("DEBUG", "False").lower() == "true",
            "DB_PATH": os.environ.get("DB_PATH", "authors_books.db"),
            "CALIBRE_DB_PATH": os.environ.get("CALIBRE_DB_PATH", "metadata.db"),
        }
    )

    # Override with provided config
    if config:
        app.config.update(config)

    # Configure logging
    if not app.debug:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]",
        )

    # Register blueprints
    from app.routes import api_bp, main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    # Initialize database on first request
    with app.app_context():
        from app.services.database import initialize_database

        result = initialize_database(
            app.config["DB_PATH"], app.config["CALIBRE_DB_PATH"]
        )
        if result["success"]:
            app.logger.info(result["message"])
        else:
            app.logger.error(result["message"])

    return app
