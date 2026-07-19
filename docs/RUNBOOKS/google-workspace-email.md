# Google Workspace Email Setup

Stonegate uses Google Workspace for active seller and deal communication. Cold outreach is a
separate future Smartlead integration and must not use these operational mailboxes.

Email deploys disabled. No message can send and no mailbox can synchronize until the Google OAuth
configuration is complete and both email feature flags are enabled.

## Google Cloud

1. Create or select the Google Cloud project owned by Stonegate.
2. Enable the Gmail API.
3. Configure the OAuth consent screen. Use an Internal app when all connected accounts belong to
   the same Google Workspace organization. Otherwise, keep the app in Testing and add each
   Stonegate mailbox as a test user until Google verification is complete.
4. Create an OAuth client with application type `Web application`.
5. Add this exact authorized redirect URI:

   `https://oakwell-api.onrender.com/api/v1/email/oauth/google/callback`

6. Retain the generated client ID and client secret in Render only. Do not commit them.

Stonegate requests `gmail.modify` because the inbox must read seller replies, send messages, retain
threading, and retrieve attachments. Google classifies this as a restricted scope. A public
external rollout can require Google OAuth verification and possibly an additional security review.

## Render Variables

Generate two independent secrets locally:

```bash
openssl rand -hex 32
openssl rand -hex 32
```

Set these variables on both `oakwell-api` and `oakwell-worker`. The values must match between the
two services:

```text
EMAIL_ENABLED=true
EMAIL_SYNC_ENABLED=true
EMAIL_SYNC_POLL_SECONDS=30
EMAIL_MAX_ATTACHMENT_BYTES=10000000
EMAIL_TOKEN_ENCRYPTION_KEY=<first generated secret>
EMAIL_OAUTH_STATE_SECRET=<second generated secret>
EMAIL_WEB_APP_BASE_URL=https://oakwell-web.onrender.com
GOOGLE_OAUTH_CLIENT_ID=<Google web client ID>
GOOGLE_OAUTH_CLIENT_SECRET=<Google web client secret>
GOOGLE_OAUTH_REDIRECT_URI=https://oakwell-api.onrender.com/api/v1/email/oauth/google/callback
```

Deploy both services after setting the variables. The token encryption key is permanent
application data: changing it disconnects every stored mailbox.

## Connect And Verify

1. Sign in to the Stonegate OS with the staff member's own account.
2. Open **Shared inbox** and select **Connect email**.
3. Choose the matching company Google mailbox and approve access.
4. Open the Email composer, add the salesperson's signature, and save it.
5. Send a message to a controlled external test address.
6. Reply from that address and select **Sync now**. Confirm the reply appears in the same
   chronological seller conversation.
7. Test a PDF attachment in both directions.
8. Confirm the worker logs `email_account_synced` without exposing message bodies or tokens.

Each salesperson connects their own mailbox. Administrators can mark a mailbox shared, but staff
credentials and Google accounts are never shared.

## Operational Behavior

- OAuth access and refresh tokens are encrypted before database storage.
- The browser never receives Google tokens or client secrets.
- Outbound messages use MIME, preserve Gmail thread IDs, and include `In-Reply-To` and
  `References` headers.
- The worker performs incremental Gmail history synchronization and recovers a stale history
  cursor by checking the most recent 30 days for known seller addresses.
- Messages from unknown addresses are not converted into leads automatically.
- Attachment bytes stay in Google. Stonegate stores metadata and proxies downloads only after an
  authenticated conversation permission check.
- Disconnecting an account stops sending and synchronization without deleting the retained CRM
  timeline.
