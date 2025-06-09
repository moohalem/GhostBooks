#!/usr/bin/env python3
"""
Flask Web Interface for Calibre Library Monitor
Shows authors, titles, missing books, and provides IRC search functionality
"""

import os

from flask import Flask, render_template

# Import API blueprint
from app.routes.api import api_bp
from app.services.database import initialize_database

# Import config manager
from config.config_manager import config_manager

app = Flask(__name__, template_folder="app/templates", static_folder="app/static")
app.secret_key = "calibre_monitor_secret_key_change_in_production"

# Register API blueprint
app.register_blueprint(api_bp, url_prefix="/api")

# Database paths
DB_PATH = "data/authors_books.db"
CALIBRE_DB_PATH = "metadata.db"

# Configure Flask app
app.config["DB_PATH"] = DB_PATH


# Load persistent configuration
def load_persistent_config():
    """Load persistent configuration settings."""
    # Load saved Calibre database path if available
    saved_calibre_path = config_manager.get_calibre_db_path()
    if saved_calibre_path and os.path.exists(saved_calibre_path):
        app.config["CALIBRE_DB_PATH"] = saved_calibre_path
        print(f"Loaded persistent Calibre database path: {saved_calibre_path}")
    else:
        app.config["CALIBRE_DB_PATH"] = CALIBRE_DB_PATH
        print(f"Using default Calibre database path: {CALIBRE_DB_PATH}")


# Load configuration on startup
load_persistent_config()


@app.route("/")
def index():
    """Single page application main page."""
    return render_template("index.html")


# API Endpoints for SPA
if __name__ == "__main__":
    # Initialize database if it doesn't exist
    if not os.path.exists(DB_PATH):
        print("Database not found. Attempting to initialize from Calibre metadata...")
        result = initialize_database(DB_PATH, CALIBRE_DB_PATH)
        if not result["success"]:
            print(f"Failed to initialize database: {result['message']}")
            print(
                "Please ensure metadata.db exists or run the initialization manually."
            )
        else:
            print(result["message"])

    print("Starting Calibre Monitor Web Interface...")
    print("Access the web interface at: http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
