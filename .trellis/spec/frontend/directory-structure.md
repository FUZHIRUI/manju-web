# Frontend Directory Structure

> How frontend code is organized in this project.

---

## Overview

The frontend is a single-page application (SPA) built with vanilla JavaScript (ES6+), HTML5, and CSS3. It uses a simple, lightweight architecture without a framework like React or Vue.

The architecture follows these principles:
- **Modular functions** instead of components
- **Direct DOM manipulation** for UI updates
- **Event-driven** user interactions
- **API polling** for real-time status updates

---

## Directory Layout

```
/frontend/
├── index.html          # Main HTML structure (UI containers)
├── app.js             # Main application logic (ES6 modules)
└── static/
    └── style.css      # CSS styles (responsive layout)
```

---

## File Responsibilities

### index.html

The HTML file defines the UI structure with semantic containers:

```html
<!-- /frontend/index.html -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>剧本工作台 - TTZ Script Workbench</title>
    <link rel="stylesheet" href="static/style.css">
</head>
<body>
    <!-- Header -->
    <header class="app-header">
        <h1>剧本工作台</h1>
        <div class="project-selector">
            <select id="projectSelect">
                <option value="">选择项目...</option>
            </select>
        </div>
    </header>

    <!-- Main Content -->
    <main class="app-main">
        <!-- Tab Navigation -->
        <nav class="tab-nav">
            <button class="tab-btn active" data-tab="batch">批量生成</button>
            <button class="tab-btn" data-tab="characters">角色</button>
            <button class="tab-btn" data-tab="locations">场景</button>
            <button class="tab-btn" data-tab="storyboards">分镜</button>
            <button class="tab-btn" data-tab="videos">视频</button>
        </nav>

        <!-- Tab Content Containers -->
        <div class="tab-content">
            <section id="batch-tab" class="tab-panel active">
                <!-- Job list will be rendered here -->
                <div id="jobList" class="job-list"></div>
            </section>
            <!-- Other tab panels... -->
        </div>
    </main>

    <!-- Modal Container -->
    <div id="modalContainer" class="modal-container" style="display: none;">
        <div class="modal">
            <header class="modal-header">
                <h3 id="modalTitle">Modal Title</h3>
                <button class="modal-close" onclick="closeModal()">×</button>
            </header>
            <div class="modal-body" id="modalBody">
                <!-- Dynamic content -->
            </div>
        </div>
    </div>

    <!-- Log Viewer Modal -->
    <div id="logModal" class="modal-container" style="display: none;">
        <div class="modal modal-large">
            <header class="modal-header">
                <h3>Job Logs</h3>
                <button class="modal-close" onclick="closeLogModal()">×</button>
            </header>
            <div class="modal-body">
                <div id="logContent" class="log-content"></div>
            </div>
        </div>
    </div>

    <script src="app.js"></script>
</body>
</html>
```

### app.js

The JavaScript file contains all application logic:

```javascript
// /frontend/app.js

// ============================================
// State Management
// ============================================

let currentProject = null;
let currentFlow = null;
let activeJobs = new Map();
let pollInterval = null;

// ============================================
// Initialization
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
});

function initializeApp() {
    loadProjectList();
    setupEventListeners();
    startPolling();
}

// ============================================
// Event Handlers
// ============================================

function setupEventListeners() {
    // Project selection
    document.getElementById('projectSelect').addEventListener('change', (e) => {
        selectProject(e.target.value);
    });

    // Tab navigation
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
}

// ============================================
// API Functions
// ============================================

async function fetchProjectList() {
    const response = await fetch('/api/projects');
    return response.json();
}

async function fetchJobs(project) {
    const response = await fetch(`/api/projects/${project}/jobs`);
    return response.json();
}

async function startJob(jobType, payload) {
    const response = await fetch('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            type: jobType,
            project: currentProject,
            payload
        })
    });
    return response.json();
}

// ============================================
// Rendering Functions
// ============================================

function renderJobList(jobs) {
    const container = document.getElementById('jobList');
    container.innerHTML = '';

    jobs.forEach(job => {
        const jobCard = createJobCard(job);
        container.appendChild(jobCard);
    });
}

function createJobCard(job) {
    const card = document.createElement('div');
    card.className = `job-card job-status-${job.status}`;
    card.dataset.jobId = job.id;

    card.innerHTML = `
        <div class="job-header">
            <span class="job-type">${formatJobType(job.type)}</span>
            <span class="job-status">${formatStatus(job.status)}</span>
        </div>
        <div class="job-body">
            <p class="job-description">${job.description || 'No description'}</p>
            <time class="job-time">${formatTime(job.created_at)}</time>
        </div>
        <div class="job-actions">
            ${renderJobActions(job)}
        </div>
    `;

    return card;
}

function renderJobActions(job) {
    if (job.status === 'running') {
        return `<button disabled>Running...</button>`;
    }

    if (job.status === 'error') {
        return `
            <button onclick="retryJob('${job.id}')">Retry</button>
            <button onclick="viewLogs('${job.id}')">Logs</button>
        `;
    }

    return `<button onclick="viewLogs('${job.id}')">View Logs</button>`;
}
```

### style.css

The CSS file defines styles:

```css
/* /frontend/static/style.css */

/* ============================================
   CSS Variables
   ============================================ */

:root {
    --primary-color: #1890ff;
    --success-color: #52c41a;
    --warning-color: #faad14;
    --error-color: #f5222d;
    --text-color: #262626;
    --text-secondary: #595959;
    --border-color: #d9d9d9;
    --bg-color: #f5f5f5;
    --card-bg: #ffffff;
}

/* ============================================
   Base Styles
   ============================================ */

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: var(--text-color);
    background-color: var(--bg-color);
    line-height: 1.5;
}

/* ============================================
   Layout
   ============================================ */

.app-header {
    background: var(--card-bg);
    border-bottom: 1px solid var(--border-color);
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.app-main {
    max-width: 1200px;
    margin: 0 auto;
    padding: 24px;
}

/* ============================================
   Tabs
   ============================================ */

.tab-nav {
    display: flex;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 24px;
}

.tab-btn {
    background: none;
    border: none;
    padding: 12px 24px;
    cursor: pointer;
    color: var(--text-secondary);
    font-size: 14px;
    border-bottom: 2px solid transparent;
}

.tab-btn:hover {
    color: var(--primary-color);
}

.tab-btn.active {
    color: var(--primary-color);
    border-bottom-color: var(--primary-color);
}

.tab-panel {
    display: none;
}

.tab-panel.active {
    display: block;
}

/* ============================================
   Job Cards
   ============================================ */

.job-list {
    display: grid;
    gap: 16px;
}

.job-card {
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 16px;
}

.job-card.job-status-running {
    border-left: 4px solid var(--primary-color);
}

.job-card.job-status-completed {
    border-left: 4px solid var(--success-color);
}

.job-card.job-status-error {
    border-left: 4px solid var(--error-color);
}

.job-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}

.job-type {
    font-weight: 600;
    font-size: 14px;
}

.job-status {
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 4px;
    background: var(--bg-color);
}

.job-body {
    color: var(--text-secondary);
    font-size: 13px;
}

.job-actions {
    margin-top: 12px;
    display: flex;
    gap: 8px;
}

/* ============================================
   Modal
   ============================================ */

.modal-container {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}

.modal {
    background: var(--card-bg);
    border-radius: 8px;
    width: 90%;
    max-width: 600px;
    max-height: 90vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.modal-large {
    max-width: 900px;
}

.modal-header {
    padding: 16px 24px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.modal-header h3 {
    margin: 0;
    font-size: 16px;
}

.modal-close {
    background: none;
    border: none;
    font-size: 20px;
    cursor: pointer;
    color: var(--text-secondary);
}

.modal-body {
    padding: 24px;
    overflow-y: auto;
    flex: 1;
}

/* ============================================
   Log Viewer
   ============================================ */

.log-content {
    font-family: 'Monaco', 'Menlo', monospace;
    font-size: 12px;
    line-height: 1.5;
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 16px;
    border-radius: 4px;
    max-height: 500px;
    overflow-y: auto;
}

.log-entry {
    margin-bottom: 4px;
    white-space: pre-wrap;
    word-break: break-all;
}

.log-entry.log-level-INFO { color: #4fc1ff; }
.log-entry.log-level-WARN { color: #ffcc00; }
.log-entry.log-level-ERROR { color: #ff6b6b; }

/* ============================================
   Buttons
   ============================================ */

button {
    font-family: inherit;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.2s;
}

.btn {
    padding: 8px 16px;
    border-radius: 4px;
    border: 1px solid var(--border-color);
    background: var(--card-bg);
    color: var(--text-color);
}

.btn:hover {
    border-color: var(--primary-color);
    color: var(--primary-color);
}

.btn-primary {
    background: var(--primary-color);
    border-color: var(--primary-color);
    color: white;
}

.btn-primary:hover {
    background: #40a9ff;
    border-color: #40a9ff;
}

.btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

/* ============================================
   Forms
   ============================================ */

select, input[type="text"], input[type="number"] {
    font-family: inherit;
    font-size: 14px;
    padding: 8px 12px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    background: var(--card-bg);
    color: var(--text-color);
}

select:focus, input:focus {
    outline: none;
    border-color: var(--primary-color);
}

/* ============================================
   Responsive
   ============================================ */

@media (max-width: 768px) {
    .app-main {
        padding: 16px;
    }

    .tab-nav {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }

    .tab-btn {
        padding: 12px 16px;
        white-space: nowrap;
    }

    .job-card {
        padding: 12px;
    }

    .modal {
        width: 95%;
        margin: 16px;
    }
}

/* ============================================
   Utilities
   ============================================ */

.hidden {
    display: none !important;
}

.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
}

.text-center {
    text-align: center;
}

.text-muted {
    color: var(--text-secondary);
}
