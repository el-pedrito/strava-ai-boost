/**
 * Strava AI Boost - Local Interface JavaScript
 * 
 * Additional JavaScript functionality for the local web interface
 */

// Global configuration
window.StravaAIBoostConfig = {
    autoRefreshInterval: 30000, // 30 seconds
    apiTimeout: 10000, // 10 seconds
    maxRetries: 3
};

// Enhanced API client with retry logic
class APIClient {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
        this.retryCount = 0;
    }
    
    async request(url, options = {}) {
        const fullUrl = this.baseUrl + url;
        const defaultOptions = {
            timeout: window.StravaAIBoostConfig.apiTimeout,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        };
        
        const finalOptions = { ...defaultOptions, ...options };
        
        try {
            const response = await fetch(fullUrl, finalOptions);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.retryCount = 0; // Reset on success
            return data;
            
        } catch (error) {
            if (this.retryCount < window.StravaAIBoostConfig.maxRetries) {
                this.retryCount++;
                console.warn(`API request failed, retrying (${this.retryCount}/${window.StravaAIBoostConfig.maxRetries}):`, error);
                
                // Exponential backoff
                const delay = Math.pow(2, this.retryCount) * 1000;
                await new Promise(resolve => setTimeout(resolve, delay));
                
                return this.request(url, options);
            }
            
            this.retryCount = 0;
            throw error;
        }
    }
    
    async get(url) {
        return this.request(url, { method: 'GET' });
    }
    
    async post(url, data) {
        return this.request(url, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }
    
    async put(url, data) {
        return this.request(url, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }
    
    async delete(url) {
        return this.request(url, { method: 'DELETE' });
    }
}

// Global API client instance
window.apiClient = new APIClient();

// Enhanced notification system
class NotificationManager {
    constructor() {
        this.container = null;
        this.notifications = [];
        this.init();
    }
    
    init() {
        // Create notification container if it doesn't exist
        this.container = document.querySelector('.flash-messages');
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'flash-messages';
            
            const contentWrapper = document.querySelector('.content-wrapper');
            if (contentWrapper) {
                contentWrapper.insertBefore(this.container, contentWrapper.firstChild);
            }
        }
    }
    
    show(message, type = 'info', duration = 5000) {
        const notification = document.createElement('div');
        notification.className = `flash-message flash-${type}`;
        notification.innerHTML = `
            <span>${message}</span>
            <button onclick="this.parentElement.remove()" style="background: none; border: none; color: inherit; cursor: pointer; float: right; font-weight: bold;">×</button>
        `;
        
        this.container.appendChild(notification);
        this.notifications.push(notification);
        
        // Auto-remove after duration
        if (duration > 0) {
            setTimeout(() => {
                if (notification.parentElement) {
                    notification.remove();
                    this.notifications = this.notifications.filter(n => n !== notification);
                }
            }, duration);
        }
        
        return notification;
    }
    
    success(message, duration = 5000) {
        return this.show(message, 'success', duration);
    }
    
    error(message, duration = 8000) {
        return this.show(message, 'error', duration);
    }
    
    warning(message, duration = 6000) {
        return this.show(message, 'warning', duration);
    }
    
    info(message, duration = 5000) {
        return this.show(message, 'info', duration);
    }
    
    clear() {
        this.notifications.forEach(notification => {
            if (notification.parentElement) {
                notification.remove();
            }
        });
        this.notifications = [];
    }
}

// Global notification manager
window.notifications = new NotificationManager();

// Real-time data manager
class RealTimeDataManager {
    constructor() {
        this.subscriptions = new Map();
        this.isActive = true;
        this.defaultInterval = window.StravaAIBoostConfig.autoRefreshInterval;
    }
    
    subscribe(key, callback, interval = null) {
        if (this.subscriptions.has(key)) {
            this.unsubscribe(key);
        }
        
        const actualInterval = interval || this.defaultInterval;
        const intervalId = setInterval(() => {
            if (this.isActive && !document.hidden) {
                callback();
            }
        }, actualInterval);
        
        this.subscriptions.set(key, {
            callback,
            intervalId,
            interval: actualInterval
        });
        
        // Call immediately
        if (this.isActive) {
            callback();
        }
    }
    
    unsubscribe(key) {
        const subscription = this.subscriptions.get(key);
        if (subscription) {
            clearInterval(subscription.intervalId);
            this.subscriptions.delete(key);
        }
    }
    
    pause() {
        this.isActive = false;
    }
    
    resume() {
        this.isActive = true;
    }
    
    clear() {
        this.subscriptions.forEach((subscription, key) => {
            this.unsubscribe(key);
        });
    }
}

// Global real-time data manager
window.realTimeData = new RealTimeDataManager();

// Page visibility handling
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        window.realTimeData.pause();
    } else {
        window.realTimeData.resume();
    }
});

// Form validation utilities
window.FormValidator = {
    validateEmail: function(email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    },
    
    validateUrl: function(url) {
        try {
            new URL(url);
            return true;
        } catch {
            return false;
        }
    },
    
    validateRequired: function(value) {
        return value && value.trim().length > 0;
    },
    
    validateMinLength: function(value, minLength) {
        return value && value.length >= minLength;
    },
    
    validateMaxLength: function(value, maxLength) {
        return !value || value.length <= maxLength;
    },
    
    validateNumeric: function(value) {
        return !isNaN(value) && !isNaN(parseFloat(value));
    },
    
    showFieldError: function(fieldElement, message) {
        // Remove existing error
        this.clearFieldError(fieldElement);
        
        // Add error styling
        fieldElement.style.borderColor = '#d13212';
        
        // Add error message
        const errorDiv = document.createElement('div');
        errorDiv.className = 'field-error';
        errorDiv.style.cssText = 'color: #d13212; font-size: 12px; margin-top: 4px;';
        errorDiv.textContent = message;
        
        fieldElement.parentElement.appendChild(errorDiv);
    },
    
    clearFieldError: function(fieldElement) {
        fieldElement.style.borderColor = '';
        const errorDiv = fieldElement.parentElement.querySelector('.field-error');
        if (errorDiv) {
            errorDiv.remove();
        }
    },
    
    clearAllErrors: function(formElement) {
        const fields = formElement.querySelectorAll('input, textarea, select');
        fields.forEach(field => this.clearFieldError(field));
    }
};

// Loading state manager
window.LoadingManager = {
    activeLoaders: new Set(),
    
    show: function(element, text = 'Loading...') {
        if (!element) return;
        
        const loaderId = Math.random().toString(36).substr(2, 9);
        
        // Store original state
        element.dataset.originalText = element.innerHTML;
        element.dataset.originalDisabled = element.disabled;
        element.dataset.loaderId = loaderId;
        
        // Apply loading state
        element.disabled = true;
        element.innerHTML = `<span class="loading-spinner"></span> ${text}`;
        
        this.activeLoaders.add(loaderId);
        return loaderId;
    },
    
    hide: function(element) {
        if (!element || !element.dataset.loaderId) return;
        
        const loaderId = element.dataset.loaderId;
        
        // Restore original state
        element.innerHTML = element.dataset.originalText || 'Submit';
        element.disabled = element.dataset.originalDisabled === 'true';
        
        // Clean up
        delete element.dataset.originalText;
        delete element.dataset.originalDisabled;
        delete element.dataset.loaderId;
        
        this.activeLoaders.delete(loaderId);
    },
    
    hideAll: function() {
        document.querySelectorAll('[data-loader-id]').forEach(element => {
            this.hide(element);
        });
        this.activeLoaders.clear();
    }
};

// Enhanced utility functions
window.Utils = {
    formatBytes: function(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    },
    
    formatDistance: function(meters) {
        if (meters < 1000) {
            return Math.round(meters) + ' m';
        } else {
            return (meters / 1000).toFixed(1) + ' km';
        }
    },
    
    formatPace: function(secondsPerKm) {
        const minutes = Math.floor(secondsPerKm / 60);
        const seconds = Math.round(secondsPerKm % 60);
        return `${minutes}:${seconds.toString().padStart(2, '0')} /km`;
    },
    
    formatHeartRate: function(bpm) {
        return Math.round(bpm) + ' bpm';
    },
    
    formatElevation: function(meters) {
        return Math.round(meters) + ' m';
    },
    
    debounce: function(func, wait, immediate = false) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                timeout = null;
                if (!immediate) func(...args);
            };
            const callNow = immediate && !timeout;
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
            if (callNow) func(...args);
        };
    },
    
    throttle: function(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },
    
    copyToClipboard: async function(text) {
        try {
            await navigator.clipboard.writeText(text);
            window.notifications.success('Copied to clipboard');
            return true;
        } catch (err) {
            console.error('Failed to copy to clipboard:', err);
            window.notifications.error('Failed to copy to clipboard');
            return false;
        }
    }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('Strava AI Boost - Local Interface initialized');
    
    // Initialize tooltips (if any)
    const tooltips = document.querySelectorAll('[data-tooltip]');
    tooltips.forEach(element => {
        element.addEventListener('mouseenter', function() {
            // Simple tooltip implementation
            const tooltip = document.createElement('div');
            tooltip.className = 'tooltip';
            tooltip.textContent = this.dataset.tooltip;
            tooltip.style.cssText = `
                position: absolute;
                background: #232f3e;
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
                z-index: 1000;
                pointer-events: none;
            `;
            
            document.body.appendChild(tooltip);
            
            const rect = this.getBoundingClientRect();
            tooltip.style.left = rect.left + 'px';
            tooltip.style.top = (rect.top - tooltip.offsetHeight - 5) + 'px';
            
            this.addEventListener('mouseleave', function() {
                tooltip.remove();
            }, { once: true });
        });
    });
    
    // Initialize keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd + R: Refresh current page data
        if ((e.ctrlKey || e.metaKey) && e.key === 'r' && e.shiftKey) {
            e.preventDefault();
            if (typeof refreshData === 'function') {
                refreshData();
            } else if (typeof refreshDashboard === 'function') {
                refreshDashboard();
            }
        }
        
        // Escape: Close modals or clear notifications
        if (e.key === 'Escape') {
            window.notifications.clear();
        }
    });
});

// Global utility functions for templates
window.StravaAIBoost = {
    showLoading: function(element, text = 'Loading...') {
        return window.LoadingManager.show(element, text);
    },
    
    hideLoading: function(element, originalText = null) {
        window.LoadingManager.hide(element);
        if (originalText && element) {
            element.innerHTML = originalText;
        }
    },
    
    showFlash: function(message, type = 'info') {
        return window.notifications.show(message, type);
    },
    
    formatDate: function(dateString) {
        if (!dateString) return 'Unknown';
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
        } catch {
            return dateString;
        }
    }
};

// Auto-refresh functionality
let autoRefreshInterval = null;

function startAutoRefresh(callback, interval = 30000) {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
    autoRefreshInterval = setInterval(callback, interval);
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    window.realTimeData.clear();
    window.LoadingManager.hideAll();
    stopAutoRefresh();
});