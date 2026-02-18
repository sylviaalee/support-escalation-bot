# API Error Codes Reference

## 4xx Client Errors
| Code | Meaning | Common Cause |
|------|---------|-------------|
| 400 | Bad Request | Malformed JSON, missing required field |
| 401 | Unauthorized | Invalid/expired API key |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource doesn't exist or you lack access |
| 409 | Conflict | Duplicate resource (e.g., name already taken) |
| 422 | Unprocessable Entity | Validation error on request body |
| 429 | Too Many Requests | Rate limit exceeded |

## 5xx Server Errors
| Code | Meaning | Action |
|------|---------|--------|
| 500 | Internal Server Error | Retry with backoff; contact support if persistent |
| 502 | Bad Gateway | Transient; retry |
| 503 | Service Unavailable | Check status.example.com |
| 504 | Gateway Timeout | Request too large or system under load |

## Error Response Format
```json
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "You have exceeded your rate limit of 60 req/min",
    "details": { "limit": 60, "window": "1m", "retry_after": 23 }
  }
}
```

## Checking Service Status
Visit **status.example.com** for real-time status and incident history.