/**
 * View management functions for the Calibre Monitor application
 */

import { 
    hideAllViews, 
    showLoading, 
    updateActiveNav, 
    showToast,
    escapeHtml 
} from './utils.js';
import { 
    apiRequest,
    loadStats, 
    loadRecentlyProcessedAuthors, 
    loadAuthors, 
    loadMissingBooks, 
    loadMissingBooksStats,
    loadAuthorDetail,
    loadDatabaseInfo,
    loadMetadataInfo,
    refreshOlidCacheStats,
    ignoreBook,
    unignoreBook,
    getBookIgnoreStatus
} from './api.js';

/**
 * Dashboard View Functions
 */
export async function showDashboard() {
    hideAllViews();
    showLoading(true);
    
    try {
        // Load dashboard stats and database info
        const [stats, recentlyProcessedAuthors] = await Promise.all([
            loadStats(),
            loadRecentlyProcessedAuthors()
        ]);
        
        // Load database info
        await loadDatabaseInfo();
        
        // Update stats cards
        updateDashboardStats(stats);
        
        // Update missing books database statistics
        await updateMissingBooksStats();
        
        // Update recently processed authors
        const recentAuthors = Array.isArray(recentlyProcessedAuthors) ? recentlyProcessedAuthors.slice(0, 10) : [];
        updateRecentAuthors(recentAuthors);
        
        document.getElementById('dashboard-view').style.display = 'block';
        
        // Update active nav
        updateActiveNav('dashboard');
        
    } catch (error) {
        showToast('Failed to load dashboard data', 'danger');
        updateRecentAuthors([]);
    } finally {
        showLoading(false);
    }
}

/**
 * Authors View Functions
 */
export async function showAuthors() {
    hideAllViews();
    showLoading(true);
    
    try {
        await loadAuthorsData();
        document.getElementById('authors-view').style.display = 'block';
        
        // Initialize search for accordion
        setupAccordionSearch();
        
        // Update active nav
        updateActiveNav('authors');
        
    } catch (error) {
        showToast('Failed to load authors', 'danger');
    } finally {
        showLoading(false);
    }
}

/**
 * Missing Books View Functions
 */
export async function showMissing() {
    hideAllViews();
    showLoading(true);
    
    try {
        await loadMissingBooksData();
        document.getElementById('missing-view').style.display = 'block';
        
        // Update active nav
        updateActiveNav('missing');
        
    } catch (error) {
        showToast('Failed to load missing books', 'danger');
    } finally {
        showLoading(false);
    }
}

/**
 * Settings View Functions
 */
export async function showSettings() {
    hideAllViews();
    document.getElementById('settings-view').style.display = 'block';
    
    // Update active nav
    updateActiveNav('settings');
    
    // Load settings data
    await loadMetadataInfo();
    await loadDatabaseInfo();
    await refreshOlidCacheStats();
}

/**
 * Author Detail View Functions
 */
export async function showAuthorDetail(authorName) {
    console.log('showAuthorDetail called with:', authorName);
    hideAllViews();
    showLoading(true);
    
    try {
        console.log('Loading author detail for:', authorName);
        const authorData = await loadAuthorDetail(authorName);
        console.log('Author data received:', authorData);
        
        // Update author detail view
        updateAuthorDetailView(authorData);
        
        const authorDetailView = document.getElementById('author-detail-view');
        if (authorDetailView) {
            authorDetailView.style.display = 'block';
            console.log('Author detail view displayed');
        } else {
            console.error('Author detail view element not found');
        }
        
        // Store current author for refresh
        window.currentAuthor = authorName;
        
    } catch (error) {
        console.error('Error loading author detail:', error);
        showToast(`Failed to load author: ${authorName}`, 'danger');
    } finally {
        showLoading(false);
    }
}

/**
 * Load books for a specific author in accordion
 */
export async function loadAuthorBooks(accordionBody, authorName) {
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
                    <div class="d-flex align-items-center ms-2">
                        ${book.status === 'missing_local' ? `
                            <button class="btn btn-sm btn-outline-danger me-2" 
                                    onclick="handleIgnoreBook('${escapeHtml(authorName)}', '${escapeHtml(book.title)}')"
                                    title="Ignore this missing book">
                                <i class="fas fa-times"></i>
                            </button>
                        ` : ''}
                        <i class="${statusIcon} ${statusClass}" 
                           title="${statusText}"
                           data-bs-toggle="tooltip"></i>
                    </div>
                </div>
            `;
        }).join('');
        
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

/**
 * Helper Functions for View Data Loading
 */
export async function loadAuthorsData(page = 1, search = '') {
    const response = await loadAuthors(page, search);
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
}

async function loadMissingBooksData() {
    const missingBooks = await loadMissingBooks();
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
                            onclick="searchAuthorIRC('${escapeHtml(author)}')" 
                            title="Search IRC for this author's books">
                        <i class="fas fa-search"></i> IRC Search
                    </button>
                </div>
            </div>
            <div class="card-body">
                <div class="row">
                    ${books.map(book => {
                        const isNew = book.discovered_date && 
                                     new Date(book.discovered_date) > new Date(Date.now() - 7*24*60*60*1000);
                        const discoveredDate = book.discovered_date ? 
                                             new Date(book.discovered_date).toLocaleDateString() : null;
                        
                        return `
                            <div class="col-md-6 mb-2">
                                <div class="d-flex justify-content-between align-items-start">
                                    <div class="flex-grow-1">
                                        <div class="d-flex align-items-center">
                                            <span class="text-truncate">${escapeHtml(book.title)}</span>
                                            ${isNew ? '<span class="badge bg-primary badge-sm ms-1">New</span>' : '<span class="badge bg-secondary badge-sm ms-1">Legacy</span>'}
                                        </div>
                                        ${discoveredDate ? `<small class="text-muted d-block mt-1"><i class="fas fa-calendar"></i> ${discoveredDate}</small>` : ''}
                                        <small class="text-muted d-block"><i class="fas fa-database"></i> ${book.source || 'legacy'}</small>
                                    </div>
                                    <div class="ms-2">
                                        <button class="btn btn-sm btn-outline-danger" 
                                                onclick="handleIgnoreBook('${escapeHtml(author)}', '${escapeHtml(book.title)}')"
                                                title="Ignore this book">
                                            <i class="fas fa-times"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        </div>
    `).join('');
}

/**
 * Helper Functions for View Updates
 */
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

async function updateMissingBooksStats() {
    try {
        const stats = await loadMissingBooksStats();
        
        // Update missing books view statistics
        const totalEl = document.getElementById('missing-stats-total');
        const authorsEl = document.getElementById('missing-stats-authors');
        const recentEl = document.getElementById('missing-stats-recent');
        const sourcesEl = document.getElementById('missing-stats-sources');
        
        if (totalEl) totalEl.textContent = stats.total_missing;
        if (authorsEl) authorsEl.textContent = stats.authors_with_missing;
        if (recentEl) recentEl.textContent = stats.recent_discoveries;
        if (sourcesEl) sourcesEl.textContent = stats.sources ? stats.sources.join(', ') : 'OpenLibrary';
        
        // Update dashboard missing books database statistics cards
        const missingDbTotal = document.querySelector('[data-stat="missing-db-total"]');
        const missingDbRecent = document.querySelector('[data-stat="missing-db-recent"]');
        
        if (missingDbTotal) missingDbTotal.textContent = stats.total_missing;
        if (missingDbRecent) missingDbRecent.textContent = stats.recent_discoveries;
        
    } catch (error) {
        console.warn('Could not load missing books statistics:', error);
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

function updateAuthorDetailView(authorData) {
    console.log('updateAuthorDetailView called with:', authorData);
    
    // Update author name
    const authorNameEl = document.getElementById('author-name');
    if (authorNameEl) {
        authorNameEl.textContent = authorData.author;
        console.log('Updated author name to:', authorData.author);
    } else {
        console.error('author-name element not found');
    }
    
    // Update book counts
    const allBooksCountEl = document.getElementById('all-books-count');
    const missingBooksCountEl = document.getElementById('missing-books-count');
    
    if (allBooksCountEl) {
        allBooksCountEl.textContent = authorData.total_books || 0;
        console.log('Updated all books count to:', authorData.total_books);
    } else {
        console.error('all-books-count element not found');
    }
    
    if (missingBooksCountEl) {
        missingBooksCountEl.textContent = authorData.missing_count || 0;
        console.log('Updated missing books count to:', authorData.missing_count);
    } else {
        console.error('missing-books-count element not found');
    }
    
    // Update stats
    updateAuthorStats(authorData);
    
    // Update books tables
    updateAuthorBooksTable(authorData.books || []);
    updateAuthorMissingBooksTable(authorData.missing_books || []);
}

function updateAuthorStats(authorData) {
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

function updateAuthorBooksTable(books) {
    console.log('updateAuthorBooksTable called with:', books);
    const tbody = document.getElementById('all-books-list');
    if (!tbody) {
        console.error('all-books-list element not found');
        return;
    }
    
    const html = books.map(book => `
        <tr>
            <td>${escapeHtml(book.title)}</td>
            <td>
                <span class="badge bg-${book.missing ? 'warning' : 'success'}">
                    ${book.missing ? 'Missing' : 'Available'}
                </span>
            </td>
            <td>
                ${book.missing ? `
                    <button class="btn btn-sm btn-outline-danger" 
                            onclick="handleIgnoreBook('${escapeHtml(window.currentAuthor)}', '${escapeHtml(book.title)}')"
                            title="Ignore this missing book">
                        <i class="fas fa-times"></i> Ignore
                    </button>
                ` : ''}
            </td>
        </tr>
    `).join('');
    
    tbody.innerHTML = html;
    console.log('Updated books table with', books.length, 'books');
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
            <td>
                <button class="btn btn-sm btn-outline-danger" 
                        onclick="handleIgnoreBook('${escapeHtml(window.currentAuthor)}', '${escapeHtml(book.title)}')"
                        title="Ignore this missing book">
                    <i class="fas fa-times"></i> Ignore
                </button>
            </td>
        </tr>
    `).join('');
}

/**
 * Pagination and Search Functions
 */
function updatePaginationControls(pagination, search = '') {
    const paginationContainer = document.getElementById('authors-pagination');
    if (!paginationContainer) return;
    
    const paginationList = paginationContainer.querySelector('.pagination');
    if (!paginationList) return;
    
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
            <a class="page-link" href="#" onclick="loadAuthorsData(${currentPage - 1}, '${search}'); return false;">
                <i class="fas fa-chevron-left"></i>
            </a>
        </li>
    `;
    
    // Page numbers logic
    const maxVisible = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    
    if (endPage - startPage < maxVisible - 1) {
        startPage = Math.max(1, endPage - maxVisible + 1);
    }
    
    // First page and ellipsis
    if (startPage > 1) {
        paginationHTML += `
            <li class="page-item">
                <a class="page-link" href="#" onclick="loadAuthorsData(1, '${search}'); return false;">1</a>
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
                <a class="page-link" href="#" onclick="loadAuthorsData(${i}, '${search}'); return false;">${i}</a>
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
                <a class="page-link" href="#" onclick="loadAuthorsData(${totalPages}, '${search}'); return false;">${totalPages}</a>
            </li>
        `;
    }
    
    // Next button
    paginationHTML += `
        <li class="page-item ${currentPage >= totalPages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="loadAuthorsData(${currentPage + 1}, '${search}'); return false;">
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

function setupAccordionSearch() {
    const searchInput = document.getElementById('author-search');
    if (searchInput) {
        searchInput.removeEventListener('keyup', filterAuthors);
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
}

/**
 * Select author from accordion and update UI
 */
export function selectAuthorFromAccordion(authorName) {
    window.selectedAuthor = authorName;
    
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

/**
 * Handle ignoring a book
 * @param {string} author - Author name
 * @param {string} title - Book title
 */
async function handleIgnoreBook(author, title) {
    try {
        showLoading(true);
        
        // Show confirmation dialog
        const confirmed = confirm(`Are you sure you want to ignore "${title}" by ${author}? This book will be removed from the missing books list.`);
        
        if (!confirmed) {
            showLoading(false);
            return;
        }
        
        // Call the ignore book API
        await ignoreBook(author, title);
        
        // Show success message
        showToast(`Successfully ignored "${title}" by ${author}`, 'success');
        
        // Refresh the current view
        await refreshCurrentView();
        
    } catch (error) {
        console.error('Error ignoring book:', error);
        showToast(`Failed to ignore book: ${error.message}`, 'error');
    } finally {
        showLoading(false);
    }
}

/**
 * Refresh the current view based on the active page
 */
async function refreshCurrentView() {
    const activeNav = document.querySelector('.nav-link.active');
    
    if (!activeNav) return;
    
    const activeView = activeNav.getAttribute('data-view');
    
    switch (activeView) {
        case 'dashboard':
            await showDashboard();
            break;
        case 'authors':
            await showAuthors();
            break;
        case 'missing':
            await showMissing();
            break;
        case 'settings':
            await showSettings();
            break;
    }
    
    // If we're on author detail page, reload the author
    if (window.currentAuthor) {
        await showAuthorDetail(window.currentAuthor);
    }
}

// Global exports for backwards compatibility
window.showDashboard = showDashboard;
window.showAuthors = showAuthors;
window.showMissing = showMissing;
window.showSettings = showSettings;
window.showAuthorDetail = showAuthorDetail;
window.loadAuthorBooks = loadAuthorBooks;
window.selectAuthorFromAccordion = selectAuthorFromAccordion;
window.handleIgnoreBook = handleIgnoreBook;
