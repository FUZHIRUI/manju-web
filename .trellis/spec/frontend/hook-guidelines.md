# Hook Guidelines

> How hooks/custom logic is organized in this project.

---

## Overview

This project uses **vanilla JavaScript** without React or Vue, so there are no React-style hooks. Instead, the project uses a pattern of **utility functions** and **event-driven state management** to achieve similar separation of concerns.

This guide documents the patterns used to replace common hook functionality:
- `useState` → Direct variable + DOM updates
- `useEffect` → Event listeners + manual cleanup
- `useCallback` → Function declarations
- `useMemo` → Manual caching

---

## State Management Utilities

### Simple State Container

```javascript
// /frontend/app.js

/**
 * Simple state container with subscribers
 * Replaces: const [state, setState] = useState(initial)
 */
function createState(initialValue) {
    let value = initialValue;
    const subscribers = new Set();

    return {
        get() {
            return value;
        },
        set(newValue) {
            const oldValue = value;
            value = newValue;
            subscribers.forEach(callback => callback(newValue, oldValue));
        },
        subscribe(callback) {
            subscribers.add(callback);
            // Return unsubscribe function (like useEffect cleanup)
            return () => subscribers.delete(callback);
        }
    };
}

// Usage example
const projectState = createState(null);

// Subscribe to changes (like useEffect)
const unsubscribe = projectState.subscribe((newProject, oldProject) => {
    console.log(`Project changed: ${oldProject} -> ${newProject}`);
    updateProjectUI(newProject);
});

// Update state (like setState)
projectState.set('new_project');

// Cleanup when done (important!)
unsubscribe();
```

### Computed State

```javascript
/**
 * Computed state that updates when dependencies change
 * Replaces: const computed = useMemo(() => compute(a, b), [a, b])
 */
function createComputed(dependencies, computeFn) {
    let cachedValue;
    let dependencyValues = dependencies.map(dep => dep.get());

    const recompute = () => {
        const newValues = dependencies.map(dep => dep.get());
        // Only recompute if dependencies changed
        if (JSON.stringify(newValues) !== JSON.stringify(dependencyValues)) {
            dependencyValues = newValues;
            cachedValue = computeFn(...newValues);
        }
        return cachedValue;
    };

    // Subscribe to all dependencies
    const unsubscribes = dependencies.map(dep =>
        dep.subscribe(() => recompute())
    );

    return {
        get: recompute,
        destroy: () => unsubscribes.forEach(unsub => unsub())
    };
}

// Usage example
const jobsState = createState([]);
const filterState = createState('all');

const filteredJobs = createComputed(
    [jobsState, filterState],
    (jobs, filter) => {
        if (filter === 'all') return jobs;
        return jobs.filter(job => job.status === filter);
    }
);

// Get computed value
console.log(filteredJobs.get());

// Cleanup
filteredJobs.destroy();
```

---

## Lifecycle Patterns

### Initialization (replaces useEffect with empty deps)

```javascript
// Replaces: useEffect(() => { ... }, [])

function initializeApp() {
    // Run once on app start
    console.log('Initializing app...');

    // Load initial data
    loadProjectList();
    setupEventListeners();

    // Start polling for updates
    const pollInterval = setInterval(pollUpdates, 5000);

    // Return cleanup function (like useEffect cleanup)
    return () => {
        console.log('Cleaning up app...');
        clearInterval(pollInterval);
        removeEventListeners();
    };
}

// Usage
const cleanup = initializeApp();

// Later, when app is destroyed
// cleanup();
```

### Effect with Dependencies (replaces useEffect with deps)

```javascript
// Replaces: useEffect(() => { ... }, [dep1, dep2])

function createEffect(dependencies, effectFn) {
    let cleanupFn = null;
    let lastDeps = dependencies.map(d => d.get());

    const runEffect = () => {
        const currentDeps = dependencies.map(d => d.get());

        // Check if deps changed
        const depsChanged = currentDeps.some((dep, i) => dep !== lastDeps[i]);

        if (depsChanged) {
            // Run cleanup if exists
            if (cleanupFn) {
                cleanupFn();
            }

            // Run effect and store cleanup
            lastDeps = currentDeps;
            cleanupFn = effectFn();
        }
    };

    // Subscribe to all dependencies
    const unsubscribes = dependencies.map(dep =>
        dep.subscribe(() => runEffect())
    );

    // Run once immediately
    runEffect();

    // Return destroy function
    return {
        destroy: () => {
            if (cleanupFn) cleanupFn();
            unsubscribes.forEach(unsub => unsub());
        }
    };
}

// Usage example
const projectState = createState(null);
const statusState = createState('idle');

const statusEffect = createEffect(
    [projectState, statusState],
    () => {
        const project = projectState.get();
        const status = statusState.get();

        console.log(`Project ${project} status: ${status}`);

        // Return cleanup function
        return () => {
            console.log('Cleaning up status effect');
        };
    }
);

// Cleanup when done
// statusEffect.destroy();
```

---

## Common Utility Patterns

### Debounce/Throttle

```javascript
/**
 * Debounce function calls
 * @param {Function} fn - Function to debounce
 * @param {number} delay - Delay in milliseconds
 */
function debounce(fn, delay) {
    let timeoutId;
    return function (...args) {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => fn.apply(this, args), delay);
    };
}

// Usage
const debouncedSearch = debounce((query) => {
    performSearch(query);
}, 300);

input.addEventListener('input', (e) => debouncedSearch(e.target.value));
```

### Memoization

```javascript
/**
 * Memoize function results
 * @param {Function} fn - Function to memoize
 */
function memoize(fn) {
    const cache = new Map();
    return function (...args) {
        const key = JSON.stringify(args);
        if (cache.has(key)) {
            return cache.get(key);
        }
        const result = fn.apply(this, args);
        cache.set(key, result);
        return result;
    };
}

// Usage
const expensiveComputation = memoize((n) => {
    console.log('Computing...');
    return n * n;
});

expensiveComputation(5); // Computing... 25
expensiveComputation(5); // 25 (cached)
```

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why Avoid | Correct Approach |
|--------------|-----------|------------------|
| Global state without structure | Unpredictable updates | Use state containers with subscriptions |
| Direct DOM manipulation scattered | Hard to track changes | Centralize DOM updates in render functions |
| Memory leaks from event listeners | Performance degradation | Always remove listeners on cleanup |
| Synchronous polling without cleanup | Unnecessary resource usage | Clear intervals/timeouts on cleanup |
| Storing DOM references without need | Memory bloat | Query DOM when needed or use event delegation |

---

## Common Mistakes

1. **Not cleaning up event listeners** - Always remove listeners when components are destroyed
2. **Forgetting to clear intervals/timeouts** - Use cleanup functions to prevent memory leaks
3. **Mutating shared state directly** - Always use state setters to trigger updates
4. **Not handling unsubscribe in effects** - If you subscribe, you must unsubscribe
5. **Creating new functions in render** - Define functions outside or memoize them

---

## Related Guidelines

- [Directory Structure](./directory-structure.md) - Frontend organization
- [Component Guidelines](./component-guidelines.md) - UI component patterns
- [State Management](./state-management.md) - Global state patterns
- [Quality Guidelines](./quality-guidelines.md) - Code quality standards
