# Backend Deploy

This repo is already split correctly for production:

- `usebackfill.com` serves the Next.js frontend from Vercel.
- `api.usebackfill.com` should serve the FastAPI backend from a container host.

Do not point Retell at `https://usebackfill.com/webhooks/retell` unless the backend is actually mounted there. Right now the clean deployment shape is a separate backend origin.

## Target shape

- Frontend: `https://usebackfill.com`
- Backend API: `https://api.usebackfill.com`
- Retell webhook: `https://api.usebackfill.com/webhooks/retell`
- Optional split-mode Twilio SMS webhook: `https://api.usebackfill.com/webhooks/twilio/sms`

## What was added

- Health check: `GET /healthz`
- Optional CORS env: `BACKFILL_ALLOWED_ORIGINS`
- Container image: [`Dockerfile`](./Dockerfile)
- Image hygiene: [`.dockerignore`](./.dockerignore)

## Required backend env vars

Minimum:

```env
DATABASE_URL=/data/backfill.db
BACKFILL_ALLOWED_ORIGINS=https://usebackfill.com,https://www.usebackfill.com
BACKFILL_WEBHOOK_URL=https://api.usebackfill.com

RETELL_API_KEY=...
RETELL_FROM_NUMBER=+14244992663
RETELL_AGENT_ID_INBOUND=...
RETELL_AGENT_ID_OUTBOUND=...
RETELL_CHAT_AGENT_ID=...
RETELL_SMS_ENABLED=true

TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
BACKFILL_PHONE_NUMBER=+14244992663
```

Add scheduling provider credentials only if you are actively using them.

## Deploy the backend

Deploy this repo's root as a Docker service on your preferred container host.

Build behavior:

```bash
docker build -t backfill-api .
docker run -p 8000:8000 --env-file .env backfill-api
```

The container serves:

- API routes under `/api/*`
- Retell webhook under `/webhooks/retell`
- Twilio webhook under `/webhooks/twilio/sms`
- health check at `/healthz`

## DNS

Create a subdomain:

- `api.usebackfill.com` -> your backend host

After DNS resolves, verify:

```bash
curl https://api.usebackfill.com/healthz
curl https://api.usebackfill.com/api/locations
```

Expected:

- `/healthz` returns `200 {"status":"ok"}`
- `/api/locations` returns `200` with JSON or an empty array

## Frontend env on Vercel

In the Vercel project for the `web` app, set:

```env
BACKFILL_API_BASE_URL=https://api.usebackfill.com
```

That is what the frontend already expects in [`web/lib/api.ts`](./web/lib/api.ts) and [`web/lib/server-api.ts`](./web/lib/server-api.ts).

## Retell after backend deploy

After `api.usebackfill.com` is live:

1. Update the live Retell voice agent webhook to `https://api.usebackfill.com/webhooks/retell`
2. Publish the voice agent
3. Create or update the Retell SMS chat agent with the same webhook
4. Bind that chat agent to the Retell phone number for inbound and outbound SMS
5. Keep the Retell phone number termination URI pointed at `backfill.pstn.twilio.com`

## Persistence note

This repo still uses SQLite. That is acceptable for early-stage testing or a single-instance backend, but only if your backend host gives you persistent disk storage mounted to the `DATABASE_URL` path.

If the host is fully ephemeral, the database will disappear on restart. In that case, move `DATABASE_URL` to a persistent mounted volume path or migrate to Postgres before going live.
