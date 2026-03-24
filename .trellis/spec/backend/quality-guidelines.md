# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

This project maintains code quality through:
- Type hints (Python 3.6+ annotations)
- pytest for unit testing
- Consistent code style (PEP 8)
- Clear separation of concerns
- Comprehensive docstrings

---

## Type Hints

### Required Type Annotations

All functions should have type hints for:
- Parameters
- Return values
- Complex data structures

```python
# Good
from typing import Dict, Any, Optional, List, Callable

def start_job(
    job_type: str,
    project: str,
    runner: Callable[[str], None],
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Start a new job and run it in a background thread."""
    return job_repo.start_job(job_type, project, runner, payload)
```

```python
# Bad - missing type hints
def start_job(job_type, project, runner, payload):
    return job_repo.start_job(job_type, project, runner, payload)
```

### Common Type Aliases

```python
# Job type alias
Job = Dict[str, Any]

# Handler function type
HandlerFunc = Callable[[BaseHTTPRequestHandler, str], bool]

# Config type
Config = Dict[str, Union[str, int, bool, Dict]]
```

---

## Docstrings

### Function Docstrings

All public functions should have docstrings following this format:

```python
def get_job_log_page(job_id: str, offset: int = 0, limit: int = 200) -> Optional[Dict[str, Any]]:
    """Get a page of log entries for a job.

    Args:
        job_id: The unique job identifier
        offset: Number of log entries to skip (default: 0)
        limit: Maximum number of entries to return (default: 200)

    Returns:
        A dictionary containing:
            - lines: List of parsed log entries
            - total: Approximate total count
            - offset: The requested offset
        Returns None if job is not found.

    Example:
        >>> page = get_job_log_page("abc123", offset=0, limit=50)
        >>> if page:
        ...     print(f"Got {len(page['lines'])} log entries")
    """
    # Implementation...
```

### Module Docstrings

Each module should have a docstring at the top:

```python
"""Job repository module.

Provides CRUD operations for job records, including:
- Creating and starting jobs
- Updating job state
- Querying job status
- Persisting job snapshots to JSONL

Example:
    >>> job = start_job("fenjing", "my_project", runner, {})
    >>> print(f"Started job {job['id']}")
"""
```

---

## Testing

### Test File Structure

```python
# /backend/tests/test_job_repo.py

import pytest
from repositories import job_repo


def test_start_job_creates_valid_job():
    """Test that start_job creates a job with valid structure."""
    # Setup
    runner = lambda job_id: None

    # Execute
    job = job_repo.start_job("fenjing", "test_project", runner, {})

    # Assert
    assert "id" in job
    assert "trace_id" in job
    assert job["type"] == "fenjing"
    assert job["status"] == "running"
    assert "created_at" in job


def test_get_job_returns_cached_job():
    """Test that get_job returns job from in-memory cache."""
    # Setup - create a job
    runner = lambda job_id: None
    job = job_repo.start_job("fenjing", "test_project", runner, {})
    job_id = job["id"]

    # Execute
    result = job_repo.get_job(job_id)

    # Assert
    assert result is not None
    assert result["id"] == job_id
```

### Test Fixtures

```python
# /backend/tests/conftest.py

import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.fixture
def temp_data_dir():
    """Provide a temporary data directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_job():
    """Provide a sample job dictionary for tests."""
    return {
        "id": "test_job_123",
        "type": "fenjing",
        "project": "test_project",
        "status": "running",
        "created_at": 1708300000.0,
        "updated_at": 1708300000.0,
        "payload": {},
        "trace_id": "trace_123",
        "log_path": "/tmp/test_job_123.log"
    }
```

---

## Code Style

### PEP 8 Compliance

Follow PEP 8 with these project-specific conventions:

```python
# Line length: 100 characters (not 80)
# Indentation: 4 spaces

# Good - proper spacing
if status == "running":
    update_job(job_id, status="completed")

# Bad - no spacing after colon
if status == "running":
    update_job(job_id, status="completed")
```

### Imports

```python
# Standard library imports (alphabetical)
import json
import os
import time
from http import HTTPStatus
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit

# Third-party imports (alphabetical)
# (none in this project)

# Local imports (alphabetical by module name)
from repositories import config_repo, job_repo, project_repo
from services.config_service import load_concurrency_config
from services.job_service import get_job, list_jobs
```

### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Modules | snake_case | `job_repo.py` |
| Classes | PascalCase | `JobRepository` (if using classes) |
| Functions | snake_case | `get_job_by_id()` |
| Variables | snake_case | `job_id`, `project_name` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT` |
| Private/internal | _leading_underscore | `_internal_helper()` |

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why Avoid | Correct Approach |
|--------------|-----------|------------------|
| Missing type hints | Reduces code clarity and IDE support | Add type hints to all functions |
| No docstrings | Makes code hard to understand | Document all public functions |
| Deep nesting | Hard to read and test | Use early returns, extract functions |
| Magic numbers | Unclear meaning | Use named constants |
| Copy-pasted code | Maintenance burden | Extract shared functionality |
| Large functions | Hard to test and understand | Break into smaller, focused functions |
| Tight coupling | Hard to test and modify | Use dependency injection, interfaces |

---

## Common Mistakes

1. **Not using type hints for optional parameters** - Always use `Optional[T]` for nullable params
2. **Forgetting to update docstrings** - Keep docstrings in sync with code changes
3. **Inconsistent return types** - A function should always return the same type
4. **Not handling None cases** - Always check for None before accessing attributes
5. **Using mutable default arguments** - `def func(items=[])` is dangerous, use `def func(items=None)`

---

## Related Guidelines

- [Directory Structure](./directory-structure.md) - Backend organization
- [Database Guidelines](./database-guidelines.md) - Data persistence patterns
- [Error Handling](./error-handling.md) - Error management patterns
- [Logging Guidelines](./logging-guidelines.md) - Structured logging patterns
