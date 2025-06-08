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

// Export functions for global use
window.CalibreMonitor = {
    showToast,
    apiRequest,
    ircSearchManager,
    autoRefreshManager,
    initializeTableSearch
};
