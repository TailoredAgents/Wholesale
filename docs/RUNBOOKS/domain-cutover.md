# Custom Domain Cutover

Last updated: July 20, 2026

Current status: pending domain selection.

## Recommended Structure

Use a branded public domain and stable subdomains:

```text
https://<STONEGATE_DOMAIN>
https://app.<STONEGATE_DOMAIN>
https://api.<STONEGATE_DOMAIN>
```

The exact structure can be simplified if Render or Clerk constraints make a single web origin more
reliable. Do not configure DNS until Stonegate owns and controls the domain account.

## Before DNS

1. Choose and purchase the Stonegate domain.
2. Decide whether the public site and OS share one host or use `app`.
3. Confirm Render supports each desired custom domain on the existing services.
4. Record current values for rollback:
   - web Render URL,
   - API Render URL,
   - Clerk authorized parties,
   - API CORS origins,
   - Google OAuth redirect,
   - email web base URL,
   - Twilio webhook base URL.
5. Keep the existing Render URLs active.

## Cutover

1. Add the web custom domain to `oakwell-web`.
2. Add the API custom domain to `oakwell-api` only if using an API subdomain.
3. Create the exact DNS records Render provides.
4. Wait for Render TLS certificates to become valid.
5. Update `API_CORS_ORIGINS` with the final public and OS origins.
6. Update `CLERK_AUTHORIZED_PARTIES`.
7. Add the custom domain to Clerk's allowed origins and redirects.
8. Update:

   ```text
   EMAIL_WEB_APP_BASE_URL
   GOOGLE_OAUTH_REDIRECT_URI
   ```

9. Add the exact new OAuth redirect URI in Google Cloud before enabling email.
10. Update `TWILIO_WEBHOOK_BASE_URL` only if the public API host changes.
11. Update public canonical links and policy URLs after the domain is serving successfully.

## Acceptance

- Homepage, offer form, privacy, and terms return `200` on the branded domain.
- Clerk sign-in returns to the OS.
- Authenticated API calls return `200`, not CORS or `401` errors.
- Public form submission creates one lead.
- Twilio signature validation succeeds on the final API host.
- Google OAuth callback succeeds on the exact registered URI.
- Old Render URLs continue to resolve or redirect without breaking submitted A2P evidence.

## Rollback

- Restore the previous CORS and authorized-party values.
- Restore provider callbacks to the Render API URL.
- Keep DNS records until Render custom-domain removal instructions are confirmed.
- Do not delete existing Render services or databases during domain troubleshooting.
