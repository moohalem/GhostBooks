#!/usr/bin/env python3
"""
Flask Web Interface for Calibre Library Monitor
Shows authors, titles, missing books, and provides IRC search functionality
"""

import os
import sqlite3
import threading
import time
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from typing import Dict, List, Tuple
import main  # Import our main module functions

app = Flask(__name__)
app.secret_key = 'calibre_monitor_secret_key_change_in_production'

# Database path
DB_PATH = "authors_books.db"

def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_authors_with_stats():
    """Get all authors with their book counts and missing book counts."""
    conn = get_db_connection()
    query = """
    SELECT 
        author,
        COUNT(*) as total_books,
        SUM(missing) as missing_books,
        GROUP_CONCAT(CASE WHEN missing = 1 THEN title END) as missing_titles
    FROM author_book 
    GROUP BY author 
    ORDER BY author
    """
    authors = conn.execute(query).fetchall()
    conn.close()
    return authors

def get_books_by_author(author: str):
    """Get all books for a specific author."""
    conn = get_db_connection()
    query = """
    SELECT id, title, missing 
    FROM author_book 
    WHERE author = ? 
    ORDER BY title
    """
    books = conn.execute(query, (author,)).fetchall()
    conn.close()
    return books

def get_missing_books_summary():
    """Get summary of missing books."""
    conn = get_db_connection()
    
    # Total missing books
    total_missing = conn.execute("SELECT COUNT(*) FROM author_book WHERE missing = 1").fetchone()[0]
    
    # Authors with missing books
    authors_with_missing = conn.execute(
        "SELECT COUNT(DISTINCT author) FROM author_book WHERE missing = 1"
    ).fetchone()[0]
    
    # Recent missing books (top 10)
    recent_missing = conn.execute("""
        SELECT author, title 
        FROM author_book 
        WHERE missing = 1 
        ORDER BY author, title 
        LIMIT 10
    """).fetchall()
    
    conn.close()
    
    return {
        'total_missing': total_missing,
        'authors_with_missing': authors_with_missing,
        'recent_missing': recent_missing
    }

# Global variable to track IRC search status
irc_search_status = {}

@app.route('/')
def index():
    """Main dashboard page."""
    authors = get_authors_with_stats()
    summary = get_missing_books_summary()
    return render_template('index.html', authors=authors, summary=summary)

@app.route('/author/<author_name>')
def author_detail(author_name):
    """Detail page for a specific author."""
    books = get_books_by_author(author_name)
    missing_books = [book for book in books if book['missing']]
    return render_template('author_detail.html', 
                         author=author_name, 
                         books=books, 
                         missing_books=missing_books)

@app.route('/search_missing')
def search_missing():
    """Page showing all missing books with search options."""
    conn = get_db_connection()
    missing_books = conn.execute("""
        SELECT author, title, id 
        FROM author_book 
        WHERE missing = 1 
        ORDER BY author, title
    """).fetchall()
    conn.close()
    
    # Group by author
    authors_missing = {}
    for book in missing_books:
        author = book['author']
        if author not in authors_missing:
            authors_missing[author] = []
        authors_missing[author].append(book)
    
    return render_template('search_missing.html', authors_missing=authors_missing)

@app.route('/api/search_author_irc', methods=['POST'])
def search_author_irc():
    """API endpoint to search for an author on IRC."""
    data = request.get_json()
    author = data.get('author')
    
    if not author:
        return jsonify({'error': 'Author name required'}), 400
    
    # Check if search is already in progress
    if author in irc_search_status and irc_search_status[author]['status'] == 'searching':
        return jsonify({'error': 'Search already in progress for this author'}), 409
    
    # Initialize search status
    irc_search_status[author] = {
        'status': 'searching',
        'message': f'Starting IRC search for {author}...',
        'found_books': [],
        'timestamp': time.time()
    }
    
    def search_in_background():
        """Background function to perform IRC search."""
        try:
            irc_search_status[author]['message'] = f'Connecting to IRC...'
            
            # Use the existing function from main.py
            missing_books = main.process_author_for_missing_books(author, verbose=False)
            
            if missing_books:
                irc_search_status[author]['message'] = f'Found {len(missing_books)} missing books. Searching IRC...'
                
                # Connect to IRC and search
                irc = main.connect_to_irc("irc.irchighway.net", 6667, "#ebooks", "WebDarkHorse")
                found_titles = main.search_author_on_irc_and_download_zip(irc, author)
                irc.close()
                
                # Match found titles with missing books
                matched_books = []
                for author_name, title in missing_books:
                    if title.strip().lower() in found_titles:
                        matched_books.append(title)
                
                irc_search_status[author].update({
                    'status': 'completed',
                    'message': f'Search completed. Found {len(matched_books)} matching books.',
                    'found_books': matched_books,
                    'total_found_titles': len(found_titles)
                })
            else:
                irc_search_status[author].update({
                    'status': 'completed',
                    'message': 'No missing books found for this author.',
                    'found_books': []
                })
                
        except Exception as e:
            irc_search_status[author].update({
                'status': 'error',
                'message': f'Error during IRC search: {str(e)}',
                'found_books': []
            })
    
    # Start background search
    thread = threading.Thread(target=search_in_background)
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': f'IRC search started for {author}'}), 202

@app.route('/api/search_status/<author>')
def search_status(author):
    """Get the status of IRC search for an author."""
    if author not in irc_search_status:
        return jsonify({'error': 'No search found for this author'}), 404
    
    status = irc_search_status[author].copy()
    
    # Clean up old completed searches (older than 1 hour)
    if (status['status'] in ['completed', 'error'] and 
        time.time() - status['timestamp'] > 3600):
        del irc_search_status[author]
    
    return jsonify(status)

@app.route('/api/refresh_author/<author>')
def refresh_author(author):
    """Refresh OpenLibrary data for a specific author."""
    try:
        # Process author against OpenLibrary
        missing_books = main.process_author_for_missing_books(author, verbose=False)
        
        # Get updated stats
        books = get_books_by_author(author)
        missing_count = len([book for book in books if book['missing']])
        
        return jsonify({
            'success': True,
            'message': f'Refreshed data for {author}',
            'missing_count': missing_count,
            'total_books': len(books)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error refreshing author data: {str(e)}'
        }), 500

@app.route('/api/stats')
def api_stats():
    """API endpoint for dashboard statistics."""
    return jsonify(get_missing_books_summary())

if __name__ == '__main__':
    # Ensure database exists
    if not os.path.exists(DB_PATH):
        print("Database not found. Please run main.py first to initialize the database.")
        exit(1)
    
    print("Starting Calibre Monitor Web Interface...")
    print("Access the web interface at: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
