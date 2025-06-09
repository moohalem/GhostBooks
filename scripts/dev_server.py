#!/usr/bin/env python3
"""
Development server script for Calibre Library Monitor
Runs the Flask app in development mode with hot reload
"""

import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from config import get_config


def main():
    """Run the development server."""
    print("🚀 Starting Calibre Library Monitor in Development Mode...")

    # Get development configuration
    config = get_config("development")
    app = create_app(config)

    # Run with Flask's built-in development server
    print("🌐 Running Flask development server with hot reload...")
    print("📱 Visit: http://localhost:5000")
    print("🛑 Press Ctrl+C to stop\n")

    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)


if __name__ == "__main__":
    main()
