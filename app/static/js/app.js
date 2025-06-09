// Global JavaScript functions for Calibre Monitor

// Utility functions
function showToast(message, type = 'info') {
    // Create toast element
    const toastHtml = `
        <div class="toast align-items-center text-white bg-${type} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    
    // Add to toast container or create one
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(toastContainer);
    }
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    
    // Initialize and show toast
    const toastElement = toastContainer.lastElementChild;
    const toast = new bootstrap.Toast(toastElement);
    toast.show();
    
    // Remove from DOM after hidden
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function escapeHtml(text) {
    if (typeof text !== 'string') return text;
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// API helper functions
async function apiRequest(url, options = {}) {
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

// Common search functionality
function initializeTableSearch(searchInputId, tableId, searchColumnIndex = 0) {
    const searchInput = document.getElementById(searchInputId);
    const table = document.getElementById(tableId);
    
    if (!searchInput || !table) return;
    
    const debouncedSearch = debounce((searchTerm) => {
        const rows = table.querySelectorAll('tbody tr');
        
        rows.forEach(row => {
            const cells = row.querySelectorAll('td');
            if (cells.length > searchColumnIndex) {
                const cellText = cells[searchColumnIndex].textContent.toLowerCase();
                row.style.display = cellText.includes(searchTerm.toLowerCase()) ? '' : 'none';
            }
        });
        
        // Update visible count
        const visibleRows = table.querySelectorAll('tbody tr[style=""]').length;
        const totalRows = rows.length;
        updateTableInfo(tableId, visibleRows, totalRows);
    }, 300);
    
    searchInput.addEventListener('input', (e) => {
        debouncedSearch(e.target.value);
    });
}

function updateTableInfo(tableId, visibleCount, totalCount) {
    const tableContainer = document.getElementById(tableId).closest('.card');
    let infoElement = tableContainer.querySelector('.table-info');
    
    if (!infoElement) {
        infoElement = document.createElement('small');
        infoElement.className = 'table-info text-muted';
        tableContainer.querySelector('.card-body').appendChild(infoElement);
    }
    
    if (visibleCount === totalCount) {
        infoElement.textContent = `Showing ${totalCount} entries`;
    } else {
        infoElement.textContent = `Showing ${visibleCount} of ${totalCount} entries`;
    }
}

// IRC Search management
class IRCSearchManager {
    constructor() {
        this.activeSearches = new Map();
    }
    
    async startSearch(author) {
        if (this.activeSearches.has(author)) {
            showToast(`Search already in progress for ${author}`, 'warning');
            return;
        }
        
        try {
            const response = await apiRequest('/api/search_author_irc', {
                method: 'POST',
                body: JSON.stringify({ author: author })
            });
            
            this.activeSearches.set(author, { status: 'searching', startTime: Date.now() });
            showToast(`IRC search started for ${author}`, 'info');
            
            return response;
        } catch (error) {
            showToast(`Failed to start search for ${author}`, 'danger');
            throw error;
        }
    }
    
    async getSearchStatus(author) {
        try {
            const status = await apiRequest(`/api/search_status/${encodeURIComponent(author)}`);
            
            if (status.status === 'completed' || status.status === 'error') {
                this.activeSearches.delete(author);
            }
            
            return status;
        } catch (error) {
            this.activeSearches.delete(author);
            throw error;
        }
    }
    
    isSearchActive(author) {
        return this.activeSearches.has(author);
    }
    
    getActiveSearches() {
        return Array.from(this.activeSearches.keys());
    }
}

// Global IRC search manager instance
const ircSearchManager = new IRCSearchManager();

// Auto-refresh functionality
class AutoRefreshManager {
    constructor() {
        this.interval = null;
        this.refreshRate = 30000; // 30 seconds
    }
    
    start() {
        if (this.interval) return;
        
        this.interval = setInterval(() => {
            this.refreshStats();
        }, this.refreshRate);
        
        console.log('Auto-refresh started');
    }
    
    stop() {
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
            console.log('Auto-refresh stopped');
        }
    }
    
    async refreshStats() {
        try {
            const stats = await apiRequest('/api/stats');
            this.updateStatsDisplay(stats);
        } catch (error) {
            console.error('Failed to refresh stats:', error);
        }
    }
    
    updateStatsDisplay(stats) {
        // Update stats cards if they exist
        const missingBooksCard = document.querySelector('[data-stat="missing-books"]');
        if (missingBooksCard) {
            missingBooksCard.textContent = stats.total_missing;
        }
        
        const authorsWithMissingCard = document.querySelector('[data-stat="authors-with-missing"]');
        if (authorsWithMissingCard) {
            authorsWithMissingCard.textContent = stats.authors_with_missing;
        }
    }
}

// Global auto-refresh manager
const autoRefreshManager = new AutoRefreshManager();

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
    
    // Start auto-refresh if on dashboard
    if (window.location.pathname === '/' || window.location.pathname === '/index') {
        autoRefreshManager.start();
    }
    
    // Clean up on page unload
    window.addEventListener('beforeunload', () => {
        autoRefreshManager.stop();
    });
});

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Ctrl/Cmd + K to focus search
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const searchInput = document.querySelector('input[type="text"]:not([disabled])');
        if (searchInput) {
            searchInput.focus();
        }
    }
    
    // Escape to close modals
    if (e.key === 'Escape') {
        const openModal = document.querySelector('.modal.show');
        if (openModal) {
            const modalInstance = bootstrap.Modal.getInstance(openModal);
            if (modalInstance) {
                modalInstance.hide();
            }
        }
    }
});

// View management functions
function hideAllViews() {
    const views = document.querySelectorAll('.view-container');
    views.forEach(view => view.style.display = 'none');
}

function showLoading(show = true) {
    const loading = document.getElementById('loading');
    if (loading) {
        loading.style.display = show ? 'block' : 'none';
    }
}

// Navigation functions
async function showDashboard() {
    hideAllViews();
    showLoading(true);
    
    try {
        // Load dashboard stats and database info
        const [stats, authors] = await Promise.all([
            apiRequest('/api/stats'),
            apiRequest('/api/authors')
        ]);
        
        // Load database info
        await loadDatabaseInfo();
        
        // Update stats cards
        updateDashboardStats(stats);
        
        // Update recent authors - handle empty case
        const recentAuthors = Array.isArray(authors) ? authors.slice(0, 10) : [];
        updateRecentAuthors(recentAuthors);
        
        document.getElementById('dashboard-view').style.display = 'block';
        
        // Update active nav
        updateActiveNav('dashboard');
        
        // Start auto-refresh for dashboard
        autoRefreshManager.start();
        
    } catch (error) {
        showToast('Failed to load dashboard data', 'danger');
        // Show empty state for recent authors on error
        updateRecentAuthors([]);
    } finally {
        showLoading(false);
    }
}

async function showAuthors() {
    hideAllViews();
    showLoading(true);
    
    try {
        await loadAuthors();
        document.getElementById('authors-view').style.display = 'block';
        
        // Initialize search for accordion (we need to implement this)
        setupAccordionSearch();
        
        // Update active nav
        updateActiveNav('authors');
        
        // Stop auto-refresh when not on dashboard
        autoRefreshManager.stop();
        
    } catch (error) {
        showToast('Failed to load authors', 'danger');
    } finally {
        showLoading(false);
    }
}

async function showMissing() {
    hideAllViews();
    showLoading(true);
    
    try {
        await loadMissingBooks();
        document.getElementById('missing-view').style.display = 'block';
        
        // Update active nav
        updateActiveNav('missing');
        
        // Stop auto-refresh when not on dashboard
        autoRefreshManager.stop();
        
    } catch (error) {
        showToast('Failed to load missing books', 'danger');
    } finally {
        showLoading(false);
    }
}

async function showAuthorDetail(authorName) {
    hideAllViews();
    showLoading(true);
    
    try {
        const authorData = await apiRequest(`/api/author/${encodeURIComponent(authorName)}`);
        
        // Update author detail view
        document.getElementById('author-name').textContent = authorData.author;
        
        // Store current author for refresh function
        window.currentAuthor = authorName;
        
        // Update books tables
        updateAuthorBooksTable(authorData.books);
        updateAuthorMissingBooksTable(authorData.missing_books);
        
        // Update stats in author detail
        updateAuthorStats(authorData);
        
        document.getElementById('author-detail-view').style.display = 'block';
        
        // Stop auto-refresh when not on dashboard
        autoRefreshManager.stop();
        
    } catch (error) {
        showToast(`Failed to load author details for ${authorName}`, 'danger');
        showAuthors(); // Fall back to authors view
    } finally {
        showLoading(false);
    }
}

// Data loading functions
async function loadAuthors() {
    const authors = await apiRequest('/api/authors');
    const accordion = document.getElementById('authors-accordion');
    
    accordion.innerHTML = authors.map((author, index) => `
        <div class="accordion-item border-0 border-bottom">
            <h2 class="accordion-header" id="heading${index}">
                <button class="accordion-button collapsed d-flex justify-content-between align-items-center" 
                        type="button" 
                        data-bs-toggle="collapse" 
                        data-bs-target="#collapse${index}" 
                        onclick="selectAuthorFromAccordion('${escapeHtml(author.author)}')"
                        style="background: none; border: none;">
                    <div class="d-flex align-items-center flex-grow-1">
                        <i class="fas fa-user me-2"></i>
                        <strong>${escapeHtml(author.author)}</strong>
                    </div>
                    <div class="d-flex align-items-center">
                        <span class="badge bg-primary me-2">${author.total_books} books</span>
                        ${author.missing_books > 0 ? 
                            `<span class="badge bg-warning me-2">${author.missing_books} missing</span>` : 
                            `<span class="badge bg-success me-2">Complete</span>`
                        }
                    </div>
                </button>
            </h2>
            <div id="collapse${index}" 
                 class="accordion-collapse collapse" 
                 data-bs-parent="#authors-accordion"
                 data-author="${escapeHtml(author.author)}">
                <div class="accordion-body p-0">
                    <div class="loading-books text-center p-3">
                        <div class="spinner-border spinner-border-sm" role="status">
                            <span class="visually-hidden">Loading books...</span>
                        </div>
                        <small class="text-muted ms-2">Loading books...</small>
                    </div>
                </div>
            </div>
        </div>
    `).join('');
    
    // Add event listeners for accordion expansion
    accordion.addEventListener('shown.bs.collapse', async function(e) {
        const authorName = e.target.getAttribute('data-author');
        await loadAuthorBooks(e.target, authorName);
    });
    
    // Update table info
    updateTableInfo('authors-table', authors.length, authors.length);
}

async function loadMissingBooks() {
    const missingBooks = await apiRequest('/api/missing_books');
    const container = document.getElementById('missing-books-container');
    
    if (Object.keys(missingBooks).length === 0) {
        container.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> No missing books found!
            </div>
        `;
        return;
    }
    
    container.innerHTML = Object.entries(missingBooks).map(([author, books]) => `
        <div class="card mb-3">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0">
                    <a href="#" onclick="showAuthorDetail('${escapeHtml(author)}')" 
                       class="text-decoration-none">
                        ${escapeHtml(author)}
                    </a>
                    <span class="badge bg-warning ms-2">${books.length} missing</span>
                </h5>
                <div>
                    <button class="btn btn-sm btn-outline-success" 
                            onclick="refreshAuthor('${escapeHtml(author)}')">
                        <i class="fas fa-sync-alt"></i> Refresh
                    </button>
                    <button class="btn btn-sm btn-outline-info" 
                            onclick="searchAuthorIRC('${escapeHtml(author)}')">
                        <i class="fas fa-search"></i> IRC Search
                    </button>
                </div>
            </div>
            <div class="card-body">
                <div class="row">
                    ${books.map(book => `
                        <div class="col-md-6 col-lg-4 mb-2">
                            <div class="border rounded p-2 h-100">
                                <small class="text-muted">${escapeHtml(book.title)}</small>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
    `).join('');
}

// Dashboard specific functions
function updateDashboardStats(stats) {
    const missingBooksEl = document.querySelector('[data-stat="missing-books"]');
    const authorsWithMissingEl = document.querySelector('[data-stat="authors-with-missing"]');
    
    if (missingBooksEl) missingBooksEl.textContent = stats.total_missing;
    if (authorsWithMissingEl) authorsWithMissingEl.textContent = stats.authors_with_missing;
}

function updateRecentAuthors(authors) {
    const recentAuthorsEl = document.getElementById('recent-authors-list');
    if (!recentAuthorsEl) return;
    
    // Check if there are no authors
    if (!authors || authors.length === 0) {
        recentAuthorsEl.innerHTML = `
            <tr>
                <td colspan="3" class="text-center text-muted py-3">
                    <i class="fas fa-info-circle"></i> No authors found in database
                </td>
            </tr>
        `;
        return;
    }
    
    recentAuthorsEl.innerHTML = authors.map(author => `
        <tr>
            <td>
                <a href="#" onclick="showAuthorDetail('${escapeHtml(author.name)}')" 
                   class="text-decoration-none">
                    ${escapeHtml(author.name)}
                </a>
            </td>
            <td>${author.total_books}</td>
            <td>
                <span class="badge bg-${author.missing_books > 0 ? 'warning' : 'success'}">
                    ${author.missing_books}
                </span>
            </td>
        </tr>
    `).join('');
}

// Author detail functions
function updateAuthorBooksTable(books) {
    const tbody = document.getElementById('all-books-list');
    if (!tbody) return;
    
    tbody.innerHTML = books.map(book => `
        <tr>
            <td>${escapeHtml(book.title)}</td>
            <td>
                <span class="badge bg-${book.missing ? 'warning' : 'success'}">
                    ${book.missing ? 'Missing' : 'Available'}
                </span>
            </td>
        </tr>
    `).join('');
}

function updateAuthorMissingBooksTable(missingBooks) {
    const tbody = document.getElementById('missing-books-list');
    if (!tbody) return;
    
    tbody.innerHTML = missingBooks.map(book => `
        <tr>
            <td>${escapeHtml(book.title)}</td>
            <td>
                <span class="badge bg-warning">Missing</span>
            </td>
        </tr>
    `).join('');
}

function updateAuthorStats(authorData) {
    // Update any author-specific stats displays
    const statsContainer = document.querySelector('#author-detail-view .stats-container');
    if (statsContainer) {
        statsContainer.innerHTML = `
            <div class="row mb-3">
                <div class="col-md-6">
                    <div class="card bg-light">
                        <div class="card-body text-center">
                            <h4>${authorData.total_books}</h4>
                            <small class="text-muted">Total Books</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card bg-light">
                        <div class="card-body text-center">
                            <h4>${authorData.missing_count}</h4>
                            <small class="text-muted">Missing Books</small>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
}

// IRC Search functions
async function searchAuthorIRC(author) {
    if (ircSearchManager.isSearchActive(author)) {
        showToast(`Search already in progress for ${author}`, 'warning');
        return;
    }
    
    try {
        await ircSearchManager.startSearch(author);
        
        // Start polling for search status
        pollSearchStatus(author);
        
    } catch (error) {
        console.error('IRC search failed:', error);
    }
}

async function pollSearchStatus(author) {
    const maxAttempts = 60; // 5 minutes max (5 second intervals)
    let attempts = 0;
    
    const poll = async () => {
        try {
            const status = await ircSearchManager.getSearchStatus(author);
            
            // Update UI with status
            updateSearchStatus(author, status);
            
            if (status.status === 'completed' || status.status === 'error') {
                showSearchResults(author, status);
                return; // Stop polling
            }
            
            // Continue polling if still searching
            if (status.status === 'searching' && attempts < maxAttempts) {
                attempts++;
                setTimeout(poll, 5000); // Poll every 5 seconds
            } else if (attempts >= maxAttempts) {
                showToast(`Search timeout for ${author}`, 'warning');
            }
            
        } catch (error) {
            console.error('Failed to get search status:', error);
            showToast(`Failed to get search status for ${author}`, 'danger');
        }
    };
    
    // Start polling
    setTimeout(poll, 2000); // First poll after 2 seconds
}

function updateSearchStatus(author, status) {
    // Update any search status indicators in the UI
    const searchButtons = document.querySelectorAll(`button[onclick*="${author}"]`);
    searchButtons.forEach(button => {
        if (button.textContent.includes('IRC Search')) {
            if (status.status === 'searching') {
                button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Searching...';
                button.disabled = true;
            } else {
                button.innerHTML = '<i class="fas fa-search"></i> IRC Search';
                button.disabled = false;
            }
        }
    });
    
    // Show status message as toast
    if (status.message) {
        const toastType = status.status === 'error' ? 'danger' : 'info';
        showToast(`${author}: ${status.message}`, toastType);
    }
}

function showSearchResults(author, status) {
    if (status.status === 'completed' && status.found_books && status.found_books.length > 0) {
        const message = `Found ${status.found_books.length} books for ${author}: ${status.found_books.slice(0, 3).join(', ')}${status.found_books.length > 3 ? '...' : ''}`;
        showToast(message, 'success');
    } else if (status.status === 'completed') {
        showToast(`No matching books found for ${author}`, 'info');
    } else if (status.status === 'error') {
        showToast(`Search failed for ${author}: ${status.message}`, 'danger');
    }
}

// Refresh functions
async function refreshStats() {
    try {
        showLoading(true);
        const stats = await apiRequest('/api/stats');
        updateDashboardStats(stats);
        showToast('Stats refreshed successfully', 'success');
    } catch (error) {
        showToast('Failed to refresh stats', 'danger');
    } finally {
        showLoading(false);
    }
}

async function refreshAuthor(author) {
    if (!author && window.currentAuthor) {
        author = window.currentAuthor;
    }
    
    if (!author) {
        showToast('No author specified for refresh', 'warning');
        return;
    }
    
    try {
        showLoading(true);
        const response = await apiRequest(`/api/refresh_author/${encodeURIComponent(author)}`);
        
        if (response.success) {
            showToast(`Refreshed data for ${author}`, 'success');
            
            // Reload current view with updated data
            if (document.getElementById('author-detail-view').style.display !== 'none') {
                showAuthorDetail(author);
            } else if (document.getElementById('authors-view').style.display !== 'none') {
                loadAuthors();
            } else if (document.getElementById('missing-view').style.display !== 'none') {
                loadMissingBooks();
            }
        } else {
            showToast(`Failed to refresh ${author}: ${response.message}`, 'danger');
        }
    } catch (error) {
        showToast(`Error refreshing ${author}`, 'danger');
    } finally {
        showLoading(false);
    }
}

// Search and filter functions
function filterAuthors() {
    const searchTerm = document.getElementById('author-search').value.toLowerCase();
    const searchResultsInfo = document.getElementById('search-results-info');
    
    // Check if we're using the accordion interface (new) or table interface (old)
    const accordion = document.getElementById('authors-accordion');
    const table = document.getElementById('authors-table-body');
    
    if (accordion) {
        // New accordion interface
        const items = accordion.querySelectorAll('.accordion-item');
        let visibleCount = 0;
        
        items.forEach(item => {
            const authorButton = item.querySelector('.accordion-button');
            const authorName = authorButton.textContent.toLowerCase();
            
            if (authorName.includes(searchTerm)) {
                item.style.display = 'block';
                visibleCount++;
            } else {
                item.style.display = 'none';
            }
        });
        
        // Update search results info
        if (searchResultsInfo) {
            if (searchTerm.trim() === '') {
                searchResultsInfo.style.display = 'none';
            } else {
                searchResultsInfo.style.display = 'block';
                if (visibleCount === 0) {
                    searchResultsInfo.innerHTML = `<span class="text-warning">No authors found matching "${escapeHtml(searchTerm)}"</span>`;
                } else {
                    searchResultsInfo.innerHTML = `Showing ${visibleCount} of ${items.length} authors`;
                }
            }
        }
        
    } else if (table) {
        // Old table interface (fallback)
        const rows = table.querySelectorAll('tr');
        let visibleCount = 0;
        
        rows.forEach(row => {
            const authorName = row.querySelector('td').textContent.toLowerCase();
            const visible = authorName.includes(searchTerm);
            row.style.display = visible ? '' : 'none';
            if (visible) visibleCount++;
        });
        
        updateTableInfo('authors-table', visibleCount, rows.length);
    }
}

function setupAccordionSearch() {
    const searchInput = document.getElementById('author-search');
    if (searchInput) {
        // The filterAuthors function now handles both accordion and table interfaces
        // so we don't need to change the event listener
        
        // Add escape key handler to clear search
        searchInput.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                e.target.value = '';
                filterAuthors();
                e.target.blur();
            }
        });
    }
}

function filterMissingBooks() {
    const searchTerm = document.getElementById('missing-search').value.toLowerCase();
    const cards = document.querySelectorAll('#missing-books-container .card');
    
    let visibleCount = 0;
    cards.forEach(card => {
        const authorName = card.querySelector('h5 a').textContent.toLowerCase();
        const bookTitles = Array.from(card.querySelectorAll('.card-body small')).map(el => 
            el.textContent.toLowerCase()
        );
        
        const authorMatch = authorName.includes(searchTerm);
        const bookMatch = bookTitles.some(title => title.includes(searchTerm));
        
        const visible = authorMatch || bookMatch;
        card.style.display = visible ? '' : 'none';
        if (visible) visibleCount++;
    });
    
    // Update info display
    const container = document.getElementById('missing-books-container');
    let infoEl = container.querySelector('.search-info');
    if (!infoEl) {
        infoEl = document.createElement('div');
        infoEl.className = 'search-info text-muted mb-3';
        container.insertBefore(infoEl, container.firstChild);
    }
    
    if (visibleCount === cards.length) {
        infoEl.textContent = `Showing ${cards.length} authors with missing books`;
    } else {
        infoEl.textContent = `Showing ${visibleCount} of ${cards.length} authors`;
    }
}

// Search functionality for accordion interface
function setupAccordionSearch() {
    const searchInput = document.getElementById('author-search');
    if (searchInput) {
        // Remove any existing event listeners
        searchInput.removeEventListener('keyup', filterAuthors);
        // Add new event listener
        searchInput.addEventListener('keyup', filterAccordionAuthors);
    }
}

function filterAccordionAuthors() {
    const searchTerm = document.getElementById('author-search').value.toLowerCase();
    const accordion = document.getElementById('authors-accordion');
    const items = accordion.querySelectorAll('.accordion-item');
    
    let visibleCount = 0;
    
    items.forEach(item => {
        const authorButton = item.querySelector('.accordion-button');
        const authorName = authorButton.textContent.toLowerCase();
        
        if (authorName.includes(searchTerm)) {
            item.style.display = 'block';
            visibleCount++;
        } else {
            item.style.display = 'none';
        }
    });
    
    // Update some visual feedback about search results
    // We could add a small counter or message here if needed
}

// Navigation helper functions
function updateActiveNav(activeView) {
    // Remove active class from all nav links
    document.querySelectorAll('.navbar-nav .nav-link').forEach(link => {
        link.classList.remove('active');
    });
    
    // Add active class to current view
    const navLinks = {
        'dashboard': 0,
        'authors': 1, 
        'missing': 2
    };
    
    const navLinkIndex = navLinks[activeView];
    if (navLinkIndex !== undefined) {
        const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
        if (navLinks[navLinkIndex]) {
            navLinks[navLinkIndex].classList.add('active');
        }
    }
}

// Database management functions
async function loadDatabaseInfo() {
    try {
        const info = await apiRequest('/api/database_info');
        updateDatabaseInfoDisplay(info);
    } catch (error) {
        showToast('Failed to load database information', 'danger');
    }
}

function updateDatabaseInfoDisplay(info) {
    const container = document.getElementById('database-info');
    if (!container) return;
    
    if (info.initialized) {
        container.innerHTML = `
            <div class="row">
                <div class="col-md-3">
                    <div class="text-center">
                        <h6 class="text-success">Database Initialized</h6>
                        <small class="text-muted">${info.total_authors} authors, ${info.total_books} books</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center">
                        <h6 class="text-warning">Missing Books</h6>
                        <small class="text-muted">${info.missing_books} books from ${info.authors_with_missing} authors</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center">
                        <h6>Database Path</h6>
                        <small class="text-muted">${info.database_path}</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center">
                        <h6>Calibre DB</h6>
                        <small class="text-muted ${info.calibre_db_exists ? 'text-success' : 'text-danger'}">
                            ${info.calibre_db_exists ? 'Found' : 'Not Found'}
                        </small>
                    </div>
                </div>
            </div>
        `;
    } else {
        container.innerHTML = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i>
                Database not initialized. 
                ${info.calibre_db_exists ? 'Calibre database found - ready to initialize.' : 'Calibre database (metadata.db) not found.'}
            </div>
        `;
    }
}

async function processAllAuthors() {
    // Show a modal to configure batch processing
    const modal = createBatchProcessModal();
    const modalInstance = new bootstrap.Modal(modal);
    modalInstance.show();
}

function createBatchProcessModal() {
    const modalHtml = `
        <div class="modal fade" id="batchProcessModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Batch Process Authors</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="mb-3">
                            <label for="batchLimit" class="form-label">Number of authors to process:</label>
                            <input type="number" class="form-control" id="batchLimit" value="10" min="1" max="100">
                            <div class="form-text">Processing too many authors at once may take a long time and hit API rate limits.</div>
                        </div>
                        <div class="mb-3">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="randomSelection" checked>
                                <label class="form-check-label" for="randomSelection">
                                    Random selection
                                </label>
                                <div class="form-text">If unchecked, will process authors in alphabetical order.</div>
                            </div>
                        </div>
                        <div class="alert alert-info">
                            <i class="fas fa-info-circle"></i>
                            This will process authors in the background. You can continue using the application while processing occurs.
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-primary" onclick="startBatchProcessing()">Start Processing</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal if present
    const existingModal = document.getElementById('batchProcessModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    return document.getElementById('batchProcessModal');
}

async function startBatchProcessing() {
    const limit = parseInt(document.getElementById('batchLimit').value);
    const random = document.getElementById('randomSelection').checked;
    const modal = bootstrap.Modal.getInstance(document.getElementById('batchProcessModal'));
    
    try {
        const response = await apiRequest('/api/process_all_authors', {
            method: 'POST',
            body: JSON.stringify({ limit, random })
        });
        
        if (response.success) {
            showToast(`Started processing ${response.authors.length} authors in background`, 'info');
            modal.hide();
            
            // Show processing notification
            showProcessingNotification(response.authors);
        } else {
            showToast(response.message, 'danger');
        }
        
    } catch (error) {
        showToast('Failed to start batch processing', 'danger');
    }
}

function showProcessingNotification(authors) {
    const notification = `
        <div class="alert alert-info alert-dismissible fade show" role="alert" id="processing-alert">
            <i class="fas fa-cogs"></i>
            <strong>Background Processing Active</strong><br>
            Processing ${authors.length} authors: ${authors.slice(0, 3).join(', ')}${authors.length > 3 ? '...' : ''}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    const container = document.querySelector('.container');
    container.insertAdjacentHTML('afterbegin', notification);
    
    // Auto-remove after 10 seconds
    setTimeout(() => {
        const alert = document.getElementById('processing-alert');
        if (alert) {
            alert.remove();
        }
    }, 10000);
}

// Author processing with input functions
async function processSpecificAuthor() {
    const input = document.getElementById('specific-author-input');
    const button = document.getElementById('process-specific-btn');
    const authorName = input.value.trim();
    
    if (!authorName) {
        showToast('Please enter an author name', 'warning');
        input.focus();
        return;
    }
    
    const originalContent = button.innerHTML;
    
    try {
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
        button.disabled = true;
        input.disabled = true;
        
        const response = await apiRequest('/api/process_specific_author', {
            method: 'POST',
            body: JSON.stringify({ author: authorName })
        });
        
        if (response.success) {
            showToast(`Processed ${response.author}: Found ${response.missing_books_count} missing books`, 'success');
            input.value = ''; // Clear input
            hideSuggestions();
            // Reload stats
            await refreshStats();
        } else {
            showToast(response.message, 'danger');
        }
        
    } catch (error) {
        showToast('Failed to process author', 'danger');
    } finally {
        button.innerHTML = originalContent;
        button.disabled = false;
        input.disabled = false;
    }
}

// Author autocomplete functionality
let searchTimeout;
let currentSuggestions = [];

function setupAuthorAutocomplete() {
    const input = document.getElementById('specific-author-input');
    const suggestions = document.getElementById('author-suggestions');
    
    if (!input || !suggestions) return;
    
    // Setup input event listener
    input.addEventListener('input', function(e) {
        const query = e.target.value.trim();
        
        // Clear previous timeout
        if (searchTimeout) {
            clearTimeout(searchTimeout);
        }
        
        if (query.length < 2) {
            hideSuggestions();
            return;
        }
        
        // Debounce search
        searchTimeout = setTimeout(() => {
            searchAuthors(query);
        }, 300);
    });
    
    // Handle enter key
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            if (currentSuggestions.length > 0) {
                // Use first suggestion if available
                selectAuthor(currentSuggestions[0].name);
            } else {
                processSpecificAuthor();
            }
        } else if (e.key === 'Escape') {
            hideSuggestions();
        }
    });
    
    // Hide suggestions when clicking outside
    document.addEventListener('click', function(e) {
        if (!input.contains(e.target) && !suggestions.contains(e.target)) {
            hideSuggestions();
        }
    });
}

async function searchAuthors(query) {
    try {
        const authors = await apiRequest(`/api/search_authors?q=${encodeURIComponent(query)}&limit=8`);
        showSuggestions(authors);
    } catch (error) {
        console.error('Failed to search authors:', error);
        hideSuggestions();
    }
}

function showSuggestions(authors) {
    const suggestions = document.getElementById('author-suggestions');
    if (!suggestions) return;
    
    currentSuggestions = authors;
    
    if (authors.length === 0) {
        hideSuggestions();
        return;
    }
    
    suggestions.innerHTML = authors.map(author => `
        <button type="button" 
                class="list-group-item list-group-item-action d-flex justify-content-between align-items-center"
                onclick="selectAuthor('${escapeHtml(author.name)}')">
            <div>
                <strong>${escapeHtml(author.name)}</strong>
                <br><small class="text-muted">${author.book_count} books, ${author.missing_count} missing</small>
            </div>
            <i class="fas fa-chevron-right"></i>
        </button>
    `).join('');
    
    suggestions.style.display = 'block';
}

function hideSuggestions() {
    const suggestions = document.getElementById('author-suggestions');
    if (suggestions) {
        suggestions.style.display = 'none';
        currentSuggestions = [];
    }
}

function selectAuthor(authorName) {
    const input = document.getElementById('specific-author-input');
    if (input) {
        input.value = authorName;
        hideSuggestions();
        input.focus();
    }
}

// Global variable to store currently selected author for sidebar
let selectedAuthor = null;

// Author management functions for new interface
function clearAuthorSelection() {
    selectedAuthor = null;
    
    // Remove selection highlighting
    document.querySelectorAll('.accordion-button').forEach(btn => {
        btn.classList.remove('border-primary', 'bg-light');
    });
    
    // Update right sidebar
    const selectedAuthorInfo = document.getElementById('selected-author-info');
    const noAuthorSelected = document.getElementById('no-author-selected');
    const updateStatusCard = document.getElementById('update-status-card');
    
    if (selectedAuthorInfo && noAuthorSelected) {
        selectedAuthorInfo.style.display = 'none';
        noAuthorSelected.style.display = 'block';
    }
    
    // Hide any open status cards
    if (updateStatusCard) {
        updateStatusCard.style.display = 'none';
    }
}

function selectAuthorFromAccordion(authorName) {
    selectedAuthor = authorName;
    
    // Remove previous selection highlighting
    document.querySelectorAll('.accordion-button').forEach(btn => {
        btn.classList.remove('border-primary', 'bg-light');
    });
    
    // Highlight selected author
    const selectedButton = document.querySelector(`[onclick="selectAuthorFromAccordion('${authorName.replace(/'/g, "\\'")}')"]`);
    if (selectedButton) {
        selectedButton.classList.add('border-primary', 'bg-light');
    }
    
    // Update right sidebar
    const selectedAuthorInfo = document.getElementById('selected-author-info');
    const noAuthorSelected = document.getElementById('no-author-selected');
    const selectedAuthorNameEl = document.getElementById('selected-author-name');
    
    if (selectedAuthorInfo && noAuthorSelected && selectedAuthorNameEl) {
        selectedAuthorNameEl.textContent = authorName;
        selectedAuthorInfo.style.display = 'block';
        noAuthorSelected.style.display = 'none';
    }
}

async function loadAuthorBooks(accordionBody, authorName) {
    try {
        // Show loading state
        accordionBody.innerHTML = `
            <div class="loading-books text-center p-3">
                <div class="spinner-border spinner-border-sm" role="status">
                    <span class="visually-hidden">Loading books...</span>
                </div>
                <small class="text-muted ms-2">Loading book comparison...</small>
            </div>
        `;
        
        // Use the enhanced comparison API endpoint
        const authorData = await apiRequest(`/api/author/${encodeURIComponent(authorName)}/compare`);
        
        // Create books list with enhanced status indicators
        const localBooksHtml = authorData.books.map(book => {
            let statusIcon, statusClass, statusText;
            
            switch (book.status) {
                case 'exists_both':
                    statusIcon = 'fas fa-check-circle';
                    statusClass = 'text-success';
                    statusText = book.status_info;
                    break;
                case 'missing_local':
                    statusIcon = 'fas fa-exclamation-triangle';
                    statusClass = 'text-danger';
                    statusText = book.status_info;
                    break;
                case 'missing_api':
                    statusIcon = 'fas fa-question-circle';
                    statusClass = 'text-warning';
                    statusText = book.status_info;
                    break;
                case 'missing_both':
                    statusIcon = 'fas fa-times-circle';
                    statusClass = 'text-muted';
                    statusText = book.status_info;
                    break;
                default:
                    statusIcon = 'fas fa-circle';
                    statusClass = 'text-secondary';
                    statusText = 'Status unknown';
            }
            
            return `
                <div class="border-bottom py-2 px-3 d-flex justify-content-between align-items-center">
                    <div class="flex-grow-1">
                        <span class="${book.status === 'missing_local' ? 'text-danger' : ''}">${escapeHtml(book.title)}</span>
                    </div>
                    <div class="ms-2">
                        <i class="${statusIcon} ${statusClass}" 
                           title="${statusText}"
                           data-bs-toggle="tooltip"></i>
                    </div>
                </div>
            `;
        }).join('');
        
        // Add API-only books (books found in OpenLibrary but not in local library)
        const apiOnlyBooksHtml = authorData.api_only_books.map(book => `
            <div class="border-bottom py-2 px-3 d-flex justify-content-between align-items-center bg-light">
                <div class="flex-grow-1">
                    <span class="text-danger fst-italic">${escapeHtml(book.title)}</span>
                    <small class="text-muted d-block">Found in OpenLibrary only</small>
                </div>
                <div class="ms-2">
                    <i class="fas fa-exclamation-triangle text-danger" 
                       title="${book.status_info}"
                       data-bs-toggle="tooltip"></i>
                </div>
            </div>
        `).join('');
        
        accordionBody.innerHTML = `
            <div class="author-books-list">
                ${localBooksHtml}
                ${apiOnlyBooksHtml ? `
                    <div class="bg-secondary text-white px-3 py-1">
                        <small><strong>Additional books found in OpenLibrary:</strong></small>
                    </div>
                    ${apiOnlyBooksHtml}
                ` : ''}
            </div>
            <div class="p-3 bg-light border-top">
                <div class="row">
                    <div class="col-md-6">
                        <small class="text-muted">
                            <strong>Local Library:</strong> ${authorData.total_local_books} books<br>
                            <strong>Missing from Local:</strong> ${authorData.missing_from_local} books
                        </small>
                    </div>
                    <div class="col-md-6">
                        <small class="text-muted">
                            <strong>OpenLibrary API:</strong> ${authorData.total_api_books} books<br>
                            <strong>Missing from API:</strong> ${authorData.missing_from_api} books
                        </small>
                    </div>
                </div>
                ${!authorData.comparison_available ? `
                    <div class="alert alert-warning alert-sm mt-2 mb-0">
                        <i class="fas fa-exclamation-triangle"></i>
                        <small>Author not found in OpenLibrary - comparison unavailable</small>
                    </div>
                ` : ''}
            </div>
        `;
        
        // Initialize tooltips for the new elements
        const tooltipTriggerList = accordionBody.querySelectorAll('[data-bs-toggle="tooltip"]');
        tooltipTriggerList.forEach(function (tooltipTriggerEl) {
            new bootstrap.Tooltip(tooltipTriggerEl);
        });
        
    } catch (error) {
        accordionBody.innerHTML = `
            <div class="p-3 text-center text-danger">
                <i class="fas fa-exclamation-triangle"></i>
                Error loading books: ${error.message}
            </div>
        `;
    }
}

async function updateAuthorFromAPI() {
    if (!selectedAuthor) {
        showToast('No author selected', 'warning');
        return;
    }
    
    const updateStatusCard = document.getElementById('update-status-card');
    const updateProgress = document.getElementById('update-progress');
    
    // Show update status card
    updateStatusCard.style.display = 'block';
    updateProgress.innerHTML = `
        <div class="d-flex align-items-center">
            <div class="spinner-border spinner-border-sm me-2" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <span>Updating ${escapeHtml(selectedAuthor)} from OpenLibrary API...</span>
        </div>
    `;
    
    try {
        // Call the refresh API endpoint
        const result = await apiRequest(`/api/refresh_author/${encodeURIComponent(selectedAuthor)}`);
        
        updateProgress.innerHTML = `
            <div class="alert alert-success mb-0">
                <i class="fas fa-check-circle"></i> 
                ${result.message}
                <br><small>Total: ${result.total_books} books | Missing: ${result.missing_count} books</small>
            </div>
        `;
        
        // Refresh the author's book list if it's currently expanded
        const expandedAccordion = document.querySelector(`[data-author="${selectedAuthor}"].show`);
        if (expandedAccordion) {
            await loadAuthorBooks(expandedAccordion, selectedAuthor);
        }
        
        // Refresh the authors list to update counts
        await loadAuthors();
        
        showToast(`Successfully updated ${selectedAuthor}`, 'success');
        
        // Hide status card after 5 seconds
        setTimeout(() => {
            updateStatusCard.style.display = 'none';
        }, 5000);
        
    } catch (error) {
        updateProgress.innerHTML = `
            <div class="alert alert-danger mb-0">
                <i class="fas fa-exclamation-triangle"></i> 
                Error updating author: ${error.message}
            </div>
        `;
        
        setTimeout(() => {
            updateStatusCard.style.display = 'none';
        }, 5000);
    }
}

async function searchMissingOnIRC() {
    if (!selectedAuthor) {
        showToast('No author selected', 'warning');
        return;
    }
    
    // Check if search is already in progress
    if (ircSearchManager.isSearchActive(selectedAuthor)) {
        showToast(`IRC search already in progress for ${selectedAuthor}`, 'warning');
        return;
    }
    
    // Show update status card
    const updateStatusCard = document.getElementById('update-status-card');
    const updateProgress = document.getElementById('update-progress');
    
    updateStatusCard.style.display = 'block';
    updateProgress.innerHTML = `
        <div class="d-flex align-items-center">
            <div class="spinner-border spinner-border-sm me-2" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <div>
                <strong>IRC Search in Progress</strong>
                <br><small>Searching for missing books for ${selectedAuthor}...</small>
            </div>
        </div>
    `;
    
    try {
        // Start IRC search
        await ircSearchManager.startSearch(selectedAuthor);
        
        // Start polling for status
        await pollIRCSearchStatusSidebar(selectedAuthor);
        
    } catch (error) {
        updateProgress.innerHTML = `
            <div class="alert alert-danger mb-0">
                <i class="fas fa-exclamation-triangle"></i> 
                Error starting IRC search: ${error.message}
            </div>
        `;
        
        setTimeout(() => {
            updateStatusCard.style.display = 'none';
        }, 5000);
    }
}

async function pollIRCSearchStatusSidebar(author) {
    const updateProgress = document.getElementById('update-progress');
    const updateStatusCard = document.getElementById('update-status-card');
    
    const maxPolls = 60; // 5 minutes max
    let pollCount = 0;
    
    const poll = async () => {
        try {
            const status = await ircSearchManager.getSearchStatus(author);
            
            if (status.status === 'searching') {
                updateProgress.innerHTML = `
                    <div class="d-flex align-items-center">
                        <div class="spinner-border spinner-border-sm me-2" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <div>
                            <strong>IRC Search in Progress</strong>
                            <br><small>${status.message}</small>
                        </div>
                    </div>
                `;
                
                if (pollCount < maxPolls) {
                    pollCount++;
                    setTimeout(poll, 5000);
                } else {
                    updateProgress.innerHTML = `
                        <div class="alert alert-warning mb-0">
                            <i class="fas fa-clock"></i> 
                            IRC search timeout. The search may still be running in the background.
                        </div>
                    `;
                    setTimeout(() => {
                        updateStatusCard.style.display = 'none';
                    }, 5000);
                }
                
            } else if (status.status === 'completed') {
                const foundBooks = status.found_books || [];
                updateProgress.innerHTML = `
                    <div class="alert alert-success mb-0">
                        <i class="fas fa-check-circle"></i> 
                        IRC search completed for ${author}
                        <br><small>Found ${foundBooks.length} matching books${foundBooks.length > 0 ? ':' : '.'}</small>
                        ${foundBooks.length > 0 ? `
                            <div class="mt-2">
                                <div class="list-group list-group-flush">
                                    ${foundBooks.slice(0, 5).map(book => `
                                        <div class="list-group-item list-group-item-success border-0 px-0 py-1">
                                            <small>${escapeHtml(book)}</small>
                                        </div>
                                    `).join('')}
                                    ${foundBooks.length > 5 ? `
                                        <div class="list-group-item border-0 px-0 py-1">
                                            <small class="text-muted">... and ${foundBooks.length - 5} more</small>
                                        </div>
                                    ` : ''}
                                </div>
                            </div>
                        ` : ''}
                    </div>
                `;
                
                setTimeout(() => {
                    updateStatusCard.style.display = 'none';
                }, 10000);
                
            } else if (status.status === 'error') {
                updateProgress.innerHTML = `
                    <div class="alert alert-danger mb-0">
                        <i class="fas fa-exclamation-triangle"></i> 
                        IRC search failed: ${status.message}
                    </div>
                `;
                
                setTimeout(() => {
                    updateStatusCard.style.display = 'none';
                }, 5000);
            }
            
        } catch (error) {
            updateProgress.innerHTML = `
                <div class="alert alert-danger mb-0">
                    <i class="fas fa-exclamation-triangle"></i> 
                    Error checking search status: ${error.message}
                </div>
            `;
            
            setTimeout(() => {
                updateStatusCard.style.display = 'none';
            }, 5000);
        }
    };
    
    poll();
}

// Settings View Functions
function showSettings() {
    hideAllViews();
    document.getElementById('settings-view').style.display = 'block';
    loadMetadataInfo();
    loadDatabaseInfo();
}

async function loadMetadataInfo() {
    const statusDiv = document.getElementById('metadata-status');
    
    try {
        const response = await fetch('/api/metadata/info');
        const data = await response.json();
        
        if (data.success) {
            if (data.exists) {
                statusDiv.innerHTML = `
                    <div class="alert alert-success">
                        <i class="fas fa-check-circle"></i> 
                        <strong>Metadata database found!</strong><br>
                        <small>Path: <code>${data.configured_path}</code></small><br>
                        <small>Books: ${data.info.books}, Authors: ${data.info.authors}</small>
                    </div>
                `;
            } else {
                statusDiv.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="fas fa-exclamation-triangle"></i> 
                        <strong>Metadata database not found</strong><br>
                        <small>Configured path: <code>${data.configured_path}</code></small><br>
                        <small>Please locate or verify the path below</small>
                    </div>
                `;
            }
        } else {
            throw new Error(data.error || 'Failed to load metadata info');
        }
    } catch (error) {
        statusDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-times-circle"></i> 
                <strong>Error loading metadata info:</strong> ${error.message}
            </div>
        `;
    }
}

async function loadDatabaseInfo() {
    const infoDiv = document.getElementById('database-info');
    
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        
        if (data.exists) {
            infoDiv.innerHTML = `
                <div class="row">
                    <div class="col-md-4">
                        <div class="card bg-light">
                            <div class="card-body text-center">
                                <h5 class="card-title">${data.stats.authors}</h5>
                                <p class="card-text">Authors</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card bg-light">
                            <div class="card-body text-center">
                                <h5 class="card-title">${data.stats.total_books}</h5>
                                <p class="card-text">Total Books</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card bg-light">
                            <div class="card-body text-center">
                                <h5 class="card-title text-warning">${data.stats.missing_books}</h5>
                                <p class="card-text">Missing Books</p>
                            </div>
                        </div>
                    </div>
                </div>
                <p class="mt-3 text-muted">Database last updated: <em>${data.last_modified || 'Unknown'}</em></p>
            `;
        } else {
            infoDiv.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle"></i> 
                    Application database not found. It will be created when you initialize from a Calibre metadata database.
                </div>
            `;
        }
    } catch (error) {
        infoDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-times-circle"></i> 
                <strong>Error loading database info:</strong> ${error.message}
            </div>
        `;
    }
}

async function locateMetadataDb() {
    const button = event.target;
    const resultsDiv = document.getElementById('locate-results');
    
    // Show loading state
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Searching...';
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = `
        <div class="alert alert-info">
            <i class="fas fa-search"></i> Searching for metadata.db in common locations...
        </div>
    `;
    
    try {
        const response = await fetch('/api/metadata/locate');
        const data = await response.json();
        
        if (data.success) {
            if (data.found) {
                resultsDiv.innerHTML = `
                    <div class="alert alert-success">
                        <i class="fas fa-check-circle"></i> 
                        <strong>Found Calibre database!</strong><br>
                        <small>Path: <code>${data.path}</code></small><br>
                        <small>Books: ${data.info.books}, Authors: ${data.info.authors}</small><br>
                        <button class="btn btn-sm btn-primary mt-2" onclick="useFoundPath('${data.path}')">
                            <i class="fas fa-check"></i> Use This Database
                        </button>
                    </div>
                `;
            } else {
                resultsDiv.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="fas fa-exclamation-triangle"></i> 
                        <strong>No Calibre database found</strong><br>
                        <small>Please try the manual path option or ensure Calibre is installed with a library.</small>
                    </div>
                `;
            }
        } else {
            throw new Error(data.error || 'Failed to locate metadata database');
        }
    } catch (error) {
        resultsDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-times-circle"></i> 
                <strong>Search failed:</strong> ${error.message}
            </div>
        `;
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-search"></i> Locate metadata.db';
    }
}

async function verifyMetadataPath() {
    const pathInput = document.getElementById('metadata-path');
    const resultsDiv = document.getElementById('verify-results');
    const button = event.target;
    
    const path = pathInput.value.trim();
    if (!path) {
        resultsDiv.style.display = 'block';
        resultsDiv.innerHTML = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i> 
                Please enter a path to verify.
            </div>
        `;
        return;
    }
    
    // Show loading state
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Verifying...';
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = `
        <div class="alert alert-info">
            <i class="fas fa-check"></i> Verifying path...
        </div>
    `;
    
    try {
        const response = await fetch('/api/metadata/verify', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ path: path })
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (data.valid) {
                resultsDiv.innerHTML = `
                    <div class="alert alert-success">
                        <i class="fas fa-check-circle"></i> 
                        <strong>Valid Calibre database!</strong><br>
                        <small>Books: ${data.info.books}, Authors: ${data.info.authors}</small><br>
                        <button class="btn btn-sm btn-primary mt-2" onclick="useFoundPath('${path}')">
                            <i class="fas fa-check"></i> Use This Database
                        </button>
                    </div>
                `;
            } else {
                resultsDiv.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-times-circle"></i> 
                        <strong>Invalid database:</strong> ${data.message}
                    </div>
                `;
            }
        } else {
            throw new Error(data.error || 'Failed to verify metadata database');
        }
    } catch (error) {
        resultsDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-times-circle"></i> 
                <strong>Verification failed:</strong> ${error.message}
            </div>
        `;
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-check"></i> Verify Path';
    }
}

function useFoundPath(path) {
    // Set the path in the initialization input field
    const initPathInput = document.getElementById('init-metadata-path');
    const forceReinitCheckbox = document.getElementById('force-reinit');
    
    if (initPathInput) {
        initPathInput.value = path;
    }
    
    // Show confirmation and offer to initialize
    const message = `Use this database path for initialization?\n\nPath: ${path}\n\nThis will initialize your application database. If the database already exists, check "Force re-initialization" to overwrite it.`;
    
    if (confirm(message)) {
        // Check if we need to force re-initialization based on database status
        fetch('/api/stats')
            .then(response => response.json())
            .then(data => {
                if (data.exists && forceReinitCheckbox) {
                    // Database exists, suggest force re-initialization
                    if (confirm('Database already exists. Do you want to re-initialize it (this will overwrite existing data)?')) {
                        forceReinitCheckbox.checked = true;
                        initializeDatabase(path);
                    } else {
                        showToast(`Database path set to: ${path}. Check "Force re-initialization" to overwrite existing database.`, 'info');
                    }
                } else {
                    initializeDatabase(path);
                }
            })
            .catch(error => {
                // If we can't check database status, proceed with initialization
                initializeDatabase(path);
            });
    } else {
        showToast(`Database path set to: ${path}`, 'info');
    }
}

async function initializeDatabase(pathOverride = null) {
    const statusDiv = document.getElementById('initialization-status');
    const pathInput = document.getElementById('init-metadata-path');
    const forceReinitCheckbox = document.getElementById('force-reinit');
    
    // Show status div
    statusDiv.style.display = 'block';
    statusDiv.innerHTML = `
        <div class="alert alert-info">
            <div class="d-flex align-items-center">
                <div class="spinner-border spinner-border-sm me-2" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <span>Initializing database... This may take a few minutes.</span>
            </div>
        </div>
    `;
    
    try {
        const path = pathOverride || (pathInput ? pathInput.value.trim() : '');
        const forceReinit = forceReinitCheckbox ? forceReinitCheckbox.checked : false;
        
        const response = await fetch('/api/initialize_database', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                calibre_db_path: path || null,
                force_reinit: forceReinit
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            statusDiv.innerHTML = `
                <div class="alert alert-success">
                    <i class="fas fa-check-circle"></i> 
                    <strong>Database initialized successfully!</strong><br>
                    <small>${data.message}</small><br>
                    <small>Records imported: ${data.records_imported || 'N/A'}</small><br>
                    <small>Authors: ${data.authors_count || 'N/A'}</small>
                </div>
            `;
            
            // Refresh the database info displays
            await loadDatabaseInfo();
            await loadMetadataInfo();
            
            showToast('Database initialization completed successfully!', 'success');
        } else {
            statusDiv.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-times-circle"></i> 
                    <strong>Initialization failed:</strong> ${data.message || data.error}
                </div>
            `;
            showToast('Database initialization failed', 'danger');
        }
    } catch (error) {
        statusDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-times-circle"></i> 
                <strong>Error during initialization:</strong> ${error.message}
            </div>
        `;
        showToast('Database initialization error', 'danger');
    }
}

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
    
    // Initialize author autocomplete functionality
    setupAuthorAutocomplete();
    
    // Load initial view (dashboard)
    showDashboard();
});

// Export functions for global use
window.CalibreMonitor = {
    showToast,
    apiRequest,
    ircSearchManager,
    autoRefreshManager,
    initializeTableSearch
};
