# Backend Directory Structure

> How backend code is organized in this project.

---

## Overview

This project (TTZ Script Workbench - 剧本工作台) is a multi-step content generation platform. The backend follows a layered architecture with clear separation of concerns:

- **Handlers**: HTTP request processing (API endpoints)
- **Services**: Business logic and workflow orchestration
- **Repositories**: Data access layer (file-based JSONL storage)
- **Config**: Configuration management

---

## Directory Layout

```
/backend/
├── handlers/              # HTTP request handlers (API endpoints)
│   ├── __init__.py
│   ├── job_handler.py     # Job-related endpoints (/api/jobs/*)
│   ├── config_handler.py  # Config endpoints (/api/config/*)
│   └── project_handler.py # Project endpoints (/api/projects/*)
│
├── services/              # Business logic layer
│   ├── __init__.py
│   ├── job_service.py         # Job lifecycle management
│   ├── workflow_service.py    # Workflow execution orchestration
│   ├── config_service.py      # Configuration loading/validation
│   ├── status_service.py      # Project status tracking
│   └── workflow_runtime/      # Workflow execution runtime
│       ├── __init__.py
│       ├── fenjing.py         # Storyboard generation workflow
│       ├── visual_audio_assets.py
│       ├── runtime_config.py  # Runtime configuration variables
│       ├── provider_ark.py    # ARK AI service integration
│       ├── provider_tos.py    # TOS storage integration
│       ├── provider_tts.py    # TTS service integration
│       ├── io_assets.py       # Asset I/O operations
│       ├── io_data.py         # Data file operations
│       └── thread_safe_logging.py
│
├── repositories/        # Data access layer
│   ├── __init__.py
│   ├── job_repo.py      # Job CRUD and state management
│   ├── project_repo.py  # Project and asset directory management
│   ├── config_repo.py   # Configuration file operations
│   └── log_repo.py      # Log file management
│
├── config/              # Configuration files
│   ├── global_concurrency.json   # Concurrency limits
│   ├── global_auth.json          # Auth credentials
│   └── retry_policy.json         # Retry configuration
│
├── tests/               # Unit tests
│   ├── conftest.py      # pytest fixtures
│   ├── test_job_repo.py
│   └── test_config_service.py
│
├── logs/                # Job execution logs (runtime generated)
│   └── {job_id}.log
│
└── server.py            # Main HTTP server entry point
```

---

## Module Organization

### Adding a New Feature

When adding a new feature, follow this pattern:

1. **Add handler** (if new API endpoint needed)
   - File: `handlers/{feature}_handler.py`
   - Or extend existing handler

2. **Add service** (for business logic)
   - File: `services/{feature}_service.py`
   - Or extend existing service

3. **Add repository** (if new data type)
   - File: `repositories/{feature}_repo.py`
   - Or extend existing repository

4. **Add tests**
   - File: `tests/test_{feature}_*.py`

---

## File Naming Conventions

| Pattern | Example | Usage |
|---------|---------|-------|
| `*_handler.py` | `job_handler.py` | HTTP request handlers |
| `*_service.py` | `job_service.py` | Business logic services |
| `*_repo.py` | `job_repo.py` | Repository/data access |
| `provider_*.py` | `provider_ark.py` | External service integrations |
| `io_*.py` | `io_assets.py` | I/O operation modules |
| `test_*.py` | `test_job_repo.py` | Unit test files |

---

## Import Conventions

**Within a layer**, use direct imports:
```python
# In job_handler.py
from services.job_service import get_job, list_jobs
from repositories.job_repo import start_job
```

**Cross-layer imports** follow the dependency direction:
```
Handler → Service → Repository
```

**Avoid circular imports** by not importing upward in the hierarchy.

---

## Key Examples

### Handler Structure
```python
# /backend/handlers/job_handler.py

def handle_get(handler: BaseHTTPRequestHandler, path: str) -> bool:
    """Handle job-related GET requests."""
    parsed = urlsplit(path)
    clean_path = parsed.path

    if clean_path.startswith("/api/projects/") and clean_path.endswith("/jobs"):
        parts = clean_path.split("/")
        project = project_repo.safe_project_name(parts[3])
        if not project:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_project"})
            return True
        send_json(handler, HTTPStatus.OK, {"jobs": job_service.list_jobs(project)})
        return True

    return False
```

### Service Structure
```python
# /backend/services/job_service.py

def start_job(job_type: str, project: str, runner: callable, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Start a new job and run it in a background thread."""
    return job_repo.start_job(job_type, project, runner, payload)

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job details, searching in memory and on disk if needed."""
    job = job_repo.get_job(job_id)
    if job:
        return job
    return job_repo.find_job_on_disk(job_id)
```

### Repository Structure
```python
# /backend/repositories/job_repo.py

def start_job(job_type: str, project: str, runner: callable, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new job, persist it, and start execution in a background thread."""
    job_id = uuid.uuid4().hex
    trace_id = uuid.uuid4().hex
    created_at = time.time()
    job = {
        "id": job_id,
        "type": job_type,
        "project": project,
        "status": "running",
        "created_at": created_at,
        "updated_at": created_at,
        "payload": payload,
        "trace_id": trace_id,
        "log_path": build_log_path(job_id, created_at),
        "exit_code": None,
        "error": None,
        "partial_failed": False,
        "partial_failed_count": 0,
        "partial_failed_types": [],
    }
    persist_job_snapshot(job)
    thread = threading.Thread(target=runner, args=(job_id,), daemon=True)
    thread.start()
    return job
```

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why Avoid | Correct Approach |
|--------------|-----------|------------------|
| Business logic in handlers | Violates separation of concerns | Handlers only parse requests/responses; logic goes in services |
| Direct file operations in services | Makes testing hard; bypasses data layer | Use repositories for all I/O operations |
| Circular imports between layers | Causes import errors | Maintain strict hierarchy: handlers → services → repositories |
| Hardcoded paths/strings | Makes changes difficult | Use constants or configuration |
| Mixing sync and async without care | Can cause deadlocks or race conditions | Be explicit about threading; use provided thread-safe utilities |

---

## Common Mistakes

1. **Not using the repository layer for data access** - Always go through repositories for consistency
2. **Forgetting to handle job state transitions properly** - Use job_repo.update_job() to ensure state persistence
3. **Not using thread-safe logging** - In workflow runtime, always use thread_safe_logging module
4. **Hardcoding external service endpoints** - Use runtime_config for service URLs and credentials

---

## Related Guidelines

- [Database Guidelines](./database-guidelines.md) - Data persistence patterns
- [Error Handling](./error-handling.md) - Error management conventions
- [Logging Guidelines](./logging-guidelines.md) - Structured logging patterns
- [Quality Guidelines](./quality-guidelines.md) - Code review standards
