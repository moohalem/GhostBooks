/**
 * Utility functions for the Calibre Monitor application
 */

/**
 * Display a toast notification
 * @param {string} message - Message to display
 * @param {string} type - Toast type (info, success, warning, danger)
 */
export function showToast(message, type = 'info') {
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

/**
 * Debounce function to limit function calls
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
export function debounce(func, wait) {
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

/**
 * Escape HTML characters to prevent XSS
 * @param {string} text - Text to escape
 * @returns {string} Escaped text
 */
export function escapeHtml(text) {
    if (typeof text !== 'string') return text;
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Show/hide loading indicator
 * @param {boolean} show - Whether to show loading
 */
export function showLoading(show = true) {
    const loading = document.getElementById('loading');
    if (loading) {
        loading.style.display = show ? 'block' : 'none';
    }
}

/**
 * Hide all view containers
 */
export function hideAllViews() {
    const views = document.querySelectorAll('.view-container');
    views.forEach(view => view.style.display = 'none');
}

/**
 * Update active navigation state
 * @param {string} activeView - The active view name
 */
export function updateActiveNav(activeView) {
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
        const navLinksEl = document.querySelectorAll('.navbar-nav .nav-link');
        if (navLinksEl[navLinkIndex]) {
            navLinksEl[navLinkIndex].classList.add('active');
        }
    }
}

/**
 * Autocomplete utility class
 */
export class Autocomplete {
    constructor(inputElement, dropdownElement, options = {}) {
        this.input = inputElement;
        this.dropdown = dropdownElement;
        this.options = {
            minLength: 2,
            delay: 300,
            maxResults: 10,
            searchFunction: null,
            renderItem: this.defaultRenderItem.bind(this),
            onSelect: null,
            ...options
        };
        
        this.currentFocus = -1;
        this.isOpen = false;
        this.searchTimeout = null;
        this.suggestions = [];
        
        this.init();
    }
    
    init() {
        // Input event listeners
        this.input.addEventListener('input', this.handleInput.bind(this));
        this.input.addEventListener('keydown', this.handleKeydown.bind(this));
        this.input.addEventListener('focus', this.handleFocus.bind(this));
        this.input.addEventListener('blur', this.handleBlur.bind(this));
        
        // Dropdown event listeners
        this.dropdown.addEventListener('mousedown', this.handleMousedown.bind(this));
        this.dropdown.addEventListener('click', this.handleClick.bind(this));
    }
    
    handleInput(e) {
        const value = e.target.value.trim();
        
        // Clear existing timeout
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }
        
        if (value.length < this.options.minLength) {
            this.close();
            return;
        }
        
        // Debounce search
        this.searchTimeout = setTimeout(() => {
            this.search(value);
        }, this.options.delay);
    }
    
    async search(query) {
        if (!this.options.searchFunction) {
            console.error('No search function provided to Autocomplete');
            return;
        }
        
        try {
            this.showLoading();
            const results = await this.options.searchFunction(query);
            this.suggestions = results.suggestions || [];
            this.lastSearchType = results.type || 'search_results';
            this.lastSearchMessage = results.message || '';
            this.render();
        } catch (error) {
            console.error('Autocomplete search error:', error);
            this.showError();
        }
    }
    
    render() {
        if (this.suggestions.length === 0) {
            this.showNoResults();
            return;
        }
        
        let html = '';
        
        // Add header if we have a message
        if (this.lastSearchMessage) {
            html += `<div class="autocomplete-header">${this.lastSearchMessage}</div>`;
        }
        
        // Add suggestion items
        html += this.suggestions.map((item, index) => {
            return this.options.renderItem(item, index);
        }).join('');
        
        this.dropdown.innerHTML = html;
        this.open();
    }
    
    defaultRenderItem(item, index) {
        const stats = [];
        if (item.total_books) {
            stats.push(`<span class="autocomplete-item-stat"><i class="fas fa-book"></i> ${item.total_books} books</span>`);
        }
        if (item.missing_books && item.missing_books > 0) {
            stats.push(`<span class="autocomplete-item-stat text-warning"><i class="fas fa-exclamation-circle"></i> ${item.missing_books} missing</span>`);
        }
        if (item.completion_rate !== undefined) {
            const rateClass = item.completion_rate >= 90 ? 'text-success' : item.completion_rate >= 70 ? 'text-warning' : 'text-danger';
            stats.push(`<span class="autocomplete-item-stat ${rateClass}"><i class="fas fa-percentage"></i> ${item.completion_rate}%</span>`);
        }
        
        return `
            <div class="autocomplete-item" data-index="${index}">
                <div class="autocomplete-item-name">${escapeHtml(item.name || item.title || item.text)}</div>
                ${stats.length > 0 ? `<div class="autocomplete-item-stats">${stats.join('')}</div>` : ''}
            </div>
        `;
    }
    
    showLoading() {
        this.dropdown.innerHTML = '<div class="autocomplete-loading"><i class="fas fa-spinner fa-spin"></i> Searching...</div>';
        this.open();
    }
    
    showNoResults() {
        this.dropdown.innerHTML = '<div class="autocomplete-no-results">No results found</div>';
        this.open();
    }
    
    showError() {
        this.dropdown.innerHTML = '<div class="autocomplete-no-results text-danger">Search error occurred</div>';
        this.open();
    }
    
    open() {
        this.dropdown.style.display = 'block';
        this.isOpen = true;
        this.currentFocus = -1;
    }
    
    close() {
        this.dropdown.style.display = 'none';
        this.isOpen = false;
        this.currentFocus = -1;
    }
    
    handleKeydown(e) {
        if (!this.isOpen) return;
        
        const items = this.dropdown.querySelectorAll('.autocomplete-item');
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this.currentFocus = Math.min(this.currentFocus + 1, items.length - 1);
            this.updateFocus(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this.currentFocus = Math.max(this.currentFocus - 1, -1);
            this.updateFocus(items);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (this.currentFocus >= 0 && items[this.currentFocus]) {
                this.selectItem(this.currentFocus);
            }
        } else if (e.key === 'Escape') {
            this.close();
        }
    }
    
    updateFocus(items) {
        items.forEach((item, index) => {
            item.classList.toggle('selected', index === this.currentFocus);
        });
    }
    
    handleFocus() {
        if (this.input.value.trim().length >= this.options.minLength && this.suggestions.length > 0) {
            this.open();
        } else if (this.input.value.trim().length === 0) {
            // Show popular suggestions when focused with empty input
            this.searchPopular();
        }
    }
    
    async searchPopular() {
        try {
            this.showLoading();
            const results = await this.options.searchFunction('');
            this.suggestions = results.suggestions || [];
            this.lastSearchType = results.type || 'popular';
            this.lastSearchMessage = results.message || 'Popular authors';
            this.render();
        } catch (error) {
            console.error('Popular authors search error:', error);
            this.showError();
        }
    }
    
    handleBlur(e) {
        // Delay closing to allow for clicks on dropdown
        setTimeout(() => {
            if (!this.dropdown.contains(document.activeElement)) {
                this.close();
            }
        }, 150);
    }
    
    handleMousedown(e) {
        // Prevent input blur when clicking dropdown
        e.preventDefault();
    }
    
    handleClick(e) {
        const item = e.target.closest('.autocomplete-item');
        if (item) {
            const index = parseInt(item.dataset.index);
            this.selectItem(index);
        }
    }
    
    selectItem(index) {
        if (index >= 0 && index < this.suggestions.length) {
            const item = this.suggestions[index];
            
            // Update input value
            this.input.value = item.name || item.title || item.text || '';
            
            // Call onSelect callback
            if (this.options.onSelect) {
                this.options.onSelect(item);
            }
            
            // Close dropdown
            this.close();
        }
    }
}

/**
 * Show a Bootstrap modal
 * @param {string} modalId - ID of the modal to show
 */
export function showModal(modalId) {
    const modalElement = document.getElementById(modalId);
    if (modalElement) {
        const modal = new bootstrap.Modal(modalElement);
        modal.show();
        return modal;
    } else {
        console.error(`Modal with ID '${modalId}' not found`);
        return null;
    }
}

/**
 * Hide a Bootstrap modal
 * @param {string} modalId - ID of the modal to hide
 */
export function hideModal(modalId) {
    const modalElement = document.getElementById(modalId);
    if (modalElement) {
        const modal = bootstrap.Modal.getInstance(modalElement);
        if (modal) {
            modal.hide();
        } else {
            // If no instance exists, create one and hide it
            const newModal = new bootstrap.Modal(modalElement);
            newModal.hide();
        }
    } else {
        console.error(`Modal with ID '${modalId}' not found`);
    }
}
