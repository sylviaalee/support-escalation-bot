# API Authentication Errors

## Common Causes
- Invalid or expired API key
- Missing `Authorization` header
- Incorrect header format (must be `Bearer <token>`)

## Resolution Steps
1. Verify your API key in the dashboard under **Settings > API Keys**
2. Ensure the header is formatted as: `Authorization: Bearer YOUR_API_KEY`
3. Check if the key has been revoked — generate a new one if needed
4. Confirm the key has the correct permission scopes for the endpoint you're calling

## Error Codes
- `401 Unauthorized` — invalid or missing credentials
- `403 Forbidden` — valid credentials but insufficient permissions

## Notes
API keys rotate every 90 days by default. Enable auto-rotation reminders in account settings.