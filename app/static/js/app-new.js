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
    
    // Initialize managers
    ircSearchManager = new IRCSearchManager();
    autoRefreshManager = new AutoRefreshManager();
    progressModalManager = new ProgressModalManager();
    
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
 * Set up search functionality
 */
function setupSearch() {
    const searchInput = document.getElementById('author-search');
    if (searchInput) {
        // Use debounced search from utils
        const debouncedSearch = Utils.debounce(async (searchTerm) => {
            await performAuthorSearch(searchTerm);
        }, 300);
        
        searchInput.addEventListener('input', (e) => {
            debouncedSearch(e.target.value);
        });
        
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                performAuthorSearch(e.target.value);
            }
        });
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

// Database functions
window.clearOlidCache = async function() {
    try {
        Utils.showLoading(true);
        await API.clearOlidCache();
        Utils.showToast('OLID cache cleared successfully', 'success');
        await Views.showSettings(); // Refresh settings view
    } catch (error) {
        Utils.showToast('Failed to clear OLID cache', 'danger');
        console.error('Error clearing OLID cache:', error);
    } finally {
        Utils.showLoading(false);
    }
};

window.clearDatabase = async function() {
    if (confirm('Are you sure you want to clear the entire database? This action cannot be undone.')) {
        try {
            Utils.showLoading(true);
            await API.clearDatabase();
            Utils.showToast('Database cleared successfully', 'success');
            await Views.showDashboard(); // Refresh to dashboard
        } catch (error) {
            Utils.showToast('Failed to clear database', 'danger');
            console.error('Error clearing database:', error);
        } finally {
            Utils.showLoading(false);
        }
    }
};

// Pagination functions
window.loadAuthorsPage = async function(page, search = '') {
    try {
        Utils.showLoading(true);
        await Views.loadAuthorsData(page, search);
    } catch (error) {
        Utils.showToast('Failed to load authors page', 'danger');
        console.error('Error loading authors page:', error);
    } finally {
        Utils.showLoading(false);
    }
};

// Search functions
window.searchAuthors = async function() {
    const searchInput = document.getElementById('author-search');
    if (searchInput) {
        await performAuthorSearch(searchInput.value);
    }
};

window.clearSearch = async function() {
    const searchInput = document.getElementById('author-search');
    if (searchInput) {
        searchInput.value = '';
        await performAuthorSearch('');
    }
};

// Initialize application when DOM is loaded
document.addEventListener('DOMContentLoaded', initializeApp);

// Export for potential use by other scripts
export { initializeApp };
