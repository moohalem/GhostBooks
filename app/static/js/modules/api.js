/**
 * API functions for the Calibre Monitor application
 */

import { showToast } from './utils.js';

/**
 * Make an API request with proper error handling
 * @param {string} url - API endpoint URL
 * @param {Object} options - Fetch options
 * @returns {Promise<Object>} API response data
 */
export async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API request failed:', error);
        showToast(`Request failed: ${error.message}`, 'danger');
        throw error;
    }
}

/**
 * Load dashboard statistics
 * @returns {Promise<Object>} Dashboard stats
 */
export async function loadStats() {
    return await apiRequest('/api/stats');
}

/**
 * Load recently processed authors
 * @returns {Promise<Array>} Recently processed authors
 */
export async function loadRecentlyProcessedAuthors() {
    return await apiRequest('/api/recently_processed_authors');
}

/**
 * Load authors with pagination and search
 * @param {number} page - Page number
 * @param {string} search - Search term
 * @param {number} perPage - Items per page
 * @returns {Promise<Object>} Authors data with pagination
 */
export async function loadAuthors(page = 1, search = '', perPage = 50) {
    const params = new URLSearchParams({ 
        page: page, 
        per_page: perPage
    });
    if (search) {
        params.append('search', search);
    }
    
    return await apiRequest(`/api/authors?${params}`);
}

/**
 * Load missing books data
 * @returns {Promise<Object>} Missing books data
 */
export async function loadMissingBooks() {
    return await apiRequest('/api/missing_books');
}

/**
 * Load missing books statistics
 * @returns {Promise<Object>} Missing books stats
 */
export async function loadMissingBooksStats() {
    return await apiRequest('/api/missing_books/stats');
}

/**
 * Load author detail data
 * @param {string} authorName - Author name
 * @returns {Promise<Object>} Author detail data
 */
export async function loadAuthorDetail(authorName) {
    return await apiRequest(`/api/author/${encodeURIComponent(authorName)}`);
}

/**
 * Process a specific author
 * @param {string} authorName - Author name to process
 * @returns {Promise<Object>} Processing result
 */
export async function processAuthor(authorName) {
    return await apiRequest('/api/process_specific_author', {
        method: 'POST',
        body: JSON.stringify({ author: authorName })
    });
}

/**
 * Start IRC search for an author
 * @param {string} authorName - Author name to search
 * @returns {Promise<Object>} Search result
 */
export async function startIRCSearch(authorName) {
    return await apiRequest('/api/search_author_irc', {
        method: 'POST',
        body: JSON.stringify({ author: authorName })
    });
}

/**
 * Get IRC search status
 * @param {string} authorName - Author name
 * @returns {Promise<Object>} Search status
 */
export async function getIRCSearchStatus(authorName) {
    return await apiRequest(`/api/search_status/${encodeURIComponent(authorName)}`);
}

/**
 * Cancel population process
 * @returns {Promise<Object>} Cancellation result
 */
export async function cancelPopulation() {
    return await apiRequest('/api/missing_books/populate/cancel', {
        method: 'POST'
    });
}

/**
 * Clear missing books database
 * @returns {Promise<Object>} Clear result
 */
export async function clearMissingBooksDatabase() {
    return await apiRequest('/api/missing_books/clear', {
        method: 'POST'
    });
}

/**
 * Ignore a book (removes it from missing books and adds to ignored list)
 * @param {string} author - Author name
 * @param {string} title - Book title
 * @returns {Promise<Object>} Ignore result
 */
export async function ignoreBook(author, title) {
    return await apiRequest('/api/book/ignore', {
        method: 'POST',
        body: JSON.stringify({ author, title })
    });
}

/**
 * Unignore a book (removes it from ignored list)
 * @param {string} author - Author name
 * @param {string} title - Book title
 * @returns {Promise<Object>} Unignore result
 */
export async function unignoreBook(author, title) {
    return await apiRequest('/api/book/unignore', {
        method: 'POST',
        body: JSON.stringify({ author, title })
    });
}

/**
 * Check if a book is ignored
 * @param {string} author - Author name
 * @param {string} title - Book title
 * @returns {Promise<Object>} Ignore status
 */
export async function getBookIgnoreStatus(author, title) {
    const params = new URLSearchParams({ author, title });
    return await apiRequest(`/api/book/ignore_status?${params}`);
}

/**
 * Get all ignored books
 * @param {string|null} author - Optional author filter
 * @returns {Promise<Array>} Ignored books list
 */
export async function getIgnoredBooks(author = null) {
    const params = new URLSearchParams();
    if (author) {
        params.append('author', author);
    }
    return await apiRequest(`/api/ignored_books?${params}`);
}

/**
 * Get ignored books statistics
 * @returns {Promise<Object>} Ignored books stats
 */
export async function getIgnoredBooksStats() {
    return await apiRequest('/api/ignored_books/stats');
}

/**
 * Search authors for autocomplete
 * @param {string} query - Search query
 * @returns {Promise<Array>} Matching authors
 */
export async function searchAuthors(query) {
    return await apiRequest(`/api/search_authors?q=${encodeURIComponent(query)}`);
}

/**
 * Search authors with autocomplete suggestions
 */
export async function searchAuthorsAutocomplete(query, limit = 10) {
    const params = new URLSearchParams({ 
        q: query || '', 
        limit: limit.toString() 
    });
    return await apiRequest(`/api/search_authors/autocomplete?${params}`);
}

/**
 * Load database information
 * @returns {Promise<Object>} Database info
 */
export async function loadDatabaseInfo() {
    return await apiRequest('/api/database_info');
}

/**
 * Load metadata database information
 * @returns {Promise<Object>} Metadata database info
 */
export async function loadMetadataInfo() {
    return await apiRequest('/api/metadata/info');
}

/**
 * Refresh OLID cache statistics
 * @returns {Promise<Object>} OLID cache stats
 */
export async function refreshOlidCacheStats() {
    return await apiRequest('/api/cache/olid/status');
}

/**
 * Clear OLID cache
 * @returns {Promise<Object>} Clear result
 */
export async function clearOlidCache() {
    return await apiRequest('/api/clear-olid-cache', { method: 'POST' });
}

/**
 * Clear the entire database
 */
export async function clearDatabase() {
    return await apiRequest('/api/clear-database', { method: 'POST' });
}

/**
 * Locate metadata database
 */
export async function locateMetadataDb() {
    return await apiRequest('/api/locate-metadata-db', { method: 'POST' });
}

/**
 * Verify metadata path
 */
export async function verifyMetadataPath() {
    return await apiRequest('/api/verify-metadata-path', { method: 'GET' });
}

/**
 * Initialize database
 */
export async function initializeDatabase() {
    return await apiRequest('/api/initialize-database', { method: 'POST' });
}
