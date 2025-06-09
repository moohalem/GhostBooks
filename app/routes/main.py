#!/usr/bin/env python3
"""
Main routes for Calibre Library Monitor
Handles the main SPA route
"""

from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Main SPA route."""
    return render_template("index.html")
