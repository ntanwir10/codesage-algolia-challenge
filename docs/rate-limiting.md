# Rate Limiting Implementation

This document describes the rate limiting implementation added to the CodeSage MCP Server backend.

## Overview

Rate limiting has been implemented using `slowapi`, a FastAPI port of Flask-Limiter, to prevent abuse and ensure fair usage of the API endpoints.

## Configuration

### Settings

Rate limiting settings are configured in `app/core/config.py`:

```python
# Rate Limiting Settings
enable_rate_limiting: bool = True
rate_limit_default: str = "100/minute"      # Default rate limit for most endpoints
rate_limit_search: str = "50/minute"        # Lower limit for search endpoints (more expensive)
rate_limit_upload: str = "10/minute"        # Very low limit for upload endpoints
rate_limit_ai: str = "30/minute"            # Moderate limit for AI/MCP endpoints
rate_limit_storage_uri: Optional[str] = None # Redis URI for distributed rate limiting (None = in-memory)
```

### Environment Variables

You can override these settings using environment variables:

```bash
ENABLE_RATE_LIMITING=true
RATE_LIMIT_DEFAULT="100/minute"
RATE_LIMIT_SEARCH="50/minute"
RATE_LIMIT_UPLOAD="10/minute"
RATE_LIMIT_AI="30/minute"
RATE_LIMIT_STORAGE_URI="redis://localhost:6379"  # Optional: for distributed setup
```

## Implementation Details

### Rate Limiting Service

The `RateLimitingService` class in `app/services/security_service.py` provides:

- **Flexible Storage**: In-memory (default) or Redis-based storage
- **Custom Key Generation**: Currently uses IP address, extendable to user-based limiting
- **Decorator Patterns**: Easy-to-use decorators for different endpoint types
- **Custom Error Handling**: Structured JSON responses for rate limit violations

### Decorators

Four rate limiting decorators are available:

```python
from app.services.security_service import (
    rate_limit_default,    # 100/minute - general endpoints
    rate_limit_search,     # 50/minute - search operations
    rate_limit_upload,     # 10/minute - file uploads
    rate_limit_ai,         # 30/minute - AI/MCP operations
)
```

## Applied Endpoints

### Search Endpoints (`/api/v1/search/`)

- **Limit**: 50 requests/minute
- **Reason**: Search operations are computationally expensive

### AI/MCP Endpoints (`/api/v1/ai/`)

- **Limit**: 30 requests/minute  
- **Reason**: AI operations require significant resources

### Upload Endpoints (`/api/v1/repositories/{id}/upload`)

- **Limit**: 10 requests/minute
- **Reason**: File uploads are resource-intensive

### File Endpoints (`/api/v1/files/`)

- **Limit**: 100 requests/minute (default)
- **Reason**: Standard read operations

### Repository Endpoints (`/api/v1/repositories/`)

- **Limit**: 100 requests/minute (default)
- **Reason**: Standard CRUD operations

## Error Response Format

When rate limits are exceeded, the API returns:

```json
{
  "error": "Rate limit exceeded",
  "message": "Too many requests. Try again in 60 seconds.",
  "retry_after": 60,
  "limit": "50/minute"
}
```

With HTTP status code `429` and `Retry-After` header.

## Usage Examples

### Adding Rate Limiting to New Endpoints

```python
from app.services.security_service import rate_limit_default

@router.get("/my-endpoint")
@rate_limit_default
async def my_endpoint():
    return {"message": "This endpoint is rate limited"}
```

### Custom Rate Limiting

```python
from app.services.security_service import get_rate_limiting_service

service = get_rate_limiting_service()

@router.get("/custom-endpoint")
@service.limiter.limit("200/minute")  # Custom limit
async def custom_endpoint():
    return {"message": "Custom rate limit"}
```

## Testing

### Manual Testing

1. Start the server:

   ```bash
   uvicorn app.main:app --reload
   ```

2. Make rapid requests to a rate-limited endpoint:

   ```bash
   # Test search endpoint (50/minute limit)
   for i in {1..60}; do
     curl -X POST "http://localhost:8000/api/v1/search/" \
          -H "Content-Type: application/json" \
          -d '{"query": "test", "page": 0, "per_page": 10}'
     sleep 0.5
   done
   ```

3. Verify you receive 429 responses after exceeding the limit.

### Automated Testing

Run the test suite:

```bash
cd backend
python -m pytest tests/test_rate_limiting.py -v
```

## Monitoring and Metrics

### Logging

Rate limit violations are logged with structured logging:

```json
{
  "level": "warning",
  "message": "Rate limit exceeded",
  "ip": "127.0.0.1",
  "path": "/api/v1/search/",
  "method": "POST",
  "retry_after": 60
}
```

### Health Checks

Rate limiting status is included in the startup logs:

```json
{
  "level": "info",
  "message": "Rate limiting configured",
  "enabled": true,
  "default_limit": "100/minute",
  "search_limit": "50/minute",
  "upload_limit": "10/minute",
  "ai_limit": "30/minute"
}
```

## Advanced Configuration

### Redis-Based Distributed Rate Limiting

For multi-instance deployments, configure Redis storage:

```python
# In .env file
RATE_LIMIT_STORAGE_URI=redis://localhost:6379/0
```

### User-Based Rate Limiting

Extend the key generation function in `RateLimitingService`:

```python
def _get_rate_limit_key(self, request: Request) -> str:
    # Get user from authentication
    user_id = getattr(request.state, 'user_id', None)
    if user_id:
        return f"user:{user_id}"
    
    # Fallback to IP
    return f"ip:{get_remote_address(request)}"
```

### Custom Rate Limits per User Tier

```python
def get_rate_limit_for_user(user_tier: str) -> str:
    limits = {
        "free": "50/minute",
        "premium": "200/minute", 
        "enterprise": "1000/minute"
    }
    return limits.get(user_tier, "50/minute")
```

## Security Considerations

1. **IP-Based Limiting**: Currently uses IP addresses, which can be spoofed
2. **Bypass Prevention**: Consider authenticated rate limiting for better control
3. **DDoS Protection**: Rate limiting alone isn't sufficient for DDoS protection
4. **Monitoring**: Monitor for patterns that might indicate abuse

## Performance Impact

- **In-Memory Storage**: Minimal overhead, lost on restart
- **Redis Storage**: Slight network overhead, persistent across restarts
- **Decorator Overhead**: Negligible performance impact per request

## Troubleshooting

### Common Issues

1. **Rate limits not working**: Check `enable_rate_limiting` setting
2. **Limits too strict**: Adjust rate limit values in configuration
3. **Redis connection errors**: Verify Redis URI and connectivity

### Debug Mode

Enable debug logging to see rate limiting decisions:

```python
import logging
logging.getLogger("slowapi").setLevel(logging.DEBUG)
```
