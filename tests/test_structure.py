#!/usr/bin/env python3
"""
Simple test to verify the reorganized project structure
"""

import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_imports():
    """Test that all modules can be imported correctly."""
    try:
        # Test configuration
        from config import get_config

        config = get_config("development")
        print("✅ Configuration import successful")

        # Test app factory
        from app import create_app

        app = create_app(config)
        print("✅ Flask app factory successful")

        # Test services
        from app.services.database import initialize_database
        from app.services.irc import connect_to_irc
        from app.services.openlibrary import get_author_key

        print("✅ Services import successful")

        # Test routes
        from app.routes import api_bp, main_bp

        print("✅ Routes import successful")

        print("\n🎉 All imports successful! Project structure is working correctly.")
        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    test_imports()
