# Integrations and OAuth

## Available Integrations
- **Slack**: Get notifications and run commands from Slack
- **GitHub**: Link repos, trigger workflows on code events
- **Zapier**: Connect to 5,000+ apps without code
- **Google Drive**: Import/export files directly
- **Jira**: Sync issues with projects

## Setting Up OAuth Integrations
1. Go to **Settings > Integrations**
2. Click **Connect** next to the integration
3. Authorize via the third-party OAuth flow
4. Configure settings specific to that integration

## Building Custom Integrations
Use our OAuth 2.0 flow for custom apps:
- Authorization endpoint: `https://api.example.com/oauth/authorize`
- Token endpoint: `https://api.example.com/oauth/token`
- Supported scopes: `read`, `write`, `admin`, `webhooks`

## Revoking Integrations
**Settings > Integrations > [Integration] > Disconnect**. This immediately revokes all access tokens.

## API Key vs OAuth
- Use **API keys** for server-to-server communication
- Use **OAuth** for integrations that act on behalf of users