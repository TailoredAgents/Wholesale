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
- `NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL`: `/os`.
- `NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL`: `/os`.

## API Environment Variables

- `APP_ENV`: `production`.
- `DATABASE_URL`: Render PostgreSQL connection string.
- `REDIS_URL`: Render Key Value connection string.
- `API_CORS_ORIGINS`: staging web URL.
- `DEFAULT_ORGANIZATION_NAME`: `Stonegate Home Buyers`.
- `SPEED_TO_LEAD_DUE_MINUTES`: `5`.
- `AI_ENABLED`: `true`.
- `OPENAI_API_KEY`: OpenAI project API key.
- `OPENAI_BASE_URL`: `https://api.openai.com/v1`.
- `OPENAI_DEFAULT_MODEL`: `gpt-5.6-terra`.
- `OPENAI_REASONING_EFFORT`: `medium`.
- `OPENAI_WEB_SEARCH_ENABLED`: `false`.
- `OPENAI_REQUEST_TIMEOUT_SECONDS`: `30`.
- `PROPERTY_DATA_PROVIDER`: `rentcast`.
- `RENTCAST_API_KEY`: RentCast API key for value estimates and sale comps.
- `RENTCAST_BASE_URL`: `https://api.rentcast.io/v1`.
- `ATTOM_API_KEY`: optional later upgrade for deeper property/deed/tax datasets.
- `BRIDGE_API_BASE_URL`: optional MLS/RESO feed base URL.
- `BRIDGE_API_KEY`: optional MLS/RESO feed API key.
- `UNDERWRITING_OFFER_LOW_PERCENTAGE`: `0.65`.
- `UNDERWRITING_OFFER_HIGH_PERCENTAGE`: `0.70`.
- `UNDERWRITING_DEFAULT_ASSIGNMENT_FEE_CENTS`: `1500000`.
- `UNDERWRITING_TRANSACTION_RESERVE_CENTS`: `250000`.
- `UNDERWRITING_PURCHASE_COST_PERCENTAGE`: `0.02`.
- `UNDERWRITING_FINANCING_HOLDING_PERCENTAGE`: `0.06`.
- `UNDERWRITING_RESALE_COST_PERCENTAGE`: `0.08`.
- `UNDERWRITING_NEGOTIATION_RESERVE_PERCENTAGE`: `0.08`.
- `UNDERWRITING_RENTAL_TARGET_CAP_RATE`: `0.08`.
- `CLERK_ISSUER`: Clerk issuer URL.
- `CLERK_JWKS_URL`: Clerk JWKS URL.
- `CLERK_AUDIENCE`: optional Clerk audience, if configured.
- `CLERK_AUTHORIZED_PARTIES`: staging web URL.
- `CLERK_SECRET_KEY`: Clerk secret key.

## Deploy Steps

1. Create Render resources from `render.yaml`.
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
7. Confirm `/health`, `/ready`, public website, public intake, `/os`, and speed-to-lead queue.

## Clerk Requirements

- Enable MFA for owner/admin users.
- Add staging web URL to allowed redirect URLs.
- Add staging web URL to authorized parties.
- Keep production secrets out of GitHub.
