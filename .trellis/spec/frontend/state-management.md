# State Management

> How state is managed in this project.

---

## Overview

This project uses a **simple vanilla JavaScript state management** approach without Redux, MobX, or other state libraries. State is managed through:

1. **Module-level variables** for global state
2. **Function parameters** for local/component state
3. **Custom state containers** for complex reactive state
4. **sessionStorage** for persistence across page reloads

---

## State Categories

### 1. Global Application State

State that the entire application needs access to:

```javascript
// /frontend/app.js

// ============================================
// Global State
// ============================================

let currentProject = null;    // Currently selected project
let currentFlow = null;       // Current workflow state
let activeJobs = new Map();   // Map of job_id -> job data
let isPolling = false;        // Polling state

// State change listeners
const stateListeners = {
    project: new Set(),
    jobs: new Set(),
    flow: new Set()
};

// ============================================
// State Management Functions
// ============================================

function setCurrentProject(project) {
    const oldProject = currentProject;
    currentProject = project;

    // Persist to sessionStorage
    if (project) {
        sessionStorage.setItem('currentProject', project);
    } else {
        sessionStorage.removeItem('currentProject');
    }

    // Notify listeners
    stateListeners.project.forEach(listener => {
        listener(project, oldProject);
    });
}

function subscribeToProjectChanges(listener) {
    stateListeners.project.add(listener);

    // Return unsubscribe function
    return () => {
        stateListeners.project.delete(listener);
    };
}

// ============================================
// Usage
// ============================================

// Subscribe to changes
const unsubscribe = subscribeToProjectChanges((newProject, oldProject) => {
    console.log(`Project changed from ${oldProject} to ${newProject}`);
    loadJobsForProject(newProject);
});

// Update state
setCurrentProject('my_project');

// Later: cleanup
// unsubscribe();
```

### 2. Local/Component State

State that belongs to a specific UI section:

```javascript
/**
 * Create a modal with its own internal state
 * @param {Object} options - Modal options
 */
function createModal({ title, content, onClose }) {
    // Local state
    let isOpen = false;
    let modalElement = null;

    // Methods
    function open() {
        if (isOpen) return;
        isOpen = true;

        modalElement = document.createElement('div');
        modalElement.className = 'modal-container';
        modalElement.innerHTML = `
            <div class="modal">
                <header class="modal-header">
                    <h3>${title}</h3>
                    <button class="modal-close">&times;</button>
                </header>
                <div class="modal-body">${content}</div>
            </div>
        `;

        // Event listeners
        modalElement.querySelector('.modal-close').addEventListener('click', close);
        modalElement.addEventListener('click', (e) => {
            if (e.target === modalElement) close();
        });

        document.body.appendChild(modalElement);
        document.body.style.overflow = 'hidden';
    }

    function close() {
        if (!isOpen) return;
        isOpen = false;

        if (modalElement) {
            modalElement.remove();
            modalElement = null;
        }

        document.body.style.overflow = '';

        if (onClose) {
            onClose();
        }
    }

    // Public API
    return {
        open,
        close,
        get isOpen() { return isOpen; }
    };
}

// Usage
const modal = createModal({
    title: 'Confirm Action',
    content: '<p>Are you sure you want to proceed?</p>',
    onClose: () => console.log('Modal closed')
});

modal.open();

// Later
// modal.close();
```

### 3. Server State

Data fetched from the server:

```javascript
/**
 * Server state management with caching
 */
const serverState = {
    cache: new Map(),
    loading: new Set(),
    error: new Map(),

    /**
     * Fetch data with caching
     * @param {string} key - Cache key
     * @param {Function} fetcher - Function that returns a Promise
     * @param {Object} options - Options
     */
    async fetch(key, fetcher, options = {}) {
        const { ttl = 60000, force = false } = options;

        // Return cached data if valid
        if (!force && this.cache.has(key)) {
            const { data, timestamp } = this.cache.get(key);
            if (Date.now() - timestamp < ttl) {
                return { data, cached: true };
            }
        }

        // Prevent duplicate in-flight requests
        if (this.loading.has(key)) {
            // Wait for existing request
            return new Promise((resolve) => {
                const check = () => {
                    if (!this.loading.has(key)) {
                        const { data } = this.cache.get(key) || {};
                        resolve({ data, cached: true });
                    } else {
                        setTimeout(check, 50);
                    }
                };
                check();
            });
        }

        // Fetch data
        this.loading.add(key);
        this.error.delete(key);

        try {
            const data = await fetcher();
            this.cache.set(key, { data, timestamp: Date.now() });
            return { data, cached: false };
        } catch (err) {
            this.error.set(key, err);
            throw err;
        } finally {
            this.loading.delete(key);
        }
    },

    /**
     * Check if a key is loading
     */
    isLoading(key) {
        return this.loading.has(key);
    },

    /**
     * Get error for a key
     */
    getError(key) {
        return this.error.get(key);
    },

    /**
     * Invalidate cached data
     */
    invalidate(key) {
        this.cache.delete(key);
    },

    /**
     * Clear all cached data
     */
    clear() {
        this.cache.clear();
        this.loading.clear();
        this.error.clear();
    }
};

// Usage example
async function loadJobs(project) {
    const { data, cached } = await serverState.fetch(
        `jobs:${project}`,
        () => fetch(`/api/projects/${project}/jobs`).then(r => r.json()),
        { ttl: 10000 } // Cache for 10 seconds
    );

    console.log(`Jobs loaded (cached: ${cached})`, data);
    return data;
}

// Check loading state
if (serverState.isLoading(`jobs:${project}`)) {
    showLoadingSpinner();
}
```

---

## When to Use Global vs Local State

| Use Global State | Use Local State |
|-----------------|-----------------|
| Current project selection | Modal open/close state |
| User authentication | Form input values |
| Application configuration | Hover/Focus states |
| Shared job data (with caching) | Animation state |
| Cross-tab communication | Component-specific UI state |

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why Avoid | Correct Approach |
|--------------|-----------|------------------|
| Modifying global state directly | Unpredictable updates, hard to debug | Use setter functions that notify listeners |
| Not cleaning up event listeners | Memory leaks | Always remove listeners in cleanup |
| Storing derived state | Data inconsistency | Compute on demand or use memoization |
| Synchronous polling without debounce | Unnecessary CPU/network usage | Debounce or use exponential backoff |
| Mixing server and UI state | Confusion about data source | Keep server state separate with caching |

---

## Common Mistakes

1. **Not unsubscribing from state changes** - Always clean up subscriptions when components are destroyed
2. **Mutating state directly** - Create new objects/arrays instead of modifying existing ones
3. **Forgetting to handle loading states** - Always show appropriate UI while data is loading
4. **Not handling errors** - Always have error handling for async operations
5. **Storing everything in global state** - Keep local state local to avoid unnecessary complexity

---

## Related Guidelines

- [Directory Structure](./directory-structure.md) - Frontend organization
- [Component Guidelines](./component-guidelines.md) - UI component patterns
- [Hook Guidelines](./hook-guidelines.md) - Custom logic patterns
- [Quality Guidelines](./quality-guidelines.md) - Code quality standards
