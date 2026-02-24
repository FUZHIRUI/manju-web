# Error Handling

> How errors are handled in this project.

---

## Overview

The project uses a simple but consistent error handling approach based on Python's built-in exceptions and HTTP status codes. Errors are propagated through the call stack and returned to clients as JSON responses with appropriate HTTP status codes.

---

## Error Types

### Built-in Python Exceptions

The project primarily uses built-in Python exceptions:

| Exception | Usage |
|-----------|-------|
| `ValueError` | Invalid parameter values, configuration errors |
| `FileNotFoundError` | Missing files or directories |
| `KeyError` | Missing dictionary keys |
| `json.JSONDecodeError` | Invalid JSON parsing |

### Custom Error Codes

Error codes are returned as strings in API responses:

| Error Code | Description | HTTP Status |
|------------|-------------|-------------|
| `invalid_project` | Project name is invalid or not found | 400 |
| `invalid_job_type` | Job type is not recognized | 400 |
| `invalid_config_items` | Configuration items are invalid | 400 |
| `job_not_found` | Job ID does not exist | 404 |
| `config_not_found` | Configuration file not found | 404 |
| `internal_error` | Unexpected server error | 500 |

---

## Error Handling Patterns

### Handler-Level Error Handling

Handlers catch exceptions and convert them to HTTP responses:

```python
# /backend/handlers/config_handler.py

def handle_post(handler: BaseHTTPRequestHandler, path: str) -> bool:
    """Handle config update requests."""
    parsed = urlsplit(path)

    if parsed.path == "/api/config/concurrency":
        try:
            content_length = int(handler.headers.get('Content-Length', 0))
            if content_length == 0:
                send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "empty_body"})
                return True

            post_data = handler.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            # Service layer may raise ValueError for invalid data
            config_service.update_concurrency_config(data)

            send_json(handler, HTTPStatus.OK, {"message": "updated"})
            return True

        except json.JSONDecodeError:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return True
        except ValueError as e:
            send_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(e)})
            return True

    return False
```

### Service-Level Error Handling

Services validate inputs and raise exceptions for invalid data:

```python
# /backend/services/config_service.py

def update_concurrency_config(config: Dict[str, Any]) -> None:
    """Update concurrency configuration after validation."""
    # Validate config structure
    invalid_items = []
    for key, value in config.items():
        if not isinstance(value, int) or value < 0:
            invalid_items.append(key)

    if invalid_items:
        raise ValueError(f"invalid_config_items:{','.join(invalid_items)}")

    # Persist valid config
    config_repo.save_concurrency_config(config)
```

### Repository-Level Error Handling

Repositories handle file I/O errors and data consistency:

```python
# /backend/repositories/job_repo.py

def persist_job_snapshot(job: Dict[str, Any]) -> None:
    """Append job snapshot to JSONL file."""
    line = json.dumps(job, ensure_ascii=False, separators=(",", ":")) + "\n"
    try:
        with open(_JOB_SNAPSHOTS_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except IOError as e:
        # Log error but don't crash - job is still in memory
        print(f"Failed to persist job {job.get('id')}: {e}", file=sys.stderr)
```

---

## API Error Responses

### Standard Error Response Format

All API errors follow this JSON structure:

```json
{
  "error": "error_code_string"
}
```

Or with additional details:

```json
{
  "error": "invalid_config_items",
  "details": ["max_concurrent_jobs", "worker_timeout"]
}
```

### HTTP Status Codes

| Status Code | Usage |
|-------------|-------|
| 200 OK | Successful GET/POST/PUT/PATCH |
| 400 Bad Request | Invalid parameters, malformed JSON, validation errors |
| 404 Not Found | Resource doesn't exist |
| 500 Internal Server Error | Unexpected errors, bugs |

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why Avoid | Correct Approach |
|--------------|-----------|------------------|
| Catching generic `Exception` | Hides bugs, makes debugging hard | Catch specific exceptions only |
| Silent failures (empty catch blocks) | Errors go unnoticed | Always log errors, even if handling them |
| Returning error details in 200 OK | Breaks HTTP semantics | Use appropriate error status codes |
| Raising exceptions in normal flow | Exceptions are for exceptional cases | Use return values for expected conditions |
| Not validating inputs at layer boundaries | Invalid data propagates deep | Validate at entry points (handlers) |

---

## Common Mistakes

1. **Forgetting to set HTTP status code on errors** - Always set appropriate status code (400, 404, 500)
2. **Not handling JSON decode errors** - Always wrap `json.loads()` in try-catch
3. **Leaking internal error details to clients** - Log full error internally, return generic message to client
4. **Not checking if files exist before reading** - Always check existence or catch `FileNotFoundError`
5. **Inconsistent error code strings** - Use defined error codes, don't make up new ones ad-hoc

---

## Related Guidelines

- [Directory Structure](./directory-structure.md) - Backend organization
- [Database Guidelines](./database-guidelines.md) - Data persistence patterns
- [Logging Guidelines](./logging-guidelines.md) - Structured logging patterns
- [Quality Guidelines](./quality-guidelines.md) - Code review standards
