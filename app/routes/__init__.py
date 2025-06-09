#!/usr/bin/env python3
"""
API routes initialization for Calibre Library Monitor
"""

from .api import api_bp
from .main import main_bp

__all__ = ["main_bp", "api_bp"]
