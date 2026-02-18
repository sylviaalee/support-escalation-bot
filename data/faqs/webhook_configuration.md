# Webhook Configuration

## Overview
Webhooks allow your application to receive real-time notifications when events occur.

## Setting Up Webhooks
1. Go to **Settings > Integrations > Webhooks**
2. Click **Add Endpoint**
3. Enter your endpoint URL (must be HTTPS)
4. Select event types to subscribe to
5. Save — we'll send a test event immediately

## Supported Events
- `project.created`, `project.updated`, `project.deleted`
- `file.uploaded`, `file.processed`, `file.failed`
- `billing.invoice_created`, `billing.payment_failed`
- `user.invited`, `user.joined`, `user.removed`

## Security
Each webhook includes a `X-Signature-256` header. Verify it:
```python
import hmac, hashlib
expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
assert hmac.compare_digest(f"sha256={expected}", signature)
```

## Retry Policy
Failed deliveries are retried with exponential backoff: 1m, 5m, 30m, 2h, 8h.
After 5 failures, the endpoint is automatically disabled and you are notified.

## Debugging
View delivery logs under **Settings > Integrations > Webhooks > [your endpoint] > Logs**.