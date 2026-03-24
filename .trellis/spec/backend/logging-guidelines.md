# Logging Guidelines

> How logging is done in this project.

---

## Overview

The project uses structured JSON logging for all log output. Logs are written to per-job log files and include contextual information like trace IDs, timestamps, and severity levels. The logging system is designed to be thread-safe for concurrent job execution.

---

## Log Levels

| Level | Usage |
|-------|-------|
| `DEBUG` | Detailed information for debugging (function entry/exit, variable values) |
| `INFO` | General operational information (job start, task completion, state changes) |
| `WARN` | Warning conditions that don't prevent operation (retries, fallbacks, deprecated usage) |
| `ERROR` | Error conditions that prevent specific operations but not system crash |

---

## Structured Logging Format

All logs are JSON objects with the following standard fields:

```json
{
  "trace_id": "abc123def456",
  "ts": 1708300000.123,
  "level": "INFO",
  "msg": "Job started successfully",
  "job_id": "job_123",
  "job_type": "fenjing"
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `trace_id` | string | Unique identifier for tracing requests across the system |
| `ts` | number | Unix timestamp with millisecond precision |
| `level` | string | Log level (DEBUG, INFO, WARN, ERROR) |
| `msg` | string | Human-readable log message |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | Associated job identifier |
| `job_type` | string | Type of job (e.g., "fenjing", "video") |
| `step` | string | Current workflow step |
| `duration_ms` | number | Operation duration in milliseconds |
| `error` | string | Error message for ERROR logs |
| `stack_trace` | string | Stack trace for ERROR logs |

---

## Log Storage

### Per-Job Log Files

Each job has its own log file:
```
/backend/logs/{job_id}.log
```

### Log File Structure

Log files contain one JSON object per line (JSONL format):
```jsonl
{"trace_id": "abc123", "ts": 1708300000.123, "level": "INFO", "msg": "Starting job"}
{"trace_id": "abc123", "ts": 1708300000.456, "level": "DEBUG", "msg": "Loading configuration"}
{"trace_id": "abc123", "ts": 1708300001.789, "level": "INFO", "msg": "Job completed"}
```

---

## Thread-Safe Logging

The `thread_safe_logging` module provides thread-safe log writing for concurrent job execution.

### Usage

```python
# /backend/services/workflow_runtime/thread_safe_logging.py

import threading
import json
from typing import Dict, Any

# Thread-local storage for log context
_log_context = threading.local()

def set_log_context(trace_id: str, job_id: str, job_type: str) -> None:
    """Set logging context for current thread."""
    _log_context.trace_id = trace_id
    _log_context.job_id = job_id
    _log_context.job_type = job_type

def get_log_context() -> Dict[str, str]:
    """Get current thread's logging context."""
    return {
        "trace_id": getattr(_log_context, "trace_id", "unknown"),
        "job_id": getattr(_log_context, "job_id", "unknown"),
        "job_type": getattr(_log_context, "job_type", "unknown"),
    }

def log(level: str, msg: str, **extra: Any) -> None:
    """Write a structured log entry."""
    context = get_log_context()
    entry = {
        "trace_id": context["trace_id"],
        "ts": time.time(),
        "level": level,
        "msg": msg,
        "job_id": context["job_id"],
        "job_type": context["job_type"],
        **extra
    }

    # Write to job-specific log file
    log_path = build_log_path(context["job_id"])
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
```

### Convenience Functions

```python
def log_info(msg: str, **extra: Any) -> None:
    log("INFO", msg, **extra)

def log_debug(msg: str, **extra: Any) -> None:
    log("DEBUG", msg, **extra)

def log_warn(msg: str, **extra: Any) -> None:
    log("WARN", msg, **extra)

def log_error(msg: str, error: Optional[Exception] = None, **extra: Any) -> None:
    extra_fields = extra
    if error:
        extra_fields["error"] = str(error)
        extra_fields["stack_trace"] = traceback.format_exc()
    log("ERROR", msg, **extra_fields)
```

---

## Logging Best Practices

### Do's

1. **Always include trace_id** - Enables request tracing across the system
2. **Log at appropriate levels** - DEBUG for details, INFO for operations, WARN/ERROR for issues
3. **Include context** - job_id, job_type, step name for workflow logs
4. **Log at entry/exit points** - Function calls, API requests, job state changes
5. **Use structured fields** - Don't put variable data in msg, use extra fields

```python
# Good
log_info("Job started", job_id=job_id, job_type=job_type, payload_size=len(payload))

# Bad
log_info(f"Job {job_id} of type {job_type} started with payload size {len(payload)}")
```

### Don'ts

1. **Don't log sensitive data** - Never log passwords, API keys, tokens
2. **Don't use print()** - Always use the structured logging system
3. **Don't log at ERROR for expected conditions** - Use WARN for retriable failures
4. **Don't create too many log entries** - Avoid logging inside tight loops
5. **Don't forget to handle logging errors** - Log file I/O can fail

---

## Log Retrieval

### Viewing Job Logs

Logs can be retrieved via the API:

```python
# /backend/services/job_service.py

def get_job_log_page(job_id: str, offset: int = 0, limit: int = 200) -> Optional[Dict[str, Any]]:
    """Get a page of log entries for a job."""
    job = get_job(job_id)
    if not job:
        return None

    log_path = job.get("log_path")
    if not log_path or not os.path.exists(log_path):
        return {"lines": [], "total": 0, "offset": offset}

    lines = []
    with open(log_path, "r", encoding="utf-8") as f:
        # Skip to offset
        for _ in range(offset):
            next(f, None)

        # Read up to limit lines
        for _ in range(limit):
            line = f.readline()
            if not line:
                break
            lines.append(json.loads(line.strip()))

    return {
        "lines": lines,
        "total": offset + len(lines),  # Approximate for streaming
        "offset": offset
    }
```

---

## Common Mistakes

1. **Not setting log context in new threads** - Always call `set_log_context()` at thread start
2. **Logging before context is set** - Results in "unknown" trace_ids
3. **Not handling log file rotation** - Log files can grow unbounded
4. **Mixing print() with structured logs** - Makes log parsing difficult
5. **Not including enough context in error logs** - Makes debugging difficult

---

## Related Guidelines

- [Directory Structure](./directory-structure.md) - Backend organization
- [Database Guidelines](./database-guidelines.md) - Data persistence patterns
- [Error Handling](./error-handling.md) - Error management patterns
- [Quality Guidelines](./quality-guidelines.md) - Code review standards
