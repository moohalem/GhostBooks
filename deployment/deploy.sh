#!/bin/bash
# Production deployment script for Calibre Library Monitor

set -e

echo "🚀 Setting up Calibre Library Monitor for production..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check if database exists, if not initialize it
if [ ! -f "authors_books.db" ]; then
    echo "📊 Initializing database..."
    python scripts/db_manager.py init
fi

# Copy deployment files
echo "📄 Setting up deployment configuration..."
cp config/gunicorn.conf.py ./
cp deployment/calibre-monitor.service /tmp/ 2>/dev/null || echo "⚠️  Service file not copied (run as root to install systemd service)"

echo "✅ Setup complete!"
echo ""
echo "🔧 To start the production server, run:"
echo "   source venv/bin/activate"
echo "   python main.py"
echo ""
echo "📋 Environment variables you can set:"
echo "   GUNICORN_WORKERS=4           # Number of worker processes"
echo "   GUNICORN_BIND=0.0.0.0:5001   # Bind address and port"
echo "   GUNICORN_LOG_LEVEL=info      # Log level"
echo "   GUNICORN_TIMEOUT=30          # Worker timeout"
echo ""
echo "🌐 The application will be available at: http://localhost:5001"
