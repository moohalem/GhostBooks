# Calibre Library Monitor

A modern web interface for monitoring your Calibre library against OpenLibrary and searching IRC for missing books. Built as a Single Page Application (SPA) with comprehensive API backend.

## Features

- **📊 Dashboard**: Overview of all authors with book counts and missing book statistics
- **👥 Authors Management**: Detailed view of each author's books with missing book indicators
- **🔍 IRC Search**: Search IRC #ebooks channel for missing books by author name
- **⚡ Real-time Updates**: Live search progress and status updates
- **📱 Responsive Design**: Modern Bootstrap UI that works on desktop and mobile devices
- **🌐 Production Ready**: Gunicorn WSGI server support for production deployment

## Quick Start

### Development Mode

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Start Development Server**:
   ```bash
   python app.py
   ```

3. **Access Web Interface**:
   Open your browser to: http://localhost:5001

### Production Deployment

1. **Quick Setup**:
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

2. **Start Production Server**:
   ```bash
   source venv/bin/activate
   python main.py
   ```

3. **Access Application**:
   Open your browser to: http://localhost:5001

## Usage

### Dashboard
- View all authors with their book counts
- See which authors have missing books (not found in OpenLibrary)
- Search and filter authors
- Quick actions: View details, Search IRC, Refresh data

### Author Details
- View all books by a specific author
- See which books are missing from OpenLibrary
- Search IRC for missing books for that author
- Refresh author data from OpenLibrary

### Missing Books Search
- Overview of all missing books across all authors
- Bulk IRC search for multiple authors
- Individual author IRC searches

### IRC Search Process
The IRC search works by:
1. Connecting to `irc.irchighway.net` #ebooks channel
2. Sending `@find AuthorName` command (searches by author, not individual book titles)
3. Downloading the zip file containing that author's book collection
4. Parsing the zip files to extract book titles
5. Matching extracted titles against your missing books

## Key Points

- **Search by Author**: The IRC search looks for the author name, not individual book titles
- **Efficient**: One search per author covers all their books
- **Real-time**: Progress updates and results shown live in the web interface
- **Safe**: Testing mode processes one author at a time to avoid rate limits

## File Structure

```
calibre_monitor/
├── main.py              # Core library monitoring logic
├── app.py               # Flask web application
├── metadata.db          # Calibre database (input)
├── authors_books.db     # Generated database with missing flags
├── requirements.txt     # Python dependencies
├── downloads/           # IRC download cache
├── templates/           # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── author_detail.html
│   └── search_missing.html
└── static/              # CSS and JavaScript
    ├── css/style.css
    └── js/app.js
```

## API Endpoints

The application provides a comprehensive REST API:

### Core Endpoints
- `GET /` - Main SPA interface
- `GET /api/stats` - Dashboard statistics
- `GET /api/database_info` - Database information
- `POST /api/initialize_database` - Initialize database from Calibre

### Author Management
- `GET /api/authors` - List all authors with stats
- `GET /api/author/<name>` - Get specific author details
- `GET /api/search_authors?q=<query>` - Search authors by name
- `GET /api/author/<name>/compare` - Compare author with OpenLibrary

### Book Processing
- `POST /api/process_specific_author` - Process specific author
- `POST /api/process_all_authors` - Batch process multiple authors
- `GET /api/refresh_author/<name>` - Refresh author data

### Missing Books & IRC Search
- `GET /api/missing_books` - Get all missing books
- `POST /api/search_author_irc` - Search IRC for author's missing books
- `GET /api/search_status/<author>` - Get IRC search status

## Architecture

### Frontend
- **Single Page Application** built with vanilla JavaScript
- **Bootstrap 5** for responsive UI components
- **Font Awesome** icons for enhanced UX
- **Real-time updates** via API polling

### Backend
- **Flask** web framework with comprehensive API
- **SQLite** database for local data storage
- **OpenLibrary API** integration for book verification
- **IRC client** for automated book searching
- **Gunicorn WSGI** server for production deployment

### Database Schema
```sql
CREATE TABLE author_book (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author TEXT NOT NULL,
    title TEXT NOT NULL,
    missing BOOLEAN NOT NULL DEFAULT 0
);
```

## Notes

- The web interface uses the same IRC search logic as the command-line version
- IRC searches are performed in the background to avoid blocking the UI
- Search progress is tracked and displayed in real-time
- The system searches IRC by author name for efficiency

## Production Deployment Options

### 1. Using Gunicorn (Recommended)

The application includes a production-ready Gunicorn WSGI server:

```bash
# Install and run
pip install -r requirements.txt
python main.py
```

**Environment Variables:**
```bash
export GUNICORN_WORKERS=4              # Number of worker processes
export GUNICORN_BIND=0.0.0.0:5001      # Bind address and port
export GUNICORN_LOG_LEVEL=info         # Log level (debug, info, warning, error)
export GUNICORN_TIMEOUT=30             # Worker timeout in seconds
export GUNICORN_WORKER_CLASS=sync      # Worker class (sync, gevent, etc.)
```

### 2. Using Docker

```bash
# Build and run with Docker
docker build -t calibre-monitor .
docker run -p 5001:5001 -v $(pwd)/metadata.db:/app/metadata.db:ro calibre-monitor
```

### 3. Using Docker Compose

```bash
# Run with docker-compose
docker-compose up -d
```

### 4. Using Systemd (Linux)

1. **Install to system directory**:
   ```bash
   sudo cp -r . /opt/calibre-monitor
   sudo chown -R calibre:calibre /opt/calibre-monitor
   ```

2. **Install systemd service**:
   ```bash
   sudo cp calibre-monitor.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable calibre-monitor
   sudo systemctl start calibre-monitor
   ```

### 5. With Nginx Reverse Proxy

1. **Copy nginx configuration**:
   ```bash
   sudo cp nginx.conf /etc/nginx/sites-available/calibre-monitor
   sudo ln -s /etc/nginx/sites-available/calibre-monitor /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```

## Configuration

### Database Setup

The application automatically initializes the database from your Calibre `metadata.db` file:

1. **Place your Calibre database**: Copy `metadata.db` to the application directory
2. **Auto-initialization**: The app will create `authors_books.db` on first run
3. **Manual initialization**: Run the API endpoint `/api/initialize_database`

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GUNICORN_WORKERS` | `CPU cores * 2 + 1` | Number of worker processes |
| `GUNICORN_BIND` | `0.0.0.0:5001` | Server bind address |
| `GUNICORN_TIMEOUT` | `30` | Worker timeout seconds |
| `GUNICORN_LOG_LEVEL` | `info` | Logging level |
| `GUNICORN_MAX_REQUESTS` | `1000` | Max requests per worker |
