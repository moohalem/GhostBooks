/**
 * Manager classes for the Calibre Monitor application
 */

import { apiRequest } from './api.js';
import { showToast } from './utils.js';

/**
 * IRC Search Manager
 * Handles IRC search operations and status tracking
 */
export class IRCSearchManager {
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
    
    /**
     * Search for all books by an author
     */
    async searchAuthor(author) {
        return await this.startSearch(author);
    }
    
    /**
     * Search for a single book
     */
    async searchSingleBook(author, title) {
        try {
            const response = await apiRequest('/api/search_single_book_irc', {
                method: 'POST',
                body: JSON.stringify({ author: author, title: title })
            });
            
            showToast(`IRC search started for "${title}" by ${author}`, 'info');
            return response;
        } catch (error) {
            showToast(`Failed to start search for "${title}" by ${author}`, 'danger');
            throw error;
        }
    }
}

/**
 * Auto-refresh Manager
 * Handles automatic refreshing of dashboard statistics
 */
export class AutoRefreshManager {
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

/**
 * Progress Modal Manager
 * Handles the progress modal for population operations
 */
export class ProgressModalManager {
    constructor() {
        this.eventSource = null;
        this.isPopulationCancelled = false;
    }
    
    openModal() {
        const modal = new bootstrap.Modal(document.getElementById('populationProgressModal'), {
            backdrop: 'static',
            keyboard: false
        });
        modal.show();
        
        // Reset modal state
        this.isPopulationCancelled = false;
        this.resetModal();
    }
    
    resetModal() {
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
        
        // Reset current author
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
    
    startStreaming() {
        // Close any existing event source
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        
        // Add initial connection message
        this.addToLog('Connecting to server and starting population process...', 'info');
        
        // Create new event source for streaming progress
        this.eventSource = new EventSource('/api/missing_books/populate/stream');
        
        this.eventSource.onopen = (event) => {
            console.log('EventSource connection opened');
            this.addToLog('Connected to server successfully', 'success');
        };
        
        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.updateProgress(data);
            } catch (error) {
                console.error('Error parsing progress data:', error);
            }
        };
        
        this.eventSource.onerror = (event) => {
            console.error('EventSource failed:', event);
            console.error('EventSource readyState:', this.eventSource.readyState);
            
            const currentStatus = document.getElementById('current-status');
            const statusText = document.getElementById('status-text');
            
            let errorMessage = 'Connection error occurred';
            
            // Provide more specific error messages based on readyState
            switch (this.eventSource.readyState) {
                case EventSource.CONNECTING:
                    errorMessage = 'Connection lost, attempting to reconnect...';
                    break;
                case EventSource.CLOSED:
                    errorMessage = 'Connection closed by server';
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
            this.addToLog(`Connection error: ${errorMessage}`, 'error');
            
            // Show close button
            this.showCloseButton();
            
            this.eventSource.close();
            this.eventSource = null;
        };
    }
    
    updateProgress(data) {
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
            if (this.eventSource) {
                this.eventSource.close();
                this.eventSource = null;
            }
            
            // Show close button, hide cancel button
            this.showCloseButton();
            
            // Add separator and detailed completion message
            this.addToLog('─'.repeat(50), 'info');
            const summaryMessage = `🎉 Population completed successfully! 
📊 Summary: Processed ${data.processed || 0} authors, found ${data.missing_found || 0} missing books total.
${data.errors && data.errors.length > 0 ? `⚠️ ${data.errors.length} errors occurred during processing.` : '✅ No errors encountered.'}`;
            
            this.addToLog(summaryMessage, 'success');
            
            // Show success toast
            showToast(`Successfully processed ${data.processed} authors and found ${data.missing_found} missing books`, 'success');
            
        } else if (data.status === 'cancelled') {
            if (currentStatus) currentStatus.className = 'alert alert-warning';
            if (statusText) statusText.textContent = 'Population was cancelled';
            if (currentAuthorName) currentAuthorName.innerHTML = 'Cancelled';
            if (currentAuthorSection) currentAuthorSection.style.display = 'block';
            
            // Close event source
            if (this.eventSource) {
                this.eventSource.close();
                this.eventSource = null;
            }
            
            // Show close button, hide cancel button
            this.showCloseButton();
            
            this.addToLog('Population was cancelled by user.', 'warning');
            
        } else if (data.status === 'error') {
            if (currentStatus) currentStatus.className = 'alert alert-danger';
            if (statusText) statusText.textContent = `Error: ${data.message || 'Unknown error occurred'}`;
            if (currentAuthorName) currentAuthorName.innerHTML = 'Error';
            if (currentAuthorSection) currentAuthorSection.style.display = 'block';
            
            // Close event source
            if (this.eventSource) {
                this.eventSource.close();
                this.eventSource = null;
            }
            
            // Show close button, hide cancel button
            this.showCloseButton();
            
            this.addToLog(`Error: ${data.message || 'Unknown error occurred'}`, 'error');
            
        } else {
            // Processing status
            if (currentStatus) currentStatus.className = 'alert alert-info';
            if (statusText) statusText.textContent = data.message || 'Processing...';
            
            if (data.current_author && currentAuthorName && currentAuthorSection) {
                currentAuthorName.innerHTML = this.escapeHtml(data.current_author);
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
                logType = 'success';
            } else if (data.message.includes('✗')) {
                logType = 'error';
            }
            
            this.addToLog(data.message, logType);
        }
        
        // Handle errors
        if (data.errors && data.errors.length > 0) {
            this.showErrorSummary(data.errors);
        }
    }
    
    addToLog(message, type = 'info') {
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
        
        // Add special styling for author names
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
            bgClass = 'bg-info bg-opacity-10';
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
        
        // Limit log entries to prevent memory issues
        const maxEntries = 1000;
        const entries = progressLog.children;
        if (entries.length > maxEntries) {
            const entriesToRemove = entries.length - maxEntries;
            for (let i = 0; i < entriesToRemove; i++) {
                progressLog.removeChild(entries[0]);
            }
        }
    }
    
    showErrorSummary(errors) {
        const errorSection = document.getElementById('error-section');
        const errorSummary = document.getElementById('error-summary');
        
        if (errors.length > 0) {
            errorSection.style.display = 'block';
            
            const errorList = errors.map(error => 
                `<div class="mb-1">
                    <strong>${this.escapeHtml(error.author)}:</strong> ${this.escapeHtml(error.error)}
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
    
    showCloseButton() {
        const cancelButton = document.getElementById('cancel-button');
        const closeButton = document.getElementById('close-button');
        if (cancelButton) cancelButton.style.display = 'none';
        if (closeButton) closeButton.style.display = 'inline-block';
    }
    
    async cancel() {
        if (this.isPopulationCancelled) {
            return;
        }
        
        this.isPopulationCancelled = true;
        
        try {
            const response = await fetch('/api/missing_books/populate/cancel', {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.addToLog('Cancellation request sent...', 'warning');
                
                // Disable the cancel button
                const cancelButton = document.getElementById('cancel-button');
                cancelButton.disabled = true;
                cancelButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Cancelling...';
            } else {
                showToast('Failed to cancel population', 'danger');
                this.isPopulationCancelled = false;
            }
        } catch (error) {
            console.error('Error cancelling population:', error);
            showToast('Error cancelling population', 'danger');
            this.isPopulationCancelled = false;
        }
    }
    
    close() {
        // Close event source if still open
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        
        // Hide modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('populationProgressModal'));
        if (modal) {
            modal.hide();
        }
    }
    
    escapeHtml(text) {
        if (typeof text !== 'string') return text;
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}
