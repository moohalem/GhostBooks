/**
 * IRC Search Manager
 * Manages IRC sessions and provides two-tier search functionality
 */

import { 
    showToast,
    showModal,
    hideModal
} from './utils.js';
import { 
    createIRCSession,
    getIRCSessionStatus,
    closeIRCSession,
    searchAuthorLevelIRC,
    searchTitleLevelIRC,
    smartSearchAndDownloadIRC,
    downloadWithFallbackIRC
} from './api.js';

class IRCManager {
    constructor() {
        this.currentSession = null;
        this.isConnecting = false;
        this.activeSearches = new Map(); // Track ongoing searches
    }

    /**
     * Get or create an IRC session
     */
    async getSession() {
        if (this.currentSession) {
            // Check if session is still valid
            try {
                const status = await getIRCSessionStatus(this.currentSession);
                if (status.success && status.status.connected) {
                    return this.currentSession;
                }
            } catch (e) {
                console.warn('Session validation failed:', e);
            }
        }

        // Create new session
        return await this.createNewSession();
    }

    /**
     * Create a new IRC session
     */
    async createNewSession() {
        if (this.isConnecting) {
            throw new Error('Already connecting to IRC');
        }

        this.isConnecting = true;
        showToast('Connecting to IRC...', 'info');

        try {
            const result = await createIRCSession();
            if (result.success) {
                this.currentSession = result.session_id;
                showToast('Connected to IRC successfully', 'success');
                return this.currentSession;
            } else {
                throw new Error(result.error || 'Failed to create IRC session');
            }
        } catch (error) {
            showToast(`IRC connection failed: ${error.message}`, 'danger');
            throw error;
        } finally {
            this.isConnecting = false;
        }
    }

    /**
     * Close current IRC session
     */
    async closeSession() {
        if (this.currentSession) {
            try {
                await closeIRCSession(this.currentSession);
                this.currentSession = null;
                showToast('IRC session closed', 'info');
            } catch (error) {
                console.warn('Error closing IRC session:', error);
            }
        }
    }

    /**
     * Search for all missing books by an author (author-level search)
     */
    async searchAuthorBooks(authorName) {
        const searchKey = `author:${authorName}`;
        
        if (this.activeSearches.has(searchKey)) {
            showToast('Search already in progress for this author', 'warning');
            return;
        }

        try {
            this.activeSearches.set(searchKey, true);
            
            // Show progress modal
            this.showSearchModal(authorName, null, 'author');
            
            const sessionId = await this.getSession();
            const result = await searchAuthorLevelIRC(sessionId, authorName);

            if (result.success) {
                this.handleAuthorSearchResults(authorName, result);
            } else {
                throw new Error(result.error || 'Author search failed');
            }

        } catch (error) {
            showToast(`Author search failed: ${error.message}`, 'danger');
            hideModal('irc-search-modal');
        } finally {
            this.activeSearches.delete(searchKey);
        }
    }

    /**
     * Search for a specific book (title-level search)
     */
    async searchSpecificBook(authorName, bookTitle) {
        const searchKey = `title:${authorName}:${bookTitle}`;
        
        if (this.activeSearches.has(searchKey)) {
            showToast('Search already in progress for this book', 'warning');
            return;
        }

        try {
            this.activeSearches.set(searchKey, true);
            
            // Show progress modal
            this.showSearchModal(authorName, bookTitle, 'title');
            
            const sessionId = await this.getSession();
            const result = await searchTitleLevelIRC(sessionId, authorName, bookTitle);

            if (result.success) {
                this.handleTitleSearchResults(authorName, bookTitle, result);
            } else {
                throw new Error(result.error || 'Title search failed');
            }

        } catch (error) {
            showToast(`Book search failed: ${error.message}`, 'danger');
            hideModal('irc-search-modal');
        } finally {
            this.activeSearches.delete(searchKey);
        }
    }

    /**
     * Handle author-level search results
     */
    handleAuthorSearchResults(authorName, result) {
        const uniqueBooks = result.unique_books || [];
        
        if (uniqueBooks.length === 0) {
            showToast(`No books found for ${authorName}`, 'warning');
            hideModal('irc-search-modal');
            return;
        }

        // Show results modal with download options
        this.showAuthorResultsModal(authorName, uniqueBooks);
    }

    /**
     * Handle title-level search results
     */
    handleTitleSearchResults(authorName, bookTitle, result) {
        const candidates = result.server_candidates || [];
        
        if (candidates.length === 0) {
            showToast(`No copies found for "${bookTitle}" by ${authorName}`, 'warning');
            hideModal('irc-search-modal');
            return;
        }

        // Show download options or start automatic download
        this.showTitleResultsModal(authorName, bookTitle, candidates);
    }

    /**
     * Show search progress modal
     */
    showSearchModal(authorName, bookTitle, searchType) {
        const modalHtml = `
            <div class="modal fade" id="irc-search-modal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-search"></i> IRC Search in Progress
                            </h5>
                        </div>
                        <div class="modal-body text-center">
                            <div class="spinner-border text-primary mb-3" role="status">
                                <span class="visually-hidden">Searching...</span>
                            </div>
                            <h6>${searchType === 'author' ? 'Author-Level Search' : 'Title-Level Search'}</h6>
                            <p class="mb-1"><strong>Author:</strong> ${authorName}</p>
                            ${bookTitle ? `<p class="mb-3"><strong>Book:</strong> ${bookTitle}</p>` : ''}
                            <small class="text-muted">
                                ${searchType === 'author' 
                                    ? 'Finding unique books by this author...' 
                                    : 'Finding server options for this book...'
                                }
                            </small>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if any
        const existingModal = document.getElementById('irc-search-modal');
        if (existingModal) {
            existingModal.remove();
        }

        // Add new modal
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('irc-search-modal'));
        modal.show();
    }

    /**
     * Show author search results modal
     */
    showAuthorResultsModal(authorName, uniqueBooks) {
        hideModal('irc-search-modal');
        
        const booksHtml = uniqueBooks.slice(0, 10).map(book => `
            <div class="list-group-item d-flex justify-content-between align-items-center">
                <div>
                    <strong>${book.title}</strong><br>
                    <small class="text-muted">${book.format} • ${book.size} • ${book.server}</small>
                </div>
                <button class="btn btn-sm btn-primary" 
                        onclick="ircManager.downloadSpecificBook('${book.download_command}', '${book.title}')">
                    <i class="fas fa-download"></i> Download
                </button>
            </div>
        `).join('');

        const modalHtml = `
            <div class="modal fade" id="irc-results-modal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-book"></i> Found ${uniqueBooks.length} Unique Books
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <p><strong>Author:</strong> ${authorName}</p>
                            <div class="list-group">
                                ${booksHtml}
                            </div>
                            ${uniqueBooks.length > 10 ? 
                                `<p class="text-muted mt-2">Showing first 10 of ${uniqueBooks.length} books found.</p>` : ''
                            }
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                            <button type="button" class="btn btn-primary" 
                                    onclick="ircManager.downloadAllAuthorBooks('${authorName}', ${JSON.stringify(uniqueBooks).replace(/'/g, '&#39;')})">
                                <i class="fas fa-download"></i> Download All (Top 5)
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if any
        const existingModal = document.getElementById('irc-results-modal');
        if (existingModal) {
            existingModal.remove();
        }

        // Add and show modal
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        const modal = new bootstrap.Modal(document.getElementById('irc-results-modal'));
        modal.show();
    }

    /**
     * Show title search results modal
     */
    showTitleResultsModal(authorName, bookTitle, candidates) {
        hideModal('irc-search-modal');
        
        const candidatesHtml = candidates.map((candidate, index) => `
            <div class="list-group-item d-flex justify-content-between align-items-center">
                <div>
                    <strong>Server:</strong> ${candidate.server}<br>
                    <small class="text-muted">${candidate.format} • ${candidate.size}</small>
                </div>
                <button class="btn btn-sm btn-primary" 
                        onclick="ircManager.downloadFromCandidate(${JSON.stringify(candidate).replace(/'/g, '&#39;')}, '${bookTitle}')">
                    <i class="fas fa-download"></i> Download
                </button>
            </div>
        `).join('');

        const modalHtml = `
            <div class="modal fade" id="irc-title-results-modal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-server"></i> Found ${candidates.length} Server Options
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <p><strong>Book:</strong> ${bookTitle}</p>
                            <p><strong>Author:</strong> ${authorName}</p>
                            <div class="list-group">
                                ${candidatesHtml}
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                            <button type="button" class="btn btn-primary" 
                                    onclick="ircManager.downloadWithFallback(${JSON.stringify(candidates).replace(/'/g, '&#39;')}, '${bookTitle}')">
                                <i class="fas fa-download"></i> Auto Download (with fallback)
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if any
        const existingModal = document.getElementById('irc-title-results-modal');
        if (existingModal) {
            existingModal.remove();
        }

        // Add and show modal
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        const modal = new bootstrap.Modal(document.getElementById('irc-title-results-modal'));
        modal.show();
    }

    /**
     * Download a specific book
     */
    async downloadSpecificBook(downloadCommand, bookTitle) {
        try {
            showToast(`Starting download: ${bookTitle}`, 'info');
            // Implementation for individual download
            // This would call the existing download API endpoint
        } catch (error) {
            showToast(`Download failed: ${error.message}`, 'danger');
        }
    }

    /**
     * Download multiple books for an author
     */
    async downloadAllAuthorBooks(authorName, uniqueBooks) {
        try {
            showToast(`Starting bulk download for ${authorName}`, 'info');
            hideModal('irc-results-modal');
            
            // Download top 5 books
            const topBooks = uniqueBooks.slice(0, 5);
            for (const book of topBooks) {
                await this.downloadSpecificBook(book.download_command, book.title);
                // Add delay between downloads
                await new Promise(resolve => setTimeout(resolve, 2000));
            }
            
            showToast(`Completed bulk download for ${authorName}`, 'success');
        } catch (error) {
            showToast(`Bulk download failed: ${error.message}`, 'danger');
        }
    }

    /**
     * Download with automatic fallback
     */
    async downloadWithFallback(candidates, bookTitle) {
        try {
            showToast(`Starting download with fallback: ${bookTitle}`, 'info');
            hideModal('irc-title-results-modal');
            
            const sessionId = await this.getSession();
            const result = await downloadWithFallbackIRC(sessionId, candidates);
            
            if (result.success) {
                showToast(`Download completed: ${bookTitle}`, 'success');
            } else {
                throw new Error(result.error || 'Download failed');
            }
        } catch (error) {
            showToast(`Download failed: ${error.message}`, 'danger');
        }
    }

    /**
     * Download from specific candidate
     */
    async downloadFromCandidate(candidate, bookTitle) {
        try {
            showToast(`Downloading from ${candidate.server}: ${bookTitle}`, 'info');
            await this.downloadWithFallback([candidate], bookTitle);
        } catch (error) {
            showToast(`Download failed: ${error.message}`, 'danger');
        }
    }
}

// Create global IRC manager instance
const ircManager = new IRCManager();

// Global functions for onclick handlers
window.ircManager = ircManager;
window.searchAuthorOnIRC = (authorName) => ircManager.searchAuthorBooks(authorName);
window.searchTitleOnIRC = (authorName, bookTitle) => ircManager.searchSpecificBook(authorName, bookTitle);

export default ircManager;
