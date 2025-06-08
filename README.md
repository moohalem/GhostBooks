# Calibre Library Monitor

A web interface for monitoring your Calibre library against OpenLibrary and searching IRC for missing books.

## Features

- **Dashboard**: Overview of all authors with book counts and missing book statistics
- **Author Details**: Detailed view of each author's books with missing book indicators
- **IRC Search**: Search IRC #ebooks channel for missing books by author name
- **Real-time Updates**: Live search progress and status updates
- **Responsive Design**: Works on desktop and mobile devices

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Initialize Database** (run once):
   ```bash
   python main.py
   ```
   This will create `authors_books.db` from your Calibre `metadata.db`

3. **Start Web Interface**:
   ```bash
   python app.py
   ```

4. **Access Web Interface**:
   Open your browser to: http://localhost:5000

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

- `GET /` - Dashboard
- `GET /author/<name>` - Author details
- `GET /search_missing` - Missing books overview
- `POST /api/search_author_irc` - Start IRC search
- `GET /api/search_status/<author>` - Get search status
- `GET /api/refresh_author/<author>` - Refresh author data
- `GET /api/stats` - Get dashboard statistics

## Notes

- The web interface uses the same IRC search logic as the command-line version
- IRC searches are performed in the background to avoid blocking the UI
- Search progress is tracked and displayed in real-time
- The system searches IRC by author name for efficiency
