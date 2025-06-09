# Calibre Library Monitor

A production-ready Single Page Application (SPA) for monitoring your Calibre library, finding missing books, and searching IRC networks for missing titles.

## 📁 Project Structure

```
calibre_monitor/
├── app/                    # Main application package
│   ├── __init__.py        # Flask app factory
│   ├── routes/            # Route blueprints
│   │   ├── __init__.py
│   │   ├── main.py        # Main SPA route
│   │   └── api.py         # API endpoints
│   ├── services/          # Business logic services
│   │   ├── __init__.py
│   │   ├── database.py    # Database operations
│   │   ├── openlibrary.py # OpenLibrary API integration
│   │   └── irc.py         # IRC search functionality
│   ├── static/            # Static files (CSS, JS, images)
│   │   ├── css/
│   │   └── js/
│   └── templates/         # Jinja2 templates
├── config/                # Configuration files
│   ├── __init__.py
│   ├── settings.py        # App configuration
│   └── gunicorn.conf.py   # Gunicorn configuration
├── data/                  # Runtime data (gitignored)
│   └── authors_books.db   # Application database
├── deployment/            # Deployment configurations
│   ├── deploy.sh          # Automated deployment script
│   ├── Dockerfile         # Docker configuration
│   ├── docker-compose.yml # Docker Compose setup
│   ├── calibre-monitor.service # Systemd service
│   └── nginx.conf         # Nginx reverse proxy
├── docs/                  # Documentation
│   ├── README.md          # This file
│   └── DEPLOYMENT.md      # Deployment guide
├── scripts/               # Utility scripts
│   ├── __init__.py
│   ├── dev_server.py      # Development server
│   └── db_manager.py      # Database management
├── tests/                 # Test files
│   ├── __init__.py
│   └── test_structure.py  # Structure validation
├── main.py               # Production Gunicorn entry point
└── requirements.txt      # Python dependencies
```

## 🚀 Quick Start

### Development Mode

```bash
# Start development server with hot reload
python scripts/dev_server.py
# Visit: http://localhost:5000
```

### Production Mode

```bash
# Run automated deployment
./deployment/deploy.sh

# Start production server
python main.py
# Visit: http://localhost:5001
```

## 🔧 Database Management

```bash
# Initialize database from Calibre metadata
python scripts/db_manager.py init

# Show database statistics
python scripts/db_manager.py stats

# List missing books
python scripts/db_manager.py missing
```

## 📊 Features

- **Modern SPA Interface**: Single page application with smooth navigation
- **Database Integration**: Import and analyze your Calibre library
- **Auto-Discovery**: Automatically locate Calibre metadata.db in common locations
- **Settings Management**: Configure database paths through the web interface
- **Missing Book Detection**: Compare your library with OpenLibrary
- **IRC Search**: Search IRC networks for missing books
- **Production Ready**: Gunicorn WSGI server with auto-scaling workers
- **Multiple Deployment Options**: Docker, Systemd, or standalone
- **Data Management**: Organized data storage in dedicated `data/` folder

## 🌐 API Endpoints

- `GET /api/authors` - List all authors with statistics
- `GET /api/author/<name>` - Get author details and books
- `GET /api/missing_books` - Get all missing books
- `GET /api/stats` - Get database statistics
- `POST /api/search_author_irc` - Start IRC search for author
- `GET /api/search_status/<id>` - Get IRC search status
- `POST /api/initialize_database` - Initialize database
- `GET /api/database_info` - Get database information
- `GET /api/metadata/locate` - Auto-locate Calibre metadata.db file
- `POST /api/metadata/verify` - Verify a metadata.db path
- `GET /api/metadata/info` - Get current metadata database info

## 🐳 Deployment Options

### 1. Docker
```bash
docker-compose up -d
```

### 2. Systemd Service
```bash
sudo cp deployment/calibre-monitor.service /etc/systemd/system/
sudo systemctl enable calibre-monitor
sudo systemctl start calibre-monitor
```

### 3. Nginx Reverse Proxy
```bash
sudo cp deployment/nginx.conf /etc/nginx/sites-available/calibre-monitor
sudo ln -s /etc/nginx/sites-available/calibre-monitor /etc/nginx/sites-enabled/
sudo systemctl reload nginx
```

## ⚙️ Configuration

### Environment Variables

Set environment variables to customize the application:

```bash
# Database paths
export DB_PATH="data/authors_books.db"      # Application database (auto-created)
export CALIBRE_DB_PATH="metadata.db"        # Calibre metadata database (auto-located if missing)

# Gunicorn settings
export GUNICORN_WORKERS=4
export GUNICORN_BIND="0.0.0.0:5001"
export GUNICORN_LOG_LEVEL="info"

# IRC settings
export IRC_SERVER="irc.irchighway.net"
export IRC_CHANNEL="#ebooks"
```

### Auto-Configuration

The application includes intelligent auto-configuration:

- **Database Auto-Location**: If `metadata.db` is not found, the system automatically searches common Calibre library locations
- **Settings Interface**: Use the Settings page in the web interface to locate and verify Calibre databases
- **Data Organization**: Runtime data is stored in the `data/` directory for better organization

## 📋 Requirements

- Python 3.8+
- Calibre library with metadata.db
- Internet connection for OpenLibrary API
- Optional: IRC access for book searching

## 🔧 Development

### Project Setup
```bash
# Clone and setup
git clone <repository>
cd calibre_monitor

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Initialize database
python scripts/db_manager.py init
```

### Testing Structure
```bash
python tests/test_structure.py
```

### Adding New Features

1. **New API Endpoint**: Add to `app/routes/api.py`
2. **New Service**: Create in `app/services/`
3. **New Configuration**: Add to `config/settings.py`
4. **New Script**: Add to `scripts/`

## 📚 Architecture

- **Flask Application Factory**: Modular app creation with blueprints
- **Service Layer**: Separated business logic for database, API, and IRC operations
- **Configuration Management**: Environment-based configuration system
- **Production Ready**: Gunicorn WSGI server with auto-scaling
- **Modern Frontend**: Single Page Application with responsive design

## 🤝 Contributing

1. Follow the existing project structure
2. Add tests for new features
3. Update documentation
4. Use proper error handling
5. Follow Python PEP 8 style guidelines

## 📄 License

This project is licensed under the MIT License.

## 🐛 Troubleshooting

### Common Issues

1. **Database not found**: Run `python scripts/db_manager.py init`
2. **Import errors**: Ensure all `__init__.py` files exist
3. **Port conflicts**: Change `GUNICORN_BIND` environment variable
4. **IRC timeout**: Check network connectivity and IRC server status

### Getting Help

- Check logs in the console output
- Review the API endpoints in your browser's developer tools
- Ensure Calibre metadata.db is in the correct location
- Verify all dependencies are installed

---

🚀 **Ready to monitor your Calibre library like a pro!**
