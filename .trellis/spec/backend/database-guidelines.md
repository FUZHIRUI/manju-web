# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

This project uses **file-based JSONL storage** instead of a traditional database. Data is persisted as JSON Lines (JSONL) files on the local file system.

This approach was chosen for:
- Simplicity (no database setup required)
- Human-readable data format
- Easy backup and version control of data files

---

## Storage Architecture

### JSONL Format

Each line in a `.jsonl` file is a valid JSON object:
```jsonl
{"id": "abc123", "type": "fenjing", "status": "running", "created_at": 1708300000}
{"id": "def456", "type": "video", "status": "completed", "created_at": 1708300100}
```

### Data Organization

| Data Type | Storage Location | Repository |
|-----------|-----------------|------------|
| Jobs | In-memory + disk JSONL | `job_repo.py` |
| Projects | File system directories | `project_repo.py` |
| Configurations | JSON files | `config_repo.py` |
| Logs | Per-job `.log` files | `log_repo.py` |

---

## Repository Pattern

All data access goes through repository modules:

```
Handlers → Services → Repositories → File System
```

### Repository Responsibilities

1. **CRUD Operations** - Create, read, update, delete records
2. **State Management** - Track in-memory state and persist to disk
3. **File Operations** - Handle all file I/O (JSONL, logs, configs)
4. **Data Integrity** - Ensure consistent state across operations

### Example Repository Implementation

```python
# /backend/repositories/job_repo.py

# In-memory job storage
_jobs: Dict[str, Dict[str, Any]] = {}

# Job snapshots persistence
_JOB_SNAPSHOTS_PATH = "data/jobs.jsonl"

def persist_job_snapshot(job: Dict[str, Any]) -> None:
    """Append job snapshot to JSONL file."""
    _jobs[job["id"]] = job
    line = json.dumps(job, ensure_ascii=False, separators=(",", ":")) + "\n"
    with open(_JOB_SNAPSHOTS_PATH, "a", encoding="utf-8") as f:
        f.write(line)

def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job from in-memory storage."""
    return _jobs.get(job_id)

def find_job_on_disk(job_id: str) -> Optional[Dict[str, Any]]:
    """Search for job in JSONL file."""
    if not os.path.exists(_JOB_SNAPSHOTS_PATH):
        return None
    with open(_JOB_SNAPSHOTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            job = json.loads(line)
            if job.get("id") == job_id:
                return job
    return None
```

---

## Data Patterns

### Job State Management

Jobs have a well-defined lifecycle:
```
waiting → running → [completed | failed]
```

State transitions are handled through `update_job()`:
```python
def update_job(job_id: str, **updates: Any) -> None:
    """Update job fields and persist to storage."""
    job = _jobs.get(job_id)
    if not job:
        return
    job.update(updates)
    job["updated_at"] = time.time()
    persist_job_snapshot(job)
```

### Configuration Storage

Configurations are stored as JSON files:
- `global_concurrency.json` - Concurrency limits
- `global_auth.json` - Authentication credentials
- `retry_policy.json` - Retry configuration

Access through config service:
```python
# /backend/services/config_service.py
def load_concurrency_config() -> Dict[str, Any]:
    return config_repo.load_json_config("global_concurrency.json")
```

---

## Query Patterns

### Loading All Records

For small datasets, load all records into memory:
```python
def _load_all_jobs() -> List[Dict[str, Any]]:
    jobs = []
    if not os.path.exists(_JOB_SNAPSHOTS_PATH):
        return jobs
    with open(_JOB_SNAPSHOTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            jobs.append(json.loads(line))
    return jobs
```

### Single Record Lookup

For single record lookup, scan the file:
```python
def find_job_on_disk(job_id: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(_JOB_SNAPSHOTS_PATH):
        return None
    with open(_JOB_SNAPSHOTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            job = json.loads(line.strip())
            if job.get("id") == job_id:
                return job
    return None
```

---

## Naming Conventions

### Repository Functions

| Pattern | Example | Usage |
|---------|---------|-------|
| `get_*` | `get_job(job_id)` | Get single item from in-memory cache |
| `find_*` | `find_job_on_disk(job_id)` | Search for item in persistent storage |
| `list_*` | `list_jobs_for_project(project)` | List multiple items |
| `persist_*` | `persist_job_snapshot(job)` | Save item to persistent storage |
| `start_*` | `start_job(...)` | Create and start a new entity |
| `update_*` | `update_job(job_id, ...)` | Update entity fields |

### File Names

- Repository files: `{entity}_repo.py`
- Service files: `{feature}_service.py`
- Handler files: `{feature}_handler.py`
- Data files: `{entity}s.jsonl` (plural for collection files)

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why Avoid | Correct Approach |
|--------------|-----------|------------------|
| Direct file I/O in services | Bypasses data consistency checks; hard to test | Always use repositories for file operations |
| Not persisting after state change | Data loss on process restart | Call `persist_*` after every state change |
| Loading entire JSONL into memory unnecessarily | Memory bloat for large datasets | Use generators or stream processing for large files |
| Hardcoding file paths | Makes testing and configuration difficult | Use constants or config for paths |
| Modifying in-memory state without updating disk | Data inconsistency | Always update both in-memory and persistent storage |

---

## Common Mistakes

1. **Forgetting to call `persist_job_snapshot()` after job updates** - This causes data loss if the process restarts
2. **Using `get_job()` when the job might not be in memory yet** - Use `find_job_on_disk()` or ensure jobs are loaded first
3. **Not handling file not found errors** - Always check if files exist before reading
4. **Loading entire JSONL files for simple lookups** - For large files, consider indexing or streaming

---

## Related Guidelines

- [Directory Structure](./directory-structure.md) - Overall backend organization
- [Error Handling](./error-handling.md) - Error management patterns
- [Logging Guidelines](./logging-guidelines.md) - Structured logging patterns
