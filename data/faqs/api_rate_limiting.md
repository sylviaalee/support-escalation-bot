# API Rate Limiting

## Overview
Our API enforces rate limits to ensure fair usage across all customers.

## Current Limits
- **Free tier**: 60 requests/minute, 10,000 requests/day
- **Pro tier**: 1,000 requests/minute, 500,000 requests/day
- **Enterprise tier**: Custom limits — contact sales

## Error Response
When rate limited, you receive:
```
HTTP 429 Too Many Requests
Retry-After: <seconds>
```

## Best Practices
1. Implement exponential backoff with jitter
2. Cache responses where possible
3. Use bulk endpoints instead of individual calls
4. Monitor your usage in the dashboard under **Analytics > API Usage**

## Upgrading Limits
Upgrade your plan at **Billing > Subscription** or contact enterprise sales for custom arrangements.