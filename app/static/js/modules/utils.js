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
