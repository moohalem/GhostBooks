/**
 * Main entry point for the Calibre Monitor application
 * This file imports all modules and initializes the application
 */

// Import all modules
import * as Utils from './modules/utils.js';
import * as API from './modules/api.js';
import * as Views from './modules/views.js';
import { IRCSearchManager, AutoRefreshManager, ProgressModalManager } from './modules/managers.js';

// Global state
let ircSearchManager = null;
let autoRefreshManager = null;
let progressModalManager = null;

/**
 * Initialize the application
 */
function initializeApp() {
    console.log('Initializing Calibre Monitor application...');
    console.log('Loading modules:', { Utils, API, Views });
    
    // Initialize managers
    ircSearchManager = new IRCSearchManager();
    autoRefreshManager = new AutoRefreshManager();
    progressModalManager = new ProgressModalManager();
    
    console.log('Managers initialized:', { ircSearchManager, autoRefreshManager, progressModalManager });
    
    // Set up initial navigation
    setupNavigation();
    
    // Set up search functionality
    setupSearch();
    
    // Set up refresh functionality
    setupRefreshHandlers();
    
    // Set up IRC search functionality
    setupIRCSearch();
    
    // Set up population tracking
    setupPopulationTracking();
    
    // Set up global keyboard shortcuts
    setupKeyboardShortcuts();
    
    // Show initial view
    Views.showDashboard();
    
    console.log('Application initialized successfully');
}

/**
 * Set up navigation event handlers
 */
function setupNavigation() {
    // Navigation click handlers
    document.addEventListener('click', (event) => {
        const target = event.target.closest('[data-view]');
        if (target) {
            event.preventDefault();
            const view = target.getAttribute('data-view');
            
            switch (view) {
                case 'dashboard':
                    Views.showDashboard();
                    break;
                case 'authors':
                    Views.showAuthors();
                    break;
                case 'missing':
                    Views.showMissing();
                    break;
                case 'settings':
                    Views.showSettings();
                    break;
            }
        }
    });
}

/**
 * Set up search functionality with autocomplete
 */
function setupSearch() {
    console.log('Setting up search functionality...');
    const searchInput = document.getElementById('author-search');
    const autocompleteDropdown = document.getElementById('autocomplete-dropdown');
    const clearButton = document.getElementById('clear-search');
    const searchButton = document.getElementById('search-btn');
    
    console.log('Search elements found:', { 
        searchInput: !!searchInput, 
        autocompleteDropdown: !!autocompleteDropdown,
        clearButton: !!clearButton,
        searchButton: !!searchButton
    });
    
    if (searchInput && autocompleteDropdown) {
        console.log('Creating autocomplete instance...');
        // Create autocomplete instance
        const autocomplete = new Utils.Autocomplete(searchInput, autocompleteDropdown, {
            minLength: 2,
            delay: 300,
            maxResults: 10,
            searchFunction: async (query) => {
                console.log('Autocomplete search for:', query);
                try {
                    const response = await API.searchAuthorsAutocomplete(query, 10);
                    console.log('Autocomplete response:', response);
                    return {
                        suggestions: response.suggestions || [],
                        type: response.type,
                        message: response.message
                    };
                } catch (error) {
                    console.error('Autocomplete search error:', error);
                    return { suggestions: [] };
                }
            },
            onSelect: (item) => {
                console.log('Author selected from autocomplete:', item);
                // When an author is selected from autocomplete, show their details
                if (item.name) {
                    Views.showAuthorDetail(item.name);
                } else {
                    // Fallback to regular search
                    performAuthorSearch(item.name || searchInput.value);
                }
            }
        });
        
        // Show/hide clear button based on input content
        searchInput.addEventListener('input', (e) => {
            if (clearButton) {
                clearButton.style.display = e.target.value.trim() ? 'block' : 'none';
            }
        });
        
        // Clear button functionality
        if (clearButton) {
            clearButton.addEventListener('click', () => {
                searchInput.value = '';
                clearButton.style.display = 'none';
                searchInput.focus();
                // Reset to show all authors
                Views.loadAuthorsData(1, '');
            });
        }
        
        // Search button functionality
        if (searchButton) {
            searchButton.addEventListener('click', () => {
                performAuthorSearch(searchInput.value);
            });
        }
        
        // Also keep the regular search functionality for Enter key
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                performAuthorSearch(e.target.value);
            }
        });
        
        // Store reference for later use
        window.authorAutocomplete = autocomplete;
    }
}

/**
 * Perform author search
 */
async function performAuthorSearch(searchTerm) {
    try {
        Utils.showLoading(true);
        const response = await API.loadAuthors(1, searchTerm);
        // Update authors view with search results
        await Views.loadAuthorsData(1, searchTerm);
    } catch (error) {
        Utils.showToast('Search failed', 'danger');
        console.error('Search error:', error);
    } finally {
        Utils.showLoading(false);
    }
}

/**
 * Set up refresh handlers
 */
function setupRefreshHandlers() {
    // Auto-refresh toggle
    const autoRefreshToggle = document.getElementById('auto-refresh-toggle');
    if (autoRefreshToggle) {
        autoRefreshToggle.addEventListener('change', (e) => {
            if (e.target.checked) {
                autoRefreshManager.startAutoRefresh();
            } else {
                autoRefreshManager.stopAutoRefresh();
            }
        });
    }
    
    // Manual refresh buttons
    document.addEventListener('click', (event) => {
        if (event.target.matches('[data-refresh]')) {
            event.preventDefault();
            const refreshType = event.target.getAttribute('data-refresh');
            handleRefresh(refreshType);
        }
    });
}

/**
 * Handle refresh actions
 */
async function handleRefresh(type) {
    switch (type) {
        case 'dashboard':
            await Views.showDashboard();
            break;
        case 'authors':
            await Views.showAuthors();
            break;
        case 'missing':
            await Views.showMissing();
            break;
        case 'author':
            if (window.currentAuthor) {
                await refreshAuthor(window.currentAuthor);
            }
            break;
    }
}

/**
 * Set up IRC search functionality
 */
function setupIRCSearch() {
    document.addEventListener('click', (event) => {
        if (event.target.matches('[data-irc-search]') || 
            event.target.closest('[data-irc-search]')) {
            event.preventDefault();
            const button = event.target.matches('[data-irc-search]') ? 
                          event.target : event.target.closest('[data-irc-search]');
            const author = button.getAttribute('data-irc-search');
            searchAuthorIRC(author);
        }
    });
}

/**
 * Set up population tracking
 */
function setupPopulationTracking() {
    // Population buttons
    document.addEventListener('click', (event) => {
        if (event.target.matches('[data-populate]')) {
            event.preventDefault();
            const populateType = event.target.getAttribute('data-populate');
            handlePopulation(populateType);
        }
    });
}

/**
 * Handle population actions
 */
async function handlePopulation(type) {
    switch (type) {
        case 'metadata':
            await populateMetadata();
            break;
        case 'library':
            await populateLibrary();
            break;
    }
}

/**
 * Set up global keyboard shortcuts
 */
function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Ctrl+K or Cmd+K to focus search
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            const searchInput = document.getElementById('author-search');
            if (searchInput) {
                searchInput.focus();
                Utils.showToast('Search focused (Ctrl+K)', 'info');
            }
        }
        
        // Escape to clear search and show all authors
        if (e.key === 'Escape') {
            const searchInput = document.getElementById('author-search');
            if (searchInput && document.activeElement === searchInput) {
                searchInput.blur();
                if (searchInput.value.trim()) {
                    searchInput.value = '';
                    const clearButton = document.getElementById('clear-search');
                    if (clearButton) clearButton.style.display = 'none';
                    Views.loadAuthorsData(1, '');
                    Utils.showToast('Search cleared', 'info');
                }
            }
        }
    });
}

/**
 * Global functions for backwards compatibility with onclick handlers
 */
window.showDashboard = Views.showDashboard;
window.showAuthors = Views.showAuthors;
window.showMissing = Views.showMissing;
window.showSettings = Views.showSettings;
window.showAuthorDetail = Views.showAuthorDetail;

// Author-related functions
window.refreshAuthor = async function(authorName) {
    try {
        Utils.showLoading(true);
        await API.processAuthor(authorName);
        await Views.showAuthorDetail(authorName);
        Utils.showToast(`Author ${authorName} refreshed successfully`, 'success');
    } catch (error) {
        Utils.showToast(`Failed to refresh author: ${authorName}`, 'danger');
        console.error('Error refreshing author:', error);
    } finally {
        Utils.showLoading(false);
    }
};

window.searchAuthorIRC = function(authorName) {
    if (ircSearchManager) {
        ircSearchManager.searchAuthor(authorName);
    }
};

// Accordion functions
window.selectAuthorFromAccordion = function(authorName) {
    // This is handled by the accordion expansion event
    console.log('Selected author from accordion:', authorName);
};

// Population functions
window.populateMetadata = async function() {
    if (progressModalManager) {
        progressModalManager.startPopulation('metadata');
    }
};

window.populateLibrary = async function() {
    if (progressModalManager) {
        progressModalManager.startPopulation('library');
    }
};

// Additional global functions for onclick handlers
window.refreshStats = async function() {
    await Views.showDashboard();
};

window.populateMissingBooksDatabase = async function() {
    if (progressModalManager) {
        progressModalManager.startPopulation('missing-books');
    }
};

window.clearMissingBooksDatabase = async function() {
    if (confirm('Are you sure you want to clear the missing books database? This action cannot be undone.')) {
        try {
            Utils.showLoading(true);
            await API.clearMissingBooksDatabase();
            Utils.showToast('Missing books database cleared successfully', 'success');
            await Views.showDashboard();
        } catch (error) {
            Utils.showToast('Failed to clear missing books database', 'danger');
            console.error('Error clearing missing books database:', error);
        } finally {
            Utils.showLoading(false);
        }
    }
};

window.loadAuthors = async function() {
    await Views.showAuthors();
};

window.loadMissingBooks = async function() {
    await Views.showMissing();
};

window.updateAuthorFromAPI = async function() {
    // This function needs to be implemented based on selected author
    const selectedAuthor = window.selectedAuthor || window.currentAuthor;
    if (selectedAuthor) {
        await window.refreshAuthor(selectedAuthor);
    } else {
        Utils.showToast('No author selected', 'warning');
    }
};

window.searchMissingOnIRC = async function() {
    const selectedAuthor = window.selectedAuthor || window.currentAuthor;
    if (selectedAuthor) {
        window.searchAuthorIRC(selectedAuthor);
    } else {
        Utils.showToast('No author selected', 'warning');
    }
};

window.clearAuthorSelection = function() {
    window.selectedAuthor = null;
    window.currentAuthor = null;
    // Clear any UI selection indicators
    const selectedItems = document.querySelectorAll('.author-selected');
    selectedItems.forEach(item => item.classList.remove('author-selected'));
};

window.locateMetadataDb = async function() {
    try {
        Utils.showLoading(true);
        const result = await API.locateMetadataDb();
        if (result.found) {
            Utils.showToast('Metadata database located successfully', 'success');
            await Views.showSettings();
        } else {
            Utils.showToast('Metadata database not found', 'warning');
        }
    } catch (error) {
        Utils.showToast('Failed to locate metadata database', 'danger');
        console.error('Error locating metadata database:', error);
    } finally {
        Utils.showLoading(false);
    }
};

window.verifyMetadataPath = async function() {
    try {
        Utils.showLoading(true);
        const result = await API.verifyMetadataPath();
        if (result.valid) {
            Utils.showToast('Metadata path is valid', 'success');
        } else {
            Utils.showToast('Metadata path is invalid', 'danger');
        }
    } catch (error) {
        Utils.showToast('Failed to verify metadata path', 'danger');
        console.error('Error verifying metadata path:', error);
    } finally {
        Utils.showLoading(false);
    }
};

window.initializeDatabase = async function() {
    if (confirm('Are you sure you want to initialize the database? This will clear existing data.')) {
        try {
            Utils.showLoading(true);
            await API.initializeDatabase();
            Utils.showToast('Database initialized successfully', 'success');
            await Views.showDashboard();
        } catch (error) {
            Utils.showToast('Failed to initialize database', 'danger');
            console.error('Error initializing database:', error);
        } finally {
            Utils.showLoading(false);
        }
    }
};

window.searchSingleBook = async function(author, title) {
    if (ircSearchManager) {
        ircSearchManager.searchSingleBook(author, title);
    }
};

// Modal management functions
window.minimizeProgressModal = function() {
    const modal = document.getElementById('populationProgressModal');
    if (modal) {
        modal.style.display = 'none';
        Utils.showToast('Population progress minimized', 'info');
    }
};

window.clearProgressLog = function() {
    const progressLog = document.getElementById('progress-log');
    if (progressLog) {
        progressLog.innerHTML = '';
        Utils.showToast('Progress log cleared', 'info');
    }
};

window.cancelPopulation = async function() {
    if (progressModalManager) {
        await progressModalManager.cancel();
    }
};

window.closeProgressModal = function() {
    if (progressModalManager) {
        progressModalManager.close();
    }
};

// Initialize application when DOM is loaded
document.addEventListener('DOMContentLoaded', initializeApp);

// Export for potential use by other scripts
export { initializeApp };
