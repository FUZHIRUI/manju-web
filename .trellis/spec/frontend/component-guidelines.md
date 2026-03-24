# Component Guidelines

> How components are built in this project.

---

## Overview

This project uses a **vanilla JavaScript functional approach** instead of a component framework like React or Vue. UI components are created using factory functions that return DOM elements, combined with direct DOM manipulation for updates.

This approach was chosen for:
- **Simplicity** - No build step or framework dependencies
- **Lightweight** - Minimal JavaScript bundle size
- **Direct control** - Full control over DOM operations

---

## Component Patterns

### Factory Function Pattern

Components are created using factory functions that return DOM elements:

```javascript
// /frontend/app.js

/**
 * Create a job card element
 * @param {Object} job - Job data object
 * @returns {HTMLElement} Job card DOM element
 */
function createJobCard(job) {
    // Create container
    const card = document.createElement('div');
    card.className = `job-card job-status-${job.status}`;
    card.dataset.jobId = job.id;

    // Create header section
    const header = document.createElement('div');
    header.className = 'job-header';
    header.innerHTML = `
        <span class="job-type">${formatJobType(job.type)}</span>
        <span class="job-status">${formatStatus(job.status)}</span>
    `;

    // Create body section
    const body = document.createElement('div');
    body.className = 'job-body';
    body.innerHTML = `
        <p class="job-description">${job.description || 'No description'}</p>
        <time class="job-time">${formatTime(job.created_at)}</time>
    `;

    // Create actions section
    const actions = document.createElement('div');
    actions.className = 'job-actions';
    actions.innerHTML = renderJobActions(job);

    // Assemble card
    card.appendChild(header);
    card.appendChild(body);
    card.appendChild(actions);

    // Add event listeners
    attachJobCardListeners(card, job);

    return card;
}
```

### Template String Pattern

For simpler components, use template strings:

```javascript
/**
 * Render job action buttons based on job status
 * @param {Object} job - Job data
 * @returns {string} HTML string
 */
function renderJobActions(job) {
    if (job.status === 'running') {
        return `<button class="btn" disabled>Running...</button>`;
    }

    if (job.status === 'error') {
        return `
            <button class="btn btn-primary" data-action="retry" data-job-id="${job.id}">
                Retry
            </button>
            <button class="btn" data-action="logs" data-job-id="${job.id}">
                View Logs
            </button>
        `;
    }

    return `
        <button class="btn" data-action="logs" data-job-id="${job.id}">
            View Logs
        </button>
    `;
}
```

---

## Props Conventions

Since this is vanilla JavaScript, "props" are simply function parameters:

### Parameter Naming

```javascript
// Good - clear parameter names
function createJobCard(job, options = {}) {
    const { showActions = true, compact = false } = options;
    // ...
}

// Bad - unclear abbreviations
function createJobCard(j, opts = {}) {
    const { sa = true, cmp = false } = opts;
    // ...
}
```

### Default Values

```javascript
function createButton({
    text = 'Click',
    variant = 'default', // 'default' | 'primary' | 'danger'
    disabled = false,
    onClick = null
}) {
    const button = document.createElement('button');
    button.textContent = text;
    button.className = `btn btn-${variant}`;
    button.disabled = disabled;

    if (onClick) {
        button.addEventListener('click', onClick);
    }

    return button;
}

// Usage
const submitBtn = createButton({
    text: 'Submit',
    variant: 'primary',
    onClick: handleSubmit
});
```

---

## Composition Patterns

### Composing Components

Build complex components by composing simpler ones:

```javascript
/**
 * Create a job list section
 * @param {Array} jobs - Array of job objects
 * @returns {HTMLElement} Job list container
 */
function createJobList(jobs) {
    const container = document.createElement('div');
    container.className = 'job-list';

    if (jobs.length === 0) {
        const emptyState = createEmptyState({
            message: 'No jobs yet',
            action: {
                text: 'Create Job',
                onClick: openCreateJobModal
            }
        });
        container.appendChild(emptyState);
        return container;
    }

    jobs.forEach(job => {
        const card = createJobCard(job);
        container.appendChild(card);
    });

    return container;
}

/**
 * Create an empty state component
 * @param {Object} options - Empty state options
 * @returns {HTMLElement} Empty state element
 */
function createEmptyState({ message, action = null }) {
    const container = document.createElement('div');
    container.className = 'empty-state';

    const messageEl = document.createElement('p');
    messageEl.className = 'empty-message';
    messageEl.textContent = message;
    container.appendChild(messageEl);

    if (action) {
        const btn = createButton({
            text: action.text,
            variant: 'primary',
            onClick: action.onClick
        });
        container.appendChild(btn);
    }

    return container;
}
```

---

## Event Handling

### Inline Event Handlers (Discouraged)

Avoid inline `onclick` attributes:

```javascript
// Bad - hard to maintain, mixes HTML and JS
function renderJobActions_bad(job) {
    return `
        <button onclick="retryJob('${job.id}')">Retry</button>
    `;
}
```

### Data Attributes + Event Delegation (Preferred)

Use data attributes and event delegation:

```javascript
// Good - separation of concerns, easier to maintain
function renderJobActions(job) {
    return `
        <button class="btn btn-primary"
                data-action="retry"
                data-job-id="${job.id}">Retry</button>
        <button class="btn"
                data-action="view-logs"
                data-job-id="${job.id}">View Logs</button>
    `;
}

// Event delegation setup
function setupEventListeners() {
    // Use event delegation for dynamic content
    document.getElementById('jobList').addEventListener('click', (e) => {
        const button = e.target.closest('[data-action]');
        if (!button) return;

        const action = button.dataset.action;
        const jobId = button.dataset.jobId;

        switch (action) {
            case 'retry':
                retryJob(jobId);
                break;
            case 'view-logs':
                openLogModal(jobId);
                break;
        }
    });
}

// Specific job card listeners
function attachJobCardListeners(card, job) {
    // Card-level events if needed
    card.addEventListener('click', (e) => {
        // Don't trigger if clicking on a button
        if (e.target.closest('button')) return;

        // Navigate to job detail
        navigateToJobDetail(job.id);
    });
}
```

---

## Accessibility

### Basic A11y Requirements

```javascript
// Create accessible button
function createAccessibleButton({ text, ariaLabel, onClick }) {
    const button = document.createElement('button');
    button.textContent = text;
    button.type = 'button'; // Prevent form submission

    if (ariaLabel) {
        button.setAttribute('aria-label', ariaLabel);
    }

    button.addEventListener('click', onClick);

    return button;
}

// Create accessible modal
function createAccessibleModal({ title, content, onClose }) {
    const modal = document.createElement('div');
    modal.className = 'modal-container';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'modal-title');

    modal.innerHTML = `
        <div class="modal" role="document">
            <header class="modal-header">
                <h3 id="modal-title">${title}</h3>
                <button
                    type="button"
                    class="modal-close"
                    aria-label="Close"
                >
                    ×
                </button>
            </header>
            <div class="modal-body">${content}</div>
        </div>
    `;

    // Close on escape key
    const handleKeydown = (e) => {
        if (e.key === 'Escape') {
            onClose();
            document.removeEventListener('keydown', handleKeydown);
        }
    };
    document.addEventListener('keydown', handleKeydown);

    // Close on click outside
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            onClose();
        }
    });

    // Close button
    modal.querySelector('.modal-close').addEventListener('click', onClose);

    return modal;
}
```

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why Avoid | Correct Approach |
|--------------|-----------|------------------|
| `innerHTML` for user input | XSS security risk | Use `textContent` or sanitize HTML |
| Mixing HTML and logic | Hard to maintain | Use template functions or factory patterns |
| Inline styles | Hard to override, bloated HTML | Use CSS classes |
| Deeply nested ternaries | Hard to read | Use early returns or helper functions |
| Not cleaning up event listeners | Memory leaks | Remove listeners in cleanup/teardown |
| Hardcoded strings | No i18n support | Use string constants or i18n library |
| Not handling null/undefined | Runtime errors | Use optional chaining, null checks |

---

## Common Mistakes

1. **Not sanitizing user input before rendering** - Always escape HTML when displaying user data
2. **Forgetting to remove event listeners** - Clean up listeners when components are destroyed
3. **Using `innerHTML` for simple text updates** - Use `textContent` instead
4. **Not handling loading/error states** - Always show appropriate UI for async operations
5. **Hardcoding colors/sizes** - Use CSS variables for consistency

---

## Related Guidelines

- [Directory Structure](./directory-structure.md) - Frontend organization
- [Hook Guidelines](./hook-guidelines.md) - State and side effects
- [State Management](./state-management.md) - Global state patterns
- [Quality Guidelines](./quality-guidelines.md) - Code quality standards
