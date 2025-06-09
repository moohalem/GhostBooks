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
    const tableElement = document.getElementById(tableId);
    if (!tableElement) {
        // No table found - probably using accordion interface
        return;
    }
    
    const tableContainer = tableElement.closest('.card');
    if (!tableContainer) {
        return;
    }
    
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
        
        // Update missing books database stats if available
        if (stats.missing_book_stats) {
            const missingDbTotal = document.querySelector('[data-stat="missing-db-total"]');
            const missingDbRecent = document.querySelector('[data-stat="missing-db-recent"]');
            
            if (missingDbTotal) missingDbTotal.textContent = stats.missing_book_stats.total_missing;
            if (missingDbRecent) missingDbRecent.textContent = stats.missing_book_stats.recent_discoveries;
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
    
    // Handle database initialization card toggle
    const initToggle = document.getElementById('database-init-toggle');
    const initCollapse = document.getElementById('database-init-collapse');
    
    if (initToggle && initCollapse) {
        initCollapse.addEventListener('show.bs.collapse', function() {
            const chevron = initToggle.querySelector('.float-end');
            if (chevron) {
                chevron.className = 'fas fa-chevron-down float-end';
            }
            initToggle.classList.remove('collapsed');
            initToggle.setAttribute('aria-expanded', 'true');
        });
        
        initCollapse.addEventListener('hide.bs.collapse', function() {
            const chevron = initToggle.querySelector('.float-end');
            if (chevron) {
                chevron.className = 'fas fa-chevron-right float-end';
            }
            initToggle.classList.add('collapsed');
            initToggle.setAttribute('aria-expanded', 'false');
        });
    }
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
        // Load both stats and recently processed authors
        const [stats, recentlyProcessedAuthors] = await Promise.all([
            apiRequest('/api/stats'),
            apiRequest('/api/recently_processed_authors')
        ]);
        
        // Load database info
        await loadDatabaseInfo();
        
        // Update stats cards
        updateDashboardStats(stats);
        
        // Update missing books database statistics
        await updateMissingBooksStats();
        
        // Update recently processed authors - handle empty case
        const recentAuthors = Array.isArray(recentlyProcessedAuthors) ? recentlyProcessedAuthors.slice(0, 10) : [];
        updateRecentAuthors(recentAuthors);
        
        document.getElementById('dashboard-view').style.display = 'block';
        
        // Update active nav
        updateActiveNav('dashboard');
        
        // Start auto-refresh for dashboard
        autoRefreshManager.start();
        
    } catch (error) {
        showToast('Failed to load dashboard data', 'danger');
        // Show empty state for recently processed authors on error
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

// Pagination controls
function updatePaginationControls(pagination, search = '') {
    const paginationContainer = document.getElementById('authors-pagination');
    if (!paginationContainer) {
        return;
    }
    
    const paginationList = paginationContainer.querySelector('.pagination');
    if (!paginationList) {
        return;
    }
    
    if (!pagination || !pagination.pages || pagination.pages <= 1) {
        paginationContainer.style.display = 'none';
        return;
    }
    
    paginationContainer.style.display = 'block';
    
    const currentPage = pagination.page || 1;
    const totalPages = pagination.pages || 1;
    
    let paginationHTML = '';
    
    // Previous button
    paginationHTML += `
        <li class="page-item ${currentPage <= 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="loadAuthors(${currentPage - 1}, '${search}'); return false;">
                <i class="fas fa-chevron-left"></i>
            </a>
        </li>
    `;
    
    // Page numbers
    const maxVisible = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    
    // Adjust start if we're near the end
    if (endPage - startPage < maxVisible - 1) {
        startPage = Math.max(1, endPage - maxVisible + 1);
    }
    
    // First page and ellipsis
    if (startPage > 1) {
        paginationHTML += `
            <li class="page-item">
                <a class="page-link" href="#" onclick="loadAuthors(1, '${search}'); return false;">1</a>
            </li>
        `;
        if (startPage > 2) {
            paginationHTML += '<li class="page-item disabled"><span class="page-link">...</span></li>';
        }
    }
    
    // Page numbers
    for (let i = startPage; i <= endPage; i++) {
        paginationHTML += `
            <li class="page-item ${i === currentPage ? 'active' : ''}">
                <a class="page-link" href="#" onclick="loadAuthors(${i}, '${search}'); return false;">${i}</a>
            </li>
        `;
    }
    
    // Last page and ellipsis
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            paginationHTML += '<li class="page-item disabled"><span class="page-link">...</span></li>';
        }
        paginationHTML += `
            <li class="page-item">
                <a class="page-link" href="#" onclick="loadAuthors(${totalPages}, '${search}'); return false;">${totalPages}</a>
            </li>
        `;
    }
    
    // Next button
    paginationHTML += `
        <li class="page-item ${currentPage >= totalPages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="loadAuthors(${currentPage + 1}, '${search}'); return false;">
                <i class="fas fa-chevron-right"></i>
            </a>
        </li>
    `;
    
    paginationList.innerHTML = paginationHTML;
    
    // Update search results info
    const searchInfo = document.getElementById('search-results-info');
    if (search) {
        searchInfo.style.display = 'block';
        searchInfo.textContent = `Found ${pagination.total} authors matching "${search}" (Page ${currentPage} of ${totalPages})`;
    } else {
        searchInfo.style.display = 'none';
    }
}

// Data loading functions
async function loadAuthors(page = 1, search = '') {
    try {
        const params = new URLSearchParams({ 
            page: page, 
            per_page: 50  // Reduced from 100 for better performance
        });
        if (search) {
            params.append('search', search);
        }
        
        const response = await apiRequest(`/api/authors?${params}`);
        const authors = response.authors || [];
        const pagination = response.pagination || {};
        
        const accordion = document.getElementById('authors-accordion');
        
        if (authors.length === 0) {
            accordion.innerHTML = `
                <div class="text-center py-4">
                    <i class="fas fa-info-circle text-muted"></i>
                    <p class="text-muted mt-2">No authors found</p>
                </div>
            `;
            return;
        }
        
        accordion.innerHTML = authors.map((author, index) => `
            <div class="accordion-item border-0 border-bottom">
                <h2 class="accordion-header" id="heading${(page-1)*50 + index}">
                    <button class="accordion-button collapsed d-flex justify-content-between align-items-center" 
                            type="button" 
                            data-bs-toggle="collapse" 
                            data-bs-target="#collapse${(page-1)*50 + index}" 
                            onclick="selectAuthorFromAccordion('${escapeHtml(author.author)}')">
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
                <div id="collapse${(page-1)*50 + index}" 
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
        
        // Add pagination controls
        updatePaginationControls(pagination, search);
        
        // Add event listeners for accordion expansion
        accordion.addEventListener('shown.bs.collapse', async function(e) {
            const authorName = e.target.getAttribute('data-author');
            await loadAuthorBooks(e.target, authorName);
        });
        
        // Update table info
        updateTableInfo('authors-table', authors.length, pagination.total);
        
    } catch (error) {
        console.error('Error loading authors:', error);
        const accordion = document.getElementById('authors-accordion');
        accordion.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle"></i>
                Error loading authors: ${error.message}
            </div>
        `;
    }
}

async function loadMissingBooks() {
    try {
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

        // Update statistics
        await updateMissingBooksStats();
        
        container.innerHTML = Object.entries(missingBooks).map(([author, books]) => `
            <div class="card mb-3">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="mb-0">
                        <a href="#" onclick="showAuthorDetail(${JSON.stringify(author)})" 
                           class="text-decoration-none">
                            ${escapeHtml(author)}
                        </a>
                        <span class="badge bg-warning ms-2">${books.length} missing</span>
                    </h5>
                    <div>
                        <button class="btn btn-sm btn-outline-success" 
                                onclick="refreshAuthor(${JSON.stringify(author)})">
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
                        ${books.map(book => {
                            const isNew = book.source === 'openlibrary';
                            const discoveredDate = book.discovered_at ? new Date(book.discovered_at).toLocaleDateString() : null;
                            return `
                                <div class="col-md-6 col-lg-4 mb-2">
                                    <div class="border rounded p-2 h-100 ${isNew ? 'border-primary' : 'border-secondary'}">
                                        <div class="d-flex justify-content-between align-items-start">
                                            <small class="text-muted flex-grow-1">${escapeHtml(book.title)}</small>
                                            ${isNew ? '<span class="badge bg-primary badge-sm ms-1">New</span>' : '<span class="badge bg-secondary badge-sm ms-1">Legacy</span>'}
                                        </div>
                                        ${discoveredDate ? `<small class="text-muted d-block mt-1"><i class="fas fa-calendar"></i> ${discoveredDate}</small>` : ''}
                                        <small class="text-muted d-block"><i class="fas fa-database"></i> ${book.source || 'legacy'}</small>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        const container = document.getElementById('missing-books-container');
        container.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle"></i>
                Error loading missing books: ${error.message}
            </div>
        `;
    }
}

// Dashboard specific functions
function updateDashboardStats(stats) {
    const missingBooksEl = document.querySelector('[data-stat="missing-books"]');
    const authorsWithMissingEl = document.querySelector('[data-stat="authors-with-missing"]');
    
    if (missingBooksEl) missingBooksEl.textContent = stats.total_missing;
    if (authorsWithMissingEl) authorsWithMissingEl.textContent = stats.authors_with_missing;
    
    // Update missing books database stats if available
    if (stats.missing_book_stats) {
        const missingDbTotal = document.querySelector('[data-stat="missing-db-total"]');
        const missingDbRecent = document.querySelector('[data-stat="missing-db-recent"]');
        
        if (missingDbTotal) missingDbTotal.textContent = stats.missing_book_stats.total_missing;
        if (missingDbRecent) missingDbRecent.textContent = stats.missing_book_stats.recent_discoveries;
    }
}

// Missing books statistics update
async function updateMissingBooksStats() {
    try {
        const stats = await apiRequest('/api/missing_books/stats');
        
        // Update missing books view statistics
        const totalEl = document.getElementById('missing-stats-total');
        const authorsEl = document.getElementById('missing-stats-authors');
        const recentEl = document.getElementById('missing-stats-recent');
        const sourcesEl = document.getElementById('missing-stats-sources');
        
        if (totalEl) totalEl.textContent = stats.total_missing || 0;
        if (authorsEl) authorsEl.textContent = stats.authors_with_missing || 0;
        if (recentEl) recentEl.textContent = stats.recent_discoveries || 0;
        if (sourcesEl) sourcesEl.textContent = stats.top_authors ? stats.top_authors.length : 0;
        
        // Update dashboard missing books database statistics cards
        const missingDbTotal = document.querySelector('[data-stat="missing-db-total"]');
        const missingDbRecent = document.querySelector('[data-stat="missing-db-recent"]');
        
        if (missingDbTotal) missingDbTotal.textContent = stats.total_missing || 0;
        if (missingDbRecent) missingDbRecent.textContent = stats.recent_discoveries || 0;
        
    } catch (error) {
        console.warn('Could not load missing books statistics:', error);
    }
}

// Bulk processing functions
async function populateMissingBooksDatabase() {
    if (!confirm('This will populate the missing books database from OpenLibrary API. This may take a while. Continue?')) {
        return;
    }
    
    // Open the progress modal
    openProgressModal();
    
    // Start the streaming process
    startProgressStreaming();
}

let eventSource = null;
let isPopulationCancelled = false;

function openProgressModal() {
    const modal = new bootstrap.Modal(document.getElementById('populationProgressModal'), {
        backdrop: 'static',
        keyboard: false
    });
    modal.show();
    
    // Reset modal state
    isPopulationCancelled = false;
    resetProgressModal();
}

function resetProgressModal() {
    // Reset progress bar
    const progressBar = document.getElementById('progress-bar');
    const progressPercentage = document.getElementById('progress-percentage');
    const progressProcessed = document.getElementById('progress-processed');
    const progressTotal = document.getElementById('progress-total');
    const progressMissingFound = document.getElementById('progress-missing-found');
    
    if (progressBar) {
        progressBar.style.width = '0%';
        progressBar.setAttribute('aria-valuenow', '0');
    }
    if (progressPercentage) progressPercentage.textContent = '0%';
    if (progressProcessed) progressProcessed.textContent = '0';
    if (progressTotal) progressTotal.textContent = '0';
    if (progressMissingFound) progressMissingFound.textContent = '0';
    
    // Reset current status
    const currentStatus = document.getElementById('current-status');
    const statusText = document.getElementById('status-text');
    if (currentStatus) {
        currentStatus.className = 'alert alert-info';
    }
    if (statusText) {
        statusText.textContent = 'Initializing...';
    }
    
    // Reset current author - using the correct ID from HTML
    const currentAuthorName = document.getElementById('current-author-name');
    const currentAuthorSection = document.getElementById('current-author-section');
    if (currentAuthorName) currentAuthorName.innerHTML = '-';
    if (currentAuthorSection) currentAuthorSection.style.display = 'none';
    
    // Clear progress log
    const progressLog = document.getElementById('progress-log');
    if (progressLog) progressLog.innerHTML = '';
    
    // Hide error section
    const errorSection = document.getElementById('error-section');
    if (errorSection) errorSection.style.display = 'none';
    
    // Show cancel button, hide close button
    const cancelButton = document.getElementById('cancel-button');
    const closeButton = document.getElementById('close-button');
    if (cancelButton) {
        cancelButton.style.display = 'inline-block';
        cancelButton.disabled = false;
        cancelButton.innerHTML = '<i class="fas fa-stop"></i> Cancel';
    }
    if (closeButton) closeButton.style.display = 'none';
}

function startProgressStreaming() {
    // Close any existing event source
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    
    // Add initial connection message
    addToProgressLog('Connecting to server and starting population process...', 'info');
    
    // Create new event source for streaming progress
    eventSource = new EventSource('/api/missing_books/populate/stream');
    
    eventSource.onopen = function(event) {
        console.log('EventSource connection opened');
        addToProgressLog('Connected to server successfully', 'success');
    };
    
    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            updateProgress(data);
        } catch (error) {
            console.error('Error parsing server message:', error);
            addToProgressLog('Error parsing server message: ' + error.message, 'error');
        }
    };
    
    eventSource.onerror = function(event) {
        console.error('EventSource failed:', event);
        console.error('EventSource readyState:', eventSource.readyState);
        
        const currentStatus = document.getElementById('current-status');
        const statusText = document.getElementById('status-text');
        
        let errorMessage = 'Connection error occurred';
        
        // Provide more specific error messages based on readyState
        switch (eventSource.readyState) {
            case EventSource.CONNECTING:
                errorMessage = 'Connection is being established...';
                addToProgressLog('Attempting to reconnect to server...', 'warning');
                return; // Don't close immediately if still connecting
            case EventSource.OPEN:
                errorMessage = 'Connection is open but an error occurred';
                break;
            case EventSource.CLOSED:
                errorMessage = 'Connection has been closed due to an error';
                break;
            default:
                errorMessage = 'Unknown connection error';
        }
        
        if (currentStatus) {
            currentStatus.className = 'alert alert-danger';
        }
        if (statusText) {
            statusText.textContent = errorMessage;
        }
        
        // Add error to log
        addToProgressLog(`Connection error: ${errorMessage}`, 'error');
        
        // Show close button
        showCloseButton();
        
        eventSource.close();
        eventSource = null;
    };
}

function updateProgress(data) {
    const progressBar = document.getElementById('progress-bar');
    const progressPercentage = document.getElementById('progress-percentage');
    const progressProcessed = document.getElementById('progress-processed');
    const progressTotal = document.getElementById('progress-total');
    const progressMissingFound = document.getElementById('progress-missing-found');
    const currentStatus = document.getElementById('current-status');
    const statusText = document.getElementById('status-text');
    const currentAuthorName = document.getElementById('current-author-name');
    const currentAuthorSection = document.getElementById('current-author-section');
    
    // Update progress bar
    if (data.total > 0 && progressBar && progressPercentage) {
        const percentage = Math.round((data.processed / data.total) * 100);
        progressBar.style.width = percentage + '%';
        progressBar.setAttribute('aria-valuenow', percentage);
        progressPercentage.textContent = percentage + '%';
    }
    
    // Update counters
    if (progressProcessed) progressProcessed.textContent = data.processed || 0;
    if (progressTotal) progressTotal.textContent = data.total || 0;
    if (progressMissingFound) progressMissingFound.textContent = data.missing_found || 0;
    
    // Update current status
    if (data.status === 'completed') {
        if (currentStatus) currentStatus.className = 'alert alert-success';
        if (statusText) statusText.textContent = 'Population completed successfully!';
        if (currentAuthorName) currentAuthorName.innerHTML = 'Completed';
        if (currentAuthorSection) currentAuthorSection.style.display = 'block';
        
        // Close event source
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        
        // Show close button, hide cancel button
        showCloseButton();
        
        // Add separator and detailed completion message
        addToProgressLog('─'.repeat(50), 'info');
        const summaryMessage = `🎉 Population completed successfully! 
📊 Summary: Processed ${data.processed || 0} authors, found ${data.missing_found || 0} missing books total.
${data.errors && data.errors.length > 0 ? `⚠️ ${data.errors.length} errors occurred during processing.` : '✅ No errors encountered.'}`;
        
        addToProgressLog(summaryMessage, 'success');
        
        // Show success toast
        showToast(`Successfully processed ${data.processed} authors and found ${data.missing_found} missing books`, 'success');
        
    } else if (data.status === 'cancelled') {
        if (currentStatus) currentStatus.className = 'alert alert-warning';
        if (statusText) statusText.textContent = 'Population was cancelled';
        if (currentAuthorName) currentAuthorName.innerHTML = 'Cancelled';
        if (currentAuthorSection) currentAuthorSection.style.display = 'block';
        
        // Close event source
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        
        // Show close button, hide cancel button
        showCloseButton();
        
        addToProgressLog('Population was cancelled by user.', 'warning');
        
    } else if (data.status === 'error') {
        if (currentStatus) currentStatus.className = 'alert alert-danger';
        if (statusText) statusText.textContent = `Error: ${data.message || 'Unknown error occurred'}`;
        if (currentAuthorName) currentAuthorName.innerHTML = 'Error';
        if (currentAuthorSection) currentAuthorSection.style.display = 'block';
        
        // Close event source
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        
        // Show close button, hide cancel button
        showCloseButton();
        
        addToProgressLog(`Error: ${data.message || 'Unknown error occurred'}`, 'error');
        
    } else {
        // Processing status
        if (currentStatus) currentStatus.className = 'alert alert-info';
        if (statusText) statusText.textContent = data.message || 'Processing...';
        
        if (data.current_author && currentAuthorName && currentAuthorSection) {
            currentAuthorName.innerHTML = escapeHtml(data.current_author);
            currentAuthorSection.style.display = 'block';
        }
    }
    
    // Add all messages to log (including detailed verbose messages)
    if (data.message) {
        let logType = 'info';
        
        // Determine log type based on message content or status
        if (data.status === 'completed') {
            logType = 'success';
        } else if (data.status === 'cancelled') {
            logType = 'warning';
        } else if (data.status === 'error') {
            logType = 'error';
        } else if (data.message.includes('✓')) {
            // Success messages (e.g., "✓ Author: Found X missing books")
            logType = 'success';
        } else if (data.message.includes('✗')) {
            // Error messages (e.g., "✗ Author: Error - message")
            logType = 'error';
        } else if (data.message.includes('Processing author') || data.message.includes('querying OpenLibrary')) {
            // Processing messages
            logType = 'info';
        } else if (data.message.includes('Found') && data.message.includes('local books')) {
            // Information about local books found
            logType = 'info';
        } else if (data.message.includes('Clearing') || data.message.includes('Loading')) {
            // System status messages
            logType = 'info';
        }
        
        addToProgressLog(data.message, logType);
    }
    
    // Handle errors
    if (data.errors && data.errors.length > 0) {
        showErrorSummary(data.errors);
    }
}

function addToProgressLog(message, type = 'info') {
    const progressLog = document.getElementById('progress-log');
    if (!progressLog) return;
    
    const timestamp = new Date().toLocaleTimeString();
    
    let iconClass = 'fas fa-info-circle';
    let textClass = 'text-muted';
    
    switch (type) {
        case 'success':
            iconClass = 'fas fa-check-circle';
            textClass = 'text-success';
            break;
        case 'warning':
            iconClass = 'fas fa-exclamation-triangle';
            textClass = 'text-warning';
            break;
        case 'error':
            iconClass = 'fas fa-times-circle';
            textClass = 'text-danger';
            break;
    }
    
    // Handle special message formatting
    let formattedMessage = message;
    
    // Replace checkmark and X symbols with appropriate styling
    if (message.includes('✓')) {
        formattedMessage = message.replace('✓', '<i class="fas fa-check text-success"></i>');
        textClass = 'text-success';
        iconClass = 'fas fa-check-circle';
    } else if (message.includes('✗')) {
        formattedMessage = message.replace('✗', '<i class="fas fa-times text-danger"></i>');
        textClass = 'text-danger';
        iconClass = 'fas fa-times-circle';
    }
    
    // Add special styling for author names (text between "Processing author" and ":")
    if (message.includes('Processing author')) {
        formattedMessage = formattedMessage.replace(
            /(Processing author \d+\/\d+: )(.+)/,
            '$1<strong class="text-primary">$2</strong>'
        );
    }
    
    // Add styling for book counts
    formattedMessage = formattedMessage.replace(
        /(\d+) (missing books?|local books?|books? are available)/g,
        '<strong class="text-info">$1</strong> $2'
    );
    
    // Add styling for "newly added" text
    formattedMessage = formattedMessage.replace(
        /(\d+) newly added/g,
        '<strong class="text-success">$1 newly added</strong>'
    );
    
    const logEntry = document.createElement('div');
    logEntry.className = 'mb-1 px-2 py-1';
    
    // Add background color for certain message types
    let bgClass = '';
    if (type === 'success' && message.includes('✓')) {
        bgClass = 'bg-success bg-opacity-10';
    } else if (type === 'error' && message.includes('✗')) {
        bgClass = 'bg-danger bg-opacity-10';
    } else if (message.includes('Processing author')) {
        bgClass = 'bg-light';
    }
    
    if (bgClass) {
        logEntry.className += ` ${bgClass} rounded`;
    }
    
    logEntry.innerHTML = `
        <span class="text-muted small">[${timestamp}]</span> 
        <i class="${iconClass} ${textClass} me-1"></i> 
        <span class="${textClass}">${formattedMessage}</span>
    `;
    
    progressLog.appendChild(logEntry);
    
    // Auto-scroll to bottom
    progressLog.scrollTop = progressLog.scrollHeight;
    
    // Limit log entries to prevent memory issues (keep last 1000 entries)
    const maxEntries = 1000;
    const entries = progressLog.children;
    if (entries.length > maxEntries) {
        // Remove oldest entries
        const entriesToRemove = entries.length - maxEntries;
        for (let i = 0; i < entriesToRemove; i++) {
            progressLog.removeChild(entries[0]);
        }
    }
}

function showErrorSummary(errors) {
    const errorSection = document.getElementById('error-section');
    const errorSummary = document.getElementById('error-summary');
    
    if (errors.length > 0) {
        errorSection.style.display = 'block';
        
        const errorList = errors.map(error => 
            `<div class="mb-1">
                <strong>${escapeHtml(error.author)}:</strong> ${escapeHtml(error.error)}
            </div>`
        ).join('');
        
        errorSummary.innerHTML = `
            <div class="mb-2">
                <i class="fas fa-exclamation-triangle"></i> 
                <strong>${errors.length} error(s) encountered:</strong>
            </div>
            ${errorList}
        `;
    }
}

function showCloseButton() {
    const cancelButton = document.getElementById('cancel-button');
    const closeButton = document.getElementById('close-button');
    if (cancelButton) cancelButton.style.display = 'none';
    if (closeButton) closeButton.style.display = 'inline-block';
}

function clearProgressLog() {
    const progressLog = document.getElementById('progress-log');
    if (progressLog) {
        progressLog.innerHTML = '';
    }
}

async function cancelPopulation() {
    if (isPopulationCancelled) {
        return;
    }
    
    isPopulationCancelled = true;
    
    try {
        const response = await fetch('/api/missing_books/populate/cancel', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            addToProgressLog('Cancellation request sent...', 'warning');
            
            // Disable the cancel button
            const cancelButton = document.getElementById('cancel-button');
            cancelButton.disabled = true;
            cancelButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Cancelling...';
        } else {
            showToast('Failed to cancel population', 'danger');
            isPopulationCancelled = false;
        }
    } catch (error) {
        console.error('Error cancelling population:', error);
        showToast('Error cancelling population', 'danger');
        isPopulationCancelled = false;
    }
}

function closeProgressModal() {
    // Close event source if still open
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    
    // Hide modal
    const modal = bootstrap.Modal.getInstance(document.getElementById('populationProgressModal'));
    if (modal) {
        modal.hide();
    }
    
    // Refresh the current view to show updated data
    refreshCurrentView();
}

async function refreshCurrentView() {
    try {
        // Refresh the current view
        if (document.getElementById('missing-view').style.display !== 'none') {
            await loadMissingBooks();
        }
        if (document.getElementById('dashboard-view').style.display !== 'none') {
            await refreshStats();
        }
    } catch (error) {
        console.error('Error refreshing view:', error);
    }
}

async function clearMissingBooksDatabase() {
    if (!confirm('This will clear all data from the missing books database. This action cannot be undone. Continue?')) {
        return;
    }
    
    try {
        showLoading(true);
        const result = await apiRequest('/api/missing_books/clear', {
            method: 'POST'
        });
        
        if (result.success) {
            showToast(`Successfully cleared ${result.deleted_count} missing book records`, 'success');
            
            // Refresh the current view
            if (document.getElementById('missing-view').style.display !== 'none') {
                await loadMissingBooks();
            }
            if (document.getElementById('dashboard-view').style.display !== 'none') {
                await refreshStats();
            }
        } else {
            showToast(`Clear failed: ${result.message}`, 'danger');
        }
        
    } catch (error) {
        showToast(`Clear failed: ${error.message}`, 'danger');
    } finally {
        showLoading(false);
    }
}

function updateRecentAuthors(authors) {
    const recentAuthorsEl = document.getElementById('recently-processed-authors-list');
    if (!recentAuthorsEl) return;
    
    // Check if there are no authors
    if (!authors || authors.length === 0) {
        recentAuthorsEl.innerHTML = `
            <tr>
                <td colspan="3" class="text-center text-muted py-3">
                    <i class="fas fa-info-circle"></i> No recently processed authors found
                </td>
            </tr>
        `;
        return;
    }
    
    recentAuthorsEl.innerHTML = authors.map(author => `
        <tr>
            <td>
                <a href="#" onclick="showAuthorDetail(${JSON.stringify(author.name)})" 
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
let searchTimeout;
function filterAuthors() {
    const searchTerm = document.getElementById('author-search').value;
    
    // Debounce search to avoid too many API calls
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        loadAuthors(1, searchTerm);
    }, 300);
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
        'missing': 2,
        'settings': 3
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
let authorSearchTimeout;
let currentSuggestions = [];

function setupAuthorAutocomplete() {
    const input = document.getElementById('specific-author-input');
    const suggestions = document.getElementById('author-suggestions');
    
    if (!input || !suggestions) return;
    
    // Setup input event listener
    input.addEventListener('input', function(e) {
        const query = e.target.value.trim();
        
        // Clear previous timeout
        if (authorSearchTimeout) {
            clearTimeout(authorSearchTimeout);
        }
        
        if (query.length < 2) {
            hideSuggestions();
            return;
        }
        
        // Debounce search
        authorSearchTimeout = setTimeout(() => {
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
        
        // Validate API response
        if (!authorData || !authorData.books || !Array.isArray(authorData.books)) {
            throw new Error('Invalid API response: missing books array');
        }
        
        // Create books list with enhanced status indicators
        const localBooksHtml = authorData.books.map(book => {
            let statusIcon, statusClass, statusText;
            
            switch (book.status) {
                case 'exists_both':
                    statusIcon = 'fas fa-check-circle';
                    statusClass = 'text-success';
                    statusText = book.status_info || 'Available in library';
                    break;
                case 'missing_local':
                    statusIcon = 'fas fa-exclamation-triangle';
                    statusClass = 'text-danger';
                    statusText = book.status_info || 'Missing from local library';
                    break;
                case 'missing_api':
                    statusIcon = 'fas fa-question-circle';
                    statusClass = 'text-warning';
                    statusText = book.status_info || 'Could not verify with API';
                    break;
                case 'missing_both':
                    statusIcon = 'fas fa-times-circle';
                    statusClass = 'text-muted';
                    statusText = book.status_info || 'Missing from both sources';
                    break;
                default:
                    statusIcon = 'fas fa-circle';
                    statusClass = 'text-secondary';
                    statusText = book.status_info || 'Status unknown';
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
        
        // No need for separate API-only books section since they're now included in the main books array
        
        accordionBody.innerHTML = `
            <div class="author-books-list">
                ${localBooksHtml}
            </div>
            <div class="p-3 bg-light border-top">
                <div class="row">
                    <div class="col-md-6">
                        <small class="text-muted">
                            <strong>Local Library:</strong> ${authorData.local_count || 0} books<br>
                            <strong>Missing Books:</strong> ${authorData.missing_count || 0} books
                        </small>
                    </div>
                    <div class="col-md-6">
                        <small class="text-muted">
                            <strong>OpenLibrary API:</strong> ${authorData.openlibrary_count || 0} books<br>
                            <strong>Comparison:</strong> ${authorData.success ? 'Available' : 'Failed'}
                        </small>
                    </div>
                </div>
                ${!authorData.success ? `
                    <div class="alert alert-warning alert-sm mt-2 mb-0">
                        <i class="fas fa-exclamation-triangle"></i>
                        <small>${authorData.message || 'Comparison with OpenLibrary failed'}</small>
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
    // Update active nav
    updateActiveNav('settings');
    loadMetadataInfo();
    loadDatabaseInfo();
    refreshOlidCacheStats();
}

async function loadMetadataInfo() {
    const statusDiv = document.getElementById('metadata-status');
    const initCard = document.getElementById('database-init-card');
    const initCollapse = document.getElementById('database-init-collapse');
    const initToggle = document.getElementById('database-init-toggle');
    const initChevron = document.getElementById('database-init-chevron');
    
    try {
        const response = await fetch('/api/metadata/info');
        const data = await response.json();
        
        if (data.success) {
            if (data.exists) {
                // Database found - show success status and collapse the initialization card
                statusDiv.innerHTML = `
                    <div class="alert alert-success">
                        <i class="fas fa-check-circle"></i> 
                        <strong>Metadata database found!</strong><br>
                        <small>Path: <code>${data.configured_path}</code></small><br>
                        <small>Books: ${data.info.books}, Authors: ${data.info.authors}</small>
                    </div>
                `;
                
                // Collapse the initialization card and update header to show found status
                if (initCollapse && initToggle) {
                    // Hide the collapse content
                    const bsCollapse = bootstrap.Collapse.getOrCreateInstance(initCollapse);
                    bsCollapse.hide();
                    
                    // Update header text to show database found
                    initToggle.innerHTML = `
                        <i class="fas fa-database text-success"></i> Database Initialization - <span class="text-success">Metadata Database Found</span>
                        <i class="fas fa-chevron-right float-end"></i>
                    `;
                    
                    // Update the toggle to indicate collapsed state
                    initToggle.setAttribute('aria-expanded', 'false');
                    initToggle.classList.add('collapsed');
                }
                
            } else {
                // Database not found - show warning and ensure card is expanded
                statusDiv.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="fas fa-exclamation-triangle"></i> 
                        <strong>Metadata database not found</strong><br>
                        <small>Configured path: <code>${data.configured_path}</code></small><br>
                        <small>Please locate or verify the path below</small>
                    </div>
                `;
                
                // Ensure the initialization card is expanded
                if (initCollapse && initToggle) {
                    // Show the collapse content
                    const bsCollapse = bootstrap.Collapse.getOrCreateInstance(initCollapse);
                    bsCollapse.show();
                    
                    // Update header text to show database not found
                    initToggle.innerHTML = `
                        <i class="fas fa-database text-warning"></i> Database Initialization - <span class="text-warning">Setup Required</span>
                        <i class="fas fa-chevron-down float-end"></i>
                    `;
                    
                    // Update the toggle to indicate expanded state
                    initToggle.setAttribute('aria-expanded', 'true');
                    initToggle.classList.remove('collapsed');
                }
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
        
        // On error, ensure the initialization card is expanded for troubleshooting
        if (initCollapse && initToggle) {
            const bsCollapse = bootstrap.Collapse.getOrCreateInstance(initCollapse);
            bsCollapse.show();
            initToggle.innerHTML = `
                <i class="fas fa-database text-danger"></i> Database Initialization - <span class="text-danger">Error</span>
                <i class="fas fa-chevron-down float-end"></i>
            `;
            initToggle.setAttribute('aria-expanded', 'true');
            initToggle.classList.remove('collapsed');
        }
    }
}

async function loadDatabaseInfo() {
    // Check both dashboard and settings database info divs
    const dashboardInfoDiv = document.getElementById('dashboard-database-info');
    const settingsInfoDiv = document.getElementById('database-info');
    
    if (!dashboardInfoDiv && !settingsInfoDiv) {
        console.error('No database-info divs found');
        return;
    }
    
    try {
        const response = await fetch('/api/stats');
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        let contentHtml = '';
        
        if (data.exists) {
            contentHtml = `
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
            contentHtml = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle"></i> 
                    Application database not found. It will be created when you initialize from a Calibre metadata database.
                </div>
            `;
        }
        
        // Update both divs if they exist
        if (dashboardInfoDiv) {
            dashboardInfoDiv.innerHTML = contentHtml;
        }
        if (settingsInfoDiv) {
            settingsInfoDiv.innerHTML = contentHtml;
        }
        
    } catch (error) {
        console.error('Error loading database info:', error);
        const errorHtml = `
            <div class="alert alert-danger">
                <i class="fas fa-times-circle"></i> 
                <strong>Error loading database info:</strong> ${error.message}
            </div>
        `;
        
        if (dashboardInfoDiv) {
            dashboardInfoDiv.innerHTML = errorHtml;
        }
        if (settingsInfoDiv) {
            settingsInfoDiv.innerHTML = errorHtml;
        }
    }
    
    // Update sync button state based on database status
    updateSyncButtonState();
}

// OLID Cache Management Functions
async function refreshOlidCacheStats() {
    const statsDiv = document.getElementById('olid-cache-stats');
    const recentDiv = document.getElementById('olid-cache-recent');
    
    try {
        statsDiv.innerHTML = `
            <div class="d-flex align-items-center">
                <div class="spinner-border spinner-border-sm me-2" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <span>Loading cache statistics...</span>
            </div>
        `;
        
        const response = await fetch('/api/cache/olid/status');
        const data = await response.json();
        
        if (data.success) {
            const stats = data.stats;
            statsDiv.innerHTML = `
                <div class="row">
                    <div class="col-md-3">
                        <div class="text-center">
                            <h6 class="text-primary">${stats.total_entries}</h6>
                            <small class="text-muted">Cached Authors</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="text-center">
                            <h6 class="text-info">${stats.entries_with_olid}</h6>
                            <small class="text-muted">With OLID</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="text-center">
                            <h6 class="text-warning">${stats.entries_without_olid}</h6>
                            <small class="text-muted">Without OLID</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="text-center">
                            <h6 class="text-success">${stats.cache_hit_rate}%</h6>
                            <small class="text-muted">Cache Hit Rate</small>
                        </div>
                    </div>
                </div>
            `;
            
            // Show recent entries if we have any
            if (data.recent_entries && data.recent_entries.length > 0) {
                const recentTableBody = document.getElementById('recent-olid-entries');
                recentTableBody.innerHTML = data.recent_entries.map(entry => `
                    <tr>
                        <td>${escapeHtml(entry.author_name)}</td>
                        <td><code>${entry.olid || 'N/A'}</code></td>
                        <td>${new Date(entry.last_updated).toLocaleString()}</td>
                    </tr>
                `).join('');
                recentDiv.style.display = 'block';
            } else {
                recentDiv.style.display = 'none';
            }
            
        } else {
            throw new Error(data.error || 'Failed to load cache statistics');
        }
    } catch (error) {
        statsDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-times-circle"></i> 
                <strong>Error loading cache stats:</strong> ${error.message}
            </div>
        `;
        recentDiv.style.display = 'none';
    }
}

async function clearOlidCache() {
    if (!confirm('Are you sure you want to clear all cached OpenLibrary IDs? This will require fresh API calls for all authors.')) {
        return;
    }
    
    try {
        const response = await fetch('/api/cache/olid/clear', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(`Successfully cleared ${data.cleared_count} cached OLID entries`, 'success');
            await refreshOlidCacheStats(); // Refresh the display
        } else {
            throw new Error(data.error || 'Failed to clear cache');
        }
    } catch (error) {
        showToast(`Error clearing cache: ${error.message}`, 'danger');
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
    const pathInput = document.getElementById('init-metadata-path');
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

async function useFoundPath(path) {
    // Set the path in the initialization input field
    const initPathInput = document.getElementById('init-metadata-path');
    const forceReinitCheckbox = document.getElementById('force-reinit');
    
    if (initPathInput) {
        initPathInput.value = path;
    }
    
    try {
        // First, update the metadata path configuration
        const updateResponse = await fetch('/api/metadata/update_path', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ path: path })
        });
        
        const updateData = await updateResponse.json();
        
        if (!updateData.success) {
            showToast(`Failed to update metadata path: ${updateData.error}`, 'danger');
            return;
        }
        
        showToast('Metadata database path updated successfully!', 'success');
        
        // Refresh the metadata info display and sync button state
        await loadMetadataInfo();
        updateSyncButtonState();
        
        // Show confirmation and offer to initialize
        const message = `Metadata database path has been updated!\n\nPath: ${path}\n\nWould you like to initialize/update your application database now?`;
        
        if (confirm(message)) {
            // Check if we need to force re-initialization based on database status
            try {
                const statsResponse = await fetch('/api/stats');
                const statsData = await statsResponse.json();
                
                if (statsData.exists && forceReinitCheckbox) {
                    // Database exists, suggest force re-initialization
                    if (confirm('Application database already exists. Do you want to re-initialize it (this will overwrite existing data)?')) {
                        forceReinitCheckbox.checked = true;
                        initializeDatabase(path);
                    } else {
                        showToast('Database path updated. You can initialize later if needed.', 'info');
                    }
                } else {
                    initializeDatabase(path);
                }
            } catch (error) {
                // If we can't check database status, proceed with initialization
                initializeDatabase(path);
            }
        } else {
            showToast('Database path updated. You can initialize when ready.', 'info');
        }
        
    } catch (error) {
        showToast(`Error updating metadata path: ${error.message}`, 'danger');
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

async function syncDatabase() {
    const button = document.getElementById('sync-database-btn');
    const statusDiv = document.getElementById('sync-status');
    
    // Show loading state
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Syncing...';
    statusDiv.style.display = 'block';
    statusDiv.innerHTML = `
        <div class="alert alert-info">
            <div class="d-flex align-items-center">
                <div class="spinner-border spinner-border-sm me-2" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <span>Synchronizing with Calibre metadata... This may take a few minutes.</span>
            </div>
        </div>
    `;
    
    try {
        const response = await fetch('/api/database/sync', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            statusDiv.innerHTML = `
                <div class="alert alert-success">
                    <i class="fas fa-check-circle"></i> 
                    <strong>Database synchronization completed!</strong><br>
                    <small>${data.message}</small><br>
                    <small>New records: ${data.new_records || 'N/A'}</small><br>
                    <small>Updated records: ${data.updated_records || 'N/A'}</small><br>
                    <small>Total authors: ${data.total_authors || 'N/A'}</small>
                </div>
            `;
            
            // Refresh the database info displays
            await loadDatabaseInfo();
            await refreshOlidCacheStats();
            
            showToast('Database synchronization completed successfully!', 'success');
        } else {
            statusDiv.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-times-circle"></i> 
                    <strong>Synchronization failed:</strong> ${data.message || data.error}
                </div>
            `;
            showToast('Database synchronization failed', 'danger');
        }
    } catch (error) {
        statusDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-times-circle"></i> 
                <strong>Error during synchronization:</strong> ${error.message}
            </div>
        `;
        showToast('Database synchronization error', 'danger');
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-sync-alt"></i> Sync Database';
        
        // Re-check database status to update button state
        updateSyncButtonState();
    }
}

function updateSyncButtonState() {
    const syncButton = document.getElementById('sync-database-btn');
    if (!syncButton) return;
    
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            if (data.exists && data.stats) {
                // Database is initialized, enable sync button
                syncButton.disabled = false;
                syncButton.title = 'Sync with latest Calibre metadata';
            } else {
                // Database not initialized, keep button disabled
                syncButton.disabled = true;
                syncButton.title = 'Initialize database first before syncing';
            }
        })
        .catch(error => {
            console.error('Error checking database status:', error);
            syncButton.disabled = true;
            syncButton.title = 'Unable to check database status';
        });
}