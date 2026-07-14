# Render Staging Checklist

## Required Inputs

- Render account/project access.
- Clerk project for staging.
- Staging web URL.
- Staging API URL.
- Owner email to bootstrap.

## Web Environment Variables

- `API_BASE_URL`: internal or public API base URL.
- `NEXT_PUBLIC_API_BASE_URL`: browser-accessible API base URL.
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`: Clerk publishable key.
- `CLERK_SECRET_KEY`: Clerk secret key.
- `NEXT_PUBLIC_CLERK_SIGN_IN_URL`: `/sign-in`.
- `NEXT_PUBLIC_CLERK_SIGN_UP_URL`: `/sign-up`.
- `NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL`: `/`.
- `NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL`: `/`.

## API Environment Variables

- `APP_ENV`: `production`.
- `DATABASE_URL`: Render PostgreSQL connection string.
- `REDIS_URL`: Render Key Value connection string.
- `API_CORS_ORIGINS`: staging web URL.
- `DEFAULT_ORGANIZATION_NAME`: `Oakwell Home Buyers`.
- `SPEED_TO_LEAD_DUE_MINUTES`: `5`.
- `CLERK_ISSUER`: Clerk issuer URL.
- `CLERK_JWKS_URL`: Clerk JWKS URL.
- `CLERK_AUDIENCE`: optional Clerk audience, if configured.
- `CLERK_AUTHORIZED_PARTIES`: staging web URL.
- `CLERK_SECRET_KEY`: Clerk secret key.

## Deploy Steps

1. Create Render resources from `infra/render.yaml`.
2. Set all synced secret/env values in Render.
3. Deploy API; startup runs `alembic upgrade head`.
4. Bootstrap the owner user against staging:

```bash
cd apps/api
DATABASE_URL="<render database url>" uv run python -m app.cli.bootstrap \
  --admin-email "<owner email>" \
  --admin-name "Owner"
```

5. Sign in through Clerk.
6. Map the Clerk user to the local owner if email auto-linking did not set `external_auth_id`.
7. Confirm `/health`, `/ready`, dashboard, public intake, and speed-to-lead queue.

## Clerk Requirements

- Enable MFA for owner/admin users.
- Add staging web URL to allowed redirect URLs.
- Add staging web URL to authorized parties.
- Keep production secrets out of GitHub.
